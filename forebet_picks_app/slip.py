# slip.py — K96 PICKS · PHASE 5 (spec §6): BETSLIP BUILDER
# Chagua subset ya legs: total odds ndani ya [MIN, MAX] na joint-probability MAX.
# DP juu ya log-odds buckets (step 0.005) na back-pointers — 100% deterministic, NO random.
from __future__ import annotations
import math

try:
    import config as _cfg
except Exception:
    _cfg = None


def _cg(key, default):
    try:
        return _cfg.get(key) if _cfg else default
    except Exception:
        return default


CORR_H = 0.98            # haircut kwa kila GOOD-pair yenye correlation (same league)


def _score_leg(p):
    return math.log(max(float(p), 1e-6))


def build_slips(legs_in: list[dict], topk: int = 5, log=print):
    """Input: list ya kulola (engine v0.3 picks zenye bk_odds + p_cal).
    → list ya slips [{label, legs, total_odds, joint_prob, risk, ev, legs_n}] au []."""
    o_min = float(_cg("SLIP_ODDS_MIN", 1.50))
    o_max = float(_cg("SLIP_ODDS_MAX", 1.80))
    max_legs = int(_cg("MAX_LEGS", 12))
    force = _cg("FORCE_LEGS", None)

    # legs usable: bettable (bk_odds ipo) + p_cal ipo
    legs = []
    seen = set()
    for p in legs_in:
        if p.get("bk_odds") is None or p.get("p_cal") is None:
            continue
        if not (1.0 < float(p["bk_odds"]) <= float(_cg("LEG_ODDS_MAX", 3.50))):
            continue
        mk = (p["home"], p["away"])
        if mk in seen:
            continue
        seen.add(mk)
        legs.append({"pick": p, "o": float(p["bk_odds"]), "p": float(p["p_cal"]),
                     "lg": p.get("league", "")})
    if not legs:
        log("  [slips] hakuna legs zilizo bettable — hakuna slip leo")
        return []

    legs.sort(key=lambda l: -l["p"])
    legs = legs[:60]                                   # cap ya DP size
    n = len(legs)

    ln_min, ln_max = math.log(o_min), math.log(o_max)
    STEP = 0.005
    Bmax = 900                                          # vifu vya log-odds kufufu
    # state[(b, c)] = (score, list ya indexes) — DP classical
    states: dict = {(0, 0): (0.0, ())}
    for i, leg in enumerate(legs):
        lo, lp = math.log(leg["o"]), _score_leg(leg["p"])
        snap = list(states.items())                    # iterate mpiga state (item inatumiwa mara moja)
        for (b, c), (sc, path) in snap:
            if c >= max_legs:
                continue
            nb, nc = b + round(lo / STEP), c + 1
            if nb > Bmax:
                continue
            nsc = sc + lp
            cur = states.get((nb, nc))
            if cur is None or nsc > cur[0]:
                states[(nb, nc)] = (nsc, path + (i,))

    def slip_from(b, c):
        sc, path = states[(b, c)]
        O = math.exp(b * STEP)
        sel = [legs[i] for i in path]
        corr = 0
        for i in range(len(sel)):
            for j in range(i + 1, len(sel)):
                if sel[i]["lg"] and sel[i]["lg"] == sel[j]["lg"]:
                    corr += 1
        P = math.exp(sc) * (CORR_H ** corr)
        return {"path": path, "legs": [s["pick"] for s in sel], "total_odds": round(O, 3),
                "joint_prob": round(P, 5), "legs_n": c,
                "risk": round(1 - P, 5), "correlation_pairs": corr,
                "ev": round(P * O - 1, 4)}

    out = []
    if force and isinstance(force, int):
        # FORCE_LEGS: kamili-legs N zenye p ya juu zaidi (dsta njaba ya slip-audis)
        best = []
        for (b, c) in states:
            if c == force:
                out.append(slip_from(b, c))
        if not out:                                    # kama hajasakini: N ya juu zaidi
            sel = legs[:force]
            O = 1.0
            sc = 0.0
            for s in sel:
                O *= s["o"]; sc += _score_leg(s["pick"]["p_cal"])
            corr = sum(1 for i in range(len(sel)) for j in range(i + 1, len(sel))
                       if sel[i]["lg"] and sel[i]["lg"] == sel[j]["lg"])
            P = math.exp(sc) * (CORR_H ** corr)
            out = [{"path": None, "legs": [s["pick"] for s in sel], "total_odds": round(O, 3),
                    "joint_prob": round(P, 5), "legs_n": force,
                    "risk": round(1 - P, 5), "correlation_pairs": corr,
                    "ev": round(P * O - 1, 4)}]
            log(f"  [slips] FORCE_LEGS={force} → odds jumla ziko nje ya lengo (warn)")
            out[0]["warning"] = f"odds ya jumla {out[0]['total_odds']} iko nje ya lengo [{o_min}–{o_max}]"
        else:
            out.sort(key=lambda s: -s["joint_prob"])
            out = out[:topk]
            for s in out:
                if not (o_min <= s["total_odds"] <= o_max):
                    s["warning"] = f"odds ya jumla {s['total_odds']} iko nje ya lengo [{o_min}–{o_max}]"
    else:
        cands = []
        for (b, c) in states:
            if c == 0:
                continue
            lo_b, hi_b = math.exp(b * STEP), math.exp((b + 1) * STEP)
            if hi_b < o_min or lo_b > o_max:
                continue
            cands.append(slip_from(b, c))
        cands.sort(key=lambda s: -s["joint_prob"])
        # HAKUNA dupe ya sets zinazofanana (same legs) — DP inaweza kurudia bucket ileile
        seen_paths, uniq = set(), []
        for s in cands:
            key = ",".join(str(i) for i in s["path"])
            if key in seen_paths:
                continue
            seen_paths.add(key)
            uniq.append(s)
            if len(uniq) >= topk:
                break
        out = uniq

    if not out:
        log(f"  [slips] GUMU: hakuna subset yoyote iwezayo lengo odds {o_min}–{o_max} → 'hakuna slip salama leo'")
        return []

    # labels: SAFEST (joint_prob ya juu), BALANCED (ya 2), HIGHER_ODDS (odds ya juu)
    out.sort(key=lambda s: -s["joint_prob"])
    labels = ["SAFEST", "BALANCED", "RISK_KIDOGOWO", "ALT_4", "ALT_5"]
    hi = max(range(len(out)), key=lambda i: out[i]["total_odds"])
    out[0]["label"] = labels[0]
    if len(out) > 1:
        out[hi]["label"] = "HIGHER_ODDS"
        for i, s in enumerate(out):
            if s is not out[0] and s is not out[hi]:
                s["label"] = labels[i] if i < len(labels) else f"ALT_{i+1}"
    for i, s in enumerate(out):
        s.setdefault("label", labels[i] if i < len(labels) else f"ALT_{i+1}")
        log(f"  [slip {s['label']:13s}] legs={s['legs_n']} · odds {s['total_odds']:.2f} · joint {s['joint_prob']:.1%} · EV {s['ev']:+.3f}")
    return out


def slip_copy_text(slips: list) -> str:
    if not slips:
        return ("📋 SLIPS: hakuna slip salama leo (odds lengo zisipatikana — no forced bad slip).\n"
                "Kadiri legs zinavyoongezeka, uwezekano wa jumla unapungua.")
    L = ["📋 K96 SLIPS (smart-engine v1.0)", ""]
    for s in slips:
        L.append(f"══ {s['label']} ══ legs {s['legs_n']} · odds {s['total_odds']} · "
                 f"joint WIN {s['joint_prob']:.1%} · risk {s['risk']:.1%} · EV {s['ev']:+.3f}")
        for i, p in enumerate(s["legs"], 1):
            L.append(f"  {i}. [{p.get('time','')}] {p['match']} — {p['market']}: {p['tip']} "
                     f"@{p.get('bk_odds')} ({p.get('p_cal', 0):.0%})")
        if s.get("warning"):
            L.append(f"  ⚠ {s['warning']}")
        L.append("")
    L.append("ℹ Kadiri legs zinavyoongezeka, uwezekano wa jumla unapungua. (10 legs × 90% ≈ 35% tu!)")
    return "\n".join(L)
