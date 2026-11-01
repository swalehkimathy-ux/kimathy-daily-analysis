#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K96 SMART ENGINE - RULES DEMO (football, basketball, tennis)
============================================================
Inaonyesha jinsi engine inavyofikiri, hatua kwa hatua, kwa mechi za MFANO.
- Bookmaker odds hapa ni BANDIA (zimetengenezwa na make_book) - ni kwa mfano tu.
- Hakuna network. Python 3.9+ standard library tu.
Endesha:  python rules_demo.py
"""
import math
import re
from itertools import combinations

# ---------------------------------------------------------------- CONFIG
CFG = {
    "LEG_ODDS_MIN": 1.05,    # leg yenye odds chini ya hapa haina maana
    "LEG_ODDS_MAX": 3.50,    # leg hatari sana
    "MIN_LEG_PROB": 0.75,    # probability ya chini inayokubalika kwa leg
    "SLIP_ODDS_MIN": 1.85,
    "SLIP_ODDS_MAX": 2.50,
    "MAX_LEGS": 12,
    "W_MODEL": 0.50,         # uzito wa model dhidi ya bookmaker
    "FLAG_PENALTY": 0.01,    # kila flag inapunguza probability kwa 1 pt
    "MAX_FLAG_PENALTY": 0.03,
    "SD_BASKET_MARGIN": 11.5,   # tofauti ya pointi (kawaida)
    "SD_BASKET_TOTAL": 16.0,
    "SD_TENNIS_GAMES_BO3": 4.0,
    "SD_TENNIS_GAMES_BO5": 5.5,
    "SD_TENNIS_DIFF_BO3": 4.5,
    "SD_TENNIS_DIFF_BO5": 6.0,
}

# ---------------------------------------------------------------- MATH
def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def nppf(p):
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if ncdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2

def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)

def devig(odds, total=1.0):
    """Ondoa margin ya bookmaker: probabilities zinajumlisha 'total'."""
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [i / s * total for i in inv]

def half(x):
    return math.floor(x) + 0.5

# ---------------------------------------------------------------- BLOCK RULES (veto)
BLOCK_SUBSTR = [
    ("friendl", "mechi ya kirafiki (friendly)"),
    ("exhibition", "exhibition"),
    ("u17", "vijana"), ("u18", "vijana"), ("u19", "vijana"), ("u20", "vijana"),
    ("u21", "vijana"), ("u23", "vijana"), ("youth", "vijana"),
    ("women", "wanawake"), ("reserve", "reserves"),
    ("doubles", "doubles (tennis) - tofauti kubwa"),
    ("itf", "ITF ngazi ya chini - data dhaifu"),
    ("esoccer", "esports"), ("virtual", "virtual"),
]

def blocked(m):
    text = f"{m['league']} {m['home']} {m['away']}".lower()
    for sub, why in BLOCK_SUBSTR:
        if sub in text:
            return why
    if m["sport"] != "tennis":   # tennis: "B. Player" ni jina la mtu, si timu B
        for team in (m["home"], m["away"]):
            if re.search(r"\s(w|ii|b)$", re.sub(r"[^\w\s]", "", team.lower())):
                return "timu ya wanawake/akiba (suffix W / II / B)"
    if m.get("status", "Scheduled") != "Scheduled":
        return "mechi si 'Scheduled' (imeanza au imeisha)"
    return None

# ---------------------------------------------------------------- FOOTBALL MODEL
def grid(lh, la, n=11):
    g = [[pois(i, lh) * pois(j, la) for j in range(n)] for i in range(n)]
    s = sum(sum(r) for r in g)
    return [[v / s for v in r] for r in g]

def fit_lambdas(p1, px, p2, avg):
    """Tafuta lambdas (goli za home/away) zinazolingana na 1X2 ya Forebet na avg total."""
    best = None
    for k in range(10, 91):
        s = k / 100
        lh, la = avg * s, avg * (1 - s)
        g = grid(lh, la)
        h = sum(g[i][j] for i in range(11) for j in range(11) if i > j)
        d = sum(g[i][i] for i in range(11))
        a = 1 - h - d
        err = (h - p1) ** 2 + (d - px) ** 2 + (a - p2) ** 2
        if best is None or err < best[0]:
            best = (err, lh, la)
    return best[1], best[2], math.sqrt(best[0])

def football_model(p1, px, p2, avg):
    p1, px, p2 = p1 / 100, px / 100, p2 / 100
    t = p1 + px + p2
    p1, px, p2 = p1 / t, px / t, p2 / t
    lh, la, err = fit_lambdas(p1, px, p2, avg)
    g = grid(lh, la)
    m = {"1": p1, "X": px, "2": p2,
         "1X": p1 + px, "X2": px + p2, "12": p1 + p2,
         "DNB 1": p1 / (p1 + p2), "DNB 2": p2 / (p1 + p2)}
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        over = sum(g[i][j] for i in range(11) for j in range(11) if i + j > L)
        m[f"Over {L}"] = over
        m[f"Under {L}"] = 1 - over
    btts = sum(g[i][j] for i in range(1, 11) for j in range(1, 11))
    m["BTTS Yes"], m["BTTS No"] = btts, 1 - btts
    groups = [(("1", "X", "2"), 1.0), (("1X", "X2", "12"), 2.0), (("DNB 1", "DNB 2"), 1.0),
              (("BTTS Yes", "BTTS No"), 1.0)]
    for L in (0.5, 1.5, 2.5, 3.5, 4.5):
        groups.append(((f"Over {L}", f"Under {L}"), 1.0))
    return m, groups, {"lambda_home": round(lh, 2), "lambda_away": round(la, 2), "fit_err": round(err, 3)}

# ---------------------------------------------------------------- BASKETBALL MODEL
def basketball_model(p_home, avg_total):
    """Winner (OT imejumuishwa) + spread + total points. Margin ~ Normal(mean, sd)."""
    sd, sdt = CFG["SD_BASKET_MARGIN"], CFG["SD_BASKET_TOTAL"]
    ph = p_home / 100
    mean = sd * nppf(ph)                      # wastani wa (home - away) unaolingana na p
    m = {"Home Win": ph, "Away Win": 1 - ph}
    groups = [(("Home Win", "Away Win"), 1.0)]
    for L in (5.5, 9.5):                      # handicap: Home +L  vs  Away -L
        m[f"Home +{L}"] = ncdf((mean + L) / sd)
        m[f"Away -{L}"] = 1 - m[f"Home +{L}"]
        groups.append(((f"Home +{L}", f"Away -{L}"), 1.0))
        m[f"Away +{L}"] = ncdf((L - mean) / sd)
        m[f"Home -{L}"] = 1 - m[f"Away +{L}"]
        groups.append(((f"Away +{L}", f"Home -{L}"), 1.0))
    for off in (-10, -5, 0, 5):
        L = half(avg_total + off)
        m[f"Over {L}"] = 1 - ncdf((L - avg_total) / sdt)
        m[f"Under {L}"] = 1 - m[f"Over {L}"]
        groups.append(((f"Over {L}", f"Under {L}"), 1.0))
    return m, groups, {"mean_margin": round(mean, 1), "sd_margin": sd}

# ---------------------------------------------------------------- TENNIS MODEL
def tennis_model(p1, avg_games, best_of=3):
    sd_g = CFG["SD_TENNIS_GAMES_BO3"] if best_of == 3 else CFG["SD_TENNIS_GAMES_BO5"]
    sd_d = CFG["SD_TENNIS_DIFF_BO3"] if best_of == 3 else CFG["SD_TENNIS_DIFF_BO5"]
    pp = p1 / 100
    mean_diff = sd_d * nppf(pp)               # wastani wa (games P1 - games P2)
    m = {"P1 Win": pp, "P2 Win": 1 - pp}
    groups = [(("P1 Win", "P2 Win"), 1.0)]
    for L in (3.5,):
        m[f"P1 +{L} games"] = ncdf((mean_diff + L) / sd_d)
        m[f"P2 -{L} games"] = 1 - m[f"P1 +{L} games"]
        groups.append(((f"P1 +{L} games", f"P2 -{L} games"), 1.0))
        m[f"P2 +{L} games"] = ncdf((L - mean_diff) / sd_d)
        m[f"P1 -{L} games"] = 1 - m[f"P2 +{L} games"]
        groups.append(((f"P2 +{L} games", f"P1 -{L} games"), 1.0))
    for off in (-3, 0, 3):
        L = half(avg_games + off)
        m[f"Over {L} games"] = 1 - ncdf((L - avg_games) / sd_g)
        m[f"Under {L} games"] = 1 - m[f"Over {L} games"]
        groups.append(((f"Over {L} games", f"Under {L} games"), 1.0))
    return m, groups, {"mean_game_diff": round(mean_diff, 1), "best_of": best_of}

# ---------------------------------------------------------------- BOOKMAKER (BANDIA, kwa demo tu)
def make_book(model, groups, margin=0.06, bias=None):
    bias = bias or {}
    book = {}
    for keys, total in groups:
        ps = [model[k] * bias.get(k, 1.0) for k in keys]
        s = sum(ps)
        for k, p in zip(keys, ps):
            p = p / s * total
            book[k] = max(1.01, round(1 / (p * (1 + margin)), 2))
    return book

# ---------------------------------------------------------------- ENGINE CORE
def evaluate(model, book, groups):
    p_mkt = {}
    for keys, total in groups:
        dv = devig([book[k] for k in keys], total)
        for k, v in zip(keys, dv):
            p_mkt[k] = v
    out = []
    w = CFG["W_MODEL"]
    for k, pm in model.items():
        if k not in book:
            continue
        pk = p_mkt[k]
        pf = w * pm + (1 - w) * pk
        flags = []
        if abs(pm - pk) > 0.06:
            flags.append("model_vs_market")
        pen = min(CFG["MAX_FLAG_PENALTY"], CFG["FLAG_PENALTY"] * len(flags))
        pc = pf - pen
        out.append({"tip": k, "p_model": pm, "p_market": pk, "p_cal": pc,
                    "odds": book[k], "flags": flags, "ev": pc * book[k] - 1})
    return out

def choose(cands):
    ok, rej = [], []
    for c in cands:
        if c["odds"] < CFG["LEG_ODDS_MIN"]:
            rej.append((c, f"odds {c['odds']:.2f} < LEG_ODDS_MIN"))
        elif c["odds"] > CFG["LEG_ODDS_MAX"]:
            rej.append((c, f"odds {c['odds']:.2f} > LEG_ODDS_MAX"))
        elif c["p_cal"] < CFG["MIN_LEG_PROB"]:
            rej.append((c, f"p {c['p_cal']*100:.0f}% < MIN_LEG_PROB"))
        else:
            ok.append(c)
    if not ok:
        return None, ok, rej
    top = max(c["p_cal"] for c in ok)
    near = [c for c in ok if top - c["p_cal"] <= 0.01]      # sare ndani ya 1 pt
    best = max(near, key=lambda c: (c["odds"], c["ev"]))     # tie-break: odds kubwa, kisha EV
    return best, ok, rej

def analyze(match):
    why = blocked(match)
    if why:
        return {"match": match, "blocked": why}
    sp = match["sport"]
    if sp == "football":
        model, groups, info = football_model(*match["p"], match["avg"])
    elif sp == "basketball":
        model, groups, info = basketball_model(match["p"][0], match["avg"])
    else:
        model, groups, info = tennis_model(match["p"][0], match["avg"], match.get("best_of", 3))
    book = make_book(model, groups, bias=match.get("bias"))
    cands = evaluate(model, book, groups)
    if sp == "tennis" and max(match["p"][0], 100 - match["p"][0]) >= 85:
        # RULE T-5: mechi isiyo sawa -> seti zinaisha haraka; model ya totals haijui uhusiano huu.
        cands = [c for c in cands if not c["tip"].startswith("Over")]
    best, ok, rej = choose(cands)
    return {"match": match, "info": info, "best": best, "ok": ok, "rej": rej, "n": len(cands)}

# ---------------------------------------------------------------- SLIP BUILDER (brute force kwa demo; production = DP)
def build_slips(legs, force=None, k=3):
    lo, hi = CFG["SLIP_ODDS_MIN"], CFG["SLIP_ODDS_MAX"]
    res = []
    sizes = [force] if force else range(1, min(CFG["MAX_LEGS"], len(legs)) + 1)
    for r in sizes:
        if r > len(legs):
            continue
        for combo in combinations(legs, r):
            O = math.prod(c["odds"] for c in combo)
            P = math.prod(c["p_cal"] for c in combo)
            if force is None and not (lo <= O <= hi):
                continue
            res.append((P, O, combo))
    res.sort(key=lambda x: -x[0])
    return res[:k]

# ---------------------------------------------------------------- DEMO DATA
MATCHES = [
    # --- FOOTBALL ---
    dict(id="F1", sport="football", league="Bundesliga", home="Bayern Munich", away="Union Berlin",
         p=(76, 15, 9), avg=3.7, status="Scheduled", note="Favorite mkubwa nyumbani"),
    dict(id="F2", sport="football", league="Serie A", home="Torino", away="Udinese",
         p=(36, 33, 31), avg=2.1, status="Scheduled", note="Mechi sawa-sawa - 1X2 haina pick; zinabaki goal-markets pekee"),
    dict(id="F3", sport="football", league="Club Friendlies", home="Real Madrid", away="Al Nassr",
         p=(70, 18, 12), avg=3.4, status="Scheduled", note="Friendly - lazima izuiwe"),
    dict(id="F4", sport="football", league="Premier League", home="Brentford", away="Burnley",
         p=(55, 25, 20), avg=3.0, status="Scheduled", bias={"Under 1.5": 0.5},
         note="Bookie anaona Over 1.5 salama kuliko model (+9pt) -> flag model_vs_market"),
    dict(id="F5", sport="football", league="Division 1 Women", home="Lyon W", away="PSG W",
         p=(60, 22, 18), avg=3.1, status="Scheduled", note="Wanawake - izuiwe"),
    # --- BASKETBALL ---
    dict(id="B1", sport="basketball", league="Euroleague", home="Real Madrid", away="Zalgiris",
         p=(84, 0, 16), avg=165.0, status="Scheduled", note="Favorite mkubwa; kuna handicap + total"),
    dict(id="B2", sport="basketball", league="NBA", home="Hornets", away="Pacers",
         p=(49, 0, 51), avg=232.0, status="Scheduled", note="Mechi ngumu - epuka"),
    # --- TENNIS ---
    dict(id="T1", sport="tennis", league="ATP Masters", home="J. Sinner", away="Q. Qualifier",
         p=(91, 0, 9), avg=19.5, best_of=3, status="Scheduled", note="Mchezaji bora vs qualifier"),
    dict(id="T2", sport="tennis", league="ATP 250", home="A. Player", away="B. Player",
         p=(55, 0, 45), avg=22.5, best_of=3, status="Scheduled", note="Karibu sawa"),
    dict(id="T3", sport="tennis", league="ATP Doubles", home="Duo A", away="Duo B",
         p=(75, 0, 25), avg=21.0, best_of=3, status="Scheduled", note="Doubles - izuiwe"),
]

def pct(x):
    return f"{x*100:5.1f}%"

def show(res):
    m = res["match"]
    head = f"[{m['id']}] {m['home']} vs {m['away']}  ({m['league']}, {m['sport']})  - {m['note']}"
    print("\n" + head)
    if res.get("blocked"):
        print(f"    X BLOCKED: {res['blocked']}")
        return
    print(f"    model info: {res['info']}")
    b = res["best"]
    if not b:
        print("    X HAKUNA PICK SALAMA (hakuna candidate iliyopita vichujio).")
        top = sorted(res["ok"] + [c for c, _ in res["rej"]], key=lambda c: -c["p_cal"])[:3]
        for c in top:
            why = next((w for cc, w in res["rej"] if cc is c), "ok")
            print(f"       karibu: {c['tip']:<16} p={pct(c['p_cal'])} odds={c['odds']:<5} -> {why}")
        return
    print(f"    OK BEST TIP: {b['tip']}  p_cal={pct(b['p_cal'])} (model {pct(b['p_model'])}, bookie {pct(b['p_market'])})"
          f"  odds={b['odds']}  EV={b['ev']*100:+.1f}%  flags={b['flags'] or '-'}")
    alts = sorted([c for c in res["ok"] if c is not b], key=lambda c: -c["p_cal"])[:3]
    for c in alts:
        print(f"       mbadala: {c['tip']:<16} p={pct(c['p_cal'])} odds={c['odds']}")
    skipped = [(c, w) for c, w in res["rej"] if c["p_cal"] > b["p_cal"]]
    for c, w in sorted(skipped, key=lambda x: -x[0]["p_cal"])[:3]:
        print(f"       imekataliwa: {c['tip']:<16} p={pct(c['p_cal'])} odds={c['odds']} -> {w}")

def run():
    print("=" * 78)
    print("K96 SMART ENGINE - RULES DEMO  (odds za bookmaker ni BANDIA)")
    print("=" * 78)
    results = [analyze(m) for m in MATCHES]
    for r in results:
        show(r)

    # ---- self-checks (zinahakikisha rules hazibadiliki kimya kimya)
    f1, _, _ = football_model(76, 15, 9, 3.7)
    assert abs(f1["1X"] - 0.91) < 1e-9, "DC lazima iwe p1+px, bila nyongeza ya rules"
    assert abs(f1["Over 2.5"] + f1["Under 2.5"] - 1) < 1e-9
    assert abs(sum(devig([1.5, 3.8, 6.0])) - 1) < 1e-9
    liv, _, _ = football_model(57, 30, 13, 3.0)
    assert abs(liv["1X"] - 0.87) < 1e-9, "Liverpool 1X lazima 87%, SI 98%"
    assert all(r.get("blocked") for r in results if r["match"]["id"] in ("F3", "F5", "T3"))

    legs = []
    for r in results:
        if r.get("best"):
            b = dict(r["best"])
            b["label"] = f"{r['match']['home']} - {b['tip']}"
            legs.append(b)
    print("\n" + "=" * 78)
    print(f"LEGS ZILIZOPATIKANA: {len(legs)}  (kila mechi 1 tu)")
    for b in sorted(legs, key=lambda x: -x["p_cal"]):
        print(f"   {b['label']:<34} p={pct(b['p_cal'])} odds={b['odds']}")

    print("\n--- MODE AUTO: total odds kati ya "
          f"{CFG['SLIP_ODDS_MIN']} na {CFG['SLIP_ODDS_MAX']}, risk ndogo kwanza ---")
    slips = build_slips(legs)
    if not slips:
        print("   hakuna slip salama leo")
    for i, (P, O, combo) in enumerate(slips, 1):
        print(f"   #{i}  legs={len(combo)}  odds={O:.2f}  joint P={pct(P)}  risk={pct(1-P)}  EV={(P*O-1)*100:+.1f}%")
        for c in combo:
            print(f"        - {c['label']}  @{c['odds']}  p={pct(c['p_cal'])}")

    n = min(5, len(legs))
    print(f"\n--- MODE FORCE_LEGS={n}: legs {n} hata odds ziwe nje ya range ---")
    for P, O, combo in build_slips(legs, force=n, k=1):
        warn = "" if CFG["SLIP_ODDS_MIN"] <= O <= CFG["SLIP_ODDS_MAX"] else "  (!) odds nje ya lengo"
        print(f"   legs={len(combo)} odds={O:.2f} joint P={pct(P)} risk={pct(1-P)}{warn}")
    print("\nKUMBUKA: kadiri legs zinavyoongezeka, joint probability inashuka (inazidishwa).")

if __name__ == "__main__":
    run()
