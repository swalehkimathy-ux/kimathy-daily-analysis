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
    """Hifadhi mechi za sport moja Supabase PAPO HAPO (hakuna kusubiri sports zote)."""
    rows = [rec_to_row(day, sport, r) for r in recs]
    for chunk in (rows[i:i + 200] for i in range(0, len(rows), 200)):
        sb("POST", "matches?on_conflict=day,sport,home,away", chunk,
           prefer="resolution=merge-duplicates,return=minimal")
    log(f"   [DB] {sport}: mechi {len(rows)} zimehifadhiwa Supabase ✓")


def _scrape_day(day, no_enrich=True, log=print):
    """Chota sports zote za `day` HARAKA (bila H2H ya kila mechi) na uhifadhi kila sport papo hapo.
    H2H inafanywa baadaye na Run Engine — kwa mechi zenye nafasi tu (si 1000+)."""
    import scraper
    SPORTS = ["football", "basketball", "tennis"]
    log(f"== [SCRAPE] kuchota Forebet: siku {day} (haraka — H2H itafanywa na Engine kwa wateule tu) ...")
    # day_cache kwanza (matches zina FK kwenda day_cache)
    sb("POST", "day_cache?on_conflict=day",
       {"day": day, "match_count": 0, "engine_version": ENGINE_VERSION},
       prefer="resolution=merge-duplicates,return=minimal")
    records_by_sport, total = {}, 0
    for sport in SPORTS:
        try:
            recs = scraper.collect(sport, day, False, log)
        except Exception as e:  # noqa: BLE001
            log(f"   !! [{sport}] imeshindika: {e}")
            recs = []
        records_by_sport[sport] = recs
        log(f"   [{sport}] {len(recs)} mechi")
        if recs:
            try:
                _save_sport(day, sport, recs, log)
                total += len(recs)
                sb("POST", "day_cache?on_conflict=day",
                   {"day": day, "match_count": total, "engine_version": ENGINE_VERSION},
                   prefer="resolution=merge-duplicates,return=minimal")
            except Exception as e:  # noqa: BLE001
                log(f"   ✗✗ [DB] {sport}: kuhifadhi Supabase kumeshindwa: {str(e)[:200]}")
    log(f"== [DB] jumla: mechi {total} zimehifadhiwa ({day}).")
    if total == 0:
        log(f"   ⚠ {day}: imepatikana SIFURI (Forebet blocked?) — angalia Activity Log juu (✗✗ remedies)")
        try:
            sb("DELETE", f"day_cache?day=eq.{day}", prefer="return=minimal")
        except RuntimeError:
            pass   # siku ina history (picks/matches) — DB hairuhusu kufuta; data ya zamani inabaki
    return records_by_sport


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
    """GOLD-FLOW: (1) scrape leo/day (cache-aware), (2) scrape JANA fresh (results!),
    (3) settle picks za jana automatic."""
    import scraper
    _ = scraper  # sanity
    print(f"━━━ [SCRAPE MODE] lengo: {day} + jana (results refresh) ━━━")
    recs_d = _scrape_day(day)
    n_day = sum(len(v) for v in recs_d.values())

    import datetime as dtm
    yday = (_dt.date.fromisoformat(day) - dtm.timedelta(days=1)).isoformat()
    print(f"\n━━━ [SCRAPE] JANA {yday} — FRESH (tunataka FT results zipate updates) ━━━")
    # (hakuna DELETE: _scrape_day huchota upya kila mara + upsert merge; DB inalinda history)
    recs_y = _scrape_day(yday)

    n_yday = sum(len(v) for v in recs_y.values())
    finals = _finals_from_records(recs_y)
    print(f"\n━━━ [SETTLE] jana {yday}: finals {len(finals)} kutoka data hio hio ━━━")
    _settle_day_from_finals(yday, finals)

    print(f"\n━━━ MUHTASARI: {day} → {n_day} mechi · jana {yday} → {n_yday} mechi "
          f"({len(finals)} na matokeo) ━━━")
    if n_day == 0:
        print("✗✗ SCRAPE IMESHINDWA: mechi 0 za siku husika — Forebet haikufikiwa.\n"
              "   Suluhisho: (1) hakikisha internet, (2) INSTALL_K96.bat (curl_cffi + playwright chromium),\n"
              "   (3) acha dirisha la browser lifunguke na upite Cloudflare, kisha jaribu tena.\n"
              "   USIBONYEZE 'Run Engine' bado — hakuna data mpya.")
        raise SystemExit(2)
    print("✓ SCRAPE IMEFANIKIWA — sasa bonyeza '2) Run Engine' kupata picks/slips.")
    return {"day": n_day, "yday": n_yday, "finals": len(finals)}


def _settle_day_from_finals(d, finals):
    """Settle picks+slips za siku d kutoka finals-map { (home,away): (fh,fa) }."""
    win = loss = push = unk = 0
    pending = sb("GET", f"picks?day=eq.{d}&result=eq.pending&select=*")
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


# ──────────────────────────────────────────────────────────────────────────
# MODE: run — scrape (au tumia cache) → engine → Supabase
# ──────────────────────────────────────────────────────────────────────────
def cmd_run(day, min_prob, force, no_enrich):
    import scraper, picks, engine   # APP modules

    SPORTS = ["football", "basketball", "tennis"]
    cached = sb("GET", f"day_cache?day=eq.{day}&select=*")
    using_cache = bool(cached) and not force
    # Phase 7.1 FIX: cache TUPU (match_count=0 au matches rows 0) halimfai cache — rescrape FORCE
    if using_cache:
        mc = (cached[0].get("match_count") or 0)
        n_rows = len(sb("GET", f"matches?day=eq.{day}&select=id&limit=1") or [])
        if mc <= 0 or n_rows == 0:
            print(f"⚠ [CACHE] cache ya {day} IKO TUPU (match_count={mc}, rows={n_rows}) — "
                  "scraping ya kwanza ilishindika; tunafuta day_cache TUPU + rescrape FRESH…")
            try:
                sb("DELETE", f"day_cache?day=eq.{day}", prefer="return=minimal")
            except RuntimeError:
                pass   # DB inalinda history — rescrape itafanya upsert juu yake
            using_cache = False

    if using_cache:
        print(f"== [CACHE] siku {day} imeshapatikana (scraped_at {cached[0]['scraped_at']}) — tunatumia data hizo; Forebet haiguswi.")
        rows = sb_all(f"matches?day=eq.{day}&select=*&order=time_eat,id")
        records_by_sport = {s: [] for s in SPORTS}
        for row in rows:
            records_by_sport[row["sport"]].append(row_to_rec(row))
        records_by_sport = {s: v for s, v in records_by_sport.items() if v}
    else:
        records_by_sport = _scrape_day(day)

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
        t_ver = time.time()
        print(f"   [BOOKIE] uthibitisho wa picks: wagombea {len(ordered)} (max dk {VERIFY_BUDGET_S // 60})")
        for cand in ordered:
            if len(ok_picks) >= _eng.TARGET_MAX:
                break
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

    # furaga picks (futa za zamu iliyopita, weka mpya — engine inabadilika)
    sb("DELETE", f"picks?day=eq.{day}", prefer="return=minimal")
    PROB_KEYS = ("p_model", "p_market", "p_final", "p_cal", "bk_odds", "bookmaker", "ev", "flags")
    prows = [{
        "day": day, "sport": p["sport"], "league": p.get("league", ""),
        "time_eat": p.get("time", ""), "home": p["home"], "away": p["away"],
        "market": p["market"], "tip": p["tip"], "conf": p["conf"],
        "forebet": p["forebet"], "adj": p.get("adj"),
        "odd": p.get("bk_odds") if p.get("bk_odds") is not None else p.get("odd"),
        "rank": p.get("rank"), "why": p.get("why") or [], "decision": p.get("decision", ""),
        "engine_version": ENGINE_VERSION,
        **{k: p.get(k) for k in PROB_KEYS if p.get(k) is not None},
    } for p in payload["picks"]]
    if prows:
        r_p = sb_resp("POST", "picks", prows, prefer="return=minimal")
        if r_p.status_code >= 400:
            # schema_v2 haijatumika bado? jaribio la pili bila prob columns
            sb("DELETE", f"picks?day=eq.{day}", prefer="return=minimal")
            prows_slim = [{k: v for k, v in row.items() if k not in PROB_KEYS} for row in prows]
            r2 = sb_resp("POST", "picks", prows_slim, prefer="return=minimal")
            if r2.status_code >= 400:
                print(f"   ⚠ [DB] picks insert imefeli: HTTP {r2.status_code} {r2.text[:160]} — "
                      f"angalia schema (RUN schema_v2.sql ili kupata columns za prob)")
            else:
                print("   ⚠ [DB] imehifadhiwa BILA p_model/p_cal (schema_v2 haijarun — fanya hivo)")
    print(f"== [DB] picks {len(prows)} zimehifadhiwa siku {day}.")

    # ── PHASE 5: BETSLIPS (safest subset kufikia lengo odds, joint-P max) ──────
    slips = []
    try:
        import slip as _slip
        slips = _slip.build_slips(payload["picks"], topk=5, log=print)
        payload["slips"] = slips
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠ [slips] imeshindika: {str(e)[:110]}")

    if slips:
        try:
            sb("DELETE",
               f"slips?day=eq.{day}", prefer="return=minimal")
            r_sl = sb_resp("POST", "slips", [{
                "day": day, "label": s["label"], "legs": s["legs_n"],
                "total_odds": s["total_odds"], "joint_prob": s["joint_prob"],
                "ev": s.get("ev"), "engine_version": ENGINE_VERSION} for s in slips],
                prefer="return=representation")
            if r_sl and r_sl.status_code in (200, 201):
                srows = r_sl.json()
                idmap = {r["label"]: r["id"] for r in srows}
                legs_rows = []
                for s in slips:
                    sid = idmap.get(s["label"])
                    for l in s["legs"]:
                        legs_rows.append({"slip_id": sid, "home": l["home"], "away": l["away"],
                                          "market": l["market"], "tip": l["tip"],
                                          "odds": l.get("bk_odds"), "p_cal": l.get("p_cal")})
                if legs_rows:
                    sb("POST", "slip_legs", legs_rows, prefer="return=minimal")
                print(f"   [SLIPS] {len(slips)} slips zimehifadhiwa Supabase ✓")
            else:
                print("   [SLIPS] table haipo — RUN schema_v2.sql Supabase (kuweza ku-save slips)")
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠ [SLIPS] save ikishindwa: {str(e)[:110]}")
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
        rows = sb_all("picks?result=eq.pending&select=day&order=day,id")
        days = sorted({r["day"] for r in (rows or []) if r["day"] < today_eat().isoformat()})
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
        pending = sb("GET", f"picks?day=eq.{d}&result=eq.pending&select=*")
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
    rows = sb("GET", f"slips?day=eq.{day_iso}&result=eq.pending") or []
    if not rows:
        return
    for s in rows:
        legs = sb("GET", f"slip_legs?slip_id=eq.{s['id']}") or []
        if not legs:
            continue
        # result ya kila leg kutoka picks table (home+away+market+tip match)
        done = True
        res_of = []
        for l in legs:
            kws = (f"day=eq.{day_iso}&home=eq.{urllib.parse.quote(l['home'])}"
                   f"&away=eq.{urllib.parse.quote(l['away'])}")
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
    pr = sb("GET", f"picks?day=eq.{day_iso}&select=*") or []
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
        cached = sb("GET", f"day_cache?day=eq.{today}&select=day") or []
        if not cached:
            print(f"== [DAEMON] leo {today} haijachotwa — inachota sasa hivi…")
            cmd_run(today, min_prob, False, False)
            last_run = today
        pend = sb("GET", "picks?result=eq.pending&select=day&order=day&limit=200") or []
        if any(p["day"] < today for p in pend):
            print("== [DAEMON] kuna picks za zamani zisizo-settled — settle scratch…")
            cmd_settle()
            last_settle = today
    except Exception as e:  # noqa: BLE001
        print("  !! catch-up imekwanguka:", e)
    while True:
        try:
            now = _dt.datetime.now()
            t = now.strftime("%Y-%m-%d")
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
