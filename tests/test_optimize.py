"""Majaribio: kiboreshaji cha accumulator (Sehemu 12) — 1.80–2.00 pamoja na mipaka."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import optimize
from kimathy.config import Config

BASE = {"accumulator": {"combined_odds_min": 1.80, "combined_odds_max": 2.00,
                        "max_legs": 12, "force_legs": None, "correlation_haircut": 0.98}}


def leg(home, away, odds, p, league="Ligi X"):
    return {"home": home, "away": away, "match": f"{home} vs {away}", "odds": odds,
            "p_engine": p, "league": league, "sport": "football", "market_name": "Total Goals",
            "selection": "Over 1.5", "bookmaker": "betpawa"}


def main():
    cfg = Config(dict(BASE))
    log = lambda *a: None

    # 1. mchanganyiko unaopata 1.80–2.00
    cands = [leg("A", "B", 1.30, 0.90, "L1"), leg("C", "D", 1.45, 0.85, "L2"),
             leg("E", "F", 1.10, 0.95, "L3"), leg("G", "H", 1.60, 0.75, "L4")]
    acc, reasons = optimize.build(cands, cfg, log)
    assert acc is not None, reasons
    assert 1.80 <= acc.total_odds <= 2.00, acc.total_odds
    assert acc.status == "QUALIFIED ACCUMULATOR"

    # 2. miguu miwili kutoka mechi MOJA haipatikani kamwe
    keys = [(l["home"], l["away"]) for l in acc.legs]
    assert len(keys) == len(set(keys)), keys

    # 3. uwezekano wa pamoja = Πp × haircut^pairs
    prod = 1.0
    for l in acc.legs:
        prod *= l["p_engine"]
    expected = round(prod * (0.98 ** acc.correlation_pairs), 6)
    assert abs(acc.joint_prob - expected) < 1e-6, (acc.joint_prob, expected)
    assert acc.risk == round(1 - acc.joint_prob, 6)

    # 4. mipaka inahesabika: 1.80 haswa na 2.00 haswa zinakubaliwa
    acc_lo, _ = optimize.build([leg("A", "B", 1.20, 0.9), leg("C", "D", 1.50, 0.8)], cfg, log)
    assert acc_lo is not None and abs(acc_lo.total_odds - 1.80) < 1e-6, acc_lo
    acc_hi, _ = optimize.build([leg("A", "B", 1.60, 0.9), leg("C", "D", 1.25, 0.8)], cfg, log)
    assert acc_hi is not None and abs(acc_hi.total_odds - 2.00) < 1e-6, acc_hi

    # 5. nje ya safu kidogo → hakuna accumulator (hatulazimishi)
    acc_out, r5 = optimize.build([leg("A", "B", 1.20, 0.9), leg("C", "D", 1.49, 0.8)], cfg, log)
    assert acc_out is None and r5, "inapaswa kukataa 1.788"

    # 6. NO QUALIFIED — hakuna mchanganyiko wowote unaofikia 1.80
    weak = [leg("A", "B", 1.05, 0.95), leg("C", "D", 1.10, 0.95), leg("E", "F", 1.15, 0.9)]
    acc6, r6 = optimize.build(weak, cfg, log)
    assert acc6 is None and any("hakuna mchanganyiko" in x for x in r6), r6
    noq = optimize.no_qualified(r6, weak, cfg)
    assert noq.status == "NO QUALIFIED ACCUMULATOR"
    assert noq.legs == [] and noq.total_odds == 0.0
    assert any("hakuna mchanganyiko" in x for x in noq.reasons)

    # 7. hakuna mgombea → NO QUALIFIED (si mchanganyiko wa kubuni)
    acc7, r7 = optimize.build([], cfg, log)
    assert acc7 is None and any("hakuna mgombea" in x for x in r7), r7

    # 8. idadi ya miguu inabadilika (si lazima) — mguu 1, 3 na 4 zote zinawezekana
    a1, _ = optimize.build([leg("Solo", "Team", 1.90, 0.80)], cfg, log)
    assert a1 is not None and a1.legs_count() == 1, a1
    varied = [leg("A", "a", 1.30, 0.88, "L1"), leg("B", "b", 1.25, 0.88, "L2"),
              leg("C", "c", 1.20, 0.88, "L3"), leg("D", "d", 1.15, 0.88, "L4"),
              leg("E", "e", 1.10, 0.88, "L5"), leg("F", "f", 1.05, 0.88, "L6")]
    av, _ = optimize.build(varied, cfg, log)
    assert av is not None and av.legs_count() >= 3, av
    assert 1.80 <= av.total_odds <= 2.00

    # 9. correlation haircut inatumika kwa ligi moja
    corr = [leg("A", "B", 1.30, 0.90, "Ligi Moja"), leg("C", "D", 1.40, 0.85, "Ligi Moja")]
    ac, _ = optimize.build(corr, cfg, log)
    assert ac is not None and ac.correlation_pairs == 1, ac.correlation_pairs
    assert abs(ac.joint_prob - 0.90 * 0.85 * 0.98) < 1e-6, ac.joint_prob

    # 10. deterministic — matokeo mamoja kwa pembejeo moja
    a1, _ = optimize.build(cands, cfg, log)
    a2, _ = optimize.build(cands, cfg, log)
    assert a1.total_odds == a2.total_odds and a1.joint_prob == a2.joint_prob

    # 11. EV ya accumulator = P*O - 1
    assert abs(acc.ev - (acc.joint_prob * acc.total_odds - 1)) < 1e-3, acc.ev

    print(f"✓ optimize: ALL GREEN (11 makundi · mfano: miguu {acc.legs_count()} "
          f"@ {acc.total_odds} · joint {acc.joint_prob:.1%})")


if __name__ == "__main__":
    main()
