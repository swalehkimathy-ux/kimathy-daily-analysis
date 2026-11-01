#!/usr/bin/env python3
"""Phase 5 tests: slip.py DP builder — bila mtandao (fixtures)."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import slip, config

def leg(home, odds, p, lg="EPL"):
    return {"home": home, "away": f"v{home}", "match": f"{home} vs v{home}", "league": lg,
            "market": "1X2", "tip": "1", "bk_odds": odds, "p_cal": p, "time": "20:00"}

LEGS = [leg(f"T{i}", o, p) for i, (o, p) in enumerate([
    (1.22, 0.90), (1.30, 0.88), (1.15, 0.92), (1.45, 0.80),
    (1.60, 0.78), (2.00, 0.70), (1.10, 0.94), (1.35, 0.85)])]

# ── 1. default: odds lazima ziwe ndani ya range ──────────────────────────
S = slip.build_slips(LEGS, 5, lambda s: None)
assert S, "slips lazima zipatikane"
for s in S:
    assert config.DEFAULTS["SLIP_ODDS_MIN"] - 0.05 <= s["total_odds"] <= config.DEFAULTS["SLIP_ODDS_MAX"] + 0.05, s
    assert s["label"] in ("SAFEST", "BALANCED", "HIGHER_ODDS", "RISK_KIDOGOWO", "ALT_4", "ALT_5")
    # joint P = product ya p (× correlation haircut)
    prod = 1.0
    for l in s["legs"]:
        prod *= l["p_cal"]
    assert s["joint_prob"] <= prod + 1e-9, "correlation haircut haifai kuzisaaaa"
    assert abs(s["ev"] - (s["joint_prob"] * s["total_odds"] - 1)) < 1e-3

# ── 2. determinism ────────────────────────────────────────────────────────
S2 = slip.build_slips(list(LEGS), 5, lambda s: None)
assert [ (s["label"], s["total_odds"]) for s in S ] == [ (s["label"], s["total_odds"]) for s in S2 ]

# ── 3. labels: SAFEST ni ya joint_prob ya juu ─────────────────────────────
assert S[0]["label"] == "SAFEST"
assert S[0]["joint_prob"] == max(x["joint_prob"] for x in S)

# ── 4. FORCE_LEGS=10: legs 8 tu → naamax: 8 legs tu zipo (≤) ─────────────
config.set("FORCE_LEGS", 8)
try:
    S3 = slip.build_slips(LEGS, 3, lambda s: None)
    assert all(s["legs_n"] == 8 for s in S3)
finally:
    config.set("FORCE_LEGS", None)

# ── 5. no-duplicates kwa match ────────────────────────────────────────────
dup = [leg("A", 1.2, 0.9), leg("A", 1.5, 0.7), leg("B", 1.4, 0.8)]
S4 = slip.build_slips(dup, 3, lambda s: None)
for s in S4:
    homes = [l["home"] for l in s["legs"]]
    assert len(homes) == len(set(homes))

# ── 6. legs bila bk_odds → haziingiwi ────────────────────────────────────
nb = [{"home": "X", "away": "Y", "match": "X vs Y", "league": "EPL", "market": "1X2",
       "tip": "1", "bk_odds": None, "p_cal": 0.9, "time": "20:00"}]
S5 = slip.build_slips(nb, 3, lambda s: None)
assert S5 == [], "leg isiyo-verified hairuhusiwi"

# ── 7. empty input handled ────────────────────────────────────────────────
assert slip.build_slips([], 3, lambda s: None) == []

# ── 8. copy text ina ujumbe wa elimu ─────────────────────────────────────
txt = slip.slip_copy_text(S)
assert "unapungua" in txt and "SAFEST" in txt

print(f"✓ slip tests: ALL GREEN (8 groups) · SAFEST: {S[0]['legs_n']} legs @ {S[0]['total_odds']} "
      f"(joint {S[0]['joint_prob']:.1%})")
