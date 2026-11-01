#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K96 PICKS — GUI server (local web GUI, hakuna dependencies mpya!).
Inatumia http.server ya Python pekee. Bind 0.0.0.0 ili preview ionekane.

Endpoints:
  GET  /                 → index.html (GUI)
  GET  /logo_k96.png     → logo
  GET  /api/day?day=&demo=1|0 → picks za siku (demo = engine inatengeneza synthetic, real = Supabase)
  GET  /api/status       → day_cache + engine_stats
  POST /api/run          → {day, min_prob, enrich} → subprocess worker.py run (async job)
  POST /api/settle       → job ya settle
  GET  /api/job?id=      → {done, log}
"""
import datetime as _dt
import json
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
_BUNDLE = BACKEND
if getattr(sys, "frozen", False):                       # ndani ya .exe (PyInstaller)
    BACKEND = Path(sys.executable).resolve().parent     # sehemu ya kuandika (karibu na exe)
    _BUNDLE = Path(sys._MEIPASS)                        # resources za ndani ya exe
APP = _BUNDLE / "forebet_picks_app" if getattr(sys, "frozen", False) else BACKEND.parent / "forebet_picks_app"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(_BUNDLE))


def res_path(name):
    """Angalia karibu na exe kwanza (user anaweza badilisha), halafu ndani ya bundle."""
    for base in (BACKEND, _BUNDLE):
        cand = base / name
        if cand.exists():
            return cand
    return BACKEND / name

HOST, PORT = "0.0.0.0", 8777
APP_VERSION = "2.8.3"
_EAT = _dt.timezone(_dt.timedelta(hours=3))


def today_eat():
    """Tarehe ya leo kwa saa za Afrika Mashariki (EAT) — haitegemei saa/timezone ya PC."""
    return _dt.datetime.now(_EAT).date()


def con(msg):
    """Andika kwenye console (dirisha jeusi) — mtumiaji aone kila hatua."""
    try:
        print(f"[{_dt.datetime.now(_EAT):%H:%M:%S}] {msg}", flush=True)
    except Exception:  # noqa: BLE001
        pass
JOBS = {}          # job_id -> {"done": bool, "log": str, "rc": int|None}


# ─────────────────────────── Demo data (synthetic, halisi-look) ──────────────────
def demo_records(day):
    """Records za mfano zenye muonekano halisi — engine itazichambua (si manual).
    League zote zina 'K96 TEST' ili ziweze kutofautishwa na data halisi."""
    import engine
    D = _dt.datetime.fromisoformat(day).replace(hour=20, minute=0)

    def mk(sport, p, od, home, away, league, ps=None, avg=None, hf=None, af=None,
           hp="", ap="", h2h="", kelly=None, hh=20):
        dt = D.replace(hour=hh)
        return {"dt": dt, "league": "K96 TEST " + league, "home": home, "away": away,
                "status": "Scheduled", "p": p, "ps": ps, "avg": avg, "od": od,
                "url": f"forebet/{home}-{away}", "h2h": h2h, "hf": hf or [], "af": af or [],
                "hp": hp, "ap": ap, "kelly": kelly}

    return {
        "football": [
            mk("f", [92, 6, 2], [1.15, 7.0, 15.0], "Bayern Munich", "Bochum",
               "Bundesliga", ps=[3, 0], avg=3.0, hp="1", ap="15",
               hf=["W", "W", "W", "D", "W"], af=["L", "L", "D", "L", "W"], kelly=0.14, hh=19),
            mk("f", [57, 30, 13], [1.35, 5.2, 8.0], "Liverpool", "Tottenham",
               "Premier League", ps=[3, 1], avg=3.2, hp="2", ap="9",
               hf=["W", "W", "W", "W", "D"], af=["L", "D", "L", "L", "D"],
               h2h="10 meetings: Liverpool 6W - 2D - 2L vs Tottenham.", kelly=0.13),
            mk("f", [40, 32, 28], [2.60, 3.3, 2.8], "Man City", "Chelsea",
               "Premier League", ps=[2, 1], avg=3.4, hp="4", ap="6", hh=21),
            mk("f", [45, 33, 22], [1.75, 3.4, 4.5], "Genoa", "Torino",
               "Serie A", ps=[1, 0], avg=1.8, hp="12", ap="14", hh=22),
            mk("f", [88, 9, 3], [1.30, 5.0, 9.5], "Real Madrid", "Al Nassr",
               "Club Friendlies", ps=[2, 0], avg=2.2, hp="2", ap="45", hh=23),
        ],
        "basketball": [
            mk("b", [88, None, 12], [1.22, 4.8], "LA Lakers", "Chicago Bulls", "NBA",
               avg=201.5, hh=23),
        ],
        "tennis": [
            mk("t", [81, None, 19], [1.30, 3.4], "I. Swiatek", "C. Gauff", "WTA Finals",
               avg=22.4, hh=18),
        ],
    }


def demo_payload(day):
    import engine
    records = demo_records(day)
    engine.MIN_CONF = 80
    engine.RELAX_STEPS = [80, 75, 70]
    picks_, used_min = engine.analyze_day(records, log=lambda s: None)
    out = []
    for p in picks_:
        p = dict(p)
        p["pred_score"] = "{}-{}".format(*p["ps"]) if p.get("ps") and None not in p["ps"] else ""
        p.pop("ps", None)
        p["day"] = day
        out.append(p)
    counts = {s: len(v) for s, v in records.items()}
    return {"day": day, "min_prob": used_min, "total_picks": len(out),
            "counts": counts, "picks": out, "mode": "demo"}


def real_payload(day):
    from worker import sb, sb_all
    prows = sb("GET", f"picks?day=eq.{day}&select=*&order=rank") or []
    mrows = sb_all(f"matches?day=eq.{day}&select=sport&order=id")
    counts = {}
    for m in mrows:
        counts[m["sport"]] = counts.get(m["sport"], 0) + 1
    picks = []
    for p in prows:
        picks.append({
            "sport": p["sport"], "rank": p.get("rank"), "time": p.get("time_eat") or "",
            "league": p.get("league") or "", "home": p["home"], "away": p["away"],
            "match": f'{p["home"]} vs {p["away"]}', "market": p["market"], "tip": p["tip"],
            "conf": p["conf"], "forebet": p["forebet"], "odd": p.get("odd"),
            "odds": p.get("odd"), "pred_score": "", "avg": None, "status": p.get("result") or "",
            "why": p.get("why") or [], "result": p.get("result"), "final": p.get("final_score"),
            "day": day,
        })
    return {"day": day, "min_prob": None, "total_picks": len(picks), "counts": counts,
            "picks": picks, "mode": "live", "note": "Supabase"}


def status_payload():
    try:
        from worker import sb
        days = sb("GET", "day_cache?select=*&order=day.desc&limit=7") or []
        stats = sb("GET", "engine_stats?select=*") or []
        return {"ok": True, "days": days, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "days": [], "stats": []}


def _results_from_picks(picks, finals=None):
    """picks + (optional finals map {(home,away):(fh,fa)}) → result per pick kupitia worker.settle_pick."""
    from worker import settle_pick
    out = []
    for p in picks:
        q = dict(p)
        fh = fa = None
        if p.get("final") and "-" in str(p.get("final")):
            try:
                fh, fa = [int(x) for x in str(p["final"]).split("-")][:2]
            except Exception:
                fh = fa = None
        elif finals and (p["home"], p["away"]) in finals:
            fh, fa = finals[(p["home"], p["away"])]
            q["final"] = f"{fh}-{fa}"
        q["result"] = settle_pick(p["market"], p["tip"], fh, fa) if (fh is not None and fa is not None) else "pending"
        out.append(q)
    return out


def results_payload(day=None, demo=False):
    """Historia ya mikeka: tip vs matokeo halisi + hit-rate (engine learning)."""
    by_day = {}
    if demo:
        for off in (2, 1):                       # juzi na jana
            d = (today_eat() - _dt.timedelta(days=off)).isoformat()
            if day and d != day:
                continue                           # date selector ya results-tab
            pay = demo_payload(d)
            finals = {
                ("Bayern Munich", "Bochum"): (3, 0), ("Liverpool", "Tottenham"): (3, 1),
                ("Man City", "Chelsea"): (1, 0) if off == 1 else (2, 2),
                ("Genoa", "Torino"): (1, 0), ("Real Madrid", "Al Nassr"): (2, 2),
                ("LA Lakers", "Chicago Bulls"): (108, 101) if off == 1 else (99, 108),
                ("I. Swiatek", "C. Gauff"): (2, 1),
            }
            rows = _results_from_picks(pay["picks"], finals)
            by_day[d] = [r for r in rows if r["result"] != "pending"]
    else:
        from worker import sb
        # onyesha PIA zilizo pending (chip ya ⏳): mtu ajue matokeo yabaki bado
        if day:
            qs = f"picks?day=eq.{day}&select=*&order=rank"
        else:
            qs = "picks?select=*&order=day.desc,rank&limit=150"
        for p in sb("GET", qs) or []:
            by_day.setdefault(p["day"], []).append({
                "sport": p["sport"], "home": p["home"], "away": p["away"],
                "match": f'{p["home"]} vs {p["away"]}', "league": p.get("league") or "",
                "market": p["market"], "tip": p["tip"], "conf": p["conf"],
                "forebet": p["forebet"], "final": p.get("final_score") or "",
                "result": p.get("result"), "day": p["day"], "rank": p.get("rank"),
            })
    tot_w = tot_l = tot_p = 0
    per_mkt = {}
    for d, rows in by_day.items():
        for r in rows:
            if r["result"] == "win": tot_w += 1
            elif r["result"] == "loss": tot_l += 1
            elif r["result"] == "push": tot_p += 1
            if r["result"] in ("win", "loss"):
                s = per_mkt.setdefault(r["market"], {"w": 0, "l": 0})
                s["w" if r["result"] == "win" else "l"] += 1
    played = tot_w + tot_l
    overall = {"settled": played + tot_p, "wins": tot_w, "losses": tot_l, "push": tot_p,
               "hit": round(100.0 * tot_w / played, 1) if played else None,
               "per_market": {k: round(100.0 * v["w"] / (v["w"] + v["l"]), 1) for k, v in per_mkt.items()}}
    days = [{"day": d, "picks": rows} for d, rows in sorted(by_day.items(), reverse=True)]
    return {"ok": True, "days": days, "overall": overall, "mode": "demo" if demo else "live"}


def running_job():
    for k, v in JOBS.items():
        if not v.get("done") and v.get("mode") in ("run", "scrape", "settle"):
            return k
    return None


def start_job(mode, day=None, min_prob=80, enrich=True):
    busy = running_job()
    if busy and mode in ("run", "scrape", "settle"):
        con(f"JOB {busy} bado inaendelea — naunganisha GUI nayo (hakuna kazi mpya)")
        return busy
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"done": False, "log": "", "rc": None, "mode": mode, "day": day}
    logdir = BACKEND / "logs"
    try:
        logdir.mkdir(exist_ok=True)
        logf = open(logdir / f"{_dt.datetime.now(_EAT):%Y-%m-%d_%H%M%S}_{mode}_{day or 'leo'}.log",
                    "a", encoding="utf-8")
    except Exception:  # noqa: BLE001
        logf = None
    con(f"JOB {jid}: {mode} · siku {day or today_eat()} — imeanza")

    def _add(s):
        JOBS[jid]["log"] += s
        if logf:
            try:
                logf.write(s); logf.flush()
            except Exception:  # noqa: BLE001
                pass

    def _finish(rc):
        JOBS[jid]["rc"] = rc
        JOBS[jid]["done"] = True
        con(f"JOB {jid}: {mode} — imeisha (rc={rc})" + ("" if rc == 0 else "  ← angalia Activity Log / folda logs"))
        if logf:
            try:
                logf.close()
            except Exception:  # noqa: BLE001
                pass

    class _Cap:                                             # redirect print → job log
        def write(self, s):
            if s:
                _add(s)
        def flush(self):
            pass

    def inproc():                                           # ndani ya .exe — haina python mwingine
        import contextlib
        import worker
        try:
            with contextlib.redirect_stdout(_Cap()), contextlib.redirect_stderr(_Cap()):
                if mode == "run":
                    worker.cmd_run(day, min_prob, force=False, no_enrich=not enrich)
                elif mode == "scrape":
                    worker.cmd_scrape(day or today_eat().isoformat())
                elif mode == "settle":
                    worker.cmd_settle(day=day)
                else:
                    worker.cmd_status()
            rc = 0
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
        except Exception as e:  # noqa: BLE001
            import traceback
            _add(f"\n!!! error: {e}\n{traceback.format_exc()}")
            rc = 1
        _finish(rc)

    if getattr(sys, "frozen", False):
        threading.Thread(target=inproc, daemon=True).start()
        return jid

    cmd = [sys.executable, "-u", str(_BUNDLE / "worker.py"), mode]
    if day:
        cmd += ["--date", day]
    if mode == "run":
        cmd += ["--min-prob", str(min_prob)]
        if not enrich:
            cmd += ["--no-enrich"]

    def bg():
        import os
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
        rc = 1
        try:
            proc = subprocess.Popen(cmd, cwd=str(BACKEND), env=env, encoding="utf-8", errors="replace",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
            _add(f"> {' '.join(cmd[1:])}\n")
            for line in proc.stdout:
                _add(line)
                s = line.strip()
                if s.startswith(("==", "━━━", "✓", "✗", "!!", "⚠", "   [football]", "   [basketball]", "   [tennis]")):
                    con("   " + s[:150])
            proc.wait(timeout=1800)
            rc = proc.returncode
        except Exception as e:  # noqa: BLE001
            _add(f"\n!!! error: {e}")
        _finish(rc)

    threading.Thread(target=bg, daemon=True).start()
    return jid


# ─────────────────────────── HTTP handler ──────────────────────────────────────────
# ────────────────── SEED/CLEAN demo → Supabase (testing ya pipeline halisi) ──────
FINALS_DEMO = {("Bayern Munich", "Bochum"): (3, 0), ("Liverpool", "Tottenham"): (3, 1),
               ("Man City", "Chelsea"): (1, 0), ("Genoa", "Torino"): (1, 0),
               ("Real Madrid", "Al Nassr"): (2, 2), ("LA Lakers", "Chicago Bulls"): (108, 101),
               ("I. Swiatek", "C. Gauff"): (2, 1)}


def seed_demo(day):
    """Andika demo-records kwenye Supabase (kama worker) → engine → picks.
    Huithibitisha cache-mode: ikitumwa mara ya pili, DB inarudia zile-zile."""
    from worker import sb, rec_to_row
    import engine
    records = demo_records(day)
    rows = [rec_to_row(day, s, r) for s, rs in records.items() for r in rs]
    sb("POST", "day_cache?on_conflict=day",
       {"day": day, "match_count": len(rows), "engine_version": "seed-demo"},
       prefer="resolution=merge-duplicates,return=minimal")
    sb("POST", "matches?on_conflict=day,sport,home,away", rows,
       prefer="resolution=merge-duplicates,return=minimal")
    engine.MIN_CONF = 80
    engine.RELAX_STEPS = [80, 75, 70]
    picks_, used = engine.analyze_day(records, log=lambda s: None)
    sb("DELETE", f"picks?day=eq.{day}", prefer="return=minimal")
    prows = [{"day": day, "sport": p["sport"], "league": p.get("league", ""),
              "time_eat": p.get("time", ""), "home": p["home"], "away": p["away"],
              "market": p["market"], "tip": p["tip"], "conf": p["conf"],
              "forebet": p["forebet"], "adj": p.get("adj"), "odd": p.get("odd"),
              "rank": p.get("rank"), "why": p.get("why") or [], "decision": p.get("decision", ""),
              "engine_version": "seed-demo"} for p in picks_]
    if prows:
        sb("POST", "picks", prows, prefer="return=minimal")
    return {"ok": True, "matches": len(rows), "picks": len(prows)}


def seed_results(day):
    """Matokeo bandia → update matches finals + settle picks (pipeline ya 'settle' halisi)."""
    from worker import sb, settle_pick
    n = w = l = 0
    for (home, away), (fh, fa) in FINALS_DEMO.items():
        sb("PATCH", f"matches?day=eq.{day}&home=eq.{urllib.parse.quote(home)}&away=eq.{urllib.parse.quote(away)}",
           {"final_home": fh, "final_away": fa, "status": "Finished"}, prefer="return=minimal")
        for p in sb("GET", f"picks?day=eq.{day}&home=eq.{urllib.parse.quote(home)}&away=eq.{urllib.parse.quote(away)}&result=eq.pending&select=*") or []:
            res = settle_pick(p["market"], p["tip"], fh, fa)
            sb("PATCH", f"picks?id=eq.{p['id']}",
               {"result": res, "final_score": f"{fh}-{fa}", "settled_at": _dt.datetime.utcnow().isoformat()},
               prefer="return=minimal")
            n += 1
            w += res == "win"
            l += res == "loss"
    return {"ok": True, "settled": n, "wins": w, "losses": l}


def cleanup_demo():
    from worker import sb
    d1 = sb("DELETE", "picks?league=ilike.K96%20TEST%25", prefer="return=representation") or []
    d2 = sb("DELETE", "matches?league=ilike.K96%20TEST%25", prefer="return=representation") or []
    # futa day_cache zenye 0 mechi zinazohusiana (siku za jaribio pekee)
    d1 = sb("DELETE", "picks?league=ilike.K96%20TEST%25", prefer="return=representation") or []
    d2 = sb("DELETE", "matches?league=ilike.K96%20TEST%25", prefer="return=representation") or []
    d3 = sb("DELETE", "day_cache?engine_version=eq.seed-demo", prefer="return=representation") or []
    return {"ok": True, "picks_deleted": len(d1), "matches_deleted": len(d2), "days_deleted": len(d3)}


# ─────────────────────────── HTTP handler ──────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", code)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/" or u.path == "/index.html":
                return self._send(res_path("index.html").read_text(encoding="utf-8"))
            if u.path in ("/logo", "/logo_k96.png"):
                return self._send(res_path("logo_k96.png").read_bytes(), "image/png")
            if u.path in ("/api/version", "/api/ping"):
                return self._json({"ok": True, "app": "K96 PICKS", "version": APP_VERSION,
                                   "today_eat": today_eat().isoformat()})
            if u.path == "/api/day":
                day = (q.get("day") or [today_eat().isoformat()])[0]
                demo = (q.get("demo") or ["0"])[0] == "1"
                pl = demo_payload(day) if demo else real_payload(day)
                pl["ok"] = True
                pl["count"] = pl.get("total_picks", len(pl.get("picks") or []))
                pl["min"] = pl.get("min_prob")
                if pl["min"] is None and pl.get("picks"):
                    pl["min"] = min(p.get("conf", 0) for p in pl["picks"])
                return self._json(pl)
            if u.path == "/api/status":
                return self._json(status_payload())
            if u.path == "/api/results":
                demo = (q.get("demo") or ["0"])[0] == "1"
                day = (q.get("day") or [None])[0]
                return self._json(results_payload(day=day, demo=demo))
            if u.path == "/api/running":
                k = running_job()
                return self._json({"ok": True, "job": k, "mode": (JOBS.get(k) or {}).get("mode")})
            if u.path == "/api/job":
                jid = (q.get("id") or [""])[0]
                return self._json(JOBS.get(jid) or {"done": True, "log": "??", "rc": -1})
            if u.path == "/api/slips":
                day = (q.get("day") or [today_eat().isoformat()])[0]
                out = {"ok": True, "day": day, "slips": []}
                try:
                    from worker import sb
                    slips = sb("GET", f"slips?day=eq.{day}&order=id.desc") or []
                    ids = ",".join(str(s["id"]) for s in slips) or "0"
                    legs = sb("GET", f"slip_legs?slip_id=in.({ids})") or []
                    for s_ in slips:
                        s_["legs_list"] = [l for l in legs if l.get("slip_id") == s_["id"]]
                    out["slips"] = slips
                except Exception as e:  # noqa: BLE001
                    out["note"] = f"slips tables hayajapatikana (RUN schema_v2.sql): {str(e)[:90]}"
                return self._json(out)
            if u.path == "/api/calibration":
                out = {"ok": True, "buckets": [], "slips": [], "slip_stats": {}}
                from worker import sb
                try:
                    out["buckets"] = sb("GET", "calibration?select=bucket,n,avg_pred,actual&order=bucket") or []
                except Exception as e:  # noqa: BLE001
                    out["note"] = f"calibration view haipo — RUN schema_v2.sql ({str(e)[:80]})"
                try:
                    out["slips"] = sb("GET", "slips?result=in.(win,loss,void)&order=day.desc&limit=30") or []
                    w = [s for s in out["slips"] if s.get("result") == "win"]
                    out["slip_stats"] = {"n": len(out["slips"]), "win": len(w),
                                         "win_rate": round(len(w) / max(1, len(out["slips"])), 3)}
                except Exception as e:  # noqa: BLE001
                    out.setdefault("note", f"slips table haipo — RUN schema_v2.sql ({str(e)[:80]})")
                return self._json(out)
            if u.path == "/api/settings":
                try:
                    sys.path.insert(0, str(res_path(".").parent / "forebet_picks_app"))
                    import config as _c
                    return self._json({"ok": True, "settings": _c.all_settings()})
                except Exception as e:  # noqa: BLE001
                    return self._json({"ok": False, "error": str(e)[:200]})
            return self._send("404", "text/plain", 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "error": str(e)[:300]}, 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln).decode("utf-8") if ln else "{}"
        try:
            data = json.loads(body or "{}")
        except Exception:
            data = {}
        try:
            if u.path == "/api/run":
                jid = start_job("run", day=data.get("day"),
                                min_prob=int(data.get("min_prob") or 80),
                                enrich=bool(data.get("enrich", True)))
                return self._json({"ok": True, "job": jid})
            if u.path == "/api/scrape":
                jid = start_job("scrape", day=data.get("day"))
                return self._json({"ok": True, "job": jid})
            if u.path == "/api/settle":
                jid = start_job("settle", day=data.get("day") or None)
                return self._json({"ok": True, "job": jid})
            if u.path == "/api/seed_demo":
                return self._json(seed_demo(data.get("day") or today_eat().isoformat()))
            if u.path == "/api/seed_results":
                return self._json(seed_results(data.get("day") or today_eat().isoformat()))
            if u.path == "/api/cleanup_demo":
                return self._json(cleanup_demo())
            if u.path == "/api/calibration":
                out = {"ok": True, "buckets": [], "slips": [], "slip_stats": {}}
                from worker import sb
                try:
                    out["buckets"] = sb("GET", "calibration?select=bucket,n,avg_pred,actual&order=bucket") or []
                except Exception as e:  # noqa: BLE001
                    out["note"] = f"calibration view haipo — RUN schema_v2.sql ({str(e)[:80]})"
                try:
                    out["slips"] = sb("GET", "slips?result=in.(win,loss,void)&order=day.desc&limit=30") or []
                    w = [s for s in out["slips"] if s.get("result") == "win"]
                    out["slip_stats"] = {"n": len(out["slips"]), "win": len(w),
                                         "win_rate": round(len(w) / max(1, len(out["slips"])), 3)}
                except Exception as e:  # noqa: BLE001
                    out.setdefault("note", f"slips table haipo — RUN schema_v2.sql ({str(e)[:80]})")
                return self._json(out)
            if u.path == "/api/settings":
                allowed = {"LEG_ODDS_MIN", "LEG_ODDS_MAX", "SLIP_ODDS_MIN", "SLIP_ODDS_MAX",
                           "MAX_LEGS", "FORCE_LEGS", "MIN_LEG_PROB", "BLOCK_FRIENDLY",
                           "FLAG_PENALTY", "MIN_CONF", "W_MODEL"}
                sys.path.insert(0, str(res_path(".").parent / "forebet_picks_app"))
                import config as _c
                saved = {}
                for k, v in (data or {}).items():
                    if k not in allowed:
                        continue
                    if v in ("", None):
                        v = None
                    _c.set(k, v)
                    saved[k] = v
                return self._json({"ok": True, "saved": saved})
            return self._send("404", "text/plain", 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "error": str(e)[:300]}, 500)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # browser ikifunga connection mapema (refresh/kufunga tab) — si kosa, usitishe mtumiaji
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def _open_browser():
    """Fungua GUI kama dirisha la app (Edge/Chrome --app). Hakuna Electron inayohitajika."""
    import os
    if os.environ.get("K96_NO_BROWSER") == "1" or "--no-browser" in sys.argv:
        return
    url = f"http://127.0.0.1:{PORT}/"

    def go():
        if sys.platform == "win32":
            pf = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
            cands = [os.path.join(b, *p) for b in pf if b for p in (
                ("Microsoft", "Edge", "Application", "msedge.exe"),
                ("Google", "Chrome", "Application", "chrome.exe"))]
            for exe in cands:
                if os.path.exists(exe):
                    try:
                        subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"])
                        return
                    except Exception:  # noqa: BLE001
                        pass
        import webbrowser
        webbrowser.open(url)
    threading.Timer(1.0, go).start()


def _running_version():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/version", timeout=2) as r:
            return json.loads(r.read().decode("utf-8")).get("version")
    except Exception:  # noqa: BLE001
        return None


def main():
    try:
        srv = _Server((HOST, PORT), H)
    except OSError:
        v = _running_version()
        if v == APP_VERSION:
            print(f"K96 PICKS v{v} tayari inaendesha — nafungua dirisha...", flush=True)
            _open_browser(); time.sleep(2)
            return
        print("=" * 66, flush=True)
        print(f"  [X] Port {PORT} inatumiwa na programu nyingine / K96 ya ZAMANI (version: {v or '?'}).", flush=True)
        print("      Funga K96 ya zamani (au restart PC), kisha fungua K96_START.bat tena.", flush=True)
        print("=" * 66, flush=True)
        if sys.stdin and sys.stdin.isatty():
            try:
                input("Bonyeza Enter kufunga...")
            except Exception:  # noqa: BLE001
                pass
        sys.exit(3)
    print("=" * 66, flush=True)
    print(f"  K96 PICKS v{APP_VERSION} iko hewani:  http://127.0.0.1:{PORT}", flush=True)
    print(f"  Leo (EAT): {today_eat().isoformat()}  ·  folda ya backend: {BACKEND}", flush=True)
    print("  Dirisha la app litafunguka. Kama halikufunguka, fungua link hiyo juu.", flush=True)
    print("  USIFUNGE dirisha hili - ukilifunga, app itazimika.", flush=True)
    print("=" * 66, flush=True)
    def _check_sb():
        try:
            from worker import sb
            sb("GET", "day_cache?select=day&limit=1", timeout=15)
            con("[OK] Supabase imeunganishwa (.env.local sawa).")
        except BaseException as e:  # noqa: BLE001
            con(f"[X] Supabase HAIFIKIKI: {str(e)[:160]}")
            con("    Angalia internet na .env.local kwenye folda hii.")
    threading.Thread(target=_check_sb, daemon=True).start()
    _open_browser()
    srv.serve_forever()


if __name__ == "__main__":
    main()
