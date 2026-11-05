"""Majaribio: wagombea — soko moja bora kwa mechi, bei halisi tu, data mahususi."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import candidates, markets
from kimathy.bookies.base import Offer
from kimathy.config import Config
from tests._fixtures import FixtureProvider, football_offers, rec

CFG = Config({
    "leg_filters": {"leg_odds_min": 1.05, "leg_odds_max": 3.50, "min_probability": 0.50,
                    "block_friendlies": True, "block_youth_and_women": True,
                    "max_flags_before_drop": 6},
    "probability": {"weight_model": 0.5, "uncalibrated_cap": 0.95},
})


def main():
    r1 = rec("Team Alpha", "Team Beta", 57, 30, 13, avg=3.0, league="Ligi A")
    r2 = rec("Team Gamma", "Team Delta", 36, 33, 31, avg=2.1, league="Ligi B")
    prov = FixtureProvider({
        "Team Alpha|Team Beta": football_offers("e1"),
        "Team Gamma|Team Delta": football_offers("e2"),
    })

    # 1. block list
    rf = rec("Real Madrid", "Al Nassr", 70, 20, 10, avg=3.0, league="Club Friendlies")
    assert candidates.blocked_reason(rf, "football", CFG) == "mechi_ya_kirafiki"
    rw = rec("Lyon W", "PSG W", 60, 25, 15, avg=3.0, league="Division 1 Feminine")
    assert candidates.blocked_reason(rw, "football", CFG) is not None
    rt = rec("A. Player", "B. Player", 55, 0, 45, avg=22, sport="tennis", best_of=3)
    assert candidates.blocked_reason(rt, "tennis", CFG) is None, "mchezaji 'B.' asizuiwe"

    # 2. wagombea wanapatikana na wana bei halisi
    offers, _ = prov.discover_markets(r1)
    cs = candidates.build_candidates(r1, "football", offers, prov, CFG, log=lambda *a: None)
    assert cs, "hakuna mgombea yeyote"
    for c in cs:
        assert c["odds"] is not None and 1.05 <= c["odds"] <= 3.50, c
        assert c["bookmaker"] in ("betpawa", "betway"), c
        assert c["odds_source"], "asili ya bei ni lazima"
        assert c["calibrated"] is False, "bila historia lazima iwe estimated"

    # 3. soko lisilo na bei ya bookmaker HALITUMIKI (hatutumii odds za Forebet)
    empty_prov = FixtureProvider({})
    cs_none = candidates.build_candidates(r1, "football", [], empty_prov, CFG, log=lambda *a: None)
    assert cs_none == [], cs_none

    # 4. soko bila data mahususi halitolewi (kona/kadi/madhambi/player props)
    ev = set()
    for key in ("corners", "cards", "fouls", "headed_goals", "player_shots",
                "halftime_result"):
        md = markets.ALL_MARKETS[key]
        ok, why = markets.eligibility(md, {"probs_1x2", "goal_expectation", "goal_split"})
        assert not ok and "data_inakosekana" in why, (key, why)
        assert not markets.discoverable(md), key

    # 5. masoko yenye data yanastahili
    for key in ("1x2", "double_chance", "draw_no_bet", "total_goals", "btts"):
        md = markets.ALL_MARKETS[key]
        ok, why = markets.eligibility(md, {"probs_1x2", "goal_expectation", "goal_split"})
        assert ok, (key, why)

    # 6. mgombea MOJA kwa kila mechi
    all_c = []
    for r in (r1, r2):
        o, _ = prov.discover_markets(r)
        all_c.extend(candidates.build_candidates(r, "football", o, prov, CFG, log=lambda *a: None))
    best, rejected = candidates.best_per_match(all_c)
    assert len(best) == len({(c["home"], c["away"]) for c in best}), "mechi imerudiwa!"
    assert len(best) == 2, [b["match"] for b in best]
    # mgombea bora ndiye mwenye uwezekano mkubwa zaidi kwa mechi yake
    for b in best:
        same = [c for c in all_c if (c["home"], c["away"]) == (b["home"], b["away"])]
        assert b["p_engine"] == max(c["p_engine"] for c in same), (b["match"], same)

    # 7. EV = p*odds - 1
    for c in cs:
        assert abs(c["ev"] - (c["p_engine"] * c["odds"] - 1)) < 1e-3, c

    # 8. mechi ya kirafiki haipati mgombea yeyote
    assert candidates.blocked_reason(rf, "football", CFG) is not None

    print(f"✓ candidates: ALL GREEN (8 makundi · wagombea {len(cs)} kwa mechi 1 · "
          f"moja kwa mechi imethibitishwa)")


if __name__ == "__main__":
    main()
