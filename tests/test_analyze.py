"""Majaribio: modeli ya uwezekano (Sehemu 10) — hakuna kuvimba uwezekano."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import analyze
from kimathy.bookies.base import devig, overround
from tests._fixtures import rec


def main():
    # 1. G1/F1: Double Chance ni p1+px HASWA — hakuna kuongeza pointi
    #    Liverpool 57/30/13 → 1X = 0.87 (SI 0.98 kama injini ya zamani)
    r = rec("Liverpool", "Chelsea", 57, 30, 13, avg=3.0)
    m, info = analyze.model_markets(r, "football")
    assert abs(m[("double_chance", "1X", None)] - 0.87) < 1e-9, m[("double_chance", "1X", None)]
    assert abs(m[("double_chance", "X2", None)] - 0.43) < 1e-9
    assert abs(m[("double_chance", "12", None)] - 0.70) < 1e-9

    # 2. Draw No Bet = p_fav / (p1+p2)
    assert abs(m[("draw_no_bet", "1", None)] - 0.57 / 0.70) < 1e-9

    # 3. Over+Under = 1 kwa kila mstari
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        s = m[("total_goals", "Over", line)] + m[("total_goals", "Under", line)]
        assert abs(s - 1.0) < 1e-6, (line, s)
    s = m[("btts", "Yes", None)] + m[("btts", "No", None)]
    assert abs(s - 1.0) < 1e-6

    # 4. Bayern 76/15/9, avg 3.7 → 1X = 0.91 (kama K96_ENGINE_RULES F1)
    r2 = rec("Bayern Munich", "Union Berlin", 76, 15, 9, avg=3.7)
    m2, info2 = analyze.model_markets(r2, "football")
    assert abs(m2[("double_chance", "1X", None)] - 0.91) < 1e-9
    assert info2["fit_err"] < 0.05, info2

    # 5. avg haipo → masoko ya magoli YAMEZIMWA (F3)
    r3 = rec("Torino", "Udinese", 36, 33, 31, avg=None)
    m3, info3 = analyze.model_markets(r3, "football")
    assert not any(k[0] in ("total_goals", "btts", "team_goals") for k in m3), list(m3)[:5]
    assert "ZIMWA" in info3.get("note", ""), info3

    # 6. ushahidi: goal_expectation haipo
    ev = analyze.evidence_of(r3, "football")
    assert "probs_1x2" in ev and "goal_expectation" not in ev

    # 7. devig: jumla = 1
    d = devig([1.5, 3.8, 6.0])
    assert abs(sum(d) - 1.0) < 1e-9, d
    assert abs(devig([1.5, 3.8, 6.0], total=2.0)[0] - 2 * d[0]) < 1e-9

    # 8. overround ni chanya kwa bei halisi za bookmaker
    orv = overround([1.85, 3.60, 4.40])
    assert orv is not None and 0.0 < orv < 0.15, orv

    # 9. decimal odds SI uwezekano: implied ya 2.00 = 0.50 (kabla ya margin)
    assert abs(1 / 2.00 - 0.50) < 1e-9

    # 10. kikapu: modeli ya margin inarudisha uwezekano wa mshindi
    rb = rec("Real Madrid", "Zalgiris", 84, 0, 16, avg=165, sport="basketball")
    mb, infob = analyze.model_markets(rb, "basketball")
    assert abs(mb[("winner", "P1", None)] - 0.84) < 1e-9
    assert mb[("handicap", "Home", 9.5)] > mb[("winner", "P1", None)]

    # 11. tenisi: lopsided 91/9 → Over games inaweza kuwepo lakini T5 ni kazi ya kuchuja;
    #     hapa tunathibitisha tu kwamba modeli inarudisha P1 = 0.91
    rt = rec("J. Sinner", "Q. Qualifier", 91, 0, 9, avg=19.5, sport="tennis", best_of=3)
    mt, infot = analyze.model_markets(rt, "tennis")
    assert abs(mt[("winner", "P1", None)] - 0.91) < 1e-9
    assert infot["best_of"] == 3

    # 12. best_of haipo → handicap/total za tenisi ZIMEZIMWA
    rt2 = rec("A. Player", "B. Player", 55, 0, 45, avg=22.5, sport="tennis")
    mt2, info12 = analyze.model_markets(rt2, "tennis")
    assert not any(k[0] in ("games_handicap", "total_games") for k in mt2)

    # 13. blend: p_market haipo → model_only, na adhabu inaongezeka
    p_a, used_mkt, only = analyze.blend(0.80, None, 0.5, [], 0.01, 0.03, 0.95)
    p_b, used_mkt2, only2 = analyze.blend(0.80, 0.80, 0.5, [], 0.01, 0.03, 0.95)
    assert only and not only2
    assert p_a < p_b, (p_a, p_b)          # model pekee → uaminifu mdogo

    # 14. flags ZINAPUNGUZA tu, na cap inazingatiwa
    p_c, _, _ = analyze.blend(0.99, 0.99, 0.5, ["a", "b", "c", "d"], 0.01, 0.03, 0.95)
    assert p_c <= 0.95 + 1e-9
    p_d, _, _ = analyze.blend(0.90, 0.90, 0.5, [], 0.01, 0.03, 0.95)
    p_e, _, _ = analyze.blend(0.90, 0.90, 0.5, ["a", "b"], 0.01, 0.03, 0.95)
    assert p_e < p_d, (p_d, p_e)

    # 15. fit_lambdas inarudisha jumla ya magoli iliyoombwa
    lh, la, err = analyze.fit_lambdas(76, 15, 9, 3.7)
    assert abs((lh + la) - 3.7) < 0.05, (lh, la)

    print("✓ analyze: ALL GREEN (15 makundi — hakuna kuvimba uwezekano, devig, michezo 3)")


if __name__ == "__main__":
    main()
