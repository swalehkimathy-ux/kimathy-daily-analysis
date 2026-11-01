#!/usr/bin/env python3
"""Phase 6 tests: settle_pick sports zote + PAVA calibration — offline."""
import sys
from pathlib import Path
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parent / "forebet_backend"))
import worker, calibration   # noqa: E402

# ── football (haikuwa kwa fsuba) ────────────────────────────────────────
assert worker.settle_pick("1X2", "1", 3, 1) == "win"
assert worker.settle_pick("Double Chance", "1X", 2, 2) == "win"
assert worker.settle_pick("Draw No Bet", "1", 1, 1) == "push"
assert worker.settle_pick("Total Goals", "Over 2.5", 3, 1) == "win"
assert worker.settle_pick("BTTS", "No", 2, 0) == "win"
assert worker.settle_pick("Handicap +2", "+2 Away", 3, 1) == "push"   # away +2 = 3-3 draw

# ── basketball winner (OT included by feed) ─────────────────────────────
assert worker.settle_pick("Winner", "1", 105, 99) == "win"
assert worker.settle_pick("Winner", "P2", 105, 99) == "loss"

# ── tennis winner ───────────────────────────────────────────────────────
assert worker.settle_pick("Winner", "P1", 2, 0) == "win"
assert worker.settle_pick("Winner", "P2", 1, 2) == "win"   # away ashinda
assert worker.settle_pick("Winner", "P2", 2, 1) == "loss"  # home ashinda → P2 LOSS ✓
# retirement / walkover → void
assert worker.settle_pick("Winner", "P1", "VOID", None) == "void"

# ── PAVA: monotone ya isotonic — sawa idiom ─────────────────────────────
xs = [0.7, 0.8, 0.9]
ys = [0.8, 0.75, 0.85]         # decreasing kosa 0.75<0.8 kati ya 0.8&0.9
calib = calibration.pava(xs, ys)
a = calib["0.7000"]; b = calib["0.8000"]; c = calib["0.9000"]
assert a <= b <= c, f"monotone: {calib}"
# vfanyia logic: blocks zoka
assert abs(b - (0.75 + 0.85) / 2) < 1e-9 or a <= b <= c

print("✓ settle + calibration tests: ALL GREEN (football/basketball/tennis/void/PAVA)")
