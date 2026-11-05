"""live_smoke.py — JARIBIO LA DATA HAI (si sehemu ya majaribio ya kawaida).

 python tests/live_smoke.py

KINACHOFANYWA: kinatumia matukio HALISI kutoka betPawa TZ ya leo, kisha
kinaendesha njia halisi ya injini: ulinganishaji → masoko → devig → wagombea →
kiboreshaji → Excel.

⚠ MUHIMU KWA UAMINIFU: Forebet HAIFIKIKI kutoka mazingira ya majaribio
(IP ya datacenter → HTTP 403). Kwa hiyo `probs` za mechi hazitoki Forebet;
zimekokotolewa kutoka bei za 1X2 za betPawa yenyewe (devig). Hii SI data ya
Forebet na matokeo HAYAFASILI kama uchambuzi halisi — ni jaribio la kuonyesha
kwamba msimbo unafanya kazi dhidi ya data hai ya bookmaker.

Uendeshaji halisi kwenye PC yako utatumia Forebet kama chanzo muhimu.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import candidates, clock, excel, optimize, validate
from kimathy.bookies.base import devig
from kimathy.bookies.provider import Provider
from tests._fixtures import merged_config



def main() -> int:
    tmp = tempfile.mkdtemp(prefix="kimathy_live_")
    cfg = merged_config({
        "min_minutes_before_kickoff": 60, "sports": ["football"],
        "accumulator": {"combined_odds_min": 1.80, "combined_odds_max": 2.00, "max_legs": 12},
        "leg_filters": {"leg_odds_min": 1.05, "leg_odds_max": 3.50, "min_probability": 0.60,
                        "max_flags_before_drop": 6},
        "probability": {"weight_model": 0.5, "uncalibrated_cap": 0.95},
        "output": {"folder": tmp, "filename_prefix": "KIMATHY_LIVE_SMOKE",
                   "save_raw_captures": False},
        "sources": {"tipsters": {}},
    })
    day = clock.today_tz().isoformat()
    print("=" * 76)
    print(f"  JARIBIO LA DATA HAI — betPawa TZ · tarehe {day} · "
          f"saa {clock.fmt_tz(clock.now_tz(), True)}")
    print("=" * 76)

    prov = Provider(cfg, log=lambda m: print(f"  {m}"))
    prov.build_index()
    if "betpawa_tz" not in prov.available():
        print("\n✗ betPawa haifikiki kutoka hapa — jaribio la data hai haliwezi kuendelea.")
        print(f"  sababu: {prov.down.get('betpawa_tz')}")
        return 2
    print(f"\n✓ matukio ya leo kutoka betPawa: {len(prov.index['betpawa_tz'])}")

    # --- rekodi kutoka matukio halisi (probs kutoka 1X2 ya betPawa, SI Forebet) ---
    min_min = int(cfg.get("min_minutes_before_kickoff", 60))
    ref = clock.now_tz()
    records, built = [], 0
    for ev in prov.index["betpawa_tz"][:60]:
        if built >= 25:
            break
        offers = prov.snapshot("betpawa_tz", ev["id"])
        one_x_two = [o for o in offers if o.market_name == "1X2 - FT" and o.usable
                     and o.line is None]
        by_name = {o.outcome: float(o.odds) for o in one_x_two}
        if not all(k in by_name for k in ("1", "X", "2")):
            continue
        dp = devig([by_name["1"], by_name["X"], by_name["2"]])
        if any(v is None for v in dp):
            continue
        rec = {
            "event_id": f"live:{ev['id']}", "sport": "football",
            "league": ev.get("league") or "", "home": ev.get("home") or "",
            "away": ev.get("away") or "", "kickoff_tz": ev.get("kickoff_tz"),
            "status": "Scheduled",
            "probs": {"1": round(dp[0] * 100), "X": round(dp[1] * 100), "2": round(dp[2] * 100)},
            "predicted_score": None, "avg": None, "odds_1x2": None,
            "home_form": [], "away_form": [], "avg_h": None, "avg_a": None, "best_of": None,
            "source": "betpawa-1x2-devig (SI FOREBET)",
            "source_url": f"https://www.betpawa.co.tz/api/sportsbook/v4/events/{ev['id']}",
            "retrieved_at": clock.now_tz().isoformat(timespec="seconds"), "raw": {},
        }
        ok, _ = validate.validate_record(rec, "football")
        if not ok:
            continue
        e_ok, _ = clock.eligibility(rec["kickoff_tz"], rec["status"], reference=ref,
                                    min_minutes=min_min, day=ref.date())
        if not e_ok:
            continue
        records.append(rec)
        built += 1

    print(f"✓ rekodi zilizotumika kwa jaribio: {len(records)}")
    if not records:
        print("  hakuna mechi inayostahili kwa sasa (muda/hali) — jaribu tena baadaye.")
        return 0

    # --- njia halisi: wagombea ---
    all_cands = []
    markets_seen: set[str] = set()
    for rec in records:
        offers, _used = prov.discover_markets(rec)
        if not offers:
            continue
        for o in offers:
            markets_seen.add(o.market_name)
        cs = candidates.build_candidates(rec, "football", offers, prov, cfg, log=lambda *a: None)
        all_cands.extend(cs)
    best, _ = candidates.best_per_match(all_cands)

    print(f"\n✓ aina za masoko zilizogunduliwa kwenye bookmaker: {len(markets_seen)}")
    print(f"✓ wagombea wote (wana bei halisi): {len(all_cands)}")
    print(f"✓ baada ya 'mgombea mmoja kwa mechi': {len(best)}")
    if all_cands:
        by_m: dict[str, int] = {}
        for c in all_cands:
            by_m[c["market_name"]] = by_m.get(c["market_name"], 0) + 1
        print("  masoko yaliyochambuliwa (wagombea):")
        for k in sorted(by_m, key=lambda x: -by_m[x]):
            print(f"     {k[:44]:44s} {by_m[k]}")

    acc, reasons = optimize.build(best, cfg, log=lambda *a: None)
    if acc is None:
        acc = optimize.no_qualified(reasons, best, cfg)
    print(f"\nHALI: {acc.status}")
    if acc.status == "QUALIFIED ACCUMULATOR":
        print(f"  miguu {acc.legs_count()} · odds {acc.total_odds} · "
              f"joint {acc.joint_prob:.1%} · risk {acc.risk:.1%} · EV {acc.ev:+.3f}")
        for l in acc.legs:
            print(f"    - {l['match'][:40]:40s} | {l['market_name'][:26]:26s} "
                  f"{str(l.get('line') or ''):6s} {l['selection'][:12]:12s} "
                  f"@ {l['odds']} (p={l['p_engine']:.1%})")
    else:
        for r in acc.reasons[:5]:
            print(f"    - {r}")

    meta = {"day": day, "stamp": clock.stamp_for_filename(ref), "run_time": clock.fmt_tz(ref),
            "generated_at": clock.now_tz().isoformat(timespec="seconds"),
            "summary": {"JARIBIO_LA_DATA_HAI": "betPawa pekee — Forebet haikupatikana (403)",
                        "eligible_matches": len(records),
                        "market_types_discovered": len(markets_seen),
                        "total_candidates": len(all_cands)}}
    path = excel.write(acc, cfg, meta, log=lambda m: print(f"  {m}"))
    print(f"\nFaili: {path}")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
