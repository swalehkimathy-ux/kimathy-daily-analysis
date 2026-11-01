#!/usr/bin/env python3
"""
betway.py — K96 PICKS: Betway Tanzania (primary bookie verification).

Feeds halisi za Betway Africa (zilizothibitishwa live 2026-10-28):
  config:   https://config.betwayafrica.com/cron/sports/TZ/en-US
  feeds:    https://feeds-roa2.betwayafrica.com/br/_apis/sport/v1/...
    Highlights : BetBook/Highlights/?countryCode=TZ&sportId=soccer&...&marketTypes=[Win/Draw/Win]
    Markets    : MarketGroupings/MarketGroupNamesAndMarketsForEvent?eventId=..&countryCode=TZ
                 (max 100/call → auto-paginate; eventId = SportRadar id)

Market map ya TZ (soccer/basketball/tennis):
  1X2          : CName "1X2"                     · outcomes = home/Draw/away
  Double Chance: CName "double-chance"           · outcomes = "<Home> Or Draw" | "<Home> Or <Away>" | "Draw Or <Away>"
  Draw No Bet  : CName "draw-no-bet"             · outcomes = home | away
  Total Goals  : CName "handicap-goals-over"     · name "[Total Goals]" · outcomes "Over "/"Under " + outcome.handicap = line
  BTTS         : CName "both-teams-to-score"     · outcomes Yes | No
  EH +2        : CName "handicap-wdw" · name "[Handicap] [3-Way]" · outcomes: team/Draw with outcome.handicap = ±1,±2,±3
  BB Winner    : market NAME "Winner (Incl. Overtime)" · outcomes = home | away
  TN Winner    : CName "to-win" · name "[Match Winner]" · outcomes = home | away
"""

import datetime as _dt
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request

FEEDS = "https://feeds-roa2.betwayafrica.com/br/_apis/sport/v1"
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) K96Picks/1.0",
    "Origin": "https://www.betway.co.tz",
    "Referer": "https://www.betway.co.tz/",
    "Accept": "application/json",
}

SPORT_ID = {"football": "soccer", "basketball": "basketball", "tennis": "tennis"}
EAT = _dt.timezone(_dt.timedelta(hours=3))


class BetwayError(Exception):
    pass


def _get(path_q, timeout=25, tries=2):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(FEEDS + path_q, headers=HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1 + i)
    raise BetwayError(str(err))


# Phase 2: matcher ya pamoja (spec 4.2)
import matching as _match
_norm = _match.normalize


_DAY = {}   # in-memory cache per (day)


_DOWN = {}  # day_iso → error (Betway haifikiki — usijaribu tena kwa kila mechi)


def day_index(day_iso, log):
    """events zote za siku (EAT) kwa sports 3 → list ya {id, home, away, sport, epoch}."""
    if day_iso in _DAY:
        return _DAY[day_iso]
    if day_iso in _DOWN:
        raise BetwayError(_DOWN[day_iso])
    try:
        return _day_index_fetch(day_iso, log)
    except BetwayError as e:
        _DOWN[day_iso] = str(e)
        log(f"  ⚠ betway haifikiki ({str(e)[:80]}) — haitajaribiwa tena kwa run hii")
        raise


def _day_index_fetch(day_iso, log):
    out = []
    for sport, sid in SPORT_ID.items():
        skip, kept = 0, 0
        while skip <= 300:                                  # Betway max unknown; Highlights take≈85–100
            mt = "[Win/Draw/Win]" if sport == "football" else ""
            q = (f"/BetBook/Highlights/?countryCode=TZ&sportId={sid}&Skip={skip}&Take=50"
                 f"&cultureCode=en-US&isEsport=false&boostedOnly=false&marketTypes={urllib.parse.quote(mt)}")
            d = _get(q)
            evs = d.get("events") or []
            for e in evs:
                ep = e.get("expectedStartEpoch")
                if not ep:
                    continue
                try:
                    eat = _dt.datetime.fromtimestamp(int(ep), _dt.timezone.utc).astimezone(EAT)
                except Exception:  # noqa: BLE001
                    continue
                if eat.date().isoformat() != day_iso:
                    continue
                kept += 1
                out.append({"id": str(e["eventId"]), "home": e.get("homeTeam") or "",
                            "away": e.get("awayTeam") or "", "sport": sport,
                            "league": e.get("league") or "", "time_eat": eat.strftime("%H:%M")})
            if len(evs) < 50 or not evs:
                break
            skip += 50
        log(f"  betway {sport}: {kept} events siku {day_iso}")
    _DAY[day_iso] = out
    return out


def _find_event(idx, sport, home, away, time_eat=None, league=None, log=None):
    """Delegate: matching.py (kickoff ±20min · ambiguity-reject)."""
    ev, flip, sc, why = _match.find_event(idx, sport, home, away, time_eat, league, log)
    return ev, flip


def _markets_all(event_id):
    mig, outs, prices = [], [], []
    skip = 0
    while skip < 1000:
        q = (f"/MarketGroupings/MarketGroupNamesAndMarketsForEvent?eventId={event_id}"
             f"&marketGroupId=%20&countryCode=TZ&cultureCode=en-US&skip={skip}&take=100"
             f"&isBuildABetOnly=false&searchQuery=")
        d = _get(q)
        page = d.get("marketsInGroup") or []
        mig   += page
        outs  += d.get("outcomes") or []
        prices+= d.get("prices") or []
        if len(page) < 100:
            break
        skip += 100
    return mig, outs, {p["outcomeId"]: p for p in prices}


def _find_price(mig, outs, pmap, match):
    """match: fn(outcome, market) → bool. Rudi (odds, suspended, outcome_name) | None."""
    oid2o = {o["outcomeId"]: o for o in outs}
    for m in mig:
        for o in outs:
            if o.get("marketId") != m.get("marketId"):
                continue
            if match(o, m):
                pr = pmap.get(o["outcomeId"])
                if not pr or pr.get("priceDecimal") is None:
                    return {"ok": True, "odds": None, "susp": m.get("isSuspended"), "name": o.get("name"), "no_price": True}
                return {"ok": True, "odds": pr["priceDecimal"], "susp": m.get("isSuspended"), "name": o.get("name")}
    return None


def snapshot_event(event_id) -> list[dict]:
    """Phase 3 (spec 5.2/7.3): outcomes ZOTE za event: market, outcome, line, odds, suspended.
    Yatumika = odds_snapshots + devig (p_market)."""
    mig, outs, pmap = _markets_all(event_id)
    rows = []
    for m in mig:
        mid = m.get("marketId")
        for o in outs:
            if o.get("marketId") != mid:
                continue
            pr = pmap.get(o.get("outcomeId"))
            rows.append({
                "bookmaker": "betway",
                "mline": m.get("handicap"),
                "market": m.get("marketTypeCName") or m.get("name") or "",
                "market_name": (m.get("name") or "").strip("[]"),
                "outcome": o.get("name") or "",
                "line": o.get("handicap"),
                "odds": (pr or {}).get("priceDecimal"),
                "suspended": pr is None,
            })
    return rows


def verify_pick_betway(pick, day_iso, log):
    """Return dict sawa na bookie.verify_pick ya pawa (bettable/odds/note)."""
    sport = pick.get("sport"); market = pick.get("market"); tip = pick.get("tip")
    if sport not in SPORT_ID:
        return None
    try:
        idx = day_index(day_iso, log)
    except BetwayError as e:
        return {"api_down": True, "note": f"betway unreachable: {e}", "bettable": None}
    ev, flipped = _find_event(idx, sport, pick.get("home", ""), pick.get("away", ""),
                                 pick.get("time"), pick.get("league"), print)
    if not ev:
        return {"bettable": False, "note": "mechi hapo kwenye Betway TZ — NOT BETTABLE"}
    try:
        mig, outs, pmap = _markets_all(ev["id"])
    except BetwayError as e:
        return {"api_down": True, "note": f"betway markets fail: {e}", "bettable": None}

    home_bw, away_bw = ev["home"], ev["away"]
    if flipped:
        home_bw, away_bw = away_bw, home_bw          # pimba kadi ya side za Forebet

    tip_s = str(tip or "")
    home_l, away_l = _norm(home_bw), _norm(away_bw)

    if market == "1X2":
        want = {"1": home_l, "X": "draw", "2": away_l}.get(tip_s)
        r = _find_price(mig, outs, pmap, lambda o, m: m.get("marketTypeCName") == "1X2" and _norm(o.get("name", "")) == want)
    elif market == "Draw No Bet":
        want = home_l if tip_s == "1" else away_l
        r = _find_price(mig, outs, pmap, lambda o, m: m.get("marketTypeCName") == "draw-no-bet" and _norm(o.get("name", "")) == want)
    elif market == "Double Chance":
        # outcomes: "<H> Or Draw", "<H> Or <A>", "Draw Or <A>"
        def dc_match(o, m):
            if m.get("marketTypeCName") != "double-chance": return False
            n = _norm(o.get("name", ""))
            if tip_s == "1X":  return home_l in n and "draw" in n
            if tip_s == "X2":  return away_l in n and "draw" in n
            if tip_s == "12":  return home_l in n and away_l in n and "draw" not in n
            return False
        r = _find_price(mig, outs, pmap, dc_match)
    elif market == "BTTS":
        r = _find_price(mig, outs, pmap, lambda o, m: m.get("marketTypeCName") == "both-teams-to-score"
                        and m.get("handicap") == 0 and _norm(o.get("name", "")) == _norm(tip_s))
    elif market == "Total Goals":
        mm = re.search(r"(\d+(?:\.\d+)?)", tip_s)
        side = "over" if tip_s.startswith("Over") else "under"
        line = float(mm.group(1)) if mm else None
        r = _find_price(mig, outs, pmap, lambda o, m: m.get("marketTypeCName") == "handicap-goals-over"
                        and "total goals" in _norm(m.get("name", ""))
                        and _norm(o.get("name", "")).startswith(side)
                        and (line is None or abs(float(o.get("handicap") or -999) - line) < 0.01))
    elif market == "Team Goals":
        mm = re.search(r"(\d+(?:\.\d+)?)", tip_s)
        line = float(mm.group(1)) if mm else None
        team_side = "home" if tip_s.startswith("Home ") else "away"
        outcome_side = "over" if " Over " in f" {tip_s} " else "under"
        team_name = home_l if team_side == "home" else away_l
        def team_total_match(o, m):
            if m.get("marketTypeCName") != "handicap-goals-over":
                return False
            market_name = _norm(m.get("name", ""))
            named_side = (("home" in market_name or "host" in market_name or team_name in market_name)
                          if team_side == "home" else
                          ("away" in market_name or "guest" in market_name or team_name in market_name))
            return (named_side and _norm(o.get("name", "")).startswith(outcome_side)
                    and (line is None or abs(float(o.get("handicap") or m.get("handicap") or -999) - line) < 0.01))
        r = _find_price(mig, outs, pmap, team_total_match)
    elif market == "Handicap +2":
        mm = re.search(r"([+-]?\d+(?:\.\d+)?)", tip_s)
        mag = float(mm.group(1)) if mm else 2.0
        want = home_l if "Home" in tip_s else away_l
        r = _find_price(mig, outs, pmap, lambda o, m: m.get("marketTypeCName") == "handicap-wdw"
                        and "3 way" in _norm(m.get("name", ""))
                        and _norm(o.get("name", "")) == want
                        and abs(float(o.get("handicap") or -999) - mag) < 0.01)
    elif market == "Winner":
        want = home_l if tip_s.upper() in ("1", "P1") else away_l
        if sport == "basketball":
            r = _find_price(mig, outs, pmap, lambda o, m: m.get("name") == "Winner (Incl. Overtime)"
                            and _norm(o.get("name", "")) == want)
        else:   # tennis
            r = _find_price(mig, outs, pmap, lambda o, m: (m.get("marketTypeCName") == "to-win"
                            and "match winner" in _norm(m.get("name", ""))
                            and _norm(o.get("name", "")) == want))
    else:
        return {"bettable": False, "note": f"market '{market}' haijawekewa uthibitisho wa Betway"}

    if not r:
        return {"bettable": False, "note": f"tip '{tip}' haipo kwenye Betway TZ — NOT BETTABLE",
                "event_found": ev["home"], "ev_away": ev["away"], "bw_id": ev["id"]}
    if r.get("susp"):
        return {"bettable": False, "note": "odds SUSPENDED kwenye Betway — NOT BETTABLE"}
    if r.get("no_price") or r.get("odds") is None:
        return {"bettable": False, "note": "hakuna odds inayoonekana Betway — NOT BETTABLE"}
    return {"bettable": True, "bk_odds": r["odds"], "note": f"betway TZ ✓ @{r['odds']}",
            "bw_event": f"{home_bw} vs {away_bw}", "bw_league": ev.get("league"), "bw_id": ev["id"]}
