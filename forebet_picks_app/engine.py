#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMART ENGINE v1.0 — Forebet supplies forecasts/data; this module creates and ranks tips.

  0. BLOCK: live/finished, friendlies, youth/women/reserves, doubles/ITF-low,
     esports/virtual and other volatile competitions.
  1. PROBABILITIES: football 1X2/DC/DNB + fitted Poisson total/team goals/BTTS;
     basketball and tennis use winner and sport-specific normal-distribution markets.
  2. EVIDENCE: team scoring averages, recent form, standings, H2H, predicted score,
     home advantage and available bookmaker probabilities; adverse signals subtract confidence.
  3. SELECTION: best market per match, balanced across available sports, up to 10 picks;
     confidence threshold relaxes only when there are no eligible candidates at its current level.
  4. SAFETY: only exact live bookmaker odds can make a model suggestion bettable;
     final worker verification is required before a slip is built.
"""
import math
import re
from pathlib import Path

MIN_CONF = 80                 # mwisho wa chini wa confidence (adaptive-relaxation hapa chini)
TARGET_MIN, TARGET_MAX = 1, 10
RELAX_STEPS = [80, 75, 70]
# Avoid small per-market caps; prioritize balanced representation across sports.
CAPS = {market: TARGET_MAX for market in (
    "1X2", "Double Chance", "Total Goals", "Team Goals", "Winner", "Draw No Bet",
    "BTTS", "Handicap +2", "Handicap", "Total Points", "Games Handicap", "Total Games",
)}


def _balanced_front(pool):
    """Choose top candidates without letting football-first order starve other sports."""
    sports = list(dict.fromkeys(p.get("sport") or "unknown" for p in pool))
    if not sports:
        return []
    quota = max(1, math.ceil(TARGET_MAX / len(sports)))
    counts, front = {}, []
    for pick in pool:
        sport = pick.get("sport") or "unknown"
        if counts.get(sport, 0) >= quota:
            continue
        front.append(pick)
        counts[sport] = counts.get(sport, 0) + 1
        if len(front) >= TARGET_MAX:
            break
    return front
GATE_PROB = 50                # winner/DC/DNB/EH inahitaji favorite ≥ 50%; totals hazihitaji

# ---------------------------------------------------------------------------
# 0. USALAMA — timu/ligi zisizoaminika (takwimu tete)
# ---------------------------------------------------------------------------
_BAD_LEAGUE = re.compile(
    r"(u\s?1[5-9]|u\s?2[0-3]\b|youth|junior|academy|reserv|women|woman|ladies|lady|"
    r"femen|femmin|dames|femme|frauen|girls|boys|primavera|\bw\b$)",
    re.I)
_BAD_TEAM = re.compile(r"(\sW$|\(W\)|\sU\s?1[5-9]\b|\sU\s?2[0-3]\b|\syouth\b)", re.I)


def is_blocked(rec):
    if _BAD_LEAGUE.search(rec.get("league") or ""):
        return True
    if _BAD_TEAM.search(rec.get("home") or "") or _BAD_TEAM.search(rec.get("away") or ""):
        return True
    return False


# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------
def _probs(rec):
    p = [iv if isinstance(iv, (int, float)) else None for iv in (rec.get("p") or [])]
    return [(p + [None, None, None])[i] for i in range(3)]


def _side(rec):
    vals = [x if x is not None else 0 for x in _probs(rec)]
    if max(vals) <= 0:
        return None, 0
    i = vals.index(max(vals))
    return i, int(vals[i])


def _odd_for(rec, side):
    od = rec.get("od") or []
    if len(od) == 2:
        return od[0] if side == 0 else (od[1] if side == 2 else None)
    if len(od) >= 3 and side is not None and side < 3:
        return od[side]
    return None


def _form_score(items):
    pts = n = 0
    for it in (items or [])[:6]:
        s = str(it.get("v", it) if isinstance(it, dict) else it).strip().lower()[:1]
        if s == "w": pts += 3
        elif s == "d": pts += 1
        elif s == "l": pts += 0
        else: continue
        n += 1
    return pts, n


def _pos_int(x):
    try: return int(str(x).strip())
    except (TypeError, ValueError): return None


def _lambda(rec):
    """λ ya matarajio ya magoli/points: Forebet avg; isipokuwepo, jumla ya predicted score."""
    avg = rec.get("avg")
    if isinstance(avg, (int, float)) and avg > 0:
        return float(avg)
    ps = rec.get("ps")
    if ps and None not in ps:
        return float(sum(ps))
    return None


def _lambda_split(rec, lam):
    """Gawa λ kwa home/away: nusu predicted score, nusu mgawo wa prob."""
    p1, _px, p2 = _probs(rec)
    ps = rec.get("ps")
    share = (p1 or 0) / max(1, (p1 or 0) + (p2 or 0))
    if ps and None not in ps:
        lh = (float(ps[0]) + lam * share) / 2.0
        la = (float(ps[1]) + lam * (1.0 - share)) / 2.0
    else:
        lh, la = lam * share, lam * (1.0 - share)
    return max(0.05, lh), max(0.05, la)


# ---------------------------------------------------------------------------
# 2. UHAKIKI — rules nyingi (+/− pointi) + sababu
# ---------------------------------------------------------------------------
def adjustments(rec, sport, side):
    adj = 0
    why = []
    fav_home = (side == 0)

    # (a) H2H — mikutano ya karibuni
    m = re.search(r"(\d+)\s*meetings?:.*?(\d+)W\s*-\s*(\d+)D\s*-\s*(\d+)L", rec.get("h2h") or "")
    if m:
        tot, w, _d, l = (int(m.group(i)) for i in range(1, 5))
        if tot >= 3:
            w2, l2 = (w, l) if fav_home else (l, w)
            if w2 / tot >= 0.6:
                adj += 6; why.append(f"H2H imara kwa favorite ({w2}W/{tot})")
            elif l2 / tot >= 0.4:
                adj -= 8; why.append(f"H2H inapinga favorite ({l2}L/{tot})")
            elif (w2 - l2) <= -1:
                adj -= 3; why.append("H2H haijaelekeza favorite")
    # (b) Form — favorite vs mwingine
    fh, nh = _form_score(rec.get("hf"))
    fa, na = _form_score(rec.get("af"))
    if nh >= 3 and na >= 3:
        edge = (fh - fa) if fav_home else (fa - fh)
        if edge >= 4:
            adj += 5; why.append("Form inaunga mkono favorite")
        elif edge <= -3:
            adj -= 6; why.append("Form HAIAUNGI favorite — hatari")
        fav_list = rec.get("hf" if fav_home else "af") or []
        if fav_list and all(str(x).lower()[:1] != "l" for x in fav_list[:5]):
            adj += 2; why.append("Favorite hajapoteza michezo 5 iliyopita")
    # (c) Ukubwa — nafasi za ligi
    hp, ap = _pos_int(rec.get("hp")), _pos_int(rec.get("ap"))
    if hp and ap:
        gap = (ap - hp) if fav_home else (hp - ap)
        if gap >= 8:
            adj += 4; why.append(f"Ukubwa uko upande mmoja (tofauti ya nafasi: {gap})")
        elif gap <= -2:
            adj -= 8; why.append("Favorite HAINA ukubwa kwenye standings!")
    # (d) Home advantage
    if sport == "football":
        if fav_home:
            adj += 2; why.append("Home advantage")
        else:
            adj -= 2; why.append("Favorite yuko ugenini — tahadhari kidogo")
    # (e) Uhitaji wa mchezo (motisha)
    stakes = f"{rec.get('league','')} {rec.get('rnd','')} {rec.get('tr','')}".lower()
    if re.search(r"play.?off|final\b|semi|relegation|title", stakes):
        adj += 2; why.append("Mchezo muhimu — motisha iko juu")
    if re.search(r"friendly|friendlies|kirafiki", stakes):
        adj -= 8; why.append("FRIENDLY — matokeo hayategemewi")
    # (f) Ligi kuu (takwimu thabiti zaidi)
    if re.search(r"premier league|laliga|serie a|bundesliga|ligue 1|eredivisie|"
                 r"champions league|europa league|primeira|championship\b", stakes):
        adj += 2; why.append("Ligi kuu — takwimu za kuaminika")
    # (g) PS vs Avg coherence
    ps, avg = rec.get("ps"), rec.get("avg")
    if isinstance(avg, (int, float)) and ps and None not in ps:
        if abs(sum(ps) - avg) <= 1.2:
            adj += 1
        else:
            adj -= 3; why.append("PS na Avg zinagongana — inataa")
    # (h) PS inamuunga favorite? + margin yake
    if side is not None and ps and None not in ps:
        if fav_home and ps[0] > ps[1]:
            adj += 2; why.append(f"Predicted score inamuunga ({ps[0]}-{ps[1]})")
        elif not fav_home and ps[1] > ps[0]:
            adj += 2; why.append(f"Predicted score inamuunga ({ps[0]}-{ps[1]})")
        elif ps[0] != ps[1]:
            adj -= 4; why.append("PS INAPINGA tip ya Forebet!")
        if abs(ps[0] - ps[1]) >= 2:
            adj += 2; why.append("PS ina margin kubwa (≥2)")
    # (i) Kelly (value ya Forebet)
    k = rec.get("kelly")
    if isinstance(k, (int, float)):
        if k >= 0.10:
            adj += 3; why.append(f"Kelly {k:.2f} — matarajio yana value")
        elif k < 0:
            adj -= 2; why.append("Kelly mbaya — bookies hawana imani")
    return adj, why


# ---------------------------------------------------------------------------
# 3. Masoko
# ---------------------------------------------------------------------------
def _pois_le(lam, k):
    s = math.exp(-lam)
    term = s
    for i in range(1, k + 1):
        term *= lam / i
        s += term
    return s


def goals_market(rec, min_conf, adj):
    """Total goals: λ = Forebet avg; trend (avg_h+avg_a) ina-adjust.
    Over 0.5 ni 'salama-mno' (degenerate) — inaruhusiwa tu λ≤2.7 na kupata pref 0."""
    lam = _lambda(rec)
    if not lam:
        return None
    g = adj // 2
    ah, aa = rec.get("avg_h"), rec.get("avg_a")
    if isinstance(ah, (int, float)) and isinstance(aa, (int, float)):
        if ah + aa >= lam + 0.5:
            g += 3
        elif ah + aa <= lam - 0.8:
            g -= 3
    cands = {"Over 1.5": (1 - _pois_le(lam, 1), 2), "Over 2.5": (1 - _pois_le(lam, 2), 2),
             "Over 3.5": (1 - _pois_le(lam, 3), 2),
             "Under 2.5": (_pois_le(lam, 2), 2), "Under 3.5": (_pois_le(lam, 3), 2)}
    if lam <= 2.7:
        cands["Over 0.5"] = (1 - _pois_le(lam, 0), 0)     # degenerate — milango mengine ikiziba
    lab = max(cands, key=lambda k: (cands[k][1], cands[k][0]))
    prob, pref = cands[lab]
    conf = min(99, int(round(prob * 100)) + g)
    if conf >= min_conf:
        return {"market": "Total Goals", "tip": lab, "conf": conf,
                "lever": f"λ={lam:.2f} adj={g:+d}", "pref": pref}
    return None


def btts_market(rec, min_conf, adj):
    """Both Teams To Score — Poisson mbili (λh, λa)."""
    lam = _lambda(rec)
    p1, _px, p2 = _probs(rec)
    if not lam or (p1 is None and p2 is None):
        return None
    lh, la = _lambda_split(rec, lam)
    yes = (1 - math.exp(-lh)) * (1 - math.exp(-la))
    g = adj // 3
    cands = {"Yes": yes, "No": 1 - yes}
    lab = max(cands, key=cands.get)
    conf = min(99, int(round(cands[lab] * 100)) + g)
    if conf >= min_conf:
        return {"market": "BTTS", "tip": lab, "conf": conf,
                "lever": f"λh={lh:.2f} λa={la:.2f}", "pref": 2}
    return None


def dc_market(rec, side, adj):
    """Double Chance — rudi dict {market,tip,conf} kwa kila mpangilio 1X/12/X2."""
    p1, px, p2 = _probs(rec)
    cands = {"1X": (p1 or 0) + (px or 0), "12": (p1 or 0) + (p2 or 0),
             "X2": (px or 0) + (p2 or 0)}
    lab = max(cands, key=cands.get)
    return {"market": "Double Chance", "tip": lab, "conf": min(98, int(cands[lab]) + adj),
            "lever": f"{lab}={cands[lab]}", "pref": 4}


def dnb_market(rec, side, adj):
    """Draw No Bet — prob ya favorite ikiwa draw anaratibiwa."""
    p1, px, p2 = _probs(rec)
    if side is None or px is None:
        return None
    own = (p1 or 0) if side == 0 else (p2 or 0)
    opp = (p2 or 0) if side == 0 else (p1 or 0)
    tot = own + opp
    if tot <= 0:
        return None
    lab = "1" if side == 0 else "2"
    return {"market": "Draw No Bet", "tip": lab, "conf": min(98, int(round(own / tot * 100)) + adj),
            "lever": f"{own}/{tot}", "pref": 3}


def handicap_market(rec, side, dc_conf):
    lab = "+2 Home" if side == 0 else "+2 Away"
    return {"market": "Handicap +2", "tip": lab, "conf": min(97, dc_conf + 6), "pref": 1}


# ---------------------------------------------------------------------------
# 4. Mchambuzi mmoja (mechi moja)
# ---------------------------------------------------------------------------
_SIDE_LAB = {"football": ["1", "X", "2"], "basketball": ["1", "-", "2"], "tennis": ["P1", "-", "P2"]}


def analyze_match(rec, sport, min_conf):
    if is_blocked(rec):
        return {"skip": "zimezuiliwa (youth/women/reserves)"}
    side, fb = _side(rec)
    lam = _lambda(rec)
    if side is None and lam is None:
        return {"skip": "hakuna data ya kutosha"}

    adj, why = adjustments(rec, sport, side or 0)

    # Phase 4: ODDS-BAND IMEFUTWA — odds ni mipaka tu, sio scoring-rule
    odd = _odd_for(rec, side)

    base = {"sport": sport, "home": rec.get("home", ""), "away": rec.get("away", ""),
            "match": f"{rec.get('home','')} vs {rec.get('away','')}",
            "league": rec.get("league", ""), "side": side, "forebet": fb,
            "odd": odd, "adj": adj, "why": list(why),
            "url": rec.get("url") or "", "odds": rec.get("od") or [],
            "ps": rec.get("ps"), "avg": rec.get("avg"),
            "time": rec["dt"].strftime("%H:%M") if rec.get("dt") else "",
            "status": rec.get("status") or ""}

    # --- Basketball / Tennis: WINNER pekee ---
    if sport != "football":
        if side is None or fb < GATE_PROB:
            return {"skip": f"{sport}: fb={fb} < {GATE_PROB}"}
        lab = _SIDE_LAB[sport][side]
        conf = max(5, min(98, fb + adj))
        if conf >= min_conf:
            return {**base, "market": "Winner", "tip": lab, "conf": conf,
                    "decision": f"winner {fb}{adj:+d}"}
        return {"skip": f"{sport}: winner conf {conf} < {min_conf}"}

    # --- FOOTBALL: candidates zote, chagua bora ---
    cands = []

    # (i) DIRECT WIN — lazima ≥90% + uhakiki
    conf_direct = max(5, min(98, fb + adj))
    if side is not None and fb >= 90 and conf_direct >= min_conf:
        lab = _SIDE_LAB[sport][side]
        return {**base, "market": "1X2", "tip": lab, "conf": conf_direct,
                "decision": f"direct≥90 {fb}{adj:+d}"}

    if side is not None and fb >= GATE_PROB:
        dc = dc_market(rec, side, adj)
        if dc["conf"] >= min_conf:
            cands.append({**dc, "decision": f"backup {dc['tip']} juu ya {fb} ya Forebet",
                          "extra": [f"BACKUP {dc['tip']}: confidence {fb}% → {dc['conf']}%"]})
        dnb = dnb_market(rec, side, adj)
        if dnb and dnb["conf"] >= min_conf:
            lab = _SIDE_LAB[sport][side]
            cands.append({**dnb, "decision": f"dnb {lab} (bila draw): {dnb['conf']}"})
        hl = handicap_market(rec, side, dc["conf"])
        if hl["conf"] >= min_conf:
            cands.append({**hl, "decision": f"eh+2 kutoka DC={dc['conf']}"})

    # (ii) TOTALS + BTTS zinafanya kazi hata mechi ngumu (hakuna favorite)
    gm = goals_market(rec, min_conf, adj)
    if gm:
        cands.append({**gm, "decision": f"goals {gm['lever']}"})
    bm = btts_market(rec, min_conf, adj)
    if bm:
        cands.append({**bm, "decision": f"btts {bm['lever']}"})

    if not cands:
        return {"skip": f"hakuna soko lenye conf ≥ {min_conf} (fb={fb}, adj={adj:+d})"}
    best = max(cands, key=lambda c: (c.get("pref", 0), c["conf"]))
    why_final = list(why) + best.get("extra", []) + [f"soko: {best['market']}"]
    return {**base, "why": why_final, "market": best["market"], "tip": best["tip"],
            "conf": best["conf"], "decision": best["decision"]}


# ---------------------------------------------------------------------------
# 5. SIKU nzima — idadi flexible; hakuna lengo la lazima, max 10
# ---------------------------------------------------------------------------
def analyze_day_full(records_by_sport, log=print):
    """Rudi (front iliyosawazishwa kwa sport, chosen_min, pool ya candidates).
    POOL hutumika na worker kwa 'auto-replace': bookie ikikata → candidate inayofuata inaingia."""
    pool = []
    skipped = []
    for sport, recs in records_by_sport.items():
        for rec in recs:
            r = analyze_match(rec, sport, MIN_CONF)
            (pool if isinstance(r, dict) and "skip" not in r else skipped).append(r)

    chosen_min = MIN_CONF
    if len(pool) < TARGET_MIN:
        for rel in RELAX_STEPS[1:]:
            chosen_min = rel
            pool2 = []
            for sport, recs in records_by_sport.items():
                for rec in recs:
                    r = analyze_match(rec, sport, rel)
                    if isinstance(r, dict) and "skip" not in r:
                        pool2.append(r)
            pool = pool2
            if len(pool) >= TARGET_MIN:
                log(f"  [engine] siku nyeti — min imeshushwa hadi {rel}%")
                break

    pool.sort(key=lambda p: (-p["conf"], -p["forebet"]))

    front = _balanced_front(pool)

    for i, p in enumerate(front, 1):
        p["rank"] = i
        if chosen_min < MIN_CONF:
            p["why"] = [*p.get("why", []), f"(siku nyeti: min {chosen_min}%)"]
    return front, chosen_min, pool


def analyze_day(records_by_sport, log=print):
    ptr, mn, _ = analyze_day_full(records_by_sport, log)
    return ptr, mn


# ═══════════════════════════════════════════════════════════════════════════
# SMART ENGINE v1.0 — K96 ENGINE RULES (K96_ENGINE_RULES.md)
# G1 probability-tu (hakuna +points) · G2 devig (DC→2) · G3 blend 0.5+calibrate
# G4 flags −1pt max −3 · G5 odds/prob filters · G6 odds halisi au DROP
# G7 tip moja/mechi (max p_cal; tie 1pt→odds→EV) · G8 None=sababu · G9 slip DP
# ═══════════════════════════════════════════════════════════════════════════
ENGINE_TAG = "smart-engine v1.0 (rules G/F/B/T)"

W_MODEL_DEF = 0.50
FLAG_PEN = 0.01
FLAG_PEN_MAX = 0.03
SD_BASKET_MARGIN, SD_BASKET_TOTAL = 11.5, 16.0
SD_TGAMES_BO3, SD_TGAMES_BO5 = 4.0, 5.5
SD_TDIFF_BO3, SD_TDIFF_BO5 = 4.5, 6.0


def _ncdf(x):                                   # Φ
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _nppf(p):                                   # z(p) — inverse normal (bisect)
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _ncdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _half(x):                                   # nearest .5 kuelekea chini (2.34→2.5? hapana → 1.5·...)
    return math.floor(x) + 0.5


# ---------------------------------------------------------------------------
# BLOCK RULES (veto kabla ya hisabati) — spec §0 Block list
# ---------------------------------------------------------------------------
_BLOCK_SUB = [
    ("friendl", "mechi ya kirafiki (friendly)"),
    ("exhibition", "exhibition"),
    ("u17", "vijana"), ("u18", "vijana"), ("u19", "vijana"), ("u20", "vijana"),
    ("u21", "vijana"), ("u22", "vijana"), ("u23", "vijana"),
    ("youth", "vijana"), ("junior", "vijana"), ("academy", "academy"),
    ("reserve", "reserves"), ("women", "wanawake"), ("woman", "wanawake"),
    ("ladies", "wanawake"), ("dames", "wanawake"), ("femin", "wanawake"),
    ("primavera", "youth"), ("doubles", "doubles (tennis)"),
    ("itf", "ITF ngazi ya chini"), ("esoccer", "esports"), ("virtual", "virtual"),
    ("3x3", "basketball 3x3"),
]
_SUFFIX_RE = re.compile(r"(?:\s(w|ii|b))$")


def blocked_reason(rec, sport):
    """Rudi sababu-ya-kuziba au None. Suffix W/II/B: Mwisho wa jina tu, SIO tennis
    (trap: 'B. Player' ni mchezaji, si timu B)."""
    league = (rec.get("league") or "")
    home = (rec.get("home") or "")
    away = (rec.get("away") or "")
    text = f"{league} {home} {away}".lower()
    for sub, why in _BLOCK_SUB:
        if sub in text:
            return why
    if sport in ("football", "basketball"):
        for team in (home, away):
            t = re.sub(r"[^\w\s]", "", team.lower())
            if _SUFFIX_RE.search(t):
                return "timu ya akiba/wanawake (suffix W/II/B)"
    st = (rec.get("st") or rec.get("status") or "Scheduled")
    if str(st) != "Scheduled":
        return f"mechi si Scheduled ({st})"
    if sport == "football":
        p1, px, p2 = _probs(rec)
        if p1 is None or px is None or p2 is None:
            return "probabilities hazikamilika (1X2)"
        if abs((p1 + px + p2) - 100) > 3:
            return f"p1+px+p2 = {p1+px+p2} (F4: ≠100±3)"
    return None


def _cg2(key, default):
    try:
        import config as _c
        return _c.get(key)
    except Exception:
        return default


def _pois_v(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def fit_lambdas_v2(p1, px, p2, avg):
    """RULES F2: λh+λa = avg; tafuta share ya home ili 1X2 iendane na Forebet.
    Rudi (lh, la, fit_err)."""
    t = p1 + px + p2
    f1, fx, f2 = p1 / t, px / t, p2 / t
    best = None
    for k in range(10, 91):
        s = k / 100.0
        lh, la = avg * s, avg * (1 - s)
        ph = pd = pa = 0.0
        LH = [_pois_v(i, lh) for i in range(11)]
        LA = [_pois_v(j, la) for j in range(11)]
        for i in range(11):
            for j in range(11):
                p = LH[i] * LA[j]
                if i > j:   ph += p
                elif i == j: pd += p
                else:       pa += p
        err = (ph - f1) ** 2 + (pd - fx) ** 2 + (pa - f2) ** 2
        if best is None or err < best[0]:
            best = (err, lh, la)
    return best[1], best[2], math.sqrt(best[0])


def _fb_probs_norm(rec):
    p1, px, p2 = _probs(rec)
    t = (p1 or 0) + (px or 0) + (p2 or 0)
    if t <= 0:
        return None
    return (p1 or 0) / t, (px or 0) / t, (p2 or 0) / t


def model_markets(rec, sport):
    """RULES F/B/T: probabilities za model kwa soko zote.
    Rudi (dict {(market,tip):p}, info-dict)."""
    out = {}
    if sport == "football":
        p1, px, p2 = _probs(rec)
        n = _fb_probs_norm(rec)
        if not n:
            return out, None
        f1, fx, f2 = n
        # F1: result markets EXACT kutoka Forebet — hakuna adjustments
        out[("1X2", "1")] = f1; out[("1X2", "X")] = fx; out[("1X2", "2")] = f2
        out[("Double Chance", "1X")] = f1 + fx
        out[("Double Chance", "X2")] = fx + f2
        out[("Double Chance", "12")] = f1 + f2
        if f1 + f2 > 0:
            out[("Draw No Bet", "1")] = f1 / (f1 + f2)
            out[("Draw No Bet", "2")] = f2 / (f1 + f2)
        avg = rec.get("avg")
        avg_source = "forebet_avg"
        # Forebet's projected score is a valid same-match fallback when goalsavg
        # is missing. Previously this returned early and removed every goals market.
        if not (isinstance(avg, (int, float)) and math.isfinite(float(avg)) and avg > 0.3):
            ps = rec.get("ps")
            if isinstance(ps, (list, tuple)) and len(ps) >= 2 and all(
                    isinstance(x, (int, float)) and math.isfinite(float(x)) and x >= 0 for x in ps[:2]):
                avg = float(ps[0]) + float(ps[1])
                avg_source = "predicted_score"
            else:
                ah, aa = rec.get("avg_h"), rec.get("avg_a")
                if (isinstance(ah, (int, float)) and isinstance(aa, (int, float))
                        and math.isfinite(float(ah)) and math.isfinite(float(aa))
                        and ah >= 0 and aa >= 0):
                    avg = float(ah) + float(aa)
                    avg_source = "team_scoring_averages"
        if not (isinstance(avg, (int, float)) and 0.3 < float(avg) <= 8.0):  # F3
            return out, {"note": "avg/score haipo → goal markets OFF (F3)"}
        lh, la, ferr = fit_lambdas_v2(p1 or 0, px or 0, p2 or 0, float(avg))
        # Rebalance goal expectation gently using actual team scoring rates,
        # recent form and home advantage; keep the Forebet total and 1X2 fit.
        share = lh / max(1e-9, lh + la)
        ah, aa = rec.get("avg_h"), rec.get("avg_a")
        if (isinstance(ah, (int, float)) and isinstance(aa, (int, float))
                and math.isfinite(float(ah)) and math.isfinite(float(aa)) and ah + aa > 0):
            team_share = float(ah) / (float(ah) + float(aa))
            share = 0.80 * share + 0.20 * team_share
        fh, nh = _form_score(rec.get("hf"))
        fa, na = _form_score(rec.get("af"))
        if nh >= 3 and na >= 3:
            share += max(-0.05, min(0.05, (fh / nh - fa / na) * 0.012))
        share += 0.02  # small home-field expectation, not an outcome guarantee
        share = max(0.10, min(0.90, share))
        lh, la = float(avg) * share, float(avg) * (1.0 - share)
        LH = [_pois_v(i, lh) for i in range(11)]
        LA = [_pois_v(j, la) for j in range(11)]
        over = {L: 0.0 for L in (0.5, 1.5, 2.5, 3.5, 4.5)}
        btts = 0.0
        eh2h = eh2a = 0.0
        for i in range(11):
            for j in range(11):
                p = LH[i] * LA[j]
                t = i + j
                for L in over:
                    if t > L:
                        over[L] += p
                if i >= 1 and j >= 1:
                    btts += p
                if i - j >= -1:
                    eh2h += p                # home +2 (3-way): sio draw-kitupu
                if j - i >= -1:
                    eh2a += p
        for L, ov in over.items():
            out[("Total Goals", f"Over {L}")] = ov
            out[("Total Goals", f"Under {L}")] = 1 - ov
        out[("BTTS", "Yes")] = btts
        out[("BTTS", "No")] = 1 - btts
        # Individual team goal markets give the engine a second route when
        # 1X2/DC is uncertain. The actual bookmaker verifier remains the final gate.
        for side_name, team_lam in (("Home", lh), ("Away", la)):
            for line in (0.5, 1.5):
                over_team = 1.0 - sum(_pois_v(i, team_lam) for i in range(int(line) + 1))
                out[("Team Goals", f"{side_name} Over {line}")] = over_team
                out[("Team Goals", f"{side_name} Under {line}")] = 1.0 - over_team
        out[("Handicap +2", "+2 Home")] = eh2h
        out[("Handicap +2", "+2 Away")] = eh2a
        return out, {"lambda_home": round(lh, 2), "lambda_away": round(la, 2),
                     "fit_err": round(ferr, 4), "avg_source": avg_source}
    if sport == "basketball":
        p1, _px, p2 = _probs(rec)
        if p1 is None or p2 is None or (p1 + p2) <= 0:
            return out, None
        ph = p1 / (p1 + p2)                                            # B1 normalize
        out[("Winner", "P1")] = ph
        out[("Winner", "P2")] = 1 - ph
        avg = rec.get("avg")
        if isinstance(avg, (int, float)) and avg > 0:
            mean = SD_BASKET_MARGIN * _nppf(ph)                        # B2
            for L in (5.5, 9.5):
                out[("Handicap", f"Home +{L}")] = _ncdf((mean + L) / SD_BASKET_MARGIN)
                out[("Handicap", f"Away -{L}")] = 1 - out[("Handicap", f"Home +{L}")]
                out[("Handicap", f"Away +{L}")] = _ncdf((L - mean) / SD_BASKET_MARGIN)
                out[("Handicap", f"Home -{L}")] = 1 - out[("Handicap", f"Away +{L}")]
            for off in (-10, -5, 0, 5):                                # B3
                L = _half(avg + off)
                ov = 1 - _ncdf((L - avg) / SD_BASKET_TOTAL)
                out[("Total Points", f"Over {L}")] = ov
                out[("Total Points", f"Under {L}")] = 1 - ov
            return out, {"mean_margin": round(mean, 1)}
        return out, {"note": "avg haipo → handicap/total OFF"}
    # tennis
    p1, _px, p2 = _probs(rec)
    if p1 is None:
        return out, None
    s = (p1 or 0) + (p2 or (100 - (p1 or 0)))
    pp = (p1 or 0) / max(s, 1e-9)
    best_of = int(rec.get("best_of") or 3)
    sd_g = SD_TGAMES_BO3 if best_of == 3 else SD_TGAMES_BO5             # T2/T3
    sd_d = SD_TDIFF_BO3 if best_of == 3 else SD_TDIFF_BO5
    out[("Winner", "P1")] = pp
    out[("Winner", "P2")] = 1 - pp
    avg = rec.get("avg")
    if isinstance(avg, (int, float)) and avg > 2:
        mean_d = sd_d * _nppf(pp)
        for L in (3.5,):
            out[("Games Handicap", f"P1 +{L}")] = _ncdf((mean_d + L) / sd_d)
            out[("Games Handicap", f"P2 -{L}")] = 1 - out[("Games Handicap", f"P1 +{L}")]
            out[("Games Handicap", f"P2 +{L}")] = _ncdf((L - mean_d) / sd_d)
            out[("Games Handicap", f"P1 -{L}")] = 1 - out[("Games Handicap", f"P2 +{L}")]
        for off in (-3, 0, 3):
            L = _half(avg + off)
            ov = 1 - _ncdf((L - avg) / sd_g)
            out[("Total Games", f"Over {L} games")] = ov
            out[("Total Games", f"Under {L} games")] = 1 - ov
        return out, {"mean_game_diff": round(mean_d, 1), "best_of": best_of}
    return out, {"best_of": best_of}


# ---------------------------------------------------------------------------
# FLAGS (G4 — subtract tu, 1pt kila moja, max 3)
# ---------------------------------------------------------------------------
def _flags_base(rec, sport):
    """form_against / h2h_against — zinatokana na data ya mechi yote."""
    flags = []
    fh, nh = _form_score(rec.get("hf"))
    fa, na = _form_score(rec.get("af"))
    if nh >= 3 and na >= 3 and (fa - fh) >= 4:
        flags.append("form_against")
    m = re.search(r"(\d+)\s*meetings?:.*?(\d+)W\s*-\s*(\d+)D\s*-\s*(\d+)L",
                  rec.get("h2h") or "")
    if m:
        tot, w, _d, l = (int(m.group(i)) for i in range(1, 5))
        if tot >= 3 and l / tot >= 0.4:
            flags.append("h2h_against")
    return flags


def _tip_is_away(tip):
    return tip in ("2", "X2", "Away Win", "P2") or tip.startswith(("Away +", "Away -", "P2 +", "P2 -"))


def _selected_team_side(market, tip):
    t = str(tip or "")
    if market in ("1X2", "Draw No Bet"):
        return "home" if t in ("1", "1X") else ("away" if t in ("2", "X2") else None)
    if market == "Double Chance":
        return "home" if t == "1X" else ("away" if t == "X2" else None)
    if market == "Winner":
        return "home" if t in ("P1", "1") else ("away" if t in ("P2", "2") else None)
    if market == "Team Goals":
        return "home" if t.startswith("Home ") else ("away" if t.startswith("Away ") else None)
    return None


def _evidence_flags(rec, side):
    if side not in ("home", "away"):
        return []
    flags = []
    own_form = rec.get("hf" if side == "home" else "af") or []
    opp_form = rec.get("af" if side == "home" else "hf") or []
    own_pts, own_n = _form_score(own_form)
    opp_pts, opp_n = _form_score(opp_form)
    if own_n >= 3 and opp_n >= 3 and own_pts <= opp_pts - 4:
        flags.append("form_against")
    pos_key, opp_key = (("hp", "ap") if side == "home" else ("ap", "hp"))
    own_pos, opp_pos = _pos_int(rec.get(pos_key)), _pos_int(rec.get(opp_key))
    if own_pos and opp_pos and own_pos >= opp_pos + 5:
        flags.append("rank_against")
    m = re.search(r"(\d+)\s*meetings?:.*?(\d+)W\s*-\s*(\d+)D\s*-\s*(\d+)L",
                  rec.get("h2h") or "")
    if m:
        total, home_w, _draws, home_l = (int(m.group(i)) for i in range(1, 5))
        side_losses = home_l if side == "home" else home_w
        if total >= 3 and side_losses / total >= 0.40:
            flags.append("h2h_against")
    return flags


def _flags_for_tip(rec, sport, market, tip, p_model, p_market, fit_info):
    side = _selected_team_side(market, tip)
    flags = _evidence_flags(rec, side)
    # Result-form/H2H flags must not be copied onto totals/BTTS: those markets
    # describe scoring, not which side wins.
    if p_market is not None and abs(p_model - p_market) > 0.06:
        flags.append("model_vs_market")                                # G4
    if fit_info and fit_info.get("fit_err", 0) > 0.05 and market in ("Total Goals", "Team Goals", "BTTS", "Handicap +2"):
        flags.append("model_fit_poor")                                 # F2
    ps = rec.get("ps")
    if ps and None not in ps and market in ("1X2", "Double Chance", "Draw No Bet"):
        if side == "away" and ps[0] > ps[1]:
            flags.append("ps_contradicts")
        elif side == "home" and ps[1] > ps[0]:
            flags.append("ps_contradicts")
    elif ps and None not in ps and market == "Team Goals" and side:
        team_score = ps[0] if side == "home" else ps[1]
        line_match = re.search(r"(\d+(?:\.\d+)?)", str(tip))
        line = float(line_match.group(1)) if line_match else 0.5
        if (str(tip).find("Over") >= 0 and team_score <= line) or (
                str(tip).find("Under") >= 0 and team_score > line):
            flags.append("ps_contradicts")
    if sport == "football" and _tip_is_away(tip):
        flags.append("favourite_away")
    return list(dict.fromkeys(flags))                                  # unique, order-dume


_CALIB = None


def load_calibration():
    global _CALIB
    try:
        import json as _j
        pth = Path(__file__).resolve().parent / "data" / "calibration.json"
        _CALIB = _j.loads(pth.read_text(encoding="utf-8"))["buckets"]
    except Exception:
        _CALIB = None


def calibrate(p):
    """Identity kabla data ya kutosha (G3); baada ya ≥300 settled → isotonic."""
    global _CALIB
    if _CALIB is None:
        load_calibration()
    if not _CALIB:
        return p
    import bisect
    keys = [float(k) for k in _CALIB]
    i = max(0, min(bisect.bisect_right(keys, p) - 1, len(keys) - 1))
    return _CALIB[str(keys[i])]


def best_tip_for_match(rec, sport, bk=None, min_prob=0.75, log=print):
    """G7: tip moja yenye p_cal ya JUU zaidi. bk = {'probs','odds','found',...}.
    Rudi dict au None (G8: sababu inakalilihwa)."""
    why_block = blocked_reason(rec, sport)
    if why_block:
        log(f"  [v1.0] BLOCKED: {rec.get('home')} vs {rec.get('away')} — {why_block}")
        return None

    mm, fit_info = model_markets(rec, sport)
    if not mm:
        return None
    bk = bk if isinstance(bk, dict) else {}
    bk_found = bk.get("found")
    bk_probs = bk.get("probs") or {}
    bk_odds = bk.get("odds") or {}
    w = float(_cg2("W_MODEL", W_MODEL_DEF))
    lo_o = float(_cg2("LEG_ODDS_MIN", 1.01))
    hi_o = float(_cg2("LEG_ODDS_MAX", 3.50))

    # RULES B4/T7 + tennis T5 lopsided veto: favourite ≥85% → angua Over games zote
    p1, _px, p2 = _probs(rec)
    lopsided_t = (sport == "tennis" and p1 is not None
                  and max(p1, (p2 or 0) or (100 - p1)) >= 85)

    cands = []
    for (market, tip), p_model in mm.items():
        if lopsided_t and market == "Total Games" and tip.startswith("Over"):
            continue                                                       # T5
        bkp = bk_probs.get((market, tip))
        bko = bk_odds.get((market, tip))
        # Bookmaker data is an optional evidence source, not a generation gate.
        # A missing exact market stays model-only and is checked against live
        # bookie markets by worker.verify_pick before it can enter a slip.
        p_final = (w * p_model + (1 - w) * bkp) if bkp is not None else p_model
        flags = _flags_for_tip(rec, sport, market, tip, p_model, bkp,
                               fit_info if fit_info else None)
        if bk.get("disagree"):
            flags.append("bookies_disagree")
        pen = min(len(flags) * FLAG_PEN, FLAG_PEN_MAX)                    # G4
        # No uncalibrated statistical estimate is presented as >95% certainty.
        p_cal = max(0.0, min(0.95, calibrate(p_final) - pen))            # G3
        ev = (p_cal * float(bko) - 1.0) if bko else None
        cands.append({"market": market, "tip": tip,
                      "p_model": round(p_model, 4),
                      "p_market": (round(bkp, 4) if bkp is not None else None),
                      "p_final": round(p_final, 4), "p_cal": round(p_cal, 4),
                      "bk_odds": (float(bko) if bko else None),
                      "flags": flags, "ev": (round(ev, 4) if ev is not None else None)})

    # G5: filters (odds ni mipaka — si scoring)
    ok, rej = [], []
    for c in cands:
        # Never reject a high-confidence model-only pick using inverse
        # probability as if it were a bookmaker price. Only real odds are gated.
        if c["bk_odds"] is not None and c["bk_odds"] < lo_o:
            rej.append((c, f"odds {c['bk_odds']:.2f} < LEG_ODDS_MIN"))
        elif c["bk_odds"] is not None and c["bk_odds"] > hi_o:
            rej.append((c, f"odds {c['bk_odds']:.2f} > LEG_ODDS_MAX"))
        elif c["p_cal"] < min_prob:
            rej.append((c, f"p {c['p_cal']:.0%} < MIN_LEG_PROB"))
        else:
            ok.append(c)

    # When the provider confirms an event and has at least one supported,
    # priced market, choose among those bettable candidates first. This keeps
    # model-only experimental markets from displacing a verified market.
    priced = [c for c in ok if c["bk_odds"] is not None]
    if bk_found is True and priced:
        ok = priced

    if not ok:                                                            # G8
        if rej:
            top_r = sorted(rej, key=lambda x: -x[0]["p_cal"])[:3]
            log(f"  [v1.0] {rec.get('home')} vs {rec.get('away')}: HAKUNA tip — "
                + " · ".join(f"{c['tip']} → {w_}" for c, w_ in top_r))
        return None

    top = max(c["p_cal"] for c in ok)
    near = [c for c in ok if top - c["p_cal"] <= 0.01]                    # G7 tie ≤1pt
    best = max(near, key=lambda c: ((c["bk_odds"] or 0), (c["ev"] or -9)))
    alts = sorted([c for c in ok if c is not best], key=lambda c: -c["p_cal"])[:3]
    rej_top = sorted((c for c, _w in rej if c["p_cal"] > best["p_cal"]),
                     key=lambda c: -c["p_cal"])[:3]

    tm = rec.get("time")
    if not tm and hasattr(rec.get("dt"), "strftime"):
        tm = rec["dt"].strftime("%H:%M")
    why = [f"model={best['p_model']:.0%} · market="
           + (f"{best['p_market']:.0%}" if best["p_market"] is not None else "—(model_only)")
           + f" → p_cal={best['p_cal']:.0%}"]
    if bk_found is not True or best["bk_odds"] is None:
        why.append("⚠ exact bookmaker market/odds haipo — model_only; hakikisha kabla ya bet")
    for f in best["flags"]:
        why.append(f"⚑ {f} (−{FLAG_PEN:.0%})")
    if alts:
        why.append("alternatives: " + " · ".join(
            f"{a['market']}:{a['tip']}@{a['bk_odds'] or '—'} ({a['p_cal']:.0%})" for a in alts))
    out = {
        "sport": sport, "home": rec.get("home"), "away": rec.get("away"),
        "match": f"{rec.get('home')} vs {rec.get('away')}",
        "league": rec.get("league"), "time": tm or "",
        "market": best["market"], "tip": best["tip"],
        "conf": round(best["p_cal"] * 100),
        "forebet": round((mm.get((best["market"], best["tip"])) or 0) * 100),
        "p_model": best["p_model"], "p_market": best["p_market"],
        "p_final": best["p_final"], "p_cal": best["p_cal"], "ev": best["ev"],
        "bk_odds": best["bk_odds"], "bookmaker": bk.get("bookmaker"),
        "flags": best["flags"], "alts": alts, "rejected": [c for c in rej_top],
        "odd": best["bk_odds"], "odds": rec.get("od") or rec.get("odds") or [],
        "why": why,
        "status": rec.get("st") or rec.get("status") or "Scheduled",
        "decision": f"{ENGINE_TAG} · {best['p_cal']:.0%}",
        "reason": f"{best['market']}:{best['tip']} · model {best['p_model']:.0%} vs bookie "
                  + (f"{best['p_market']:.0%}" if best["p_market"] is not None else "—"),
        "pred_score": (f"{rec['ps'][0]}-{rec['ps'][1]}" if rec.get("ps") and None not in rec["ps"] else ""),
        "url": rec.get("url", ""),
    }
    if fit_info and isinstance(fit_info, dict) and fit_info.get("lambda_home") is not None:
        out["why"] = [f"λ fit: {fit_info['lambda_home']}/{fit_info['lambda_away']} "
                      f"(fit_err {fit_info.get('fit_err', 0):.3f})"] + out["why"]
    return out


def predict_day(records_by_sport, provider=None, min_conf=None, log=print):
    """Rank available candidates into a sport-balanced front (0–10)."""
    min_conf = int(min_conf if min_conf is not None else 80)
    steps_pct = [min_conf] + [s for s in RELAX_STEPS if s < min_conf]
    steps = [s / 100.0 for s in dict.fromkeys(steps_pct)]
    chosen = steps[0]
    pool = []
    for min_p in steps:
        chosen = min_p
        pool = []
        for sport, recs in records_by_sport.items():
            for rec in recs:
                bk = None
                if provider:
                    try:
                        bk = provider(rec, sport, None)
                    except Exception:
                        bk = {"found": None}
                bt = best_tip_for_match(rec, sport, bk, min_p, lambda s: None)
                if bt:
                    pool.append(bt)
        pool.sort(key=lambda p: -p["conf"])
        if len(pool) >= TARGET_MIN:
            chosen = min_p
            break
    front = _balanced_front(pool)
    for i, p in enumerate(front, 1):
        p["rank"] = i
        if chosen < (min_conf / 100.0):
            p["why"].append(f"(siku nyeti: min {chosen * 100:.0f}%)")
    log(f"  [{ENGINE_TAG}] pool={len(pool)} front={len(front)} min={chosen:.0%}")
    return front, pool, chosen


def analyze_day(records_by_sport, log=print):
    """Legacy wrapper (gui_server demo/seed): model-only predict_day."""
    front, _pool, chosen = predict_day(records_by_sport, provider=None,
                                       min_conf=MIN_CONF, log=log)
    return front, int(round(chosen * 100))

