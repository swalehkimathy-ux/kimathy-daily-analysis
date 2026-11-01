#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K96 PICKS — PC WORKER (kila kitu shuleni la Forebet → Supabase).

MODE 3:
  run    --date YYYY-MM-DD [--force] [--no-enrich]
         siku ikiwa tayari kwenye cache → engine inatumia data za database bila
         kurudia Forebet (kama ulivyoomba: "same data mpaka siku ipinduke").
  settle [--date YYYY-MM-DD]
         itafute final scores za mechi zilizochezwa → picks.result = win/loss/push.
         (football: Forebet feed inapea results. Basketball/tennis: kama hazionekani
          kwa leo, huwa 'unknown' baada ya siku 2.)
  status → totals + engine_stats (hit-rate) kutoka Supabase.

Hakuna dependencies mpya — inatumia urllib ya Python pekee (PostgREST).
"""
import argparse
import datetime as _dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
_EXE_DIR = BACKEND
_BUNDLE = BACKEND
if getattr(sys, "frozen", False):                       # ekukimbiza ndani ya .exe (PyInstaller)
    _EXE_DIR = Path(sys.executable).resolve().parent    # .env.local/Excel → karibu na .exe
    BACKEND = _EXE_DIR
    _BUNDLE = Path(sys._MEIPASS)                        # resources za ndani ya exe
    for _d in (_BUNDLE / "forebet_picks_app", _BUNDLE):
        if _d.exists() and str(_d) not in sys.path:
            sys.path.insert(0, str(_d))
APP = _BUNDLE / "forebet_picks_app" if getattr(sys, "frozen", False) else BACKEND.parent / "forebet_picks_app"
sys.path.insert(0, str(APP))

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(errors="replace")
    except Exception:
        pass

ENGINE_VERSION = "smart-engine v1.0 (rules)"
_EAT = _dt.timezone(_dt.timedelta(hours=3))


def today_eat():
    """Leo kwa saa za Afrika Mashariki (EAT) — haitegemei timezone ya PC."""
    return _dt.datetime.now(_EAT).date()


# ──────────────────────────────────────────────────────────────────────────
# .env.local — ufunguo wa Supabase
# ──────────────────────────────────────────────────────────────────────────
def _jwt_claims(tok: str):
    """Decode payload ya JWT bila verify-seza sirri (SB keys ni JWT za kawaida)."""
    import base64, json as _json
    try:
        _, pay, _ = tok.split(".")
        pay += "=" * (-len(pay) % 4)
        return _json.loads(base64.urlsafe_b64decode(pay))
    except Exception:
        return {}


def load_env():
    cand = [BACKEND / ".env.local", _BUNDLE / ".env.local"]
    env_path = next((p for p in cand if p.exists()), None)
    if env_path is None:
        print(f"!!! .env.local haipo — weka .env.local karibu na K96_PICKS.exe: {BACKEND}")
        raise SystemExit(2)
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")

    url = (env.get("SUPABASE_URL") or "").strip().rstrip("/")
    srv = (env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    anon = (env.get("SUPABASE_ANON_KEY") or "").strip()

    import re as _re
    m = _re.fullmatch(r"https://([a-z0-9]{20})\.supabase\.co", url)
    if not m:
        print("!!! SUPABASE_URL imeandikwa vibaya (mfano: https://abcdef...supabase.co) — kanda .env.local")
        raise SystemExit(2)
    proj_ref = m.group(1)

    for label, tok, role in (("SERVICE_ROLE", srv, "service_role"), ("ANON", anon, "anon")):
        if not tok.startswith("ey"):
            print(f"!!! SUPABASE_{label}_KEY haizuri/hakuna — kanda .env.local")
            raise SystemExit(2)
        c = _jwt_claims(tok)
        if c.get("role") != role:
            print(f"!!! SUPABASE_{label}_KEY siyo role '{role}' (role: {c.get('role', '?')}) — kanda .env.local")
            raise SystemExit(2)
        if c.get("ref") and c["ref"] != proj_ref:
            print(f"!!! {label}_KEY ni ya project NYINGINE ({c['ref']}) · URL ni ya ({proj_ref}) — kanda keys za project moja")
            raise SystemExit(2)
        exp = c.get("exp")
        if exp and exp < __import__("time").time():
            print(f"!!! SUPABASE_{label}_KEY ime-KWISHA muda wake — tengeneza key mpya Supabase dashboard")
            raise SystemExit(2)
    env["SUPABASE_URL"] = url
    return env


ENV = None
def _env():
    global ENV
    if ENV is None:
        ENV = load_env()
    return ENV


def sb(method, path, body=None, prefer=None, timeout=30):
    """Mini PostgREST client (urllib pekee — hakuna pip mpya)."""
    e = _env()
    url = e["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + path
    headers = {
        "apikey": e["SUPABASE_SERVICE_ROLE_KEY"],
        "Authorization": f"Bearer {e['SUPABASE_SERVICE_ROLE_KEY']}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as he:
        msg = he.read().decode("utf-8")[:300]
        raise RuntimeError(f"Supabase {method} {path} → HTTP {he.code}: {msg}")


def sb_all(path, page=1000):
    """GET yenye kurasa — Supabase inarudisha mistari 1000 tu kwa ombi moja (mechi 1300+ kwa siku)."""
    out, off = [], 0
    sep = "&" if "?" in path else "?"
    while True:
        chunk = sb("GET", f"{path}{sep}limit={page}&offset={off}") or []
        out.extend(chunk)
        if len(chunk) < page:
            return out
        off += page


class _Resp:
    """Jibu dogo la mtindo wa `requests` (status_code / json() / text)."""
    def __init__(self, code, text):
        self.status_code, self.text = code, text

    def json(self):
        return json.loads(self.text) if self.text else None


def sb_resp(method, path, body=None, prefer=None, timeout=30):
    """Kama sb(), lakini HAIRUSHI error ya HTTP — inarudisha _Resp yenye status_code."""
    try:
        out = sb(method, path, body=body, prefer=prefer, timeout=timeout)
        return _Resp(200, json.dumps(out) if out is not None else "")
    except RuntimeError as e:
        import re as _re
        m = _re.search(r"HTTP (\d{3})", str(e))
        return _Resp(int(m.group(1)) if m else 599, str(e))


# ──────────────────────────────────────────────────────────────────────────
# DB row ↔ record ya engine
# ──────────────────────────────────────────────────────────────────────────
FINISHED_PREFIX = ("FT", "AET", "AP", "Pen.", "Fin", "Ended", "After")


def _final_of(r):
    """(fh, fa) kama mechi imeisha na score ipo, vinginevyo (None, None)."""
    st_ = (r.get("st") or r.get("status") or "").strip()
    sc = r.get("sc")
    if sc and len(sc) == 2 and None not in sc and st_.startswith(FINISHED_PREFIX):
        try:
            return int(sc[0]), int(sc[1])
        except (TypeError, ValueError):
            pass
    return None, None


def rec_to_row(day, sport, r):
    p = (r.get("p") or [None, None, None]) + [None, None, None]
    ps = (r.get("ps") or [None, None]) + [None, None]
    od = (r.get("od") or [])
    return {
        "day": day, "sport": sport, "league": r.get("league", ""),
        "time_eat": r["dt"].strftime("%H:%M") if r.get("dt") else None,
        "home": r.get("home", ""), "away": r.get("away", ""),
        "p1": p[0], "px": p[1], "p2": p[2],
        "ps_home": ps[0], "ps_away": ps[1],
        "avg_total": r.get("avg"), "kelly": r.get("kelly"),
        "odd1": od[0] if len(od) > 0 else None,
        "oddx": od[1] if len(od) > 1 else None,
        "odd2": od[2] if len(od) > 2 else (od[1] if len(od) == 2 else None),
        "status": r.get("st") or r.get("status") or "Scheduled",
        "final_home": _final_of(r)[0], "final_away": _final_of(r)[1],
        "h2h": r.get("h2h") or None, "avg_h": r.get("avg_h"), "avg_a": r.get("avg_a"),
        "form_home": r.get("hf") or None, "form_away": r.get("af") or None,
        "home_pos": r.get("hp") or None, "away_pos": r.get("ap") or None,
        "url": r.get("url") or None,
        "raw": {k: v for k, v in r.items() if k not in ("dt",)},   # backup — dt haifanyi JSON
    }


def row_to_rec(row):
    """Kurejesha row → record ya engine (kwa cache-mode)."""
    day_s = row["day"]  # "YYYY-MM-DD"
    hh, mm = 12, 0
    if row.get("time_eat"):
        try:
            hh, mm = map(int, row["time_eat"].split(":"))
        except Exception:
            pass
    dt = _dt.datetime.fromisoformat(day_s).replace(hour=hh, minute=mm)
    od = [x for x in (row.get("odd1"), row.get("oddx"), row.get("odd2")) if x is not None]
    if row.get("sport") != "football" and len(od) == 3 and row.get("oddx") is None:
        od = [od[0], od[-1]]
    return {
        "dt": dt, "league": row.get("league", ""), "home": row.get("home", ""),
        "away": row.get("away", ""), "status": row.get("status") or "",
        "st": row.get("status") or "Scheduled",
        "sc": ([row["final_home"], row["final_away"]]
               if row.get("final_home") is not None and row.get("final_away") is not None else None),
        "p": [row.get("p1"), row.get("px"), row.get("p2")],
        "ps": [row.get("ps_home"), row.get("ps_away")],
        "avg": row.get("avg_total"), "kelly": row.get("kelly"), "od": od,
        "h2h": row.get("h2h") or "", "avg_h": row.get("avg_h"), "avg_a": row.get("avg_a"),
        "hf": row.get("form_home") or [], "af": row.get("form_away") or [],
        "hp": row.get("home_pos") or "", "ap": row.get("away_pos") or "",
        "url": row.get("url") or "",
    }


# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# MODE: scrape — chota Forebet: siku husika + JANA (results) → Supabase
# ──────────────────────────────────────────────────────────────────────────
def _save_sport(day, sport, recs, log=print):
    """Hifadhi batches za sport moja; rudi idadi iliyotumwa (uhakiki unafanywa baada ya upsert)."""
    rows = [rec_to_row(day, sport, r) for r in recs]
    for chunk in (rows[i:i + 200] for i in range(0, len(rows), 200)):
        sb("POST", "matches?on_conflict=day,sport,home,away", chunk,
           prefer="resolution=merge-duplicates,return=minimal")
    log(f"   [DB] {sport}: upsert imetumwa ({len(rows)} mechi)")
    return len(rows)


def _scrape_day(day, no_enrich=True, log=print, return_report=False):
    """Chota sports zote, upsert, kisha thibitisha mechi zilizotumwa zipo DB.
    Cache metadata huwekwa mwisho; makosa yoyote huonekana kama partial/failed."""
    import scraper
    SPORTS = ["football", "basketball", "tennis"]
    started = _dt.datetime.now(_EAT).isoformat()
    log(f"== [SCRAPE] kuchota Forebet: siku {day} (H2H itafanywa na Engine kwa wateule tu) ...")
    # Usi-reset match_count ya zamani kabla ya scrape mpya kufanikiwa.
    sb("POST", "day_cache?on_conflict=day",
       {"day": day, "engine_version": ENGINE_VERSION,
        "scrape_status": "running", "scrape_started_at": started, "scrape_error": None},
       prefer="resolution=merge-duplicates,return=minimal")

    records_by_sport, errors = {}, []
    expected = set()
    for sport in SPORTS:
        try:
            recs = scraper.collect(sport, day, False, log)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{sport}: Forebet fetch: {str(e)[:180]}")
            log(f"   !! [{sport}] scrape imeshindwa: {str(e)[:180]}")
            recs = []
        records_by_sport[sport] = recs
        expected.update((sport, str(r.get("home") or ""), str(r.get("away") or "")) for r in recs)
        log(f"   [{sport}] {len(recs)} mechi zimepatikana")
        if recs:
            try:
                _save_sport(day, sport, recs, log)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{sport}: Supabase upsert: {str(e)[:180]}")
                log(f"   ✗✗ [DB] {sport}: upsert imeshindwa: {str(e)[:180]}")

    # Thibitisha kwa kusoma rows zilizohifadhiwa, si idadi iliyotolewa na Forebet pekee.
    try:
        db_rows = sb_all(f"matches?day=eq.{day}&select=sport,home,away")
        saved = {(str(r.get("sport") or ""), str(r.get("home") or ""), str(r.get("away") or ""))
                 for r in db_rows}
        missing = expected - saved
        if missing:
            errors.append(f"Supabase verification: mechi {len(missing)} hazipo baada ya upsert")
            log(f"   ✗✗ [DB] uhakiki: mechi {len(missing)} hazijaonekana Supabase")
        stored_count = len(db_rows)
    except Exception as e:  # noqa: BLE001
        db_rows = []
        stored_count = 0
        errors.append(f"Supabase verification: {str(e)[:180]}")
        log(f"   ✗✗ [DB] kusoma tena rows za uhakiki kumeshindwa: {str(e)[:180]}")

    fetched_count = sum(len(v) for v in records_by_sport.values())
    if errors:
        status = "partial" if stored_count else "failed"
    else:
        status = "succeeded" if fetched_count else "empty"
    finished = _dt.datetime.now(_EAT).isoformat()
    try:
        sb("PATCH", f"day_cache?day=eq.{day}",
           {"match_count": stored_count, "scrape_status": status,
            "scraped_at": finished, "scrape_completed_at": finished,
            "scrape_error": " | ".join(errors)[:2000] if errors else None,
            "engine_version": ENGINE_VERSION}, prefer="return=minimal")
    except Exception as e:  # noqa: BLE001
        errors.append(f"day_cache status update: {str(e)[:180]}")
        status = "partial" if stored_count else "failed"
        log(f"   ✗✗ [DB] status ya day_cache haikuweza kusasishwa: {str(e)[:180]}")

    log(f"== [DB] {day}: Forebet={fetched_count} · Supabase rows={stored_count} · hali={status}.")
    if errors:
        for error in errors:
            log(f"   ⚠ {error}")
    report = {"day": day, "status": status, "fetched_count": fetched_count,
              "stored_count": stored_count, "errors": errors}
    return (records_by_sport, report) if return_report else records_by_sport


ENRICH_MAX = 40   # H2H detail pages kwa wateule wa engine tu (~5s kila moja → ~3 min)
VERIFY_BUDGET_S = 300   # uthibitisho wa picks kwa bookie: dakika 5 max


def _enrich_shortlist(day, records_by_sport, min_prob, log=print):
    """Engine pre-pass (bila bookie) → wateule (front + pool) → H2H detail kwa hao tu → upsert DB."""
    import scraper, engine
    import contextlib, io
    engine.MIN_CONF = int(min_prob)
    engine.RELAX_STEPS = [min_prob, max(60, min_prob - 5), max(55, min_prob - 10)]
    with contextlib.redirect_stdout(io.StringIO()):
        front, pool, _ = engine.predict_day(records_by_sport, provider=None, min_conf=min_prob,
                                            log=lambda *a, **k: None)
    keys, seen = [], set()
    for p in list(front) + list(pool):
        k = (p.get("sport"), p.get("home"), p.get("away"))
        if k not in seen:
            seen.add(k); keys.append(k)
    keys = keys[:ENRICH_MAX]
    by_sport = {}
    for sport, recs in records_by_sport.items():
        idx = {(r.get("home"), r.get("away")): r for r in recs}
        sel = [idx[(h, a)] for (s, h, a) in keys if s == sport and (h, a) in idx
               and r_needs_h2h(idx[(h, a)])]
        if sel:
            by_sport[sport] = sel
    n_all = len(by_sport.get("football", []))
    n_rec = sum(len(v) for v in records_by_sport.values())
    log(f"== [H2H] wateule {len(keys)} wa engine (kati ya mechi {n_rec}) → H2H detail kwa mechi "
        f"{n_all} za football tu (~{max(1, round(n_all * 5 / 60))} dk) ...")
    for sport, sel in by_sport.items():
        if sport != "football":
            continue                       # H2H detail ni ya football (scraper.enrich)
        try:
            scraper.enrich(sel, sport, log)
            _save_sport(day, sport, sel, log)
        except Exception as e:  # noqa: BLE001
            log(f"   ⚠ [H2H] {sport}: {str(e)[:150]} — engine inaendelea bila H2H")
    return n_all


def r_needs_h2h(r):
    h = (r.get("h2h") or "").strip()
    return not h or h == "\u2014"


def _finals_from_records(records_by_sport):
    """records → {(home,away): (fh,fa) au ("VOID",None)}."""
    finals = {}
    for recs in records_by_sport.values():
        for r in recs:
            st_ = (r.get("st") or "").lower()
            if "cancl" in st_ or "postp" in st_ or "aband" in st_ or "walkover" in st_ or "wo" in st_.split():
                finals[(r["home"], r["away"])] = ("VOID", None)
                continue
            if r.get("sc") and None not in r["sc"]:
                finals[(r["home"], r["away"])] = (int(r["sc"][0]), int(r["sc"][1]))
    return finals


def cmd_scrape(day, no_enrich=False):
    """Chota siku iliyochaguliwa + jana, thibitisha Supabase, kisha settle jana."""
    print(f"━━━ [SCRAPE MODE] lengo: {day} + jana (matokeo) ━━━")
    recs_d, report_d = _scrape_day(day, return_report=True)

    yday = (_dt.date.fromisoformat(day) - _dt.timedelta(days=1)).isoformat()
    print(f"\n━━━ [SCRAPE] JANA {yday} — refresh ya matokeo ━━━")
    recs_y, report_y = _scrape_day(yday, return_report=True)

    n_day = report_d["fetched_count"]
    n_yday = report_y["fetched_count"]
    finals = _finals_from_records(recs_y)
    print(f"\n━━━ [SETTLE] jana {yday}: finals {len(finals)} zilizopatikana ━━━")
    _settle_day_from_finals(yday, finals)

    today_ok = report_d["status"] == "succeeded" and report_d["stored_count"] > 0
    yesterday_ok = report_y["status"] not in ("partial", "failed")
    overall = "succeeded" if today_ok and yesterday_ok else "partial"
    print(f"\n━━━ MUHTASARI: leo {n_day} fetched / {report_d['stored_count']} DB · "
          f"jana {n_yday} fetched / {report_y['stored_count']} DB · finals {len(finals)} · {overall} ━━━")
    if not today_ok:
        print("✗✗ SCRAPE YA SIKU ILIYOCHAGULIWA HAIJATHIBITISHWA. Usibonyeze Run Engine mpaka Activity Log ionyeshe Supabase rows.")
        if report_d["status"] == "empty":
            print("   Hakuna mechi zilizopatikana. Angalia internet, Forebet/Cloudflare, na tarehe uliyochagua.")
        raise SystemExit(2)
    if not yesterday_ok:
        print("⚠ Siku iliyochaguliwa imehifadhiwa, lakini data ya jana haikuthibitishwa kikamilifu; baadhi ya matokeo yanaweza kubaki pending.")
    print("✓ SCRAPE YA SIKU ILIYOCHAGULIWA IMEFANIKIWA NA KUTHIBITISHWA — sasa bonyeza '2) Run Engine'.")
    return {"day": n_day, "yday": n_yday, "finals": len(finals), "status": overall,
            "stored_day": report_d["stored_count"], "stored_yday": report_y["stored_count"]}


def latest_successful_run_id(day, include_demo=True):
    demo_filter = "" if include_demo else "&is_demo=eq.false"
    rows = sb("GET", f"analysis_runs?day=eq.{day}&status=eq.succeeded{demo_filter}&select=id&order=started_at.desc,id.desc&limit=1") or []
    return int(rows[0]["id"]) if rows else None


def _pending_production_days():
    pending = sb_all("picks?result=eq.pending&select=day,run_id,league&order=day,id") or []
    runs = sb_all("analysis_runs?status=eq.succeeded&is_demo=eq.false&select=id") or []
    valid_run_ids = {int(r["id"]) for r in runs}
    return sorted({r["day"] for r in pending if
                   (r.get("run_id") is not None and int(r["run_id"]) in valid_run_ids) or
                   (r.get("run_id") is None and not str(r.get("league") or "").startswith("K96 TEST"))})


def _settle_rows(table, day):
    """Picks/slips za legacy (run_id NULL) pamoja na run zilizofanikiwa pekee."""
    rows = sb("GET", f"{table}?day=eq.{day}&result=eq.pending&run_id=is.null&select=*") or []
    runs = sb("GET", f"analysis_runs?day=eq.{day}&status=eq.succeeded&is_demo=eq.false&select=id&order=id") or []
    ids = [int(r["id"]) for r in runs]
    for i in range(0, len(ids), 100):
        group = ",".join(str(x) for x in ids[i:i + 100])
        if group:
            rows.extend(sb_all(f"{table}?day=eq.{day}&result=eq.pending&run_id=in.({group})&select=*") or [])
    return rows


def _settle_day_from_finals(d, finals):
    """Settle picks+slips za siku d kutoka finals-map { (home,away): (fh,fa) }."""
    win = loss = push = unk = 0
    pending = _settle_rows("picks", d)
    for p in pending or []:
        key = (p["home"], p["away"])
        if key not in finals:
            continue
        fh, fa = finals[key]
        res = settle_pick(p["market"], p["tip"], fh, fa)
        if res == "unknown":
            continue
        sb("PATCH", f"picks?id=eq.{p['id']}",
           {"result": res, "final_score": (f"{fh}-{fa}" if fh != "VOID" else "VOID"),
            "settled_at": _dt.datetime.utcnow().isoformat()},
           prefer="return=minimal")
        if fh != "VOID":
            try:  # matches row: final score (safu halisi: final_home/final_away)
                q = urllib.parse.quote
                sb("PATCH", f"matches?day=eq.{d}&sport=eq.{q(p['sport'])}"
                            f"&home=eq.{q(p['home'])}&away=eq.{q(p['away'])}",
                   {"final_home": fh, "final_away": fa}, prefer="return=minimal")
            except Exception as e:  # noqa: BLE001
                print(f"   ! matches PATCH {p['home']} vs {p['away']}: {str(e)[:80]}")
        win += res == "win"; loss += res == "loss"; push += res in ("push", "void")
        print(f"   [{p['sport']}] {p['home']} vs {p['away']} · {p['tip']} → {res}"
              + (f" ({fh}-{fa})" if fh != "VOID" else " (VOID)"))
    print(f"== settle {d}: win {win} · loss {loss} · push/void {push}"
          + (f" · bado pending {unk}" if unk else ""))
    try:
        settle_slips(d)
    except Exception as e:
        print(f"   ! slips settle: {e}")


def _persist_engine_run(day, payload, match_count, is_demo=False):
    """Hifadhi run mpya bila kufuta run za awali; run inaonekana tu baada ya saves zote kupita."""
    start = sb_resp("POST", "analysis_runs", {
        "day": day, "status": "running", "match_count": int(match_count), "is_demo": bool(is_demo),
    }, prefer="return=representation")
    if start.status_code not in (200, 201):
        raise RuntimeError(f"analysis_runs insert imeshindwa HTTP {start.status_code}: {start.text[:180]} — RUN schema_v4_reliability.sql")
    try:
        run_row = start.json()
        run_id = int(run_row[0]["id"] if isinstance(run_row, list) else run_row["id"])
    except Exception as e:
        raise RuntimeError(f"Supabase haikurudisha run_id: {str(e)[:100]}") from e

    inserted_pick_rows, slip_rows, slips = [], [], []
    try:
        prob_keys = ("p_model", "p_market", "p_final", "p_cal", "bk_odds", "bookmaker", "ev", "flags")
        prows = [{
            "run_id": run_id, "day": day, "sport": p["sport"], "league": p.get("league", ""),
            "time_eat": p.get("time", ""), "home": p["home"], "away": p["away"],
            "market": p["market"], "tip": p["tip"], "conf": p["conf"],
            "forebet": p["forebet"], "adj": p.get("adj"),
            "odd": p.get("bk_odds") if p.get("bk_odds") is not None else p.get("odd"),
            "rank": p.get("rank"), "why": p.get("why") or [], "decision": p.get("decision", ""),
            "engine_version": ENGINE_VERSION,
            **{k: p.get(k) for k in prob_keys if p.get(k) is not None},
        } for p in payload.get("picks", [])]

        if prows:
            r_p = sb_resp("POST", "picks", prows, prefer="return=representation")
            if r_p.status_code not in (200, 201):
                raise RuntimeError(f"picks insert HTTP {r_p.status_code}: {r_p.text[:180]}")
            inserted_pick_rows = r_p.json() or []
            if len(inserted_pick_rows) != len(prows):
                raise RuntimeError(f"picks insert count mismatch: {len(inserted_pick_rows)}/{len(prows)}")
            for p in payload["picks"]:
                p["_db_pick_id"] = next((r["id"] for r in inserted_pick_rows
                    if (r.get("home"), r.get("away"), r.get("market"), r.get("tip")) ==
                       (p.get("home"), p.get("away"), p.get("market"), p.get("tip"))), None)

        import slip as _slip
        slips = _slip.build_slips(payload.get("picks", []), topk=5, log=print)
        payload["slips"] = slips
        slip_payload = [{
            "run_id": run_id, "day": day, "label": s["label"], "legs": s["legs_n"],
            "total_odds": s["total_odds"], "joint_prob": s["joint_prob"],
            "ev": s.get("ev"), "engine_version": ENGINE_VERSION,
        } for s in slips]
        if slip_payload:
            r_sl = sb_resp("POST", "slips", slip_payload, prefer="return=representation")
            if r_sl.status_code not in (200, 201):
                raise RuntimeError(f"slips insert HTTP {r_sl.status_code}: {r_sl.text[:180]}")
            slip_rows = r_sl.json() or []
            if len(slip_rows) != len(slip_payload):
                raise RuntimeError(f"slips insert count mismatch: {len(slip_rows)}/{len(slip_payload)}")
            idmap = {r["label"]: r["id"] for r in slip_rows}
            pick_id = {(p.get("home"), p.get("away"), p.get("market"), p.get("tip")): p.get("_db_pick_id")
                       for p in payload.get("picks", [])}
            legs_rows = []
            for s in slips:
                sid = idmap.get(s["label"])
                for leg in s["legs"]:
                    legs_rows.append({
                        "slip_id": sid,
                        "pick_id": pick_id.get((leg.get("home"), leg.get("away"), leg.get("market"), leg.get("tip"))),
                        "home": leg["home"], "away": leg["away"], "market": leg["market"], "tip": leg["tip"],
                        "odds": leg.get("bk_odds"), "p_cal": leg.get("p_cal"),
                    })
            if legs_rows:
                r_l = sb_resp("POST", "slip_legs", legs_rows, prefer="return=minimal")
                if r_l.status_code not in (200, 201, 204):
                    raise RuntimeError(f"slip_legs insert HTTP {r_l.status_code}: {r_l.text[:180]}")
                slip_ids = ",".join(str(int(r["id"])) for r in slip_rows)
                saved_legs = sb_all(f"slip_legs?slip_id=in.({slip_ids})&select=id")
                if len(saved_legs) != len(legs_rows):
                    raise RuntimeError(f"slip_legs verification mismatch: {len(saved_legs)}/{len(legs_rows)}")

        finish = sb_resp("PATCH", f"analysis_runs?id=eq.{run_id}", {
            "status": "succeeded", "completed_at": _dt.datetime.now(_EAT).isoformat(),
            "picks_count": len(prows), "slips_count": len(slips), "error": None,
        }, prefer="return=minimal")
        if finish.status_code not in (200, 204):
            raise RuntimeError(f"analysis_runs completion HTTP {finish.status_code}: {finish.text[:180]}")
        print(f"== [DB] run #{run_id} imehifadhiwa na kuthibitishwa: picks={len(prows)}, slips={len(slips)}.")
        return run_id, slips
    except Exception as e:
        # Run is isolated by run_id; it cannot hide the last successful run.
        try:
            sb("DELETE", f"slips?run_id=eq.{run_id}", prefer="return=minimal")
            sb("DELETE", f"picks?run_id=eq.{run_id}", prefer="return=minimal")
        except Exception:
            pass
        try:
            sb("PATCH", f"analysis_runs?id=eq.{run_id}", {
                "status": "failed", "completed_at": _dt.datetime.now(_EAT).isoformat(),
                "picks_count": len(inserted_pick_rows), "slips_count": len(slip_rows),
                "error": str(e)[:2000],
            }, prefer="return=minimal")
        except Exception:
            pass
        raise RuntimeError(f"Run #{run_id} haikuhifadhiwa kikamilifu; run ya mwisho iliyofanikiwa imeachwa salama. {e}") from e


# ──────────────────────────────────────────────────────────────────────────
# MODE: run — scrape (au tumia cache) → engine → Supabase
# ──────────────────────────────────────────────────────────────────────────
def cmd_run(day, min_prob, force, no_enrich):
    import scraper, picks, engine   # APP modules

    SPORTS = ["football", "basketball", "tennis"]
    cached = sb("GET", f"day_cache?day=eq.{day}&select=*")
    using_cache = bool(cached) and not force
    if using_cache:
        mc = int(cached[0].get("match_count") or 0)
        scrape_status = cached[0].get("scrape_status") or "unknown"
        n_rows = len(sb("GET", f"matches?day=eq.{day}&select=id&limit=1") or [])
        if mc <= 0 or n_rows == 0 or scrape_status != "succeeded":
            print(f"⚠ [CACHE] {day}: hali={scrape_status}, match_count={mc}, rows={n_rows} — cache haitumiki; rescrape.")
            using_cache = False

    if using_cache:
        print(f"== [CACHE] siku {day} imethibitishwa ({cached[0].get('scraped_at')}) — tunatumia data za Supabase.")
        rows = sb_all(f"matches?day=eq.{day}&select=*&order=time_eat,id")
        records_by_sport = {s: [] for s in SPORTS}
        for row in rows:
            if row.get("sport") in SPORTS:
                records_by_sport[row["sport"]].append(row_to_rec(row))
        records_by_sport = {s: v for s, v in records_by_sport.items() if v}
        if not records_by_sport:
            raise SystemExit("Cache ilisema imefanikiwa lakini haina mechi; kagua scrape status.")
    else:
        records_by_sport, scrape_report = _scrape_day(day, return_report=True)
        if scrape_report["status"] != "succeeded" or scrape_report["stored_count"] <= 0:
            print(f"✗ Run Engine imesimamishwa: scrape status={scrape_report['status']}, "
                  f"Forebet={scrape_report['fetched_count']}, Supabase={scrape_report['stored_count']}.")
            raise SystemExit(2)

    if not no_enrich and records_by_sport:
        try:
            _enrich_shortlist(day, records_by_sport, min_prob)
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠ [H2H] shortlist imeshindwa ({str(e)[:120]}) — engine inaendelea bila H2H")

    provider = None
    try:
        import bookie as _bk0
        provider = _bk0.make_provider(day, print)
        print("== [BOOKIE] provider ya devig imewashwa (betway→pawa, per-match markets)")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠ bookie provider haikuwaka ({str(e)[:90]}) — model-only mode")
    payload = picks.run(day, min_prob=min_prob, do_enrich=False,
                        records_by_sport=records_by_sport, provider=provider)

    # ── HATUA YA BOOKIE: BETWAY TZ → betPawa TZ · AUTO-REPLACE ──────────────
    print("== [BOOKIE] verification: betway TZ (primary) → betPawa TZ (backup) — auto-replace ON")
    try:
        import bookie, engine as _eng
        ordered = list(payload["picks"])
        seen = {(p["home"], p["away"]) for p in ordered}
        for c in payload.get("pool", []):
            if (c["home"], c["away"]) not in seen:
                ordered.append(c); seen.add((c["home"], c["away"]))

        ok_picks, dropped, api_down = [], [], False
        caps = dict(_eng.CAPS)
        eligible_sports = list(dict.fromkeys(c.get("sport") for c in ordered if c.get("sport")))
        n_sports = max(1, len(eligible_sports))
        sport_quota = max(1, (_eng.TARGET_MAX + n_sports - 1) // n_sports)
        verified_by_sport = {}
        t_ver = time.time()
        print(f"   [BOOKIE] uthibitisho wa picks: wagombea {len(ordered)} (max dk {VERIFY_BUDGET_S // 60})")
        for cand in ordered:
            if len(ok_picks) >= _eng.TARGET_MAX:
                break
            sport = cand.get("sport") or "unknown"
            if verified_by_sport.get(sport, 0) >= sport_quota:
                continue
            if time.time() - t_ver > VERIFY_BUDGET_S:          # usikwame — kikomo cha muda
                print(f"   ⚠ [BOOKIE] muda wa uthibitisho (dk {VERIFY_BUDGET_S // 60}) umeisha — nasimama na picks {len(ok_picks)}")
                if not ok_picks:
                    api_down = True                            # hakuna kilichothibitishwa → baki na picks za engine
                break
            if caps.get(cand["market"], 3) <= 0 and len(ok_picks) >= _eng.TARGET_MIN:
                continue                                   # cap ya market imejaa
            try:
                v = bookie.verify_pick(cand, day, print)
            except Exception as e:  # noqa: BLE001 — kosa la pick moja lisiangushe run
                print(f"   ⚠ [BOOKIE] kosa kuthibitisha {cand.get('match')}: {str(e)[:90]} — naruka")
                continue
            if v.get("api_down"):
                api_down = True
                break
            if v.get("bettable"):
                cand["bk_odds"] = v.get("bk_odds")
                cand["bp_name"] = v.get("event_found") or v.get("bw_event")
                cand["why"] = (cand.get("why") or []) + [v["note"]]
                ok_picks.append(cand)
                verified_by_sport[sport] = verified_by_sport.get(sport, 0) + 1
                caps[cand["market"]] = caps.get(cand["market"], 3) - 1
            else:
                dropped.append((cand, v["note"]))
                print(f"   ✗ ACHA: {cand['match']} · {cand['market']} {cand['tip']} — {v['note']}")
        if api_down:
            print("   ⚠ Betway+betPawa API haifikiki — verification imekatwa (picks zinabaki vilevile).")
        else:
            print(f"   [BOOKIE] {len(ok_picks)} bettable ✓ · {len(dropped)} zimeondolewa (auto-replace wa engine)")
        if ok_picks or not api_down:
            payload["picks"] = ok_picks
            for i, p in enumerate(ok_picks, 1):                    # re-rank
                p["rank"] = i

        # ── PHASE 3: coverage log + odds_snapshots (kwa closing-value + devig) ──
        try:
            import betway as _bw; import bookie as _bk
            bw_ix = _bw.day_index(day, print)
            pw_ix = _bk.day_index(day, print)
            for sp in ("football", "basketball", "tennis"):
                a = sum(1 for e in bw_ix if e.get("sport") == sp)
                b = sum(1 for e in pw_ix if e.get("sport") == sp)
                if sp == "football":
                    ratio = (b / a) if a else 0
                print(f"   [COVERAGE] {sp:10s} betway {a:4d} · betPawa {b:4d}"
                      + (f" · pawa/bw ratio {ratio:.2f}" if sp == "football" else ""))
        except Exception as e:  # noqa: BLE001
            print(f"   [COVERAGE] haiwezi ({str(e)[:70]})")

        snap_rows, snap_missing = [], 0
        for p in payload["picks"]:
            try:
                if p.get("bw_id"):
                    rows = _bw.snapshot_event(p["bw_id"])
                elif p.get("bp_id"):
                    rows = _bk.snapshot_event(p["bp_id"])
                else:
                    continue
                for r in rows:
                    if not r.get("market") or r.get("odds") is None:
                        continue
                    snap_rows.append({"day": day, "sport": p["sport"],
                                      "home": p["home"], "away": p["away"],
                                      "bookmaker": r["bookmaker"], "market": str(r["market"])[:120],
                                      "outcome": str(r["outcome"])[:120],
                                      "line": r.get("line"), "odds": r.get("odds"),
                                      "suspended": bool(r.get("suspended"))})
            except Exception:  # noqa: BLE001
                snap_missing += 1
        if snap_rows:
            r_sn = sb_resp("POST", "odds_snapshots", snap_rows, prefer="return=minimal")
            if r_sn.status_code in (200, 201, 204):
                print(f"   [SNAPSHOTS] {len(snap_rows)} odds zimekubuk-ka Supabase (closing-value data)")
            elif r_sn.status_code in (404, 406):
                print("   [SNAPSHOTS] table 'odds_snapshots' haipo — RUN schema_v2.sql kwenye Supabase SQL Editor")
            else:
                print(f"   [SNAPSHOTS] ilishindika HTTP {r_sn.status_code}")
        if snap_missing:
            print(f"   [SNAPSHOTS] events {snap_missing} zilikuwa hazifikiwe size")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠ [BOOKIE] verification ikishindwa kabisa ({str(e)[:120]}) — picks zinabaki vilevile.")

    # Hifadhi run mpya tofauti; hakuna kufuta picks/slips za run za awali.
    match_count = sum(len(v) for v in records_by_sport.values())
    run_id, slips = _persist_engine_run(day, payload, match_count)
    payload["run_id"] = run_id
    for pick in payload.get("picks", []):
        pick.pop("_db_pick_id", None)
    import slip as _slip
    print(_slip.slip_copy_text(slips) if slips else "")
    print(picks.copy_text(payload))
    return payload


# ──────────────────────────────────────────────────────────────────────────
# MODE: settle — matokeo → win/loss/push
# ──────────────────────────────────────────────────────────────────────────
def settle_pick(market, tip, fh, fa):
    """fh/fa = final home/away. Rudi 'win' | 'loss' | 'push' | 'void' | 'unknown'."""
    if fh == "VOID":
        return "void"
    if fh is None or fa is None:
        return "unknown"
    tot = fh + fa
    if market == "1X2":
        got = "1" if fh > fa else ("X" if fh == fa else "2")
        return "win" if tip == got else "loss"
    if market == "Double Chance":
        ok = {"1X": fh >= fa, "12": fh != fa, "X2": fa >= fh}.get(tip)
        return "win" if ok else "loss" if ok is not None else "unknown"
    if market == "Draw No Bet":
        if fh == fa: return "push"
        got = "1" if fh > fa else "2"
        return "win" if tip == got else "loss"
    if market == "Total Goals":
        side = "Over" if tip.startswith("Over") else "Under"
        line = float(tip.split()[-1])
        return "win" if (tot > line if side == "Over" else tot < line) else "loss"
    if market == "BTTS":
        btts = fh > 0 and fa > 0
        return "win" if ((tip == "Yes") == btts) else "loss"
    if market == "Handicap +2":                  # tip = "+2 Home" / "+2 Away"
        home_tipped = "Home" in tip
        h = fh + 2 if home_tipped else fh
        a = fa if home_tipped else fa + 2
        if h == a: return "push"
        covered = (h > a) if home_tipped else (a > h)   # timu TIPILIO ndiyo lazima icover
        return "win" if covered else "loss"
    if market == "Winner":                       # basketball/tennis ("1"/"2" au "P1"/"P2")
        if fh == fa:
            return "push"
        home_won = fh > fa
        tip_home = str(tip).upper() in ("1", "P1")
        return "win" if tip_home == home_won else "loss"
    return "unknown"


def cmd_settle(day=None):
    import scraper
    if day:
        days = [day]
    else:
        days = [d for d in _pending_production_days() if d < today_eat().isoformat()]
    if not days:
        print("== hakuna picks zinazosubiri matokeo.")
        return
    for d in days:
        print(f"== [SETTLE] siku {d} — kutafuta final scores kutoka Forebet…")
        finals = {}
        for sport in ("football", "basketball", "tennis"):   # Phase 6: settle sports ZOTE
            try:
                recs = scraper.collect(sport, d, False, print)
            except Exception as e:
                print(f"   !! {sport}: {e}")
                continue
            for r in recs:
                st_ = (r.get("st") or "").lower()
                if "cancl" in st_ or "postp" in st_ or "aband" in st_ or "walkover" in st_ or "wo" in st_.split():
                    finals[(r["home"], r["away"])] = ("VOID", None)
                    continue
                if r.get("sc") and None not in r["sc"]:
                    finals[(r["home"], r["away"])] = (int(r["sc"][0]), int(r["sc"][1]))
        pending = _settle_rows("picks", d)
        win = loss = push = unk = 0
        for p in pending or []:
            key = (p["home"], p["away"])
            if key not in finals:
                continue                                  # sijachezwa bado au haikuona
            fh, fa = finals[key]
            res = settle_pick(p["market"], p["tip"], fh, fa)
            if res == "unknown":
                continue
            sb("PATCH", f"picks?id=eq.{p['id']}",
               {"result": res, "final_score": (f"{fh}-{fa}" if fh != "VOID" else "VOID"),
                "settled_at": _dt.datetime.utcnow().isoformat()},
               prefer="return=minimal")
            if fh != "VOID":
                sb("PATCH", f"matches?day=eq.{d}&home=eq.{urllib.parse.quote(p['home'])}&away=eq.{urllib.parse.quote(p['away'])}",
                   {"final_home": fh, "final_away": fa}, prefer="return=minimal")
            win += res == "win"; loss += res == "loss"; push += res == "push"
            push += res == "void"; unk += res == "unknown"
        print(f"   siku {d}: win {win} · loss {loss} · push/void {push} · (bado {unk})")

        # ── Phase 6: settle SLIPS za siku hiyo ───────────────────────────────
        try:
            settle_slips(d)
        except Exception as e:  # noqa: BLE001
            print(f"   [slip-settle] {str(e)[:90]}")


def settle_slips(day_iso):
    """spec 8.1: slip inashinda ikifika yote (void legs hutolewa — odds hupunguzwa)."""
    rows = _settle_rows("slips", day_iso)
    if not rows:
        return
    for s in rows:
        legs = sb("GET", f"slip_legs?slip_id=eq.{s['id']}") or []
        if not legs:
            continue
        # Pick ID huunganisha leg na run husika; legacy rows hutumia match key.
        done = True
        res_of = []
        for l in legs:
            if l.get("pick_id") is not None:
                pr = sb("GET", f"picks?id=eq.{int(l['pick_id'])}&select=result&limit=1") or []
            else:
                kws = (f"day=eq.{day_iso}&home=eq.{urllib.parse.quote(l['home'])}"
                       f"&away=eq.{urllib.parse.quote(l['away'])}&market=eq.{urllib.parse.quote(l['market'])}"
                       f"&tip=eq.{urllib.parse.quote(l['tip'])}")
                pr = sb("GET", f"picks?{kws}&order=id.desc&limit=1") or []
            if not pr or (pr[0].get("result") in (None, "pending")):
                done = False
                break
            res_of.append((l, pr[0]["result"]))
        if not done:
            continue
        active = [(l, r) for l, r in res_of if r != "void"]
        sres = None
        if any(r == "loss" for _, r in active):
            sres = "loss"
        elif all(r in ("win", "push") for _, r in active) and any(r == "win" for _, r in active):
            sres = "win"
        elif not active:
            sres = "void"
        if not sres:
            continue
        to = 1.0
        njivile = 0
        for l, r in active:
            if r == "win":
                to *= float(l.get("odds") or 1)
                njivile += 1
            elif r == "push":
                njivile += 1                               # push: ibaki bila odds
        slip_update = {"result": sres,
                       "settled_at": _dt.datetime.utcnow().isoformat(),
                       "total_odds": round(to, 3) if active else s.get("total_odds")}
        sb("PATCH", f"slips?id=eq.{s['id']}", slip_update, prefer="return=minimal")
        for l, r in res_of:
            if r != "void":
                sb("PATCH", f"slip_legs?id=eq.{l['id']}", {"result": r}, prefer="return=minimal")
        print(f"   [slip {s['label']}] → {sres} (odds {slip_update['total_odds']})")


# ──────────────────────────────────────────────────────────────────────────
# MODE: status
# ──────────────────────────────────────────────────────────────────────────
def cmd_status():
    days = sb("GET", "day_cache?select=*&order=day.desc&limit=7") or []
    print("== day_cache (7 za mwisho):")
    for d in days:
        print(f"   {d['day']} · {d['match_count']} mechi · {d['scraped_at'][:16]}")
    stats = sb("GET", "engine_stats?select=*") or []
    print("== engine_stats (history ya matokeo):")
    for s in stats:
        print(f"   {s['sport']:10s} {s['market']:15s} n={s['total']:3d}  W={s['wins']} L={s['losses']}  hit={s['hit_pct']}%  conf~{s['avg_conf']}")


# ──────────────────────────────────────────────────────────────────────────
# MODE: daemon — auto-scrape 00:00 & auto-settle 01:00 (EMA/progr handler)
# Scraper itafanya kazi MARA MOJA kwa siku. App ifungulwe mtumiaji wakati wowote
# → data imeshahifadhiwa Supabase (cache), hakuna kuchota tena.
# PC ikiwa imezima saa ile → catch-up moja kwa moja inapowaka.
# ──────────────────────────────────────────────────────────────────────────
def _odds_refresh(day_iso):
    """06:00/12:00 — snapshot okes-side odds za picks za leo (za closing-line/value analysis)."""
    import sys as _s
    _s.path.insert(0, str(BACKEND.parent / "forebet_picks_app"))
    import bookie
    run_id = latest_successful_run_id(day_iso, include_demo=False)
    run_filter = f"&run_id=eq.{run_id}" if run_id is not None else "&run_id=is.null"
    pr = sb_all(f"picks?day=eq.{day_iso}{run_filter}&select=*") or []
    if not pr:
        return
    provider = bookie.make_provider(day_iso, print)
    rows = []
    for p in pr:
        try:
            bk = provider({"home": p["home"], "away": p["away"], "league": p.get("league"),
                           "time": p.get("time_eat")}, p["sport"], None)
            if not bk or not bk.get("found"):
                continue
            for (mkt, tip), o in (bk.get("odds") or {}).items():
                if o is None:
                    continue
                rows.append({"day": day_iso, "sport": p["sport"], "home": p["home"], "away": p["away"],
                             "bookmaker": bk["bookmaker"], "market": mkt, "outcome": tip,
                             "odds": o, "suspended": False})
        except Exception:
            continue
    if rows:
        r2 = sb_resp("POST", "odds_snapshots", rows, prefer="return=minimal")
        print(f"   [ODDS-REFRESH] {len(rows)} zimekati-kudi ({r2.status_code})")


def cmd_daemon(min_prob=80):
    print("== [DAEMON] K96 auto-worker imeanza. Ctrl+C kusimamia. ==")
    print("   · 00:00 EAT → scrape (picks za siku zionekane Supabase)")
    print("   · 01:00 EAT → settle (matokeo ya juzii/jana → results + slips)")
    print("   · 06:00 & 12:00 EAT → odds refresh snap (closing-line data)")
    print("   · Jumatatu 04:00 EAT → calibration refit (kufuatria ≥300 settled)")
    today = today_eat().isoformat()
    last_run = None
    last_settle = None
    last_snap = {}
    last_calib = today_eat().isocalendar()[:2]
    # 🔁 catch-up mara moja (PC iliwaka baadaye)
    try:
        cached = sb("GET", f"day_cache?day=eq.{today}&select=day,match_count,scrape_status") or []
        cache_ok = bool(cached) and cached[0].get("scrape_status") == "succeeded" \
            and int(cached[0].get("match_count") or 0) > 0
        if not cache_ok:
            print(f"== [DAEMON] cache ya leo {today} haijathibitishwa — inachota na kuchambua sasa hivi…")
            cmd_run(today, min_prob, False, False)
            last_run = today
        pend_days = _pending_production_days()
        if any(d < today for d in pend_days):
            print("== [DAEMON] kuna picks za zamani zisizo-settled — settle scratch…")
            cmd_settle()
            last_settle = today
    except Exception as e:  # noqa: BLE001
        print("  !! catch-up imekwanguka:", e)
    while True:
        try:
            now = _dt.datetime.now(_EAT)
            t = now.date().isoformat()
            # 🕧 Saa 00:00–00:05 — scrape ya LEO
            if now.hour == 0 and now.minute < 6 and last_run != t:
                print(f"== [DAEMON] scrape ya {t} (00:00 EAT)…")
                cmd_run(t, min_prob, False, False)
                last_run = t
            # 🕐 Saa 01:00–01:05 — matokeo ya jana
            if now.hour == 1 and now.minute < 6 and last_settle != t:
                print(f"== [DAEMON] settle ya matokeo (01:00 EAT)…")
                cmd_settle()
                last_settle = t
            # 🕕 Saa 06:00 na 12:00 — odds refresh of today's picks
            if now.hour in (6, 12) and now.minute < 6 and last_snap.get(now.hour) != t:
                try:
                    _odds_refresh(t)
                    last_snap[now.hour] = t
                except Exception as e:  # noqa: BLE001
                    print("  !! odds refresh:", e)
            # 🗓 Jumatatu ~04:00 — calibration ya wiki
            if now.weekday() == 0 and now.hour == 4 and now.minute < 6 \
                    and last_calib != (now.isocalendar()[0], now.isocalendar()[1]):
                try:
                    import subprocess
                    print("== [DAEMON] weekly calibration refit …")
                    subprocess.run([sys.executable, str(BACKEND / "calibration.py")], check=False)
                    last_calib = (now.isocalendar()[0], now.isocalendar()[1])
                except Exception as e:  # noqa: BLE001
                    print("  !! calibration refit:", e)
        except Exception as e:  # noqa: BLE001
            print("  !! daemon loop error:", e)
        time.sleep(45)


def main():
    ap = argparse.ArgumentParser(description="K96 PICKS — PC worker (Forebet → Supabase)")
    ap.add_argument("mode", choices=["run", "scrape", "settle", "status", "daemon"])
    ap.add_argument("--date", default=None)
    ap.add_argument("--min-prob", type=int, default=80)
    ap.add_argument("--force", action="store_true", help="ichote upya siku hata kama iko cache")
    ap.add_argument("--no-enrich", action="store_true", help="ache H2H enrich (haraka)")
    a = ap.parse_args()
    if a.mode == "run":
        day = a.date or today_eat().isoformat()
        cmd_run(day, a.min_prob, a.force, a.no_enrich)
    elif a.mode == "scrape":
        day = a.date or today_eat().isoformat()
        cmd_scrape(day, no_enrich=a.no_enrich)
    elif a.mode == "settle":
        cmd_settle(a.date)
    elif a.mode == "daemon":
        cmd_daemon(a.min_prob)
    else:
        cmd_status()


if __name__ == "__main__":
    main()
