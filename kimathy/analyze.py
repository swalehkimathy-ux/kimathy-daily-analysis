"""analyze.py — makadirio ya uwezekano kwa kila soko (Sehemu 10).

Kanuni:
  * Uwezekano wa MATOKEO (1X2/DC/DNB) unatoka moja kwa moja kwa Forebet — hakuna kuongeza pointi.
  * Uwezekano wa MAGOLI/POINTI/GAMES unatoka kwa modeli ya takwimu (Poisson / Normal).
  * Uwezekano wa bookmaker (uliyoondolewa margin) unachanganywa: p = w·model + (1−w)·market.
  * Alama (flags) ZINAPUNGUZA tu — kamwe hazipandishi uwezekano.
  * Bila calibration, uwezekano unawekwa kizingiti (cap) na kuandikwa "estimated".
  * decimal odds SI uwezekano: implied = 1/O kabla ya kuondoa margin.
"""
from __future__ import annotations

import math

# Vigezo vya modeli (thamani za kuanzia — hazijathibitishwa kwa historia)
SD_BASKET_MARGIN = 11.5
SD_BASKET_TOTAL = 16.0
SD_TENNIS_DIFF = {3: 4.5, 5: 6.0}
SD_TENNIS_TOTAL = {3: 4.0, 5: 5.5}
GRID = 11


# ------------------------------------------------------------------ hisabati --
def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _nppf(p: float) -> float:
    """Kinyume cha CDF ya kawaida (bisect — hakuna scipy)."""
    p = min(max(p, 1e-9), 1 - 1e-9)
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _ncdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _pois(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def fit_lambdas(p1: float, px: float, p2: float, total: float) -> tuple[float, float, float]:
    """Tafuta (λ_home, λ_away) ili gridi ya Poisson irudishe 1X2 ya Forebet
    na jumla ya magoli iwe `total`. Rudia (lh, la, fit_err)."""
    t = max(0.2, float(total))
    target = (p1 / 100.0, px / 100.0, p2 / 100.0)
    best = (t / 2, t / 2, 9.99)
    share = 0.05
    while share <= 0.9501:
        lh, la = t * share, t * (1 - share)
        LH = [_pois(i, lh) for i in range(GRID)]
        LA = [_pois(j, la) for j in range(GRID)]
        a = b = c = 0.0
        for i in range(GRID):
            for j in range(GRID):
                p = LH[i] * LA[j]
                if i > j:
                    a += p
                elif i == j:
                    b += p
                else:
                    c += p
        err = math.sqrt(((a - target[0]) ** 2 + (b - target[1]) ** 2 + (c - target[2]) ** 2) / 3)
        if err < best[2]:
            best = (lh, la, err)
        share += 0.005
    return best[0], best[1], best[2]


def score_grid(lh: float, la: float) -> list[list[float]]:
    LH = [_pois(i, lh) for i in range(GRID)]
    LA = [_pois(j, la) for j in range(GRID)]
    return [[LH[i] * LA[j] for j in range(GRID)] for i in range(GRID)]


# ------------------------------------------------------------- ushahidi ------
def evidence_of(rec: dict, sport: str) -> set[str]:
    """Vitu vilivyopo kwenye rekodi — vinavyoamua masoko yanayostahili."""
    ev: set[str] = set()
    p = rec.get("probs") or {}

    def _n(k):
        v = p.get(k)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    if sport == "football":
        p1, px, p2 = _n("1"), _n("X"), _n("2")
        if None not in (p1, px, p2) and abs((p1 + px + p2) - 100) <= 3:
            ev.add("probs_1x2")
    else:
        p1, p2 = _n("1"), _n("2")
        if None not in (p1, p2) and (p1 + p2) > 0:
            ev.add("probs_2way")

    avg = rec.get("avg")
    try:
        avgf = float(avg) if avg not in (None, "") else None
    except (TypeError, ValueError):
        avgf = None
    ps = rec.get("predicted_score")
    ah, aa = rec.get("avg_h"), rec.get("avg_a")

    if sport == "football":
        if avgf is not None and 0.3 < avgf <= 8.0:
            ev.add("goal_expectation")
        elif ps and len(ps) >= 2 and all(x is not None for x in ps[:2]):
            tot = float(ps[0]) + float(ps[1])
            if 0.3 < tot <= 8.0:
                ev.add("goal_expectation")
        elif None not in (ah, aa) and (float(ah) + float(aa)) > 0:
            ev.add("goal_expectation")
        if "goal_expectation" in ev:
            if (ps and len(ps) >= 2 and ps[0] != ps[1]) or None not in (ah, aa):
                ev.add("goal_split")
    elif sport == "basketball":
        if avgf is not None and 100 <= avgf <= 320:
            ev.add("avg_points")
    elif sport == "tennis":
        if avgf is not None and 10 <= avgf <= 60:
            ev.add("avg_games")
        if rec.get("best_of") in (3, 5) or rec.get("best_of") in ("3", "5"):
            ev.add("best_of")
    return ev


def goal_expectation(rec: dict) -> tuple[float, str]:
    """Jumla ya magoli inayotarajiwa + chanzo chake."""
    try:
        avgf = float(rec.get("avg")) if rec.get("avg") not in (None, "") else None
    except (TypeError, ValueError):
        avgf = None
    if avgf is not None and 0.3 < avgf <= 8.0:
        return avgf, "forebet_avg"
    ps = rec.get("predicted_score")
    if ps and len(ps) >= 2 and all(x is not None for x in ps[:2]):
        tot = float(ps[0]) + float(ps[1])
        if 0.3 < tot <= 8.0:
            return tot, "predicted_score"
    ah, aa = rec.get("avg_h"), rec.get("avg_a")
    if None not in (ah, aa) and (float(ah) + float(aa)) > 0:
        return float(ah) + float(aa), "team_scoring_averages"
    return 0.0, "haipo"


def _form_points(items) -> tuple[float, int]:
    tot, n = 0.0, 0
    for x in (items or []):
        s = str(x).strip().upper()
        if s in ("W", "3"):
            tot += 3; n += 1
        elif s in ("D", "1"):
            tot += 1; n += 1
        elif s in ("L", "0"):
            tot += 0; n += 1
    return tot, n


def _probs_norm(rec: dict) -> tuple[float, float, float] | None:
    p = rec.get("probs") or {}
    try:
        a, b, c = float(p.get("1")), float(p.get("X")), float(p.get("2"))
    except (TypeError, ValueError):
        return None
    s = a + b + c
    if s <= 0:
        return None
    return a / s, b / s, c / s


def _probs_2way(rec: dict) -> tuple[float, float] | None:
    p = rec.get("probs") or {}
    try:
        a, b = float(p.get("1")), float(p.get("2"))
    except (TypeError, ValueError):
        return None
    s = a + b
    if s <= 0:
        return None
    return a / s, b / s


# ------------------------------------------------------------- modeli ya soko --
def model_markets(rec: dict, sport: str) -> tuple[dict, dict]:
    """Uwezekano wa MODEL kwa kila (market_key, selection, line).

    Rudia ({(key, selection, line): p}, info).
    """
    out: dict[tuple[str, str, float | None], float] = {}
    info: dict = {}
    ev = evidence_of(rec, sport)

    if sport == "football":
        n = _probs_norm(rec)
        if n is None:
            return out, {"note": "uwezekano wa Forebet haupo → hakuna masoko"}
        f1, fx, f2 = n
        out[("1x2", "1", None)] = f1
        out[("1x2", "X", None)] = fx
        out[("1x2", "2", None)] = f2
        out[("double_chance", "1X", None)] = f1 + fx
        out[("double_chance", "X2", None)] = fx + f2
        out[("double_chance", "12", None)] = f1 + f2
        if (f1 + f2) > 0:
            out[("draw_no_bet", "1", None)] = f1 / (f1 + f2)
            out[("draw_no_bet", "2", None)] = f2 / (f1 + f2)
        if "goal_expectation" not in ev:
            info["note"] = "takwimu za magoli hazipo → masoko ya magoli YAMEZIMWA"
            return out, info

        total, src = goal_expectation(rec)
        p1, px, p2 = f1 * 100, fx * 100, f2 * 100
        lh, la, ferr = fit_lambdas(p1, px, p2, total)
        # usawazishaji mdogo kwa wastani wa kufunga wa timu + faida ya nyumbani
        share = lh / max(1e-9, lh + la)
        ah, aa = rec.get("avg_h"), rec.get("avg_a")
        if None not in (ah, aa) and (float(ah) + float(aa)) > 0:
            share = 0.80 * share + 0.20 * (float(ah) / (float(ah) + float(aa)))
        fh, nh = _form_points(rec.get("home_form"))
        fa, na = _form_points(rec.get("away_form"))
        if nh >= 3 and na >= 3:
            share += max(-0.05, min(0.05, (fh / nh - fa / na) * 0.012))
        share = max(0.10, min(0.90, share + 0.02))
        lh, la = total * share, total * (1 - share)

        g = score_grid(lh, la)
        for line in (0.5, 1.5, 2.5, 3.5, 4.5):
            ov = sum(g[i][j] for i in range(GRID) for j in range(GRID) if (i + j) > line)
            out[("total_goals", "Over", line)] = ov
            out[("total_goals", "Under", line)] = 1 - ov
        btts = sum(g[i][j] for i in range(1, GRID) for j in range(1, GRID))
        out[("btts", "Yes", None)] = btts
        out[("btts", "No", None)] = 1 - btts
        for side, lam in (("Home", lh), ("Away", la)):
            for line in (0.5, 1.5):
                ov = 1.0 - sum(_pois(i, lam) for i in range(int(line) + 1))
                out[("team_goals", f"{side} Over", line)] = ov
                out[("team_goals", f"{side} Under", line)] = 1 - ov
        # Asian handicap (mistari ya nusu)
        for line in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5):
            ph = sum(g[i][j] for i in range(GRID) for j in range(GRID)
                     if (i + line) > j)
            out[("asian_handicap", "Home", line)] = ph
            out[("asian_handicap", "Away", line)] = 1 - ph
        # European handicap +2 (njia tatu)
        eh_h = sum(g[i][j] for i in range(GRID) for j in range(GRID) if (i + 2) > j)
        eh_d = sum(g[i][j] for i in range(GRID) for j in range(GRID) if (i + 2) == j)
        out[("european_handicap", "+2 Home", None)] = eh_h
        out[("european_handicap", "Draw +2", None)] = eh_d
        out[("european_handicap", "+2 Away", None)] = max(0.0, 1 - eh_h - eh_d)
        # timu ya kwanza kufunga (makadirio: uwiano wa λ, hakuna data ya muda)
        if (lh + la) > 0:
            none_p = _pois(0, lh) * _pois(0, la)
            out[("first_to_score", "Home", None)] = (lh / (lh + la)) * (1 - none_p)
            out[("first_to_score", "Away", None)] = (la / (lh + la)) * (1 - none_p)
            out[("first_to_score", "None", None)] = none_p
        # correct score / winning margin (variance kubwa)
        for i in range(6):
            for j in range(6):
                out[("correct_score", f"{i}-{j}", None)] = g[i][j]
        for m in range(1, 5):
            wh = sum(g[i][j] for i in range(GRID) for j in range(GRID) if (i - j) == m)
            wa = sum(g[i][j] for i in range(GRID) for j in range(GRID) if (j - i) == m)
            out[("winning_margin", f"Home by {m}", None)] = wh
            out[("winning_margin", f"Away by {m}", None)] = wa
        info.update({"lambda_home": round(lh, 2), "lambda_away": round(la, 2),
                     "fit_err": round(ferr, 4), "avg_source": src,
                     "total_goals_expected": round(total, 2)})
        return out, info

    if sport == "basketball":
        n2 = _probs_2way(rec)
        if n2 is None:
            return out, {"note": "uwezekano wa Forebet haupo"}
        ph, _pa = n2
        out[("winner", "P1", None)] = ph
        out[("winner", "P2", None)] = 1 - ph
        if "avg_points" not in ev:
            return out, {"note": "wastani wa pointi haupo → handicap/total ZIMEZIMWA"}
        avg = float(rec["avg"])
        mean = SD_BASKET_MARGIN * _nppf(ph)
        for line in (5.5, 9.5, 12.5):
            ph_h = _ncdf((mean + line) / SD_BASKET_MARGIN)
            out[("handicap", "Home", line)] = ph_h
            out[("handicap", "Away", line)] = 1 - ph_h
        for off in (-10, -5, 0, 5):
            line = round(avg + off) + 0.5
            ov = 1 - _ncdf((line - avg) / SD_BASKET_TOTAL)
            out[("total_points", "Over", line)] = ov
            out[("total_points", "Under", line)] = 1 - ov
        return out, {"mean_margin": round(mean, 1), "avg_points": avg}

    # tenisi
    n2 = _probs_2way(rec)
    if n2 is None:
        return out, {"note": "uwezekano wa Forebet haupo"}
    pp, _ = n2
    out[("winner", "P1", None)] = pp
    out[("winner", "P2", None)] = 1 - pp
    if "avg_games" not in ev or "best_of" not in ev:
        return out, {"note": "wastani wa games/best_of haupo → handicap/total ZIMEZIMWA"}
    bo = int(rec.get("best_of") or 3)
    sd_d = SD_TENNIS_DIFF.get(bo, 4.5)
    sd_g = SD_TENNIS_TOTAL.get(bo, 4.0)
    avg = float(rec["avg"])
    mean_d = sd_d * _nppf(pp)
    for line in (3.5,):
        p1h = _ncdf((mean_d + line) / sd_d)
        out[("games_handicap", "P1", line)] = p1h
        out[("games_handicap", "P2", line)] = 1 - p1h
    for off in (-3, 0, 3):
        line = round(avg + off) + 0.5
        ov = 1 - _ncdf((line - avg) / sd_g)
        out[("total_games", "Over", line)] = ov
        out[("total_games", "Under", line)] = 1 - ov
    return out, {"mean_game_diff": round(mean_d, 1), "best_of": bo, "avg_games": avg}


# ------------------------------------------------------------------- flags ----
def flags_for(rec: dict, sport: str, key: str, selection: str,
              p_model: float | None, p_market: float | None,
              fit_err: float | None = None) -> list[str]:
    """Alama za hatari. ZINAPUNGUZA tu — kamwe hazipandishi uwezekano."""
    fl: list[str] = []
    if p_model is not None and p_market is not None and abs(p_model - p_market) > 0.06:
        fl.append("model_vs_market")
    if fit_err is not None and fit_err > 0.05:
        fl.append("model_fit_poor")
    fh, nh = _form_points(rec.get("home_form"))
    fa, na = _form_points(rec.get("away_form"))
    if nh >= 3 and na >= 3 and abs(fh - fa) >= 4:
        fav_home = selection in ("1", "1X", "12", "Home", "P1", "+2 Home", "Home Over")
        if (fh > fa and not fav_home) or (fa > fh and fav_home):
            fl.append("form_against")
    if key in ("1x2", "double_chance", "draw_no_bet") and selection in ("2", "X2"):
        fl.append("favourite_away")
    if key in ("correct_score", "winning_margin"):
        fl.append("high_variance")
    return fl


def blend(p_model: float | None, p_market: float | None, w_model: float,
          flags: list[str], flag_penalty: float, max_penalty: float,
          cap: float) -> tuple[float, bool, bool]:
    """Changanya modeli na soko. Rudia (p_engine, iliyotumia_soko, model_only)."""
    if p_model is None and p_market is None:
        return 0.0, False, True
    if p_market is None:
        p = float(p_model)
        model_only = True
    elif p_model is None:
        p = float(p_market)
        model_only = False
    else:
        p = w_model * float(p_model) + (1 - w_model) * float(p_market)
        model_only = False
    pen = min(len(flags) * flag_penalty, max_penalty)
    if model_only:
        pen = min(pen + flag_penalty, max_penalty)
    p = max(0.0, p - pen)
    return round(min(p, cap), 6), (p_market is not None), model_only
