#!/usr/bin/env python3
"""
bookie.py — K96 PICKS: verification ya uwezekano wa kubeti (SERVING CORRECT RULE ya user).
To chanzo ODDS HALISI + kuangalia tip iko kweli kwenye BETTING SITE.

Bookmaker: betPawa Tanzania (pawaTech v4 API halali, inatumiwa na tovuti yao).
  Header lazima:  X-Pawa-Brand: betpawa-tanzania  ·  X-Pawa-Language: en
  Endpoint:  GET /api/sportsbook/v4/events/lists/by-queries?q={queries}
           GET /api/sportsbook/v4/events/{id}     (markets zote za event)

Mantiki (kwa mechi i-picked na engine):
  1) Tafuta event kwa majina (home - away) → ikikosekana kabisa → NOT BETTABLE
  2) Fungua markets zake → K96 marketid map; tip iliswa ku-exist + isiyo-suspended
  3) Rudisha {bettable, bk_odds, bk_market, note} — odds halisi za bookie.

IDMAP ya marketType (verified kwa live API, 2026-10-28):
  Football: 1X2 FT=3743 · Double Chance FT=4693 · Draw No Bet FT=4703
            BTTS FT=3795 · Total O/U FT=5000 (row.specifier.total)
            Handicap 1X2 FT=4724  (row.specifier.hcp, e.g. "+2" / "-2")
  Basketball: Moneyline - FT incl OT = 4791 (names 1/2)
  Tennis:     Moneyline - FT          = 2043818  (names 1/2)
"""

import datetime as _dt
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request

BASE = "https://www.betpawa.co.tz/api/sportsbook/v4"
HDRS = {
    "X-Pawa-Brand": "betpawa-tanzania",
    "X-Pawa-Language": "en",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) K96Picks/1.0",
    "Accept": "application/json",
}

CAT = {"football": "2", "basketball": "3", "tennis": "452"}

MKT_ID = {
    "football": {"1X2": "3743", "Double Chance": "4693", "Draw No Bet": "4703",
                 "BTTS": "3795", "Total Goals": "5000", "Handicap +2": "4724"},
    "basketball": {"Winner": "4791"},
    "tennis": {"Winner": "2043818"},
}

EAT = _dt.timezone(_dt.timedelta(hours=3))


class BookieError(Exception):
    """Bookie API haifikiki / kosa leji — sio 'hakuna odds'."""


def _get(path, timeout=25, tries=2):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(BASE + path, headers=HDRS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1 + i)
    raise BookieError(str(err))


# Phase 2: matcher ya pamoja (spec 4.2)
import matching as _match
_norm = _match.normalize


def _fetch_day(day_iso, log):
    """Uplaod events zote za UPCOMING kwa sports 3; rudisha orodha ya event-dicts."""
    index = []
    for sport, cat in CAT.items():
        q = {"queries": [{"query": {"eventType": "UPCOMING", "categories": [cat]},
                          "sort": {"popularity": "DESC"}, "take": 100}]}
        path = "/events/lists/by-queries?q=" + urllib.parse.quote(json.dumps(q))
        data = _get(path)
        evs = []
        def walk(o):
            if isinstance(o, dict):
                if "participants" in o:
                    evs.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
        n_day = 0
        for e in evs:
            st = e.get("startTime")
            try:
                eat = _dt.datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(EAT)
            except Exception:  # noqa: BLE001
                continue
            if eat.date().isoformat() != day_iso:
                continue
            n_day += 1
            parts = (e.get("participants") or [])
            home = parts[0].get("name") if parts else ""
            away = parts[1].get("name") if len(parts) > 1 else ""
            index.append({"id": e.get("id"), "name": e.get("name") or "",
                          "home": home, "away": away, "sport": sport,
                          "competition": (e.get("competition") or {}).get("name") or "",
                          "time_eat": eat.strftime("%H:%M")})
        log(f"  betPawa {sport}: {n_day} events siku {day_iso}")
    return index


# in-memory cache per (day) — ndani ya process tu (run moja)
_DAY_CACHE = {}

_DOWN = {}   # day_iso → error (betPawa haifikiki — usijaribu tena kwa kila mechi)


def day_index(day_iso, log):
    if day_iso in _DAY_CACHE:
        return _DAY_CACHE[day_iso]
    if day_iso in _DOWN:
        raise BookieError(_DOWN[day_iso])
    try:
        _DAY_CACHE[day_iso] = _fetch_day(day_iso, log)
    except BookieError as e:
        _DOWN[day_iso] = str(e)
        log(f"  ⚠ betPawa haifikiki ({str(e)[:80]}) — haitajaribiwa tena kwa run hii")
        raise
    return _DAY_CACHE[day_iso]


def _find_event(idx, sport, home, away, time_eat=None, league=None, log=None):
    """Delegate: matching.py (kickoff ±20min · ambiguity-reject)."""
    ev, flip, sc, why = _match.find_event(idx, sport, home, away, time_eat, league, log)
    return ev, flip


def _markets(event_id):
    data = _get(f"/events/{event_id}")
    ev = data.get("event") or data
    return ev.get("markets") or []


def snapshot_event(event_id) -> list[dict]:
    """Phase 3 (spec 5.2/7.3): outcomes ZOTE za event: market, outcome, line, odds, suspended."""
    rows = []
    for m in _markets(event_id):
        mk_name = m.get("betTypeId") or m.get("name") or ""
        for row in (m.get("row") or []):
            spec = row.get("specifier") or {}
            line = spec.get("total") if spec.get("total") is not None else spec.get("hcp")
            for p in (row.get("prices") or []):
                rows.append({
                    "bookmaker": "betpawa",
                    "market": mk_name,
                    "market_name": m.get("name") or "",
                    "outcome": p.get("name") or "",
                    "line": line,
                    "odds": p.get("odds"),
                    "suspended": bool(p.get("suspended")),
                })
    return rows


def _price_from_market(market, *, tip=None, names=None, line=None, hcp=None):
    """Tafuta price halisi: names kwenye row (au line/hcp match)."""
    for row in (market.get("row") or []):
        spec = row.get("specifier") or {}
        if line is not None:
            if str(spec.get("total")) not in (str(line), f"{float(line):.1f}"):
                continue
        if hcp is not None:
            hs = str(spec.get("hcp") or "").replace(" ", "")
            hs = hs.replace("+", "")
            if hs != str(hcp):
                continue
        for p in (row.get("prices") or []):
            if names and p.get("name") not in names:
                continue
            if p.get("suspended"):
                return {"found": True, "suspended": True, "odds": p.get("odds")}
            return {"found": True, "suspended": False, "odds": p.get("odds")}
    return {"found": False}


def _hcp_for_tip(tip):
    """'+2 Home' → ('+2', '1')  ·  '+2 Away' → ('-2', '2')  (hcp ni kwa home)."""
    m = re.search(r"([+-]?\d+(?:\.\d+)?)", tip or "")
    if not m:
        return None, None
    mag = m.group(1).replace("+", "")
    if "Home" in tip:
        return mag, "1"
    return "-" + mag, "2"


def verify_pick(pick, day_iso, log):
    """K96 pick → BETWAY TZ kwanza, hapo fail → betPawa TZ. Rudi dirama as documented."""
    try:
        import betway
        r = betway.verify_pick_betway(pick, day_iso, log)
        if r is not None and not r.get("api_down"):
            return r
    except Exception as e:  # noqa: BLE001
        log(f"  [betway] imeshindika ({str(e)[:90]}) → fallback betPawa")
        r = None
    # ── fallback: betPawa ───────────────────────────────────────────────
    return _verify_pawa(pick, day_iso, log)


def _verify_pawa(pick, day_iso, log):
    """Toleo la awali la betPawa TZ (back-up)."""
    sport = pick.get("sport"); market = pick.get("market"); tip = pick.get("tip")
    if sport not in CAT:
        return {"bettable": True, "note": "sport siyo inayounjwa — imeruhusiwa"}
    mkt_id = MKT_ID.get(sport, {}).get(market)
    if not mkt_id:
        return {"bettable": False, "note": f"bookie: market '{market}' haitumiki (no id)"}
    try:
        idx = day_index(day_iso, log)
    except BookieError as e:
        return {"bettable": None, "note": f"bookie unreachable: {e}", "api_down": True}
    ev, flipped = _find_event(idx, sport, pick.get("home", ""), pick.get("away", ""),
                                pick.get("time"), pick.get("league"), print)
    if not ev:
        return {"bettable": False, "note": "mechi hapo kwenye betPawa TZ — NOT BETTABLE"}

    def _swap(t):
        """sign tips (1↔2, 1X↔X2) ikikatiliwa sides zimepindwa kwenye bookie."""
        if not flipped:
            return t
        return {"1": "2", "2": "1", "P1": "P2", "P2": "P1",
                "1X": "X2", "X2": "1X", "+2 Home": "+2 Away", "+2 Away": "+2 Home"}.get(t, t)
    tip = _swap(tip)
    try:
        markets = _markets(ev["id"])
    except BookieError as e:
        return {"bettable": None, "note": f"event markets fail: {e}", "api_down": True}
    mkt = next((m for m in markets if m.get("marketType", {}).get("id") == mkt_id), None)
    if not mkt:
        return {"bettable": False, "note": f"market '{mkt_id}' haipo kwenye event — NOT BETTABLE",
                "event_found": ev["name"], "bp_id": ev.get("id")}

    if market == "1X2":          r = _price_from_market(mkt, names=[tip])
    elif market == "Double Chance": r = _price_from_market(mkt, names=[tip])
    elif market == "Draw No Bet":   r = _price_from_market(mkt, names=[tip])
    elif market == "BTTS":          r = _price_from_market(mkt, names=[tip])
    elif market == "Winner":        r = _price_from_market(mkt, names=["1" if str(tip).upper() in ("1", "P1") else "2"])
    elif market == "Total Goals":
        m = re.search(r"(\d+(?:\.\d+)?)", tip or "")
        side = "Over" if (tip or "").startswith("Over") else "Under"
        r = _price_from_market(mkt, names=[side], line=m.group(1) if m else None)
    elif market == "Handicap +2":
        hcp, side = _hcp_for_tip(tip)
        r = _price_from_market(mkt, names=[side], hcp=hcp)
    else:
        return {"bettable": True, "note": "market haispechukiwi kutathmini — imeruhusiwa"}

    if not r.get("found"):
        return {"bettable": False, "note": f"tip '{tip}' hapo odds hiyo moja kwa moja — NOT BETTABLE",
                "event_found": ev["name"], "bp_id": ev.get("id")}
    if r.get("suspended"):
        return {"bettable": False, "note": f"odds SUSPENDED kwa betPawa — NOT BETTABLE",
                "event_found": ev["name"], "bp_id": ev.get("id")}
    return {"bettable": True, "bk_odds": r.get("odds"),
            "note": f"betPawa TZ ✓ @{r.get('odds')}", "event_found": ev["name"], "bp_id": ev.get("id"),
            "bp_competition": ev.get("competition")}


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4 (spec 5.2): PROVIDER — per-match probabilities za bookies (devig)
# Rudi: {"found": bool, "bookmaker": "betway"/"betpawa", "probs": {(mkt,tip):p},
#         "odds": {(mkt,tip):o}} — None ikikosekana kikamilifu
# ═══════════════════════════════════════════════════════════════════════
_PROV_CACHE = {}

def _bw_rows_to_probs(rows, home_n, away_n):
    """betway snapshot rows → (probs, odds) keys (K96 market, tip)."""
    import oddsx, collections
    probs, odds = {}, {}
    by_m: dict[str, list] = collections.defaultdict(list)
    for r in rows:
        if r.get("suspended") or r.get("odds") is None:
            continue
        by_m[(r["market"], r.get("mline"), r["market_name"])].append(r)

    for (mkt, mline, mname), rs in by_m.items():
        mk = (mkt or "").lower()
        if mk == "1x2":
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                if n == "draw":    labs["X"] = r["odds"]
                elif n == home_n:  labs["1"] = r["odds"]
                elif n == away_n:  labs["2"] = r["odds"]
            d = oddsx.devig([labs.get(t) for t in ("1", "X", "2")])
            for t, pr in zip(("1", "X", "2"), d):
                probs[("1X2", t)] = pr
                if labs.get(t): odds[("1X2", t)] = labs[t]
        elif mk == "double-chance":
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                has_h = home_n and home_n.split()[0] in n
                has_a = away_n and away_n.split()[0] in n
                has_x = "draw" in n
                if has_x and has_h: labs["1X"] = r["odds"]
                elif has_x and has_a: labs["X2"] = r["odds"]
                elif has_h and has_a: labs["12"] = r["odds"]
            d = oddsx.devig([labs.get(t) for t in ("1X", "X2", "12")], total=2.0)   # G2: DC sums→2
            for t, pr in zip(("1X", "X2", "12"), d):
                probs[("Double Chance", t)] = pr
                if labs.get(t): odds[("Double Chance", t)] = labs[t]
        elif mk == "draw-no-bet":
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                if n == home_n: labs["1"] = r["odds"]
                elif n == away_n: labs["2"] = r["odds"]
            d = oddsx.devig([labs.get(t) for t in ("1", "2")])
            for t, pr in zip(("1", "2"), d):
                probs[("Draw No Bet", t)] = pr
                if labs.get(t): odds[("Draw No Bet", t)] = labs[t]
        elif mk == "both-teams-to-score" and (mline in (None, 0, 0.0)):
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                if n == "yes": labs["Yes"] = r["odds"]
                elif n == "no": labs["No"] = r["odds"]
            d = oddsx.devig([labs.get(t) for t in ("Yes", "No")])
            for t, pr in zip(("Yes", "No"), d):
                probs[("BTTS", t)] = pr
                if labs.get(t): odds[("BTTS", t)] = labs[t]
        elif mk == "handicap-goals-over" and "total goals" in (mname or "").lower():
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                L = r.get("line")
                if L is None: continue
                side = "Over" if n.startswith("over") else ("Under" if n.startswith("under") else None)
                if side: labs[f"{side} {float(L):g}"] = r["odds"]
            for kv, o in labs.items():
                t = f'Over {kv.split(" ")[1]}' if kv.startswith("Over") else f'Under {kv.split(" ")[1]}'
            keys = list(labs.keys())
            d = oddsx.devig([labs[k] for k in keys])
            for k, pr in zip(keys, d):
                probs[("Total Goals", k)] = pr
                odds[("Total Goals", k)] = labs[k]
        elif mk == "handicap-wdw" and "3-way" in (mname or "").lower().replace("  ", " "):
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                L = r.get("line")
                if L is None: continue
                side = "Home" if n == home_n else ("Away" if n == away_n else None)
                if side and abs(float(L)) == 2.0:
                    labs[f"+2 {side}"] = r["odds"]
            keys = list(labs.keys())
            d = oddsx.devig([labs[k] for k in keys])
            for k, pr in zip(keys, d):
                probs[("Handicap +2", k)] = pr
                odds[("Handicap +2", k)] = labs[k]
        elif mk == "to-win" or mname == "Match Winner":
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                if n == home_n: labs["P1"] = r["odds"]
                elif n == away_n: labs["P2"] = r["odds"]
            d = oddsx.devig([labs.get(t) for t in ("P1", "P2")])
            for t, pr in zip(("P1", "P2"), d):
                probs[("Winner", t)] = pr
                if labs.get(t): odds[("Winner", t)] = labs[t]
        elif mname == "Winner (Incl. Overtime)":
            labs = {}
            for r in rs:
                n = _match.normalize(r["outcome"])
                if n == home_n: labs["P1"] = r["odds"]
                elif n == away_n: labs["P2"] = r["odds"]
            d = oddsx.devig([labs.get(t) for t in ("P1", "P2")])
            for t, pr in zip(("P1", "P2"), d):
                probs[("Winner", t)] = pr
                if labs.get(t): odds[("Winner", t)] = labs[t]
    return probs, odds


def _pawa_markets_to_probs(sport, event_id, home_n, away_n):
    """betPawa markets → (probs, odds): tip-labeled kupitia MKT_ID map."""
    import oddsx
    probs, odds = {}, {}
    try:
        mkts = _markets(event_id)
    except BookieError:
        return probs, odds
    for (sp, market), mid in MKT_ID.items():
        if sp != sport:
            continue
        m = next((x for x in mkts if x.get("marketType", {}).get("id") == mid), None)
        if not m:
            continue
        outs = []
        for row in (m.get("row") or []):
            spec = row.get("specifier") or {}
            for p in (row.get("prices") or []):
                if p.get("suspended") or not p.get("odds"):
                    continue
                outs.append((p.get("name"), p.get("odds"), spec))
        if not outs:
            continue
        if market == "1X2":
            labs = {n: o for (n, o, s) in outs if n in ("1", "X", "2")}
            d = oddsx.devig([labs.get(t) for t in ("1", "X", "2")])
            for t, pr in zip(("1", "X", "2"), d):
                probs[("1X2", t)] = pr
                if labs.get(t): odds[("1X2", t)] = labs[t]
        elif market == "Double Chance":
            labs = {n: o for (n, o, s) in outs if n in ("1X", "X2", "12")}
            d = oddsx.devig([labs.get(t) for t in ("1X", "X2", "12")], total=2.0)  # G2: DC sums→2
            for t, pr in zip(("1X", "X2", "12"), d):
                probs[("Double Chance", t)] = pr
                if labs.get(t): odds[("Double Chance", t)] = labs[t]
        elif market == "Draw No Bet":
            labs = {n: o for (n, o, s) in outs if n in ("1", "2")}
            d = oddsx.devig([labs.get(t) for t in ("1", "2")])
            for t, pr in zip(("1", "2"), d):
                probs[("Draw No Bet", t)] = pr
                if labs.get(t): odds[("Draw No Bet", t)] = labs[t]
        elif market == "BTTS":
            labs = {n: o for (n, o, s) in outs if n in ("Yes", "No")}
            d = oddsx.devig([labs.get(t) for t in ("Yes", "No")])
            for t, pr in zip(("Yes", "No"), d):
                probs[("BTTS", t)] = pr
                if labs.get(t): odds[("BTTS", t)] = labs[t]
        elif market == "Winner":
            labs = {n: o for (n, o, s) in outs if n in ("1", "2")}
            d = oddsx.devig([labs.get(t) for t in ("1", "2")])
            for t, pr in zip(("P1", "P2"), d):
                probs[("Winner", t)] = pr
                if labs.get("1" if t == "P1" else "2"): odds[("Winner", t)] = labs.get("1" if t == "P1" else "2")
        elif market == "Total Goals":
            labs = {}
            for (n, o, s) in outs:
                if s.get("total") is None or n not in ("Over", "Under"):
                    continue
                labs[f"{n} {float(s['total']):g}"] = o
            keys = list(labs.keys())
            d = oddsx.devig([labs[k] for k in keys])
            for k, pr in zip(keys, d):
                probs[("Total Goals", k)] = pr
                odds[("Total Goals", k)] = labs[k]
    return probs, odds


PROVIDER_BUDGET_S = 480      # devig ya bookie: dakika 8 max, kisha model-only kwa zilizobaki
FAIL_BREAK = 5               # makosa mfululizo ya bookie → iachwe kwa run hii


def make_provider(day_iso, log=print):
    """Inarudi callable(rec, sport, sublog) → bk dict ya phase 4.
    Kinga: bookie ikiwa down → haijaribiwi tena; makosa 5 mfululizo → inaachwa; budget dk 8; progress log."""
    import betway as _bw
    st = {"t0": time.time(), "calls": 0, "bw": 0, "pawa": 0, "miss": 0,
          "fail": {"betway": 0, "betpawa": 0}, "off": set(), "budget_hit": False}

    def _progress():
        if st["calls"] % 100 == 0:
            log(f"  [BOOKIE] devig: mechi {st['calls']} · betway {st['bw']} · betPawa {st['pawa']} · "
                f"hazipo {st['miss']} · {int(time.time() - st['t0'])}s")

    def _failed(bk, e):
        st["fail"][bk] += 1
        if st["fail"][bk] >= FAIL_BREAK and bk not in st["off"]:
            st["off"].add(bk)
            log(f"  ⚠ [BOOKIE] {bk}: makosa {FAIL_BREAK} mfululizo ({str(e)[:70]}) — naiacha kwa run hii")

    def provider(rec, sport, sublog=None):
        key = (sport, rec.get("home"), rec.get("away"))
        if key in _PROV_CACHE:
            return _PROV_CACHE[key]
        if time.time() - st["t0"] > PROVIDER_BUDGET_S:
            if not st["budget_hit"]:
                st["budget_hit"] = True
                log(f"  ⚠ [BOOKIE] muda wa devig (dk {PROVIDER_BUDGET_S // 60}) umeisha — mechi zilizobaki: model-only")
            return {"found": False}
        st["calls"] += 1
        _progress()
        home = rec.get("home", ""); away = rec.get("away", "")
        home_n = _match.normalize(home); away_n = _match.normalize(away)
        tm = rec.get("time"); lg = rec.get("league")
        # 1. betway (primary)
        if "betway" not in st["off"]:
            try:
                ix = _bw.day_index(day_iso, log)
                ev, flip = _bw._find_event(ix, sport, home, away, tm, lg, None)
                if ev:
                    if flip:
                        home_n, away_n = away_n, home_n
                    rows = _bw.snapshot_event(ev["id"])
                    probs, odds = _bw_rows_to_probs(rows, home_n, away_n)
                    out = {"found": True, "bookmaker": "betway", "probs": probs, "odds": odds,
                           "event_id": ev["id"]}
                    st["fail"]["betway"] = 0; st["bw"] += 1
                    _PROV_CACHE[key] = out
                    return out
            except Exception as e:  # noqa: BLE001
                if day_iso in getattr(_bw, "_DOWN", {}):
                    st["off"].add("betway")
                else:
                    _failed("betway", e)
        # 2. betPawa (fallback)
        if "betpawa" not in st["off"]:
            try:
                ix = day_index(day_iso, log)
                ev, flip = _find_event(ix, sport, home, away, tm, lg, None)
                if ev:
                    if flip:
                        home_n, away_n = away_n, home_n
                    probs, odds = _pawa_markets_to_probs(sport, ev["id"], home_n, away_n)
                    out = {"found": True, "bookmaker": "betpawa", "probs": probs, "odds": odds,
                           "event_id": ev.get("id")}
                    st["fail"]["betpawa"] = 0; st["pawa"] += 1
                    _PROV_CACHE[key] = out
                    return out
            except Exception as e:  # noqa: BLE001
                if day_iso in _DOWN:
                    st["off"].add("betpawa")
                else:
                    _failed("betpawa", e)
        st["miss"] += 1
        out = {"found": False}
        _PROV_CACHE[key] = out
        return out

    return provider
