"""Kinga ya bookie (v2.8.3): Run Engine isikwame bookie zikiwa down/polepole.
(a) betway+betPawa down → day_index inajaribiwa MARA MOJA tu kwa siku (_DOWN)
(b) index OK lakini markets zinafeli → breaker FAIL_BREAK inaiacha bookie
(c) polepole → PROVIDER_BUDGET_S inakata, zilizobaki ni model-only
Hakuna mtandao halisi — _get zote zimebadilishwa (monkeypatch)."""
import sys, time, importlib, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scraper, bookie, betway, random

random.seed(96)
def _name():                         # majina tofauti kabisa (Home5 vs Home15 = AMBIGUOUS kwenye matching)
    return "".join(random.choice("bcdfghjklmnprstvwz") + random.choice("aeiou") for _ in range(4)).title()
H = [_name() for _ in range(300)]; A = [_name() for _ in range(300)]

D = "2099-07-01"
REC = [scraper.empty_rec(home=H[i], away=A[i], league="L", p=[50, 25, 25],
                         od=[1.8, 3.5, 4.0], dt=dt.datetime(2099, 7, 1, 15)) for i in range(300)]
EPOCH = int(dt.datetime(2099, 7, 1, 12, tzinfo=dt.timezone.utc).timestamp())

def fresh(bw_get, pw_get, budget=480):
    for m in (betway, bookie):
        importlib.reload(m)
    bookie.PROVIDER_BUDGET_S = budget
    betway._get, bookie._get = bw_get, pw_get
    logs = []
    return bookie.make_provider(D, logs.append), logs

NET = {"bw": 0, "pw": 0}
def bw_down(*a, **k):
    NET["bw"] += 1; time.sleep(0.05); raise betway.BetwayError("timed out")
def pw_down(*a, **k):
    NET["pw"] += 1; time.sleep(0.05); raise bookie.BookieError("timed out")

# (a) zote down
prov, logs = fresh(bw_down, pw_down)
t = time.time()
for r in REC:
    assert prov(r, "football")["found"] is False
el = time.time() - t
assert NET["bw"] <= 1 and NET["pw"] <= 1, NET          # mara moja tu, si 300×
assert el < 5, el
assert any("betway haifikiki" in l for l in logs) and any("betPawa haifikiki" in l for l in logs), logs
# verify_pick nayo inarudi haraka na api_down
v = bookie.verify_pick({"sport": "football", "market": "1X2", "tip": "1", "home": H[1], "away": A[1]}, D, lambda *a: None)
assert v.get("api_down") is True, v
assert NET["bw"] <= 1 and NET["pw"] <= 1, NET
print(f"  (a) down: {el:.2f}s · maombi betway {NET['bw']} · betPawa {NET['pw']} ✓")

# (b) index OK, markets 500 → breaker
NET.update(bw=0, pw=0, idx=0, mk=0)
def bw_idx_ok(path_q, *a, **k):
    NET["bw"] += 1
    if "Highlights" in path_q:
        NET["idx"] += 1
        return {"events": [{"eventId": i, "homeTeam": H[i], "awayTeam": A[i], "league": "L",
                            "expectedStartEpoch": EPOCH} for i in range(300)]} if NET["idx"] == 1 else {"events": []}
    NET["mk"] += 1
    raise betway.BetwayError("markets 500")
prov, logs = fresh(bw_idx_ok, pw_down)
for r in REC:
    prov(r, "football")
mk = NET["mk"]
assert mk <= bookie.FAIL_BREAK + 1, NET                # breaker: si 300 maombi ya markets
assert any("mfululizo" in l for l in logs), logs
print(f"  (b) markets fail: maombi ya markets {mk} (breaker={bookie.FAIL_BREAK}) ✓")

# (c) polepole → budget
SL = {"idx": 0}
def bw_slow(path_q, *a, **k):
    if "Highlights" in path_q:
        SL["idx"] += 1
        return {"events": [{"eventId": i, "homeTeam": H[i], "awayTeam": A[i], "league": "L",
                            "expectedStartEpoch": EPOCH} for i in range(300)]} if SL["idx"] == 1 else {"events": []}
    time.sleep(0.05); return {}
prov, logs = fresh(bw_slow, pw_down, budget=1)
t = time.time()
for r in REC:
    prov(r, "football")
el = time.time() - t
assert el < 4, el
assert any("muda wa devig" in l for l in logs), logs
print(f"  (c) polepole: {el:.2f}s na budget 1s ✓")
print("✓ bookie guard tests: ALL GREEN (down-memo, breaker, budget, verify api_down)")
