"""candidates.py — mgombea MOJA bora kwa kila mechi (Sehemu 11).

Sheria ya lazima:
  1. Tathmini masoko yote yanayopatikana NA kuungwa mkono na data.
  2. Panga kwa uwezekano, bei/thamani, kutokuwa na uhakika, uaminifu wa data.
  3. Bakiza MGOMBEA MOJA tu kwa mechi.
  4. Mechi inaweza kukosa mgombea kabisa — hiyo ni jibu halali.
"""
from __future__ import annotations

import re

from . import analyze, clock, markets
from .bookies.base import devig, overround

# Majina ya masoko kwenye bookmaker (majaribio kadhaa — tunalinganisha kwa maandishi)
MARKET_ALIASES = {
    "1x2": ["1X2", "Match Result", "Full Time Result", "Win/Draw/Win", "Match Winner", "3-Way Result"],
    "double_chance": ["Double Chance"],
    "draw_no_bet": ["Draw No Bet"],
    "total_goals": ["Total Goals", "Over/Under", "Goals Over/Under", "Total"],
    "btts": ["Both Teams To Score", "BTTS", "Both Teams Score"],
    "team_goals": ["Team Total Goals", "Home Team Total Goals", "Away Team Total Goals", "Team Goals"],
    "asian_handicap": ["Asian Handicap", "Handicap Asian"],
    "european_handicap": ["Handicap", "European Handicap", "3-Way Handicap"],
    "first_to_score": ["First Team To Score", "First To Score"],
    "correct_score": ["Correct Score"],
    "winning_margin": ["Winning Margin", "Winning Margins"],
    "winner": ["Match Winner", "1X2", "Moneyline", "Match Betting", "2-Way Result"],
    "handicap": ["Handicap", "Point Spread", "Spread", "Handicap (incl. OT)"],
    "total_points": ["Total Points", "Points Over/Under", "Total"],
    "games_handicap": ["Games Handicap", "Handicap Games", "Games Spread"],
    "total_games": ["Total Games", "Games Over/Under"],
}

SELECTION_ALIASES = {
    "1": ["1", "Home"], "X": ["X", "Draw"], "2": ["2", "Away"],
    "1X": ["1X", "Home or Draw"], "X2": ["X2", "Draw or Away"], "12": ["12", "Home or Away"],
    "Yes": ["Yes"], "No": ["No"],
    "Over": ["Over"], "Under": ["Under"],
    "P1": ["1", "Home"], "P2": ["2", "Away"],
    "Home": ["Home"], "Away": ["Away"],
    "Home Over": ["Over"], "Home Under": ["Under"], "Away Over": ["Over"], "Away Under": ["Under"],
    "+2 Home": ["Home", "1"], "Draw +2": ["Draw", "X"], "+2 Away": ["Away", "2"],
}

# ------------------------------------------------------------------- block ----
BLOCK_WORDS = ("friendly", "friendlies", "exhibition", "reserve", "academy",
               "youth", "u17", "u18", "u19", "u20", "u21", "u22", "u23",
               "women", "femenino", "doubles", "esports", "virtual", "simulated")
SUFFIX_RE = re.compile(r"\s(w|ii|iii|b)\s*$", re.I)


def blocked_reason(rec: dict, sport: str, cfg) -> str | None:
    text = " ".join([str(rec.get("league", "")), str(rec.get("home", "")),
                     str(rec.get("away", ""))]).lower()
    if cfg.get("leg_filters.block_friendlies", True):
        if "friendly" in text or "friendlies" in text or "exhibition" in text:
            return "mechi_ya_kirafiki"
    if cfg.get("leg_filters.block_youth_and_women", True):
        for w in ("women", "femenino", "youth", "academy", "reserve", "u17", "u18",
                  "u19", "u20", "u21", "u22", "u23"):
            if w in text:
                return f"kikundi_kisichoaminika:{w}"
        if sport != "tennis":
            for t in (rec.get("home", ""), rec.get("away", "")):
                if SUFFIX_RE.search(str(t)):
                    return "jina_lenye_kiambishi_cha_timu_ya_akiba"
    if sport == "tennis" and "doubles" in text:
        return "doubles"
    if any(w in text for w in ("esports", "virtual", "simulated")):
        return "mchezo_wa_kubuni"
    if clock.is_not_eligible_status(rec.get("status")):
        return f"hali_haistahili:{rec.get('status')}"
    return None


# ------------------------------------------------------------- bei za soko ----
def _best_offer(provider, offers, key: str, selection: str, line, rec: dict):
    """Jaribu majina kadhaa ya soko/chaguo; rudisha Offer bora (au None)."""
    sel_names = SELECTION_ALIASES.get(selection, [selection])
    best, best_score = None, -1.0
    for m_alias in MARKET_ALIASES.get(key, [key]):
        for s_alias in sel_names:
            hit = provider.select_offer(offers, m_alias, s_alias, line, False, rec)
            if hit is None:
                continue
            score = _alias_score(m_alias, hit) * 0.5 + _alias_score(s_alias, hit) * 0.5
            if score > best_score:
                best, best_score = hit, score
    return best


def _alias_score(alias: str, offer) -> float:
    from .normalize import team_sim
    return team_sim(alias, offer.market_name or offer.market)


def market_probability(provider, offers: list, key: str, selections: list[str],
                       line, rec: dict) -> dict:
    """Devig ya soko nzima kutoka offers zilizokusanywa.

    Inahitaji bei za chaguo ZOTE za soko hilo — si chaguo moja pekee.
    """
    from . import normalize
    odds_list, found = [], []
    for sel in selections:
        hit = _best_offer(provider, offers, key, sel, line, rec)
        if hit is None or not hit.usable:
            return {"probs": None, "n": 0, "overround": None, "single_source": True}
        odds_list.append(float(hit.odds))
        found.append(hit)
    total = 2.0 if key == "double_chance" else 1.0
    probs = devig(odds_list, total=total)
    books = {o.bookmaker for o in found}
    return {"probs": probs, "n": len(books), "overround": overround(odds_list),
            "single_source": len(books) == 1, "offers": found}


# --------------------------------------------------------------- msingi ------
def build_candidates(rec: dict, sport: str, offers: list, provider, cfg,
                     log=print, max_markets_to_price: int = 8) -> list[dict]:
    """Wagombea wote wa mechi moja ambao WANA BEI HALISI ya bookmaker.

    Soko lisilo na bei ya bookmaker halitumiki — hatutumii odds za Forebet kama mbadala.
    """
    out: list[dict] = []
    pf = cfg.section("probability")
    lf = cfg.section("leg_filters")
    w_model = float(pf.get("weight_model", 0.5))
    cap = float(pf.get("uncalibrated_cap", 0.95))
    fpen = float(pf.get("flag_penalty", 0.01))
    fmax = float(pf.get("max_flag_penalty", 0.03))
    odds_min = float(lf.get("leg_odds_min", 1.05))
    odds_max = float(lf.get("leg_odds_max", 3.50))
    min_prob = float(lf.get("min_probability", 0.75))

    ev = analyze.evidence_of(rec, sport)
    model, info = analyze.model_markets(rec, sport)
    fit_err = info.get("fit_err")

    rows = []
    for mdef in markets.markets_for(sport):
        ok, why = markets.eligibility(mdef, ev)
        if not ok:
            continue
        if not markets.discoverable(mdef):
            continue
        for (key, sel, line), p_model in model.items():
            if key != mdef.key:
                continue
            if not (0.0 < p_model <= 1.0):
                continue
            rows.append((p_model, mdef, sel, line))

    rows.sort(key=lambda r: -r[0])
    priced = 0
    for p_model, mdef, sel, line in rows:
        if priced >= max_markets_to_price:
            break
        hit = _best_offer(provider, offers, mdef.key, sel, line, rec)
        if hit is None or not hit.usable:
            continue
        priced += 1
        odds = float(hit.odds)
        if not (odds_min <= odds <= odds_max):
            continue
        # uwezekano wa soko (devig) — unahitaji soko nzima
        sels = _selections_for(mdef, sel, line)
        mp = market_probability(provider, offers, mdef.key, sels, line, rec)
        p_market = None
        if mp.get("probs"):
            try:
                idx = sels.index(sel)
                p_market = mp["probs"][idx]
            except (ValueError, IndexError):
                p_market = None
        fl = analyze.flags_for(rec, sport, mdef.key, sel, p_model, p_market, fit_err)
        if mp.get("single_source") and p_market is not None:
            fl.append("single_source")
        if mp.get("overround") is not None and mp["overround"] > 0.12:
            fl.append("margin_kubwa")
        p_eng, used_market, model_only = analyze.blend(
            p_model, p_market, w_model, fl, fpen, fmax, cap)
        if len(fl) > int(lf.get("max_flags_before_drop", 3)):
            continue
        if p_eng < min_prob:
            continue
        out.append({
            "event_id": rec.get("event_id", ""), "sport": sport,
            "league": rec.get("league", ""), "home": rec.get("home", ""),
            "away": rec.get("away", ""), "match": f"{rec.get('home','')} vs {rec.get('away','')}",
            "kickoff_tz": rec.get("kickoff_tz"),
            "market_key": mdef.key,
            "market_name": hit.market_name or hit.market or mdef.name,
            "market_name_engine": mdef.name, "line": line,
            "selection": sel, "selection_bookmaker": hit.outcome,
            "p_model": round(p_model, 4),
            "p_market": round(p_market, 4) if p_market is not None else None,
            "p_engine": p_eng, "model_only": model_only,
            "calibrated": bool(pf.get("calibration_enabled", False)),
            "odds": odds, "bookmaker": hit.bookmaker, "odds_source": hit.source_url,
            "odds_retrieved_at": hit.retrieved_at,
            "overround": mp.get("overround"),
            "ev": round(p_eng * odds - 1.0, 4),
            "flags": fl, "reasons": _reasons(mdef, sel, p_model, p_market, info),
            "forebet_url": rec.get("source_url", ""),
            "evidence": sorted(ev),
        })
    out.sort(key=lambda c: (-c["p_engine"], -c["odds"], -c["ev"]))
    return out


def _selections_for(mdef, sel, line) -> list[str]:
    """Chaguo zote za soko hilo (kwa devig ya soko nzima)."""
    if mdef.key == "1x2":
        return ["1", "X", "2"]
    if mdef.key == "double_chance":
        return ["1X", "X2", "12"]
    if mdef.key in ("draw_no_bet", "btts", "winner"):
        return ["1", "2"] if mdef.key == "draw_no_bet" else (
            ["Yes", "No"] if mdef.key == "btts" else ["P1", "P2"])
    if mdef.key in ("total_goals", "total_points", "total_games", "games_handicap",
                    "asian_handicap", "handicap", "team_goals"):
        base = sel.split()[0] if sel.split()[0] in ("Over", "Under") else sel.split()[0]
        if mdef.key == "team_goals":
            side = sel.split()[0]
            return [f"{side} Over", f"{side} Under"]
        if mdef.key in ("asian_handicap", "handicap", "games_handicap"):
            return ["Home", "Away"] if mdef.key == "asian_handicap" else (
                ["P1", "P2"] if mdef.key == "games_handicap" else ["Home", "Away"])
        return ["Over", "Under"]
    if mdef.key == "european_handicap":
        return ["+2 Home", "Draw +2", "+2 Away"]
    if mdef.key == "first_to_score":
        return ["Home", "Away", "None"]
    return [sel]


def _reasons(mdef, sel, p_model, p_market, info) -> list[str]:
    r = [f"model: {p_model:.1%}"]
    if p_market is not None:
        r.append(f"soko (devig): {p_market:.1%}")
    else:
        r.append("bei ya soko haikupatikana → model pekee (uaminifu mdogo)")
    if mdef.high_variance:
        r.append("soko lenye variance kubwa")
    if info.get("fit_err") is not None:
        r.append(f"makosa ya modeli ya magoli: {info['fit_err']:.3f}")
    if info.get("note"):
        r.append(info["note"])
    return r


def best_per_match(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Bakiza mgombea MOJA bora kwa kila mechi. Rudia (bora, zilizokataliwa)."""
    best: dict[str, dict] = {}
    rejected: list[dict] = []
    for c in sorted(candidates, key=lambda x: (-x["p_engine"], -x["odds"], -x["ev"])):
        k = c["event_id"] or f"{c['home']}|{c['away']}"
        if k in best:
            rejected.append(c)
            continue
        best[k] = c
    return list(best.values()), rejected
