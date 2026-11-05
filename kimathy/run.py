"""run.py — mtiririko mzima wa uendeshaji (manual run).

 python -m kimathy.run            → endesha kwa siku ya leo (Tanzania)
 python -m kimathy.run --date 2026-11-05
 python -m kimathy.run --offline  → jaribu bila mtandao (fixtures za majaribio)

Hakuna Supabase. Hakuna GUI. Matokeo: faili moja la .xlsx kwenye folda ya Downloads.
"""
from __future__ import annotations

import argparse
import sys

from . import analyze, candidates, clock, excel, forebet, optimize, tipsters, validate
from .bookies.provider import Provider
from .config import load, resolve_output_folder
from .net import Fetcher
from .normalize import dedupe


def _banner(cfg) -> None:
    print("=" * 78)
    print("  KIMATHY SMART BETTING ENGINE  ·  standalone · hakuna Supabase · hakuna GUI")
    print("=" * 78)


def _now_line(ref) -> str:
    return (f"Saa ya Tanzania (Africa/Dar_es_Salaam): {clock.fmt_tz(ref, with_seconds=True)}  ·  "
            f"Tarehe: {clock.today_tz().isoformat()}")


def run(day: str | None = None, cfg=None, log=print, offline: bool = False,
        fixtures_provider=None) -> dict:
    cfg = cfg or load()
    ref = clock.now_tz()
    day = day or clock.today_tz().isoformat()
    min_min = int(cfg.get("min_minutes_before_kickoff", 60))
    _banner(cfg)
    log(_now_line(ref))
    log(f"Muda wa chini kabla ya kuanza mechi: dakika {min_min}")
    log(f"Combined odds inayotakiwa: "
        f"{cfg.get('accumulator.combined_odds_min')}–{cfg.get('accumulator.combined_odds_max')}")
    log(f"Folda ya matokeo: {resolve_output_folder(cfg)}")

    problems = cfg.validate()
    for p in problems:
        log(f"  ⚠ {p}")

    fetcher = Fetcher.from_config(cfg, log)
    summary: dict = {}

    # ---------------------------------------------------- 1. Forebet (chanzo muhimu)
    log("\n[1/7] FOREBET — chanzo muhimu cha utabiri")
    if offline:
        by_sport, fb_reports = {}, [{"source": "forebet", "ok": False,
                                     "error": "OFFLINE MODE", "records": 0}]
        log("  · hali ya offline — Forebet haijaguswa")
        if fixtures_provider is not None and getattr(fixtures_provider, "records", None):
            by_sport = {}
            for r in fixtures_provider.records:
                by_sport.setdefault(r.get("sport", "football"), []).append(r)
            n = sum(len(v) for v in by_sport.values())
            log(f"  · fixtures za majaribio: rekodi {n}")
    else:
        by_sport, fb_reports = forebet.collect(fetcher, day, cfg, log)
    summary["forebet_reports"] = fb_reports

    # ---------------------------------------------------- 2. uthibitishaji + uchujaji
    log("\n[2/7] UTHIBITISHAJI WA REKODI NA UCHUJAJI WA MUDA")
    stats = validate.ValidationStats()
    eligible: list[dict] = []
    dropped_time = 0
    for sport, recs in by_sport.items():
        for rec in recs:
            ok, probs = validate.validate_record(rec, sport)
            stats.add(ok, probs)
            if not ok:
                continue
            e_ok, why = clock.eligibility(rec.get("kickoff_tz"), rec.get("status"),
                                          reference=ref, min_minutes=min_min,
                                          day=clock.to_tz(ref).date())
            if not e_ok:
                dropped_time += 1
                continue
            eligible.append(rec)
    eligible, removed_dupes = dedupe(eligible)
    eligible = eligible[: int(cfg.get("run.max_events_per_run", 1500))]
    log(f"  {stats.line()}")
    log(f"  zilizotolewa kwa sababu ya muda/hali: {dropped_time}")
    log(f"  marudio yaliyoondolewa: {removed_dupes}")
    log(f"  ✓ mechi zinazostahili: {len(eligible)}")
    summary["validation"] = stats.line()
    summary["eligible_matches"] = len(eligible)
    summary["dropped_by_time_or_status"] = dropped_time
    summary["duplicates_removed"] = removed_dupes

    # ---------------------------------------------------- 3. bookmakers
    log("\n[3/7] BOOKMAKERS — ugunduzi wa masoko na bei halisi")
    if offline:
        provider = fixtures_provider
    else:
        provider = Provider(cfg, log)
        provider.build_index()
        log(f"  · waliopatikana: {provider.available() or 'HAKUNA'}")
        for n, e in provider.down.items():
            log(f"  ✗ {n}: {e}")

    # ---------------------------------------------------- 4. wagombea
    log("\n[4/7] UCHAMBUZI — masoko yote yanayopatikana, mgombea mmoja kwa mechi")
    all_cands: list[dict] = []
    blocked = 0
    no_market = 0
    if provider is None:
        log("  ✗ hakuna bookmaker aliyepatikana — hakuna bei halisi, "
            "kwa hiyo HAKUNA mgombea (hatutumii odds za Forebet kama mbadala)")
    else:
        for i, rec in enumerate(eligible, 1):
            sport = rec.get("sport", "football")
            why = candidates.blocked_reason(rec, sport, cfg)
            if why:
                blocked += 1
                continue
            offers, used = provider.discover_markets(rec)
            if not offers:
                no_market += 1
                continue
            cs = candidates.build_candidates(rec, sport, offers, provider, cfg, log)
            all_cands.extend(cs)
            if i % 100 == 0:
                log(f"    · michezo {i} imeshughulikiwa · wagombea {len(all_cands)}")
    best, rejected = candidates.best_per_match(all_cands)
    log(f"  zilizozuiwa (friendly/youth/women/hali): {blocked}")
    log(f"  mechi bila soko la bookmaker: {no_market}")
    log(f"  wagombea wote: {len(all_cands)} · baada ya 'moja kwa mechi': {len(best)}")
    summary["blocked_matches"] = blocked
    summary["matches_without_bookmaker_market"] = no_market
    summary["total_candidates"] = len(all_cands)
    summary["best_candidates_one_per_match"] = len(best)
    summary["bookmakers"] = (provider.report() if provider else {})

    # ---------------------------------------------------- 5. tipsters (maoni tu)
    log("\n[5/7] VYANZO VYA UTABIRI VYA WAHUSIKA WENGINE (maoni tu — si takwimu)")
    if offline:
        opinions, t_reports = [], [{"source": "tipsters", "ok": False,
                                    "error": "OFFLINE MODE", "records": 0}]
        log("  · hali ya offline — tovuti za utabiri hazijaguswa")
    else:
        opinions, t_reports = tipsters.collect(fetcher, eligible, cfg, log)
    log(f"  {tipsters.note_independence(t_reports)}")
    summary["tipster_reports"] = t_reports
    summary["opinions_collected"] = len(opinions)

    # ---------------------------------------------------- 6. accumulator
    log("\n[6/7] KIBORESHAJI CHA ACCUMULATOR")
    acc, reasons = optimize.build(best, cfg, log)
    if acc is None:
        acc = optimize.no_qualified(reasons, best, cfg)
        for r in reasons:
            log(f"  · {r}")
        log("  ✗ NO QUALIFIED ACCUMULATOR — hakuna dau lililolazimishwa")

    # ---------------------------------------------------- 7. uhakiki wa mwisho
    if acc.status == "QUALIFIED ACCUMULATOR" and cfg.get("run.reverify_before_export", True):
        log("\n[7/7] UHAKIKI WA MWISHO KABLA YA EXPORT")
        from . import verify as _v
        kept, dropped = _v.reverify(acc, provider, cfg, log, reference=ref,
                                    day=clock.to_tz(ref).date())
        if dropped:
            log(f"  · miguu {len(dropped)} imeondolewa — kiboreshaji kinaendeshwa tena")
            remaining = [c for c in best if (c.get("home"), c.get("away")) in
                         {(k.get("home"), k.get("away")) for k in kept}]
            acc2, reasons2 = optimize.build(remaining or kept, cfg, log)
            acc = acc2 or optimize.no_qualified(reasons2 or ["miguu iliyobaki haitoshi"],
                                                kept, cfg)
        dups = _v.check_duplicates(acc.legs)
        if dups:
            log(f"  ✗ mechi zilizorudiwa zimegunduliwa: {dups}")
        summary["reverified_legs"] = acc.legs_count()
    else:
        log("\n[7/7] UHAKIKI WA MWISHO — umerukwa (hakuna accumulator)")

    # ---------------------------------------------------- Excel
    meta = {
        "day": day, "stamp": clock.stamp_for_filename(ref),
        "run_time": clock.fmt_tz(ref), "generated_at": clock.now_tz().isoformat(timespec="seconds"),
        "summary": summary,
    }
    log("\n[EXPORT] Faili la Excel")
    path = excel.write(acc, cfg, meta, log)

    print("\n" + "=" * 78)
    print(f"  HALI: {acc.status}")
    if acc.status == "QUALIFIED ACCUMULATOR":
        print(f"  Miguu {acc.legs_count()} · combined odds {acc.total_odds} · "
              f"uwezekano wa pamoja {acc.joint_prob:.1%} · hatari {acc.risk:.1%}")
    else:
        for r in acc.reasons[:6]:
            print(f"    - {r}")
    print(f"  Faili: {path}")
    print("  Hiki ni chombo cha uchambuzi — si dhamana ya ushindi. Beti kwa uwajibikaji.")
    print("=" * 78)
    return {"status": acc.status, "accumulator": acc, "excel": str(path), "summary": summary}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KIMATHY SMART BETTING ENGINE")
    ap.add_argument("--date", help="tarehe ya uchambuzi (YYYY-MM-DD); chaguo-msingi ni leo")
    ap.add_argument("--config", help="njia ya config.json mbadala")
    ap.add_argument("--offline", action="store_true", help="jaribu bila mtandao")
    a = ap.parse_args(argv)
    cfg = load(path=a.config) if a.config else load()
    try:
        res = run(day=a.date, cfg=cfg, offline=a.offline)
    except KeyboardInterrupt:
        print("\nImesimamishwa na mtumiaji.")
        return 130
    return 0 if res["status"] in ("QUALIFIED ACCUMULATOR", "NO QUALIFIED ACCUMULATOR") else 2


if __name__ == "__main__":
    sys.exit(main())
