#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOREBET PICKS — msingi (Forebet = chanzo cha data PEKEE).
Scraper: mechi ZOTE za siku (football / basketball / tennis).
SMART ENGINE (engine.py): uhakiki wa kujitegemea + uteuzi wa soko lenye confidence
  (football: 1X2 / Double Chance / Total Goals / Handicap+2 · basketball/tennis: Winner pekee)
  · ligi/timu za watoto na wanawake zinaondolewa · odds ni mipaka ya config tu · picks 0–10, sports-balanced.
Output: Excel + @PICKS JSON + copy text. HAKUNA gate ya ziada / betslip / betpawa.
"""
import datetime as _dt
import json
import sys
from pathlib import Path

for _f in (sys.stdout, sys.stderr):            # cp1252 consoles (Windows) — kamwe usibomoke
    try:
        _f.reconfigure(errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
import os, sys as _sys
for _d in (str(HERE), str(Path.cwd())):
    if _d and _d not in _sys.path:
        _sys.path.insert(0, _d)

import scraper
import engine

SPORTS_ORDER = ["football", "basketball", "tennis"]
SPORT_LABEL = {"football": "Football", "basketball": "Basketball", "tennis": "Tennis"}


def _pred_score(ps):
    return "{}-{}".format(*ps) if ps and None not in ps else ""


def run(day: str, min_prob: int = 80, do_enrich: bool = True, log=print, records_by_sport=None,
        provider=None):
    """Msingi: collect (sports zote) → engine.analyze_day → Excel + @PICKS.
    records_by_sport: ikitolewa tayari (mf., kutoka cache ya Supabase), hatucollect kwenye mtandao tena.
    provider: PHASE 4 callable(rec, sport, sublog) → bookie probs (devig). None = model-only (offline)."""
    engine.MIN_CONF = int(min_prob)
    engine.RELAX_STEPS = [min_prob, max(60, min_prob - 5), max(55, min_prob - 10)]

    if records_by_sport is None:
        records_by_sport, totals = {}, {}
        for sport in SPORTS_ORDER:
            log(f"=== [{sport.upper()}] ===")
            try:
                recs = scraper.collect(sport, day, do_enrich, log)
            except Exception as e:              # noqa: BLE001
                log(f"!!! [{sport}] imeshindika: {e}")
                recs = []
            records_by_sport[sport] = recs
            totals[sport] = len(recs)
            log(f"  [{sport}] mechi zilizopatikana: {len(recs)}")
    else:
        totals = {s: len(v) for s, v in records_by_sport.items()}
        log(f"=== [CACHE] tunatumia records tayari zilizopokelewa: {totals} ===")

    # ── PHASE 1: ukaguzi (validation) — rekodi mbovu huondolewa + kuhesabiwa ──
    try:
        import validation as _v
        stats = _v.ValidationStats()
        clean = {}
        for sport, recs in records_by_sport.items():
            keep = []
            for rec in recs:
                ok, probs = _v.validate_record(rec, sport)
                stats.add(ok, probs)
                if ok:
                    keep.append(rec)
                else:
                    hard = [p for p in probs if not p.startswith(("odds_conflict", "status_mpya"))]
                    if not hard:                     # low-trust flags husalia lakini zina-onekana
                        rec["_flags"] = probs
                        keep.append(rec)
            clean[sport] = keep
        records_by_sport = clean
        log(stats.line())
    except Exception as e:  # noqa: BLE001
        log(f"  [validation] imeshindika ({str(e)[:80]}) — tunatumia records vilevile")

    log("=== [SMART ENGINE] uchambuzi wa siku ===")
    # ── SMART ENGINE v0.3 (Phase 4): probability halisi + bookie blend ──
    front, pool, chosen = engine.predict_day(records_by_sport, provider=provider,
                                             min_conf=min_prob, log=log)
    used_min = round(chosen * 100)
    if used_min != min_prob:
        log(f"  [engine] siku nyeti — confidence iliyotumika imepungua hadi {used_min}%")
    picks = []
    for p in front:
        p = dict(p)
        p.setdefault("pred_score", "")
        p["why"] = p.get("why") or []
        p["reason"] = p.get("decision", "")
        picks.append(p)
    log(f"  [{engine.ENGINE_TAG}] picks za mwisho: {len(picks)} (no fixed count; max 10, sports-balanced, reserve={len(pool)})")

    xlsx = _excel(day, picks, used_min, log)
    payload = {"day": day, "min_prob": used_min, "engine": engine.ENGINE_TAG,
               "excel": str(xlsx) if xlsx else None,
               "counts": totals, "total_picks": len(picks), "picks": picks,
               "pool": pool, "pool_size": len(pool)}
    log("@PICKS " + json.dumps(payload, ensure_ascii=False))
    return payload


def _excel(day, picks, used_min, log):
    if not picks:
        log("!! hakuna picks zilizopita — hakuna Excel")
        return None
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    wb.remove(wb.active)
    hdr_fill = PatternFill("solid", fgColor="1F4E78")
    band = PatternFill("solid", fgColor="EAF2FB")
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header = ["#", "League", "Time (EAT)", "Home / P1", "Away / P2", "Status",
              "Market", "TIP", "Engine Conf %", "Forebet Prob %", "Odd (favorite)",
              "Pred Score", "Avg", "SABABU (kwa nini engine ikachagua)", "Match URL"]
    widths = [5, 26, 9, 24, 24, 11, 14, 10, 9, 9, 9, 9, 8, 60, 40]
    for sport in SPORTS_ORDER:
        rows = []
        for p in picks:
            if p["sport"] != sport:
                continue
            rows.append([p["rank"], p["league"], p["time"], p["home"], p["away"], p["status"],
                         p["market"], p["tip"], p["conf"], p["forebet"], p["odd"] or "",
                         p["pred_score"], p.get("avg") or "",
                         "; ".join(p.get("why") or [])[:300], p["url"]])
        ws = wb.create_sheet(SPORT_LABEL[sport][:31])
        ws.append([f"{SPORT_LABEL[sport].upper()} — {day} · SMART ENGINE · conf ≥ {used_min}% · Forebet data pekee"])
        ws.cell(row=1, column=1).font = Font(bold=True, size=13, color="1F4E78")
        ws.append(header)
        for c in range(1, len(header) + 1):
            cell = ws.cell(row=2, column=c)
            cell.fill = hdr_fill
            cell.font = Font(color="FFFFFF", bold=True, size=10)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        for i, rrow in enumerate(rows, 1):
            ws.append(list(rrow))
            for c in range(1, len(header) + 1):
                cell = ws.cell(row=ws.max_row, column=c)
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=(c == 14))
                if i % 2 == 0:
                    cell.fill = band
        if not rows:
            ws.append(["-", f"Hakuna {SPORT_LABEL[sport]} iliyofikisha siku hii."] + [""] * (len(header) - 2))
        for ci, wd in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(ci)].width = wd
        ws.freeze_panes = "A3"
    out = HERE / f"Forebet_Picks_{day}_min{used_min}.xlsx"
    wb.save(out)
    log("Saved: " + str(out))
    return out


def copy_text(payload):
    ICON = {"football": "⚽", "basketball": "🏀", "tennis": "🎾"}
    L = [f"📅 SMART PICKS (conf ≥ {payload['min_prob']}%) — {payload['day']}", ""]
    for sport in SPORTS_ORDER:
        sp = [p for p in payload["picks"] if p["sport"] == sport]
        L.append(f"══ {ICON[sport]} {SPORT_LABEL[sport].upper()} ({len(sp)}) ══")
        for p in sp:
            extra = f" · PS {p['pred_score']}" if p["pred_score"] else ""
            L.append(f"#{p['rank']} [{p['time']}] {p['match']} — {p['market']}: {p['tip']} "
                     f"— {p['conf']}% (FB {p['forebet']}%){extra}")
        L.append("")
    L.append("Chanzo cha data: FOREBET pekee · Maamuzi: Smart Engine yetu. Bet responsibly.")
    return "\n".join(L)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="FOREBET PICKS — msingi (engine smart)")
    ap.add_argument("--date", default=None)
    ap.add_argument("--min-prob", type=int, default=80)
    ap.add_argument("--no-enrich", action="store_true",
                    help="ache miss enriching H2H/avg (haraka zaidi, uhakiki mdogo)")
    a = ap.parse_args()
    day = a.date or _dt.date.today().isoformat()
    try:
        payload = run(day, min_prob=a.min_prob, do_enrich=not a.no_enrich)
        print(copy_text(payload))
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("@PICKS " + json.dumps({"day": day, "min_prob": a.min_prob,
                                      "engine": "smart-engine v0.2 (forebet-data only)",
                                      "error": str(e)[:150], "counts": {}, "total_picks": 0, "picks": []}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
