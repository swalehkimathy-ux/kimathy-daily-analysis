#!/usr/bin/env python3
"""Phase 3 tests: oddsx devig + combine + disagree flags — bila mtandao."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oddsx

# 1. devig: margin imeondoka
p = oddsx.devig([1.66, 4.10, 3.95])
assert p and abs(sum(p) - 1.0) < 1e-9, f"devig lazima isum 1.0: {p}"
assert abs(p[0] - 0.548) < 0.01, f"P(home) ≈ 54.8%: {p}"
assert p[0] < 1/1.66, "margin removal → prob < yadedari"

# 2. odds mbovu → None sem wapi
p = oddsx.devig([1.5, None, "bad"])
assert p[0] == 1.0 and p[1] is None and p[2] is None

assert oddsx.devig([None, None]) == [None, None]

# 3. combine: average mbili bookies
a = oddsx.devig([1.66, 4.10, 3.95])            # betway
b = oddsx.devig([1.84, 3.60, 4.30])            # pawa
c = oddsx.combine_probs([(a, 0.5), (b, 0.5)])
assert c and abs(sum(c) - 1.0) < 1e-9, f"combined sum: {c}"
assert abs(c[0] - (a[0]*0.5 + b[0]*0.5)) < 1e-9

# 4. single_source: bookie moja tu
c2 = oddsx.combine_probs([(a, 0.5), (None, 0.5)])
assert c2 == a

# 5. disagree flag: >6 pts mugi
flags = oddsx.disagree_flag([[0.70, 0.30], [0.60, 0.40]])
assert flags == [True, True]
flags2 = oddsx.disagree_flag([[0.70, 0.30], [0.66, 0.34]])
assert flags2 == [False, False]

print("✓ oddsx tests: ALL GREEN (devig + combine + disagree)")
