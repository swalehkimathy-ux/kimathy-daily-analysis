#!/usr/bin/env python3
"""Phase 1 unit tests: validation.py — bila mtandao (fixtures tu)."""
import datetime, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validation as V

D = datetime.datetime(2026, 10, 27, 20, 0)

def base(**kw):
    r = {"home": "Liverpool", "away": "Chelsea", "league": "EPL", "status": "Scheduled",
         "probs": [57, 30, 13], "odds": [1.65, 4.0, 5.0], "ps": (3, 1), "avg": 3.2, "dt": D}
    r.update(kw)
    return r

ok, pr = V.validate_record(base(), "football")
assert ok and pr == [], f"clean record lazima ipite: {pr}"

ok, pr = V.validate_record(base(away="Liverpool"), "football")
assert not ok and "home==away" in pr

ok, pr = V.validate_record(base(home="Man <i>"), "football")
assert not ok and any("html" in x for x in pr)

ok, pr = V.validate_record(base(probs=[60, 30, 30]), "football")
assert not ok and any("probs_sum" in x for x in pr)

ok, pr = V.validate_record(base(probs=[50, 25, 25], odds=[9.0, 1.2, 4.0]), "football")
assert not ok and "odds_conflict" in pr              # ishara ya uaminifu, si drop-phrase halisi

ok, pr = V.validate_record(base(avg=15.0), "football")
assert not ok and any("avg_nje" in x for x in pr)

ok, pr = V.validate_record(base(status="FT"), "football")
assert not ok and any("not_pre_match" in x for x in pr)

ok, pr = V.validate_record(base(league=""), "football")
assert not ok and "league_tupu" in pr

ok, pr = V.validate_record({"home": "Lakers", "away": "Bulls", "league": "NBA",
                            "probs": [88, 12], "avg": 201.5, "status": "Scheduled"},
                           "basketball")
assert ok, f"basketball sane record: {pr}"

# Basketball projected scores are normally >15 and must not be rejected by
# football's small-goals bound.
ok, pr = V.validate_record({"home": "Lakers", "away": "Bulls", "league": "NBA",
                            "probs": [58, 42], "ps": [112, 106], "avg": 218.0,
                            "status": "Scheduled"}, "basketball")
assert ok, f"basketball projected score: {pr}"

ok, pr = V.validate_record({"home": "Lakers", "away": "Bulls", "league": "NBA",
                            "probs": [88, 12], "avg": 99.0, "status": "Scheduled"},
                           "basketball")
assert not ok and any("avg_nje" in x for x in pr)

s = V.ValidationStats()
s.add(True, []); s.add(False, ["probs_sum_120", "home:team_tupu"]); s.add(False, ["league_tupu"])
assert "1/3" in s.line() and "probs_sum=1" in s.line()

print("✓ validation tests: ALL GREEN (12 asserts)")
