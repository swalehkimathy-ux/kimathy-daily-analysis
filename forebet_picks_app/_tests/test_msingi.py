#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E synthetic test ya msingi: scraper (mock) → SMART ENGINE v0.3 → Excel/copy/@PICKS.
Ime-UPDATED (spec §0.3) kwa Phase 4:
  · Liverpool 57/30/13 → DC 1X p_model = 0.87 (siyo 0.98!)
  · Friendly (Real Madrid) inabagiwa KABISA (E6/5.6)
  · Hapana 85%+ asivyolikiwa_Diki (40/32/28) bila bookies
"""
import datetime, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scraper  # noqa: E402
import picks    # noqa: E402
import engine   # noqa: E402

D = datetime.datetime(2026, 10, 27, 20, 0)

def mk(sport, p, od, home, away, league, ps=None, avg=None, hf=None, af=None,
       hp="", ap="", h2h="", rnd="", tr=""):
    return {"dt": D, "league": league, "home": home, "away": away, "status": "Scheduled",
            "p": p, "ps": ps, "avg": avg, "od": od, "url": f"u/{home}", "h2h": h2h,
            "hf": hf or [], "af": af or [], "hp": hp, "ap": ap, "rnd": rnd, "tr": tr,
            "kelly": None, "id": "x", "rnd_num": rnd}

DATA = {
    "football": [
        mk("football", [57, 30, 13], [1.35, 5.20, 8.00], "Liverpool", "Tottenham",
           "England Premier League", ps=[3, 1], avg=3.2,
           hf=["W", "W", "W", "W", "D"], af=["L", "D", "L", "L", "D"], hp="2", ap="9",
           h2h="10 meetings: Liverpool 6W - 2D - 2L vs Tottenham."),
        mk("football", [92, 6, 2], [1.15, 7.0, 15.0], "Bayern", "Bochum",
           "Germany Bundesliga", ps=[3, 0], avg=3.0,
           hf=["W", "W", "W", "D", "W"], af=["L", "L", "D", "L", "W"], hp="1", ap="15"),
        mk("football", [95, 4, 1], [1.10, 9.0, 20.0], "Chelsea W", "Everton W",
           "England WSL Women", ps=[4, 0], avg=4.2),
        mk("football", [90, 7, 3], [1.25, 6.0, 11.0], "Real Madrid", "Al Nassr",
           "World Club Friendlies", ps=[2, 0], avg=2.2),
        mk("football", [40, 32, 28], [2.60, 3.30, 2.80], "Man City", "Chelsea",
           "England Premier League", ps=[2, 1], avg=3.4),
        mk("football", [45, 33, 22], None, "Genoa", "Torino", "Italy Serie A", ps=[1, 0], avg=1.8),
    ],
    "basketball": [
        mk("basketball", [88, None, 12], [1.22, 4.80], "Lakers", "Bulls", "NBA", avg=201.5),
        mk("basketball", [60, None, 40], [1.60, 2.40], "Nets", "Heat", "NBA", avg=190.0),
    ],
    "tennis": [
        mk("tennis", [81, None, 19], [1.30, 3.40], "Swiatek", "Gauff", "WTA Finals", avg=22.4),
    ],
}

scraper.collect = lambda sport, day, do_enrich, log: DATA[sport]

logs = []
payload = picks.run("2026-10-27", min_prob=80, do_enrich=False, log=lambda s: logs.append(s))
by_home = {p["home"]: p for p in payload["picks"]}
print(json.dumps({h: [p["market"], p["tip"], p["conf"]] for h, p in by_home.items()},
                 indent=1, ensure_ascii=False))

# ── msingi checks ───────────────────────────────────────────────────────
assert payload.get("pool") is not None, "pool inatekerzeebwa (auto-replace)"

liv = by_home.get("Liverpool"); assert liv, "Liverpool haikuchaguliwa!"
# spec 5.7: DC 1X lazima iwe 0.87 kwa probability model (kabla ilikuwa 0.98 = uwongo)
pm_liv, _ = engine.model_markets(
    next(r for r in DATA["football"] if r["home"] == "Liverpool"), "football")   # v1.0 API
dc_pm = pm_liv[("Double Chance", "1X")]
assert abs(dc_pm - 0.87) < 1e-9, f"spec 5.7: Liverpool DC 1X p_model = 0.87 → {dc_pm}"
assert liv["conf"] <= 95, f"confidence inaamini 95 zidi — umashara: {liv['conf']}"

bay = by_home.get("Bayern")
if bay:  # 92% favorite → bookie-less mode: sólo TG legs yenye fair-odds ≥1.15 hunusa;  <80% adaptive-ela phupu
    assert 75 <= bay["conf"] <= 95, bay
mc = by_home.get("Man City")
# Hii fixture has projected score 2-1 + avg 3.4, so a goals-market tip is
# allowed even though the 1X2 itself is not strong.
assert mc is None or mc["market"] in ("Total Goals", "Team Goals", "BTTS"), mc

db = {p["home"] for p in payload["picks"]}
assert "Chelsea W" not in db, "women match ILIPITA — makosa!"
assert "Real Madrid" not in db, "FRIENDLY lazima i-block kabisa (spec E6/5.6)!"
assert len(payload["picks"]) <= 10
swa = by_home.get("Swiatek"); assert swa and swa["sport"] == "tennis", "tennis tip"

# injuries: DC baada ya diversity-cap hazijazia yote
from collections import Counter
mkts = Counter(p["market"] for p in payload["picks"])
assert mkts.get("Double Chance", 0) <= 3, mkts

print("\nALL ASSERTS GREEN ✓  (smart-engine v1.0 · spec §5 updated)")
