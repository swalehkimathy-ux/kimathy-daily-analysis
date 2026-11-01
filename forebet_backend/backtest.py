#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# backtest.py — K96 (Phase 6 · spec 8.2): replay ya siku zilizopita — model-offline (bila bookies)
#   python backtest.py --from 2026-09-01 --to 2026-10-27
import argparse, json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "forebet_picks_app"))
import worker, engine  # noqa: E402


def rec_from_match(m: dict) -> dict:
    """matches table row → engine record (barchi data iliyopatikana ya historical)."""
    p = [m.get("p1"), m.get("px"), m.get("p2")]
    rec = {"home": m["home"], "away": m["away"], "league": m.get("league") or "",
           "status": "Scheduled", "p": p, "ps": (m.get("ps_home") is not None and
           m.get("ps_away") is not None and (m["ps_home"], m["ps_away"]) or None),
           "avg": m.get("avg_total"), "od": None, "url": m.get("url") or "",
           "h2h": m.get("h2h") or "", "hf": [], "af": [], "hp": m.get("pos_home") or "",
           "ap": m.get("pos_away") or "", "rnd": "", "tr": ""}
    return rec


def brier(p, win): return (p - (1.0 if win else 0.0)) ** 2
def logloss(p, win):
    p = min(max(p, 1e-12), 1 - 1e-12)
    return -(win * math.log(p) + (1 - win) * math.log(1 - p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="d0", required=True)
    ap.add_argument("--to", dest="d1", required=True)
    a = ap.parse_args()

    days = worker.sb("GET",
        f"day_cache?day=gte.{a.d0}&day=lte.{a.d1}&select=day&order=day")
    days = [r["day"] for r in (days or [])]
    if not days:
        print("Hakuna day_cache kati ya tarehe hizo.")
        return
    print(f"== BACKTEST: {len(days)} siku ({a.d0} → {a.d1}) · model-only (no bookie devig)")

    total = winsb = 0
    by_market, by_bucket = {}, {}
    bri = llg = 0.0
    for d in days:
        matches = worker.sb("GET", f"matches?day=eq.{d}") or []
        finals = {(m["home"], m["away"]): (m.get("final_home"), m.get("final_away"))
                  for m in matches}
        bysport = {}
        for m in matches:
            if None in (m.get("p1"), m.get("px"), m.get("p2")):
                continue
            bysport.setdefault(m["sport"], []).append(rec_from_match(m))
        if not bysport:
            continue
        front, pool, mn = engine.predict_day(bysport, provider=None, min_conf=80,
                                             log=lambda s: None)
        for p in pool:
            fin = finals.get((p["home"], p["away"]))
            if not fin or fin[0] is None:
                continue
            res = worker.settle_pick(p["market"], p["tip"], fin[0], fin[1])
            if res not in ("win", "loss"):
                continue
            total += 1
            win = res == "win"
            winsb += win
            pm = p.get("p_cal") or (p["conf"] / 100.0)
            bri += brier(pm, win)
            llg += logloss(pm, 1 if win else 0)
            mk = p["market"]
            by_market.setdefault(mk, [0, 0])
            by_market[mk][0] += win
            by_market[mk][1] += 1
            b = min(4, max(0, int(pm * 10 / 2)))           # buckets: 0-0.19..0.8-1.0
            by_bucket.setdefault(b, [0, 0, 0.0])
            by_bucket[b][0] += win
            by_bucket[b][1] += 1
            by_bucket[b][2] += pm

    if not total:
        print("Hakuna picks zilizo-match na finals — kwanza hifadhi finals (settle).")
        return
    print(f"\nKWA JUMLA: picks zilizo-settle: {total} · hit-rate {winsb / total:.1%}")
    print(f"Brier score: {bri / total:.4f} (chini = bora; 0.25 = mbaya sana, 0.10 ≈ nzuri)")
    print(f"Log loss:    {llg / total:.4f}")
    print("\nKwa SOKO:")
    for mk, (w, n) in sorted(by_market.items(), key=lambda x: -x[1][1]):
        print(f"  {mk:14s} {w:3d}/{n:3d} = {w / n:>5.1%}")
    print("\nKwa BUCKET ya uwezekano (predicted vs actual):")
    for b, (w, n, s) in sorted(by_bucket.items()):
        pred = s / n
        act = w / n
        flag = "✓" if abs(pred - act) <= 0.05 else "⚠"
        print(f"  [{b * 20:3d}%–{b * 20 + 20:3d}%] pred={pred:.0%} actual={act:.0%} n={n} {flag}")
    print("\nℹ walk-forward: hakuna leakage (kila siku inatumia data iliyotokea siku hiyo tu).")
    print("  Backtest huyatumia devig ya bookies — historical haijahelmishwa (Phase 3 inaendeza).")


if __name__ == "__main__":
    main()
