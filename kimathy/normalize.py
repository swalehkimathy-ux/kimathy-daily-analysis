"""normalize.py — usawazishaji wa majina, marudio, na ulinganishaji wa matukio.

Sheria (Sehemu 9 + spec 4.2):
  * token za kutofautisha (W, Women, U19, II, B, reserves, SC, Miami...) lazima zilingane;
  * muda wa kuanza lazima uwe ndani ya ±20 dakika, au alama ya jina ≥ 0.92;
  * wagombea wawili walio karibu (tofauti < 0.03) → KATAA kama utata. Kamwe usikisie.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path

ALIAS_PATH = Path(__file__).resolve().parent / "data" / "aliases.json"

DISTINGUISHING = {
    "w", "women", "f", "femenino", "ii", "iii", "b", "c", "reserves", "reserve",
    "academy", "youth", "u17", "u18", "u19", "u20", "u21", "u22", "u23", "amateur",
    "sc", "city", "united", "athletic", "rovers", "wanderers", "sporting", "olympique",
    "deportivo", "club", "fc", "cf", "afc", "cd", "ca", "if", "bk", "sk", "fk",
}
STOPWORDS = {"fc", "cf", "afc", "cd", "ca", "the", "de", "del", "la", "el", "and"}

_ALIAS_GROUPS: list[list[str]] | None = None


def _load_aliases() -> dict[str, str]:
    global _ALIAS_GROUPS
    if _ALIAS_GROUPS is None:
        _ALIAS_GROUPS = []
        if ALIAS_PATH.exists():
            try:
                data = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
                _ALIAS_GROUPS = [list(g) for g in data.get("groups", [])]
            except Exception:  # noqa: BLE001
                _ALIAS_GROUPS = []
    out: dict[str, str] = {}
    for grp in _ALIAS_GROUPS:
        if not grp:
            continue
        canonical = grp[0]
        for a in grp:
            out[a] = canonical
    return out


def normalize(s: str) -> str:
    """Unicode-fold, herufi ndogo, ondoa alama za uakifishaji na nafasi za ziada."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(n: str) -> list[str]:
    return [t for t in normalize(n).split() if t not in STOPWORDS]


def alias_of(n: str) -> str:
    return _load_aliases().get(normalize(n), "")


def distinguishing_tokens(n: str) -> set[str]:
    toks = set(_tokens(n))
    return {t for t in toks if t in DISTINGUISHING}


def team_sim(a: str, b: str) -> float:
    """0..1 — alama ya kufanana kwa majina mawili ya timu/mchezaji."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    aa, ab = alias_of(a), alias_of(b)
    if aa and ab and aa == ab:
        return 1.0
    if aa and normalize(aa) == nb:
        return 1.0
    if ab and na == normalize(ab):
        return 1.0

    # token za kutofautisha: upande mmoja akizo na mwingine hana → 0 (hakuna kukisia)
    da, db = distinguishing_tokens(a), distinguishing_tokens(b)
    if da - db or db - da:
        return 0.0

    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    # Token ya ziada isiyo ya kijumla → timu tofauti (Inter ≠ Inter Miami).
    extra = (ta - tb) | (tb - ta)
    if extra:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    return round(max(jaccard, seq), 4)


def _min_hhmm(t: str) -> int | None:
    m = re.search(r"(\d{1,2}):(\d{2})", str(t or ""))
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


TEAM_THRESHOLD = 0.80
AMBIGUITY_GAP = 0.03
TIME_WINDOW_MIN = 20


def event_score(ev_home: str, ev_away: str, home: str, away: str,
                ev_time: str = "", our_time: str = "") -> tuple[float, bool, str]:
    """Alama ya tukio. Rudia (score, flipped, reason). 0 = hailingani."""
    s_direct = team_sim(ev_home, home) * team_sim(ev_away, away)
    s_flip = team_sim(ev_home, away) * team_sim(ev_away, home)
    flipped = s_flip > s_direct
    score = max(s_direct, s_flip)
    if score < TEAM_THRESHOLD ** 2:
        return 0.0, flipped, "majina_hayalingani"

    et, ot = _min_hhmm(ev_time), _min_hhmm(our_time)
    if et is not None and ot is not None:
        if abs(et - ot) > TIME_WINDOW_MIN:
            return 0.0, flipped, f"muda_haulingani:{et}!={ot}"
    else:
        # Muda haujulikani → jina lazima lifanane HASWA (au kupitia alias).
        # Sheria hii ni kali kwa makusudi: bila muda hatukubali ulinganisho wa kukisia.
        if score < 0.999:
            return 0.0, flipped, "muda_haujulikani_na_jina_sio_sawa_haswa"
    return round(score, 4), flipped, "ok"


def find_event(events: list[dict], home: str, away: str,
               our_time: str = "") -> tuple[dict | None, bool, float, str]:
    """Tafuta tukio linalolingana. Rudia (event, flipped, score, reason).

    `events` = [{"home":..,"away":..,"time":"HH:MM", ...}]
    Wagombea wawili walio karibu sana → (None, False, 0, "utata").
    """
    scored = []
    for ev in events:
        sc, fl, why = event_score(ev.get("home", ""), ev.get("away", ""), home, away,
                                  ev.get("time", ""), our_time)
        if sc > 0:
            scored.append((sc, fl, ev, why))
    if not scored:
        return None, False, 0.0, "hakuna_tukio_linalolingana"
    scored.sort(key=lambda x: -x[0])
    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < AMBIGUITY_GAP:
        return None, False, scored[0][0], "utata_wagombea_wawili_wa_karibu"
    sc, fl, ev, why = scored[0]
    return ev, fl, sc, why


def event_key(home: str, away: str, kickoff_iso: str = "") -> str:
    """Kitambulisho cha tukio kilichosawazishwa (kwa kuondoa marudio)."""
    return "|".join([normalize(home), normalize(away), (kickoff_iso or "")[:16]])


def dedupe(records: list[dict], key_fn=None) -> tuple[list[dict], int]:
    """Ondoa marudio. Rekodi ya kwanza (au yenye data zaidi) inabaki."""
    key_fn = key_fn or (lambda r: event_key(r.get("home", ""), r.get("away", ""),
                                           str(r.get("kickoff_tz", ""))))
    seen: dict[str, dict] = {}
    removed = 0
    for r in records:
        k = key_fn(r)
        if k in seen:
            removed += 1
            old = seen[k]
            if len(str(r)) > len(str(old)):
                seen[k] = r
            continue
        seen[k] = r
    return list(seen.values()), removed
