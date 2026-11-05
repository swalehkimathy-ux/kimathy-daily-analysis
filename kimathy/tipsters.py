"""tipsters.py — vyanzo vya utabiri vya wahusika wengine (Sehemu 8).

MSIMAMO MKALI WA UWAMINIFU:
  * Tovuti hizi hutoa MAONI, si takwimu. Kila kitu kinawekwa `trust = opinion_only`.
  * HATUGEUZI maoni kuwa uwezekano. HATUTUMII kwa probability ya injini.
  * HATUBUNI utabiri. Ikiwa tovuti imezuiwa au hakuna kinacholingana na mechi za leo,
    tunarekodi `source_unavailable` / `hakuna_ulioolingana` na kuendelea.
  * Kila rekodi ina URL + muda wa kukusanya + maandishi ghafi (ushahidi unaoweza kukaguliwa).

Parseri hapa ni za KIHAFIDHINA: zinasoma tu muundo unaoweza kuthibitishwa
(maandishi ya wazi yanayotaja timu mbili za mechi ya leo pamoja na soko lililotajwa).
HTML ghafi huhifadhiwa kwenye folda ya captures ili ukaguzi uwezekane.
"""
from __future__ import annotations

import re

from . import clock
from .net import Fetcher, save_capture
from .normalize import normalize, team_sim

TRUST = "opinion_only"

# Miundo ya soko inayoweza kutambuliwa kwa uhakika katika maandishi ya utabiri
MARKET_PATTERNS = [
    (r"\b(btts|both teams to score)\b", "BTTS"),
    (r"\bover\s+([0-9](?:\.[05])?)\s*goals?\b", "Over {0}"),
    (r"\bunder\s+([0-9](?:\.[05])?)\s*goals?\b", "Under {0}"),
    (r"\bdraw no bet\b", "Draw No Bet"),
    (r"\bdouble chance\b", "Double Chance"),
    (r"\bcorrect score\b", "Correct Score"),
]
WIN_PATTERNS = (
    (r"\bto win\b|\bback\s+{team}\b|\b{team}\s+win\b", "WIN"),
)

MAX_ITEMS_PER_SOURCE = 200


def _clean(text: str) -> str:
    from html import unescape
    t = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def _detect_market(snippet: str) -> tuple[str, str] | None:
    low = snippet.lower()
    for pat, label in MARKET_PATTERNS:
        m = re.search(pat, low)
        if m:
            return label.format(*m.groups()) if "{0}" in label else label, m.group(0)
    return None


def extract_opinions(html: str, fixtures: list[dict], *, source: str, url: str,
                     retrieved_at: str, log=print) -> list[dict]:
    """Tafuta maoni yanayotaja mechi za leo. Rudia orodha ya rekodi za maoni.

    `fixtures` = rekodi za Forebet (zenye home/away halisi) — ndizo kigezo cha ulinganisho.
    """
    plain = _clean(html)
    if len(plain) < 200:
        return []
    sentences = re.split(r"(?<=[.!?])\s+|\s{3,}", plain)
    out: list[dict] = []
    seen = set()

    for sent in sentences:
        if len(sent) < 25 or len(sent) > 400:
            continue
        for fx in fixtures:
            home, away = fx.get("home", ""), fx.get("away", "")
            if not home or not away:
                continue
            nh, na = normalize(home), normalize(away)
            if not nh or not na:
                continue
            low = normalize(sent)
            if nh not in low or na not in low:
                continue
            found = _detect_market(sent)
            if not found:
                # angalia kama inataja mshindi wazi
                winner = None
                for team in (home, away):
                    for pat, _lab in WIN_PATTERNS:
                        if re.search(pat.format(team=re.escape(normalize(team))), low):
                            winner = team
                            break
                    if winner:
                        break
                if not winner:
                    continue
                market, selection = "Match Winner", winner
                matched = "to win"
            else:
                market, matched = found
                selection = market
            key = (source, fx.get("event_id"), market, selection)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "source": source, "source_url": url, "retrieved_at": retrieved_at,
                "trust": TRUST, "event_id": fx.get("event_id", ""),
                "match": f"{home} vs {away}", "market": market, "selection": selection,
                "raw_text": sent[:300], "pattern_matched": matched,
                "probability": None,          # HAKUNA — maoni si takwimu
            })
            if len(out) >= MAX_ITEMS_PER_SOURCE:
                return out
    return out


def collect(fetcher: Fetcher, fixtures: list[dict], cfg, log=print) -> tuple[list[dict], list[dict]]:
    """Kusanya maoni kutoka tovuti zote zilizowashwa.

    Rudia (opinions, reports). Chanzo kilichoshindwa kinaripotiwa — hakifichwi.
    """
    opinions: list[dict] = []
    reports: list[dict] = []
    tipsters = cfg.section("sources.tipsters")
    for name, meta in tipsters.items():
        if not meta.get("enabled"):
            reports.append({"source": name, "ok": False, "records": 0,
                            "error": "imezimwa kwenye config.json", "url": ""})
            continue
        url = meta.get("url", "")
        if not url:
            reports.append({"source": name, "ok": False, "records": 0,
                            "error": "URL haipo kwenye config.json", "url": ""})
            continue
        res = fetcher.try_fetch(url, source=name)
        if not res.ok:
            reports.append({"source": name, "ok": False, "records": 0,
                            "error": res.error or f"HTTP {res.status}", "url": url,
                            "retrieved_at": res.retrieved_at})
            log(f"  ✗ {name}: {res.error or f'HTTP {res.status}'}")
            continue
        save_capture(cfg, f"tipster_{name}", res.text, log)
        items = extract_opinions(res.text, fixtures, source=name, url=url,
                                 retrieved_at=res.retrieved_at, log=log)
        opinions.extend(items)
        reports.append({"source": name, "ok": True, "records": len(items), "url": url,
                        "retrieved_at": res.retrieved_at,
                        "trust": meta.get("trust", TRUST)})
        log(f"  ✓ {name}: maoni {len(items)} yanayolingana na mechi za leo")
    return opinions, reports


def group_by_event(opinions: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for o in opinions:
        out.setdefault(o.get("event_id", ""), []).append(o)
    return out


def note_independence(reports: list[dict]) -> str:
    """Onyo la Sehemu 6.3: makubaliano ya wengi si ushahidi."""
    n_ok = sum(1 for r in reports if r.get("ok"))
    return (f"vyanzo {len(reports)} vilijaribiwa · {n_ok} vilifika · "
            f"makubaliano ya vyanzo HAYAHESABIWI kama kura huru")
