"""excel.py — faili la matokeo `.xlsx` (Sehemu 14).

Sheria:
  * jina la kipekee kwa kila uendeshaji; faili la awali HALIFUTWI wala kuandikwa upya;
  * accumulator ya mwisho PEKEE — si orodha ya mechi zilizokataliwa;
  * kama hakuna inayostahili: faili bado linatolewa, likieleza wazi kwa nini;
  * URLs zinazobonyezeka; hakuna lebo ya "uwezekano uliothibitishwa".
"""
from __future__ import annotations

from pathlib import Path

from . import clock
from .config import resolve_output_folder

HDR = ["#", "Mchezo (Sport)", "Mechi / Fixture", "Muda wa kuanza (Africa/Dar_es_Salaam)",
       "Ligi / Mashindano", "Bookmaker / Chanzo", "Jina kamili la soko",
       "Chaguo / Matokeo kamili", "Decimal odds (zilizothibitishwa)",
       "Makadirio ya uwezekano ya injini (estimated)", "Chanzo / Rejea ya odds",
       "Muhuri wa muda wa kuzalishwa"]

TITLE_FILL = "1F4E78"
BAND_FILL = "EAF2FB"
STATUS_FILL_OK = "E2EFDA"
STATUS_FILL_BAD = "FCE4E4"


def _unique_path(folder: Path, prefix: str, stamp: str) -> Path:
    p = folder / f"{prefix}_{stamp}.xlsx"
    n = 2
    while p.exists():                      # kamwe kubatilisha faili la awali
        p = folder / f"{prefix}_{stamp}_v{n}.xlsx"
        n += 1
    return p


def write(accumulator, cfg, meta: dict, log=print) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    folder = resolve_output_folder(cfg)
    stamp = meta.get("stamp") or clock.stamp_for_filename()
    prefix = str(cfg.get("output.filename_prefix", "KIMATHY_SMART_BETTING"))
    path = _unique_path(folder, prefix, stamp)

    wb = Workbook()
    ws = wb.active
    ws.title = "ACCUMULATOR"

    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor=TITLE_FILL)
    band = PatternFill("solid", fgColor=BAND_FILL)

    status = accumulator.status if accumulator else "NO QUALIFIED ACCUMULATOR"
    ok = status == "QUALIFIED ACCUMULATOR"
    fill = PatternFill("solid", fgColor=STATUS_FILL_OK if ok else STATUS_FILL_BAD)

    # --- kichwa ---
    ws.append([f"KIMATHY SMART BETTING ENGINE — {meta.get('day','')} · "
               f"saa ya uendeshaji {meta.get('run_time','')} (Africa/Dar_es_Salaam)"])
    ws.cell(row=1, column=1).font = Font(bold=True, size=14, color=TITLE_FILL)
    ws.append([f"HALI YA UENDESHAJI:  {status}"])
    ws.cell(row=2, column=1).font = Font(bold=True, size=12,
                                         color="2E7D32" if ok else "C62828")
    ws.cell(row=2, column=1).fill = fill
    if ok:
        ws.append([f"Combined odds: {accumulator.total_odds}   ·   "
                   f"Uwezekano wa pamoja (estimated): {accumulator.joint_prob:.1%}   ·   "
                   f"Hatari: {accumulator.risk:.1%}   ·   EV: {accumulator.ev:+.3f}   ·   "
                   f"Miguu: {accumulator.legs_count()}"])
    else:
        ws.append(["Hakuna dau lililotolewa. Matokeo ya 'hakuna dau' ni bora kuliko "
                   "accumulator dhaifu au ya kubuni."])
    ws.cell(row=3, column=1).font = Font(bold=True, size=11)

    if accumulator and accumulator.correlation_pairs and ok:
        ws.append([f"ONYO LA UTEGEMEZI: jozi {accumulator.correlation_pairs} za correlation "
                   f"zimepunguzwa kwa haircut; uhuru kamili wa miguu ni DHANA, si ukweli."])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="9C5700")
    if ok and not accumulator.legs[0].get("calibrated", False):
        ws.append(["Uwezekano unaonyeshwa ni MAKADIRIO (estimated) — haujasawazishwa "
                   "(calibrated) kwa historia ya matokeo."])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="9C5700")
    ws.append([])

    # --- jedwali la accumulator ---
    start = ws.max_row + 1
    ws.append(HDR)
    for c in range(1, len(HDR) + 1):
        cell = ws.cell(row=start, column=c)
        cell.fill = hdr_fill
        cell.font = Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    if ok:
        for i, leg in enumerate(accumulator.legs, 1):
            p = leg.get("p_engine")
            row = [i, _sport_label(leg.get("sport", "")), leg.get("match", ""),
                   clock.fmt_tz(leg.get("kickoff_tz")), leg.get("league", ""),
                   leg.get("bookmaker", ""),
                   _market_full(leg), _selection_full(leg),
                   float(leg.get("odds") or 0),
                   (f"{p:.1%} (estimated)" if isinstance(p, (int, float)) else "haipatikani"),
                   leg.get("odds_source", ""), meta.get("generated_at", "")]
            ws.append(row)
            r = ws.max_row
            for c in range(1, len(HDR) + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=(c in (7, 8, 11)))
                if i % 2 == 0:
                    cell.fill = band
            link = ws.cell(row=r, column=11)
            if link.value:
                link.hyperlink = str(link.value)
                link.font = Font(color="0563C1", underline="single")
            fb = leg.get("forebet_url")
            if fb:
                mc = ws.cell(row=r, column=3)
                mc.hyperlink = str(fb)
                mc.font = Font(color="0563C1", underline="single")
        # jumla
        ws.append(["", "JUMLA", f"Miguu {accumulator.legs_count()}", "", "", "",
                   "COMBINED DECIMAL ODDS", "", accumulator.total_odds,
                   f"{accumulator.joint_prob:.1%} (estimated)", "", meta.get("generated_at", "")])
        r = ws.max_row
        for c in range(1, len(HDR) + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(bold=True, color=TITLE_FILL)
            cell.border = border
            cell.fill = PatternFill("solid", fgColor="DDEBF7")
    else:
        ws.append(["-", "Hakuna accumulator inayostahili leo.", "", "", "", "", "", "",
                   "", "", "", meta.get("generated_at", "")])
        for c in range(1, len(HDR) + 1):
            ws.cell(row=ws.max_row, column=c).border = border

    # --- sababu ---
    ws.append([])
    ws.append(["SABABU / MAELEZO"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=11, color=TITLE_FILL)
    for line in (accumulator.reasons if accumulator else ["hakuna maelezo"]):
        ws.append([f"• {line}"])
    ws.append([])
    ws.append(["MUHTASARI WA UENDESHAJI"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=11, color=TITLE_FILL)
    for k, v in (meta.get("summary") or {}).items():
        ws.append([str(k), str(v)])

    widths = [4, 13, 34, 22, 24, 13, 30, 26, 15, 22, 46, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{start + 1}"

    ws2 = wb.create_sheet("TAHADHARI")
    warn = [
        "Hiki ni chombo cha uchambuzi na kusaidia maamuzi — SI dhamana ya ushindi.",
        "Uwezekano ulioonyeshwa ni makadirio (estimated), haujasawazishwa kwa historia ya matokeo.",
        "Combined odds ya 1.80–2.00 ni KIKWAZO cha utekelezaji, si uthibitisho kuwa mchanganyiko ni mzuri.",
        "Kila mguu unaoongezwa hupunguza uwezekano wa pamoja na kuongeza margin ya bookmaker.",
        "Uhuru (independence) wa miguu ni dhana ya kihisabati, si ukweli uliopimwa.",
        "Kamari ina hatari ya kupoteza pesa. Weka mipaka ya fedha na ubeti kwa uwajibikaji.",
    ]
    for line in warn:
        ws2.append([line])
        ws2.cell(row=ws2.max_row, column=1).font = Font(size=11)
    ws2.column_dimensions["A"].width = 110

    wb.save(path)
    log(f"  ✓ Excel imehifadhiwa: {path}")
    return path


def _sport_label(s: str) -> str:
    return {"football": "⚽ Mpira wa miguu", "basketball": "🏀 Kikapu",
            "tennis": "🎾 Tenisi"}.get(s, s)


def _market_full(leg: dict) -> str:
    name = leg.get("market_name") or leg.get("market_name_engine") or ""
    line = leg.get("line")
    return f"{name} {line:g}" if isinstance(line, (int, float)) else name


def _selection_full(leg: dict) -> str:
    sb = leg.get("selection_bookmaker")
    return f"{leg.get('selection','')} ({sb})" if sb and sb != leg.get("selection") \
        else str(leg.get("selection", ""))
