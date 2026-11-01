#!/usr/bin/env python3
# K96 — Phase 1 (Section 7.4): KUPANDISHA upabe wa Supabase BILA kuchapisha sirri.
# Exit 0 = yote PASS · Exit 2 = FAIL moja au zaidi.
import json, time, datetime as dt
import urllib.request, urllib.error
from pathlib import Path

BACKEND = Path(__file__).resolve().parent

try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import worker
    env = worker.load_env()
    print("✅ [1/7] .env.local ipo na mipangilio (URL/JWT/ref/role/expiry) — PASS")
    P1 = True
except SystemExit:
    print("❌ [1/7] .env.local — FAIL (tazama ujumbe uliopitishwa juu)")
    raise SystemExit(2)

URL = env["SUPABASE_URL"]
SRV = env["SUPABASE_SERVICE_ROLE_KEY"]
ANON = env["SUPABASE_ANON_KEY"]

T = 20
def req(method, path, key, body=None):
    u = URL + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(u, data=data, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "return=minimal"})
    try:
        with urllib.request.urlopen(r, timeout=T) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa: BLE001
        return None, {}, str(e).encode()

ok = True
fails = []

def chk(n, cond, msg):
    global ok
    # print wazi bila sirri
    print(("✅" if cond else "❌"), f"[{n}/7]", msg)
    if not cond:
        fails.append(n)

# 2. service role: rest GET
st, hd, _ = req("GET", "/rest/v1/picks?limit=1", SRV)
chk(2, st == 200, f"service GET picks → HTTP {st}")

# 3. anon: rest GET (read)
st, hd, date_hdr = req("GET", "/rest/v1/picks?limit=1", ANON)
chk(3, st == 200, f"anon GET picks → HTTP {st} (kusoma kunaruhusiwa)")

# 4. anon: write lazima IKATALIWE
st, _, _ = req("POST", "/rest/v1/picks", ANON, {"day": "1999-01-01", "home": "A", "away": "B",
                                               "market": "m", "tip": "t"})
chk(4, st in (401, 403), f"anon POST picks → HTTP {st} (lazima 401/403)")

# 5. zinahitajika tables/views zi-halisi
need = ["day_cache", "matches", "picks", "engine_stats"]
newo = ["odds_snapshots", "slips", "slip_legs", "calibration"]
miss, ng = [], []
for t in need + newo:
    st, _, _ = req("GET", f"/rest/v1/{t}?limit=1", SRV)
    if st == 200:
        pass
    elif t in need:
        miss.append(t)
    else:
        ng.append(t)
if not miss:
    addo = f" · phase TABLES buadaye zikosekana (OK kwa sasa): {', '.join(ng)}" if ng else " · yote yanapatikana"
    chk(5, True, f"tables core zote zipo ✓{addo}")
else:
    chk(5, False, f"tables zinazokosekana: {', '.join(miss)}")

# 6. round trip: day_cache → picks insert → delete yote (service role)
req("DELETE", "/rest/v1/picks?day=eq.1999-01-01", SRV)
req("DELETE", "/rest/v1/day_cache?day=eq.1999-01-01", SRV)
stA, _, eA = req("POST", "/rest/v1/day_cache", SRV,
                 {"day": "1999-01-01", "notes": "K96 test"})
marker = {"day": "1999-01-01", "sport": "football", "home": "TEST_HOME_K96",
          "away": "TEST_AWAY_K96", "market": "TEST", "tip": "T", "conf": 50, "forebet": 50,
          "rank": 1, "why": []}
stB, _, eB = req("POST", "/rest/v1/picks", SRV, marker)
if stA in (200, 201, 204, 409) and stB in (200, 201, 204, 409):
    stC, _, _ = req("DELETE", "/rest/v1/picks?day=eq.1999-01-01", SRV)
    stD, _, _ = req("DELETE", "/rest/v1/day_cache?day=eq.1999-01-01", SRV)
    chk(6, stC in (200, 204) and stD in (200, 204),
        f"round trip → {stA}/{stB} → delete {stC}/{stD}")
else:
    chk(6, False, f"insert test-row → cache {stA}, picks {stB}: {eB[:120]!r}")

# 7. skew ya saa (EAT vs server Date)
try:
    from email.utils import parsedate_to_datetime
    d0 = None
    _, hd, _ = req("GET", "/rest/v1/picks?limit=1", SRV)
    dsev = parsedate_to_datetime(hd.get("Date")) if hd.get("Date") else None
    skew = abs((dsev.timestamp() - time.time())) if dsev else 0
    warn = " (skew kubwa: sanidi saa ya PC)" if skew > 120 else ""
    chk(7, skew <= 120, f"saa skew {skew:.0f}s{warn}")
except Exception as e:  # noqa: BLE001
    chk(7, False, f"saa check haiwezi: {e}")

print()
print("╔═══ MATOKEO:", "YOTE YAMEFANIKIWA ✓" if not fails else f"FAIL: {sorted(set(fails))}", "═══╗")
raise SystemExit(0 if not fails else 2)
