"""Worker flow (offline): rec_to_row/row_to_rec, finals, sb_resp, cmd_scrape → settle.
Inazuia hitilafu za v2.8 crosscheck zisirudi (st/status, final_home/away, URL-encode, status_code)."""
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
assert worker.rec_to_row("2099-01-01", "football", r_live)["final_home"] is None   # live ≠ final
back = worker.row_to_rec({**row, "day": "2099-01-01"})
assert back["st"] == "FT" and back["sc"] == [2, 1]

# 2) finals: FT / Postponed / Walkover
f = worker._finals_from_records({"football": [r_ft, scraper.empty_rec(home="X", away="Y", st="Postp.")],
                                 "tennis": [scraper.empty_rec(home="P", away="Q", st="Walkover")]})
assert f[("A & B FC", "C")] == (2, 1) and f[("X", "Y")] == ("VOID", None) and f[("P", "Q")][0] == "VOID"

# 3) sb_resp: HTTP error → status_code (hairushi)
orig_sb = worker.sb
def boom(*a, **k): raise RuntimeError("Supabase POST slips → HTTP 404: nope")
worker.sb = boom
r = worker.sb_resp("POST", "slips", [])
assert r.status_code == 404 and "nope" in r.text
worker.sb = lambda *a, **k: [{"id": 7, "label": "SAFEST"}]
r = worker.sb_resp("POST", "slips", [])
assert r.status_code == 200 and r.json()[0]["id"] == 7

# 4) cmd_scrape: siku + jana → settle jana kwa safu sahihi + URL-encode; 0 mechi → SystemExit(2)
calls = []
def fake_sb(method, path, body=None, prefer=None, timeout=30):
    calls.append((method, path, body))
    if method == "GET" and path.startswith("picks?day=eq.2099-01-01&result=eq.pending"):
        return [{"id": 1, "sport": "football", "home": "A & B FC", "away": "C", "market": "1X2", "tip": "1"}]
    return []
worker.sb = fake_sb
worker.settle_slips = lambda d: None
ENRICH_FLAGS = []
def fake_collect(sport, day, enrich, log):
    ENRICH_FLAGS.append(enrich)
    if sport != "football": return []
    return [r_ft] if day == "2099-01-01" else [r_sch]
scraper.collect = fake_collect
out = worker.cmd_scrape("2099-01-02", no_enrich=True)
assert out == {"day": 1, "yday": 1, "finals": 1}, out
assert ENRICH_FLAGS and not any(ENRICH_FLAGS), "Scraper HAIPASWI kufungua H2H ya kila mechi (1000+ = saa 1.5)"
saves = [p for m, p, _ in calls if m == "POST" and p.startswith("matches?")]
dc = [i for i, (m, p, _) in enumerate(calls) if m == "POST" and p.startswith("day_cache")]
ms = [i for i, (m, p, _) in enumerate(calls) if m == "POST" and p.startswith("matches?")]
assert saves and dc and dc[0] < ms[0], "day_cache lazima itangulie matches (FK)"
assert not any(m == "DELETE" and p.startswith("day_cache") for m, p, _ in calls), "DELETE day_cache haitakiwi"
pp = [(p, b) for m, p, b in calls if m == "PATCH" and p.startswith("picks?id=eq.1")]
assert pp and pp[0][1]["result"] == "win" and pp[0][1]["final_score"] == "2-1"
mp = [(p, b) for m, p, b in calls if m == "PATCH" and p.startswith("matches?")]
assert mp and "A%20%26%20B%20FC" in mp[0][0] and mp[0][1] == {"final_home": 2, "final_away": 1}, mp

scraper.collect = lambda *a, **k: []
try:
    worker.cmd_scrape("2099-01-02", no_enrich=True); raise AssertionError("ilipaswa SystemExit(2)")
except SystemExit as e:
    assert e.code == 2
worker.sb = orig_sb
# 5) tarehe ya EAT (UTC+3) — haitegemei timezone ya PC
import datetime as _d
assert worker.today_eat() == _d.datetime.now(_d.timezone(_d.timedelta(hours=3))).date()
print("✓ worker flow tests: ALL GREEN (rec↔row, finals, sb_resp, scrape→settle, 0-mechi=rc2, EAT date, no-H2H scrape, incremental save)")
