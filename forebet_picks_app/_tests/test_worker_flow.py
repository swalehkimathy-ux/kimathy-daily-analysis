"""Worker flow (offline): DB row mapping, verified scraping, run isolation, settlement and EAT."""
import sys, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "forebet_picks_app")); sys.path.insert(0, str(ROOT / "forebet_backend"))
import worker, scraper

# 1) rec_to_row: scraper hutumia "st" — status + final scores lazima zihifadhiwe
r_ft = scraper.empty_rec(home="A & B FC", away="C", st="FT", sc=[2, 1], dt=dt.datetime(2099, 1, 1, 18))
r_sch = scraper.empty_rec(home="D", away="E", st="Scheduled", sc=None, dt=dt.datetime(2099, 1, 1, 18))
r_live = scraper.empty_rec(home="F", away="G", st="67'", sc=[1, 0], dt=dt.datetime(2099, 1, 1, 18))
row = worker.rec_to_row("2099-01-01", "football", r_ft)
assert row["status"] == "FT" and (row["final_home"], row["final_away"]) == (2, 1), row
assert worker.rec_to_row("2099-01-01", "football", r_sch)["final_home"] is None
assert worker.rec_to_row("2099-01-01", "football", r_live)["final_home"] is None
back = worker.row_to_rec({**row, "day": "2099-01-01"})
assert back["st"] == "FT" and back["sc"] == [2, 1]

# 2) finals: FT / Postponed / Walkover
f = worker._finals_from_records({"football": [r_ft, scraper.empty_rec(home="X", away="Y", st="Postp.")],
                                 "tennis": [scraper.empty_rec(home="P", away="Q", st="Walkover")]})
assert f[("A & B FC", "C")] == (2, 1) and f[("X", "Y")] == ("VOID", None) and f[("P", "Q")][0] == "VOID"

# 3) sb_resp: HTTP error → status_code (hairushi)
orig_sb, orig_resp = worker.sb, worker.sb_resp
def boom(*a, **k): raise RuntimeError("Supabase POST slips → HTTP 404: nope")
worker.sb = boom
r = worker.sb_resp("POST", "slips", [])
assert r.status_code == 404 and "nope" in r.text
worker.sb = lambda *a, **k: [{"id": 7, "label": "SAFEST"}]
r = worker.sb_resp("POST", "slips", [])
assert r.status_code == 200 and r.json()[0]["id"] == 7

# 4) cmd_scrape verifies the records in DB before reporting success, and settles yesterday.
calls, db_matches, cache, patches = [], [], {}, []
pending_pick = {"id": 1, "sport": "football", "home": "A & B FC", "away": "C",
                "market": "1X2", "tip": "1", "result": "pending"}
fail_match_upsert = False

def fake_sb(method, path, body=None, prefer=None, timeout=30):
    global fail_match_upsert
    calls.append((method, path, body))
    if method == "POST" and path.startswith("day_cache?"):
        cache.update(body if isinstance(body, dict) else {})
        return None
    if method == "PATCH" and path.startswith("day_cache?"):
        cache.update(body if isinstance(body, dict) else {})
        return None
    if method == "POST" and path.startswith("matches?"):
        if fail_match_upsert:
            raise RuntimeError("Supabase POST matches → HTTP 503: test failure")
        for item in (body if isinstance(body, list) else [body]):
            key = (item["day"], item["sport"], item["home"], item["away"])
            db_matches[:] = [r for r in db_matches if (r["day"], r["sport"], r["home"], r["away"]) != key]
            db_matches.append(item)
        return None
    if method == "GET" and path.startswith("matches?"):
        day = path.split("day=eq.", 1)[1].split("&", 1)[0]
        rows = [r for r in db_matches if r["day"] == day]
        return rows[:1] if "limit=1" in path else rows
    if method == "GET" and path.startswith("analysis_runs?"):
        return []
    if method == "GET" and path.startswith("picks?day=eq.2099-01-01&result=eq.pending"):
        return [dict(pending_pick)]
    if method == "PATCH" and path.startswith("picks?id=eq.1"):
        patches.append((method, path, body)); return None
    if method == "PATCH" and path.startswith("matches?"):
        patches.append((method, path, body)); return None
    if method == "DELETE" and path.startswith("day_cache?"):
        raise AssertionError("day_cache yenye historia isifutwe")
    return []

worker.sb = fake_sb
worker.settle_slips = lambda d: None
collect_calls = []
def fake_collect(sport, day, enrich, log):
    collect_calls.append((sport, day, enrich))
    if sport != "football": return []
    return [r_ft] if day == "2099-01-01" else [r_sch]
scraper.collect = fake_collect
out = worker.cmd_scrape("2099-01-02", no_enrich=True)
assert out["status"] == "succeeded" and out["stored_day"] == 1 and out["stored_yday"] == 1, out
assert all(not enrich for _, _, enrich in collect_calls), "scrape haipaswi ku-enrich H2H kwa mechi zote"
assert cache["scrape_status"] == "succeeded" and cache["scraped_at"], cache
assert any(m == "POST" and p.startswith("matches?") for m, p, _ in calls)
assert any(m == "PATCH" and p.startswith("picks?id=eq.1") and b["result"] == "win" for m, p, b in patches)
assert any(m == "PATCH" and "A%20%26%20B%20FC" in p and b == {"final_home": 2, "final_away": 1}
           for m, p, b in patches), patches

# Failed DB upsert is not called a successful scrape.
fail_match_upsert = True
_, failed_report = worker._scrape_day("2099-01-03", return_report=True, log=lambda *_: None)
assert failed_report["status"] == "failed" and failed_report["stored_count"] == 0, failed_report
fail_match_upsert = False

# 5) A fresh engine run with no picks is a valid empty result and does not delete prior runs.
delete_calls = []
def no_delete_sb(method, path, *args, **kwargs):
    delete_calls.append((method, path)); return None
worker.sb = no_delete_sb
run_events = []
def fake_resp(method, path, body=None, prefer=None, timeout=30):
    run_events.append((method, path, body))
    if method == "POST" and path == "analysis_runs":
        return worker._Resp(201, '[{"id": 55}]')
    if method == "PATCH" and path.startswith("analysis_runs?id=eq.55"):
        return worker._Resp(204, "")
    return worker._Resp(204, "")
worker.sb_resp = fake_resp
run_id, slips = worker._persist_engine_run("2099-01-02", {"picks": []}, 1)
assert run_id == 55 and slips == []
assert any(m == "PATCH" and b.get("status") == "succeeded" for m, _, b in run_events)
assert not any(m == "DELETE" for m, _ in delete_calls), delete_calls

# 6) EAT date: independent of host timezone.
assert worker.today_eat() == dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date()
worker.sb, worker.sb_resp = orig_sb, orig_resp
print("✓ worker flow: verified scrape/save, no false success, run history retained, results settled, EAT OK")
