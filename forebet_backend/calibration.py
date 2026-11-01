#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# calibration.py — K96 (Phase 6 · spec 8.3): isotonic fit (PAVA) juu ya settled picks
#   python calibration.py            → refit + kuandika forebet_picks_app/data/calibration.json
import argparse, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import worker  # noqa: E402

DATA_JSON = Path(__file__).resolve().parent.parent / "forebet_picks_app" / "data" / "calibration.json"


def pava(xs, ys):
    """Pool Adjacent Violators Algorithm — mono increasing-decreasing map."""
    # sorted by xs already
    levels = list(ys)
    wts = [1.0] * len(ys)
    blocks = [[i, i] for i in range(len(ys))]                  # [start, end]
    while True:
        bad = -1
        for i in range(len(blocks) - 1):
            l0 = sum(ys[blocks[i][0]:blocks[i][1] + 1]) / (blocks[i][1] - blocks[i][0] + 1)
            l1 = sum(ys[blocks[i + 1][0]:blocks[i + 1][1] + 1]) / (blocks[i + 1][1] - blocks[i + 1][0] + 1)
            if l0 > l1:
                bad = i
                break
        if bad < 0:
            break
        blocks[bad] = [blocks[bad][0], blocks[bad + 1][1]]
        del blocks[bad + 1]
    vals = {}
    for a, b in blocks:
        lvl = sum(ys[a:b + 1]) / (b - a + 1)
        for i in range(a, b + 1):
            vals[f"{xs[i]:.4f}"] = round(lvl, 4)
    return vals


def main(min_n=300):
    rows = worker.sb("GET", "picks?result=in.(win,loss)&p_cal=not.is.null&select=p_cal,result")
    rows = rows or []
    n = len(rows)
    print(f"== CALIBRATION: settled picks zilizopo: {n}")
    if n < min_n:
        print(f"   ⚠ bado kidogo (<{min_n}) — calibration TO SAMA: identity inatumika. "
              f"Premier-league ukichapusha ujumbe wazi UI.")
        if DATA_JSON.exists():
            DATA_JSON.unlink()
            print("   (calibration.json ya zamani imefutwa)")
        return
    pts = sorted((float(r["p_cal"]), 1.0 if r["result"] == "win" else 0.0) for r in rows)
    # bucket ndogo kwanza (step 0.01) → PAVA
    xs, ys = [], []
    acc = accs = 0.0
    for p6, w in pts:
        acc += w
        accs += 1
        xs.append(p6)
        ys.append(w / 1)  # per-observation
    # per-bucket mean value (0.01 width)
    bxs, bys = [], []
    for b in range(0, 100):
        seg = [y for x, y in zip(xs, ys) if b / 100 <= x < (b + 1) / 100]
        if seg:
            bxs.append((b + 0.5) / 100)
            bys.append(sum(seg) / len(seg))
    calib = pava(bxs, bys)
    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON.write_text(json.dumps({"n": n, "buckets": calib}, indent=1), encoding="utf-8")
    print(f"   ✓ calibration.json imehifadhiwa: {len(calib)} anchors (n={n})")
    # ukaguzi: avg |pred − actual| kwa buckets kuu
    dev = sum(abs(bys[i] - calib[f"{bxs[i]:.4f}"]) for i in range(len(bxs))) / max(1, len(bxs))
    print(f"   mean |pred−actual| baada ya fit: {dev:.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=300)
    a = ap.parse_args()
    main(a.min)
