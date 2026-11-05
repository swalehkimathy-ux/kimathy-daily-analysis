"""forebet.py — adapta ya Forebet (chanzo MUHIMU, Sehemu 6.1).

Njia zilizothibitishwa kufanya kazi (zimepakiwa kutoka scraper iliyokuwa ikifanya kazi):
  * Mpira wa miguu  : feed ya JSON  https://www.forebet.com/scripts/getrs.php
  * Kikapu / Tenisi : kurasa za DOM https://www.forebet.com/en/<sport>/predictions-today

FOREBET_FORET_SHIFT: DATE_BAH ya Forebet iko UTC+2; +1 → EAT (UTC+3).
Hakuna utabiri unaobuniwa hapa — tunasoma tu yale yaliyochapishwa.
"""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata

from . import clock
from .net import FetchResult, Fetcher, save_capture, try_json

SOURCE = "forebet"
FOREBET_TZ_SHIFT_HOURS = 1          # UTC+2 (Forebet) → UTC+3 (EAT)

FEED_URL = ("https://www.forebet.com/scripts/getrs.php?ln=en&tp=1x2"
            "&in={day}&ord=0&tz=0&tzs=&tze=&output=1")
SPORT_PAGES = {
    "basketball": "https://www.forebet.com/en/basketball/predictions-today",
    "tennis": "https://www.forebet.com/en/tennis/predictions-today",
}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def match_url(sport: str, home: str, away: str, mid: str, league_name: str = "") -> str:
    if sport == "football":
        return f"https://www.forebet.com/en/football/matches/{slug(home)}-{slug(away)}-{mid}"
    lg = slug(league_name)
    if lg:
        return f"https://www.forebet.com/en/{sport}/matches/{lg}/{slug(home)}-{slug(away)}/{mid}"
    return f"https://www.forebet.com/en/{sport}/predictions-today"


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(v):
    n = _num(v)
    return int(n) if n is not None else None


def parse_bah(bah: str) -> _dt.datetime | None:
    """'2026-11-05 18:30:00' (UTC+2) → datetime ya EAT (naive, baadaye inafanywa aware)."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?", bah or "")
    if not m:
        return None
    d = _dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6] or 0))
    return d + _dt.timedelta(hours=FOREBET_TZ_SHIFT_HOURS)


def parse_dom_date(s: str) -> _dt.datetime | None:
    s = s or ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})", s)
    if m:
        d = _dt.datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5]))
        return d + _dt.timedelta(hours=FOREBET_TZ_SHIFT_HOURS)
    m = re.search(r"(\d{1,2})/(\d{1,2})\s*-\s*\d{1,2}/\d{1,2}/(\d{4})", s)
    if m:
        d = _dt.datetime(int(m[3]), int(m[2]), int(m[1]))
        return d + _dt.timedelta(hours=FOREBET_TZ_SHIFT_HOURS)
    return None


def _base_record(**kw) -> dict:
    rec = {
        "event_id": "", "sport": "", "league": "", "home": "", "away": "",
        "kickoff_tz": None, "status": "Scheduled",
        "probs": {}, "predicted_score": None, "avg": None,
        "odds_1x2": None, "home_form": [], "away_form": [],
        "home_pos": None, "away_pos": None, "trend": "", "best_of": None,
        "source": SOURCE, "source_url": "", "retrieved_at": "", "raw": {},
    }
    rec.update(kw)
    return rec


# ---------------------------------------------------------------- FOOTBALL ---
def _status_of(row: dict) -> str:
    st = row.get("comment") or "Scheduled"
    if row.get("extra_time_score"):
        st = f"AET (ET {row['extra_time_score']})"
    if row.get("penalty_score"):
        st = f"Pen. ({row['penalty_score']})"
    return st


def _league_name(leagues: dict, lid) -> str:
    try:
        e = leagues.get(str(lid)) or leagues.get(lid)
        if isinstance(e, list):
            return f"{e[0]} {e[1]}".strip()
    except Exception:  # noqa: BLE001
        pass
    return f"ligi {lid}"


def records_from_feed(rows: list, leagues: dict, day: str, retrieved_at: str,
                      feed_url: str) -> list[dict]:
    """Badilisha safu za getrs.php kuwa rekodi za injini (mpira wa miguu)."""
    out = []
    for r in rows or []:
        bah = r.get("DATE_BAH") or r.get("DATE") or ""
        if not bah:
            continue
        dt = parse_bah(bah)
        if dt is None or dt.strftime("%Y-%m-%d") != day:
            continue
        o1, ox, o2 = _num(r.get("best_odd_1")), _num(r.get("best_odd_X")), _num(r.get("best_odd_2"))
        odds = [o1, ox, o2] if (o1 and ox and o2) else None
        home = r.get("HOST_NAME") or ""
        away = r.get("GUEST_NAME") or ""
        mid = str(r.get("id") or "")
        league = _league_name(leagues or {}, r.get("league_id"))
        out.append(_base_record(
            event_id=f"forebet:{mid}" if mid else "",
            sport="football", league=league, home=home, away=away,
            kickoff_tz=clock.to_tz(dt), status=_status_of(r),
            probs={"1": _int(r.get("Pred_1")), "X": _int(r.get("Pred_X")), "2": _int(r.get("Pred_2"))},
            predicted_score=[_int(r.get("host_sc_pr")), _int(r.get("guest_sc_pr"))],
            avg=_num(r.get("goalsavg")), odds_1x2=odds,
            home_form=r.get("host_form") or [], away_form=r.get("guest_form") or [],
            home_pos=r.get("host_pos") or None, away_pos=r.get("guest_pos") or None,
            trend=((r.get("trend") or {}).get("en") or ""),
            source_url=match_url("football", home, away, mid, league),
            retrieved_at=retrieved_at, raw=r,
        ))
    out.sort(key=lambda x: (x["kickoff_tz"] or clock.now_tz(), x["league"], x["event_id"]))
    return out


def fetch_football(fetcher: Fetcher, day: str, cfg, log=print) -> tuple[list[dict], dict]:
    """Chota feed ya mpira wa miguu. Rudia (rekodi, ripoti)."""
    url = FEED_URL.format(day=day)
    res: FetchResult = fetcher.try_fetch(url, source="forebet-football")
    if not res.ok:
        return [], {"source": SOURCE, "url": url, "ok": False,
                    "error": res.error or f"HTTP {res.status}", "records": 0,
                    "retrieved_at": res.retrieved_at}
    text = re.sub(r"<[^>]+>", "", res.text).strip()
    data = try_json(text)
    if not data or not isinstance(data, list) or len(data) < 2:
        return [], {"source": SOURCE, "url": url, "ok": False,
                    "error": "jibu la getrs.php halikuwa JSON halali", "records": 0,
                    "retrieved_at": res.retrieved_at}
    rows, leagues = data[0] or [], data[1] or {}
    recs = records_from_feed(rows, leagues, day, res.retrieved_at, url)
    return recs, {"source": SOURCE, "url": url, "ok": True, "records": len(recs),
                  "fetched_rows": len(rows), "retrieved_at": res.retrieved_at}


# ------------------------------------------------------- BASKETBALL / TENNIS ---
def _txt(el) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def records_from_dom(html: str, sport: str, day: str, retrieved_at: str, page_url: str) -> list[dict]:
    """Chota safu za mechi (.rcnt) kutoka ukurasa wa utabiri wa Forebet."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for row in soup.select(".rcnt"):
        a = row.select_one(f'a[href*="/en/{sport}/matches/"]')
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"(\d+)(?:[?#].*)?$", href)
        mid = m.group(1) if m else ""

        league = ""
        sib, hops = row.find_previous_sibling(), 0
        while sib is not None and hops < 80:
            if "heading" in (sib.get("class") or []):
                league = _txt(sib)
                break
            sib, hops = sib.find_previous_sibling(), hops + 1
        if not league:
            prev = row.find_previous("div", class_="heading")
            league = _txt(prev) if prev else ""
        if not league:
            league = _txt(row.select_one(".shortTag")) or sport

        home, away = _txt(row.select_one(".homeTeam")), _txt(row.select_one(".awayTeam"))
        dt = parse_dom_date(_txt(row.select_one(".date_bah")))

        pv = []
        for sp in row.select(".fprc span"):
            t = _txt(sp)
            if t.isdigit():
                pv.append(int(t))
        probs = {}
        if len(pv) >= 3:
            probs = {"1": pv[0], "X": pv[1], "2": pv[2]}
        elif len(pv) >= 2:
            probs = {"1": pv[0], "2": pv[1]}

        ps = None
        ex = row.select_one(".ex_sc")
        if ex is not None:
            html_ex = re.sub(r"<br\s*/?>", "|", str(ex), flags=re.I)
            plain = re.sub(r"<[^>]+>", "", html_ex)
            parts = [int(x.strip()) for x in plain.split("|") if x.strip().isdigit()]
            if len(parts) >= 2:
                ps = [parts[0], parts[1]]
            else:
                dm = re.search(r"(\d+)\s*[-\u2013]\s*(\d+)", plain)
                if dm:
                    ps = [int(dm[1]), int(dm[2])]

        od = []
        for sp in row.select(".haodd span")[:3]:
            t = _txt(sp)
            v = _num(t) if t and t != "-" else None
            od.append(v)
        odds = od if any(x is not None for x in od) else None

        url = href if href.startswith("http") else "https://www.forebet.com" + href
        out.append(_base_record(
            event_id=f"forebet:{mid}" if mid else "",
            sport=sport, league=league, home=home, away=away,
            kickoff_tz=clock.to_tz(dt),
            status=_txt(row.select_one(".lmin_td")) or "Scheduled",
            probs=probs, predicted_score=ps, avg=_num(_txt(row.select_one(".avg_sc"))),
            odds_1x2=odds, source_url=url, retrieved_at=retrieved_at, raw={},
        ))
    return [r for r in out if r["kickoff_tz"] and r["kickoff_tz"].date().isoformat() == day]


def fetch_sport_dom(fetcher: Fetcher, sport: str, day: str, cfg, log=print) -> tuple[list[dict], dict]:
    url = SPORT_PAGES[sport]
    res = fetcher.try_fetch(url, source=f"forebet-{sport}")
    if not res.ok:
        return [], {"source": SOURCE, "url": url, "ok": False,
                    "error": res.error or f"HTTP {res.status}", "records": 0,
                    "retrieved_at": res.retrieved_at}
    save_capture(cfg, f"forebet_{sport}", res.text, log)
    recs = records_from_dom(res.text, sport, day, res.retrieved_at, url)
    return recs, {"source": SOURCE, "url": url, "ok": True, "records": len(recs),
                  "retrieved_at": res.retrieved_at}


def collect(fetcher: Fetcher, day: str, cfg, log=print) -> tuple[dict[str, list[dict]], list[dict]]:
    """Kusanya Forebet kwa michezo yote iliyoruhusiwa. Chanzo kilichoshindwa hakivunji run."""
    by_sport: dict[str, list[dict]] = {}
    reports: list[dict] = []
    sports = [s for s in cfg.get("sports", ["football", "basketball", "tennis"])]
    for sport in sports:
        if sport == "football":
            recs, rep = fetch_football(fetcher, day, cfg, log)
        elif sport in SPORT_PAGES:
            recs, rep = fetch_sport_dom(fetcher, sport, day, cfg, log)
        else:
            rep = {"source": SOURCE, "url": "", "ok": False,
                   "error": f"mchezo '{sport}' hauna adapta ya Forebet", "records": 0,
                   "retrieved_at": clock.now_tz().isoformat(timespec="seconds")}
            recs = []
        reports.append(rep)
        if rep["ok"]:
            log(f"  ✓ Forebet/{sport}: rekodi {rep['records']}")
        else:
            log(f"  ✗ Forebet/{sport}: {rep['error']}")
        if recs:
            by_sport[sport] = recs
    return by_sport, reports
