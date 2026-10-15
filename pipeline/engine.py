"""Eligibility, evidence scoring, and daily accumulator construction.

Scores are transparent ranking heuristics, not calibrated probabilities. Each
market must have independent, market-specific statistics before it is eligible.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

# Broader per-leg ranges allow supported goal/BTTS and basketball markets to
# contribute while the separate accumulator ceiling remains strictly < 1.90.
ODDS_BANDS = {
    "football": (Decimal("1.05"), Decimal("1.80")),
    "basketball": (Decimal("1.05"), Decimal("1.80")),
    "tennis": (Decimal("1.08"), Decimal("1.15")),
}
TARGET_MIN = Decimal("1.50")
TARGET_MAX = Decimal("1.90")

FOOTBALL_1X2_MARKETS = {"home_win_1x2", "draw_1x2", "away_win_1x2"}
FOOTBALL_SPREAD_MARKETS = {"football_home_spread", "football_away_spread"}
FOOTBALL_MARKETS = {
    "double_chance_1x",
    *FOOTBALL_1X2_MARKETS,
    *FOOTBALL_SPREAD_MARKETS,
    "btts_yes",
    "btts_no",
    "over_0_5_goals",
    "over_1_5_goals",
    "over_2_5_goals",
    "under_0_5_goals",
    "under_1_5_goals",
    "under_2_5_goals",
}
BASKETBALL_MARKETS = {
    "home_moneyline",
    "basketball_total_over",
    "basketball_total_under",
    "basketball_home_spread",
    "basketball_away_spread",
}
TENNIS_MARKETS = {"match_winner", "to_win_a_set"}


def _decimal(value: Any) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid numeric value") from exc
    if not out.is_finite():
        raise ValueError("Non-finite numeric value")
    return out


def _features(fixture: dict[str, Any]) -> dict[str, Any]:
    value = fixture.get("features", {})
    return value if isinstance(value, dict) else {}


def _market_key(fixture: dict[str, Any]) -> str:
    key = fixture.get("market_key") or _features(fixture).get("market_key")
    return str(key or "").strip().lower()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else default
    except (TypeError, ValueError, OverflowError):
        return default


def _valid_rate(features: dict[str, Any], key: str) -> float | None:
    value = _safe_float(features.get(key), -1.0)
    return value if 0.0 <= value <= 1.0 else None


def _football_market_routes(
    market: str,
    features: dict[str, Any],
    market_point: Any = None,
    selection_side: Any = None,
) -> list[str]:
    """Return independently sufficient, market-specific evidence routes.

    Each route has its own minimum sample and rate thresholds. H2H remains
    useful, but is no longer mandatory when relevant recent or venue-split form
    independently clears its stricter alternative threshold.
    """
    market = str(market or "").strip().lower()
    routes: list[str] = []

    if market == "double_chance_1x":
        table_size = _safe_int(features.get("league_table_size"))
        home_played = _safe_int(features.get("home_league_matches"))
        away_played = _safe_int(features.get("away_league_matches"))
        home_position = _safe_int(features.get("home_table_position"), 999)
        if (
            table_size >= 10 and home_played >= 5 and away_played >= 5
            and home_position <= 3 and features.get("away_bottom_five") is True
        ):
            routes.append(
                f"standings: home top-three vs away bottom-five ({home_played}/{away_played} league matches)"
            )

        h2h_sample = _safe_int(features.get("historical_1x2_sample"))
        home_wins = _safe_int(features.get("historical_home_win_count"))
        draws = _safe_int(features.get("historical_draw_count"))
        if h2h_sample >= 5 and 0 <= home_wins + draws <= h2h_sample and home_wins + draws >= 4:
            routes.append(f"H2H 1X: {home_wins + draws}/{h2h_sample}")

        home_sample = _safe_int(features.get("home_team_home_games_sample"))
        away_sample = _safe_int(features.get("away_team_away_games_sample"))
        home_unbeaten = _valid_rate(features, "home_team_home_unbeaten_rate")
        away_losses = _valid_rate(features, "away_team_away_loss_rate")
        if (
            home_sample >= 5 and away_sample >= 5
            and home_unbeaten is not None and home_unbeaten >= 0.80
            and away_losses is not None and away_losses >= 0.60
        ):
            routes.append("venue form: home unbeaten >=4/5; away lost >=3/5 away")
        return routes

    if market in FOOTBALL_1X2_MARKETS:
        count_key = {
            "home_win_1x2": "historical_home_win_count",
            "draw_1x2": "historical_draw_count",
            "away_win_1x2": "historical_away_win_count",
        }[market]
        h2h_sample = _safe_int(features.get("historical_1x2_sample"))
        h2h_hits = _safe_int(features.get(count_key), -1)
        if h2h_sample >= 5 and 0 <= h2h_hits <= h2h_sample and h2h_hits >= 4:
            routes.append(f"H2H selected 1X2 result: {h2h_hits}/{h2h_sample}")

        home_sample = _safe_int(features.get("home_team_home_games_sample"))
        away_sample = _safe_int(features.get("away_team_away_games_sample"))
        home_wins = _valid_rate(features, "home_team_home_win_rate")
        home_losses = _valid_rate(features, "home_team_home_loss_rate")
        home_draws = _valid_rate(features, "home_team_home_draw_rate")
        away_wins = _valid_rate(features, "away_team_away_win_rate")
        away_losses = _valid_rate(features, "away_team_away_loss_rate")
        away_draws = _valid_rate(features, "away_team_away_draw_rate")
        if home_sample >= 5 and away_sample >= 5:
            if (
                market == "home_win_1x2"
                and home_wins is not None and home_wins >= 0.80
                and away_losses is not None and away_losses >= 0.60
            ):
                routes.append("venue form: home won >=4/5 at home; away lost >=3/5 away")
            elif (
                market == "away_win_1x2"
                and away_wins is not None and away_wins >= 0.80
                and home_losses is not None and home_losses >= 0.60
            ):
                routes.append("venue form: away won >=4/5 away; home lost >=3/5 at home")
            elif (
                market == "draw_1x2"
                and home_draws is not None and home_draws >= 0.60
                and away_draws is not None and away_draws >= 0.60
            ):
                routes.append("venue form: each side drew >=3/5 in its relevant venue split")
        return routes

    if market in FOOTBALL_SPREAD_MARKETS:
        expected_side = "home" if market == "football_home_spread" else "away"
        if str(selection_side or "").strip().lower() != expected_side:
            return routes
        try:
            line = _decimal(market_point)
        except ValueError:
            return routes
        try:
            historical_line = _decimal(features.get("historical_spread_line"))
        except ValueError:
            historical_line = None
        try:
            form_line = _decimal(features.get("selected_spread_form_line"))
        except ValueError:
            form_line = None
        if abs(line) > Decimal("5") or line * 2 != (line * 2).to_integral_value():
            return routes
        h2h_sample = _safe_int(features.get("historical_spread_sample"))
        h2h_hits = _safe_int(features.get("historical_spread_cover_count"), -1)
        selected_sample = _safe_int(features.get("selected_spread_form_sample"))
        opponent_sample = _safe_int(features.get("opponent_spread_form_sample"))
        selected_rate = _valid_rate(features, "selected_spread_form_rate")
        opponent_rate = _valid_rate(features, "opponent_spread_form_rate")
        if (
            historical_line is not None and historical_line == line
            and form_line is not None and form_line == line and h2h_sample >= 5
            and 0 <= h2h_hits <= h2h_sample and h2h_hits >= 4
            and selected_sample >= 5 and opponent_sample >= 5
            and selected_rate is not None and selected_rate >= 0.70
            and opponent_rate is not None and opponent_rate <= 0.30
        ):
            routes.append(f"quoted-line H2H {h2h_hits}/{h2h_sample} plus recent cover form")
        if (
            form_line is not None and form_line == line and selected_sample >= 5 and opponent_sample >= 5
            and selected_rate is not None and selected_rate >= 0.80
            and opponent_rate is not None and opponent_rate <= 0.20
        ):
            routes.append("independent recent line form: selected >=4/5; opponent <=1/5")
        return routes

    if market in {"btts_yes", "btts_no"}:
        h2h_sample = _safe_int(features.get("historical_btts_sample"))
        yes_count = _safe_int(features.get("historical_btts_yes_count"), -1)
        if h2h_sample >= 5 and 0 <= yes_count <= h2h_sample:
            hits = yes_count if market == "btts_yes" else h2h_sample - yes_count
            if hits >= 4:
                routes.append(f"H2H BTTS {market.removeprefix('btts_').upper()}: {hits}/{h2h_sample}")

        home_sample = _safe_int(features.get("home_form_matches_sample"))
        away_sample = _safe_int(features.get("away_form_matches_sample"))
        home_yes = _valid_rate(features, "home_form_btts_yes_rate")
        away_yes = _valid_rate(features, "away_form_btts_yes_rate")
        if home_sample >= 5 and away_sample >= 5 and home_yes is not None and away_yes is not None:
            if market == "btts_yes" and home_yes >= 0.60 and away_yes >= 0.60:
                routes.append("independent recent form: BTTS Yes in >=3/5 for each team")
            elif market == "btts_no" and home_yes <= 0.40 and away_yes <= 0.40:
                routes.append("independent recent form: BTTS No in >=3/5 for each team")
        return routes

    match = re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market)
    if not match:
        return routes
    direction, line_tag = match.groups()
    h2h_sample = _safe_int(features.get("historical_total_goals_sample"))
    over_count = _safe_int(features.get(f"historical_over_{line_tag}_count"), -1)
    h2h_hits = -1
    if h2h_sample >= 5 and 0 <= over_count <= h2h_sample:
        h2h_hits = over_count if direction == "over" else h2h_sample - over_count

    home_sample = _safe_int(features.get("home_form_matches_sample"))
    away_sample = _safe_int(features.get("away_form_matches_sample"))
    home_over = _valid_rate(features, f"home_form_over_{line_tag}_rate")
    away_over = _valid_rate(features, f"away_form_over_{line_tag}_rate")
    form_hits = None
    if home_over is not None and away_over is not None:
        form_hits = (
            (home_over, away_over) if direction == "over"
            else (1.0 - home_over, 1.0 - away_over)
        )

    old_form_support = bool(
        home_sample >= 5 and away_sample >= 5 and form_hits is not None
        and min(form_hits) >= 0.40 and sum(form_hits) / 2 >= 0.60
    )
    strong_form_support = bool(
        home_sample >= 5 and away_sample >= 5 and form_hits is not None
        and min(form_hits) >= 0.60 and sum(form_hits) / 2 >= 0.70
    )
    if h2h_hits >= 4 and old_form_support:
        routes.append(f"H2H {direction} {line_tag.replace('_', '.')}: {h2h_hits}/{h2h_sample} plus recent form")
    if strong_form_support:
        routes.append(f"independent recent totals form: each >=3/5 and mean >=70% at {direction} {line_tag.replace('_', '.')}")
    return routes


def _football_market_evidence(
    market: str,
    features: dict[str, Any],
    market_point: Any = None,
    selection_side: Any = None,
) -> bool:
    return bool(_football_market_routes(market, features, market_point, selection_side))


def football_evidence_assessment(fixture: dict[str, Any]) -> dict[str, Any]:
    """Explain the passing route or the missing evidence for a quoted market."""
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    features = _features(fixture)
    if sport != "football":
        return {
            "qualified": False, "route": None, "alternatives": [],
            "reason": "The sport-specific evidence route is not represented in the football assessor.",
        }
    routes = _football_market_routes(
        market, features, fixture.get("market_point"), fixture.get("selection_side")
    )
    if routes:
        return {
            "qualified": True, "route": routes[0], "alternatives": routes[1:],
            "reason": "Evidence route passed: " + routes[0] + ".",
        }

    if market in FOOTBALL_1X2_MARKETS or market == "double_chance_1x":
        h2h_n = _safe_int(features.get("historical_1x2_sample"))
    elif market in {"btts_yes", "btts_no"}:
        h2h_n = _safe_int(features.get("historical_btts_sample"))
    elif market in FOOTBALL_SPREAD_MARKETS:
        h2h_n = _safe_int(features.get("historical_spread_sample"))
    elif re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market):
        h2h_n = _safe_int(features.get("historical_total_goals_sample"))
    else:
        h2h_n = 0
    home_n = _safe_int(features.get("home_form_matches_sample"))
    away_n = _safe_int(features.get("away_form_matches_sample"))
    home_venue_n = _safe_int(features.get("home_team_home_games_sample"))
    away_venue_n = _safe_int(features.get("away_team_away_games_sample"))
    if market in FOOTBALL_1X2_MARKETS:
        criteria = {
            "home_win_1x2": "H2H 4/5, or 5 home games with >=80% home wins plus 5 away games with >=60% away losses",
            "away_win_1x2": "H2H 4/5, or 5 away games with >=80% away wins plus 5 home games with >=60% home losses",
            "draw_1x2": "H2H 4/5, or both venue splits with >=60% draws in five games",
        }[market]
        return {"qualified": False, "route": None, "alternatives": [],
                "reason": f"No 1X2 route passed. Required: {criteria}. Samples now: H2H={h2h_n}, home-at-home={home_venue_n}, away-away={away_venue_n}."}
    if market == "double_chance_1x":
        return {"qualified": False, "route": None, "alternatives": [],
                "reason": f"No 1X route passed. Need top-three/bottom-five standings, H2H 1X >=4/5, or venue form >=4/5 home-unbeaten and >=3/5 away losses. Samples now: H2H={h2h_n}, home-at-home={home_venue_n}, away-away={away_venue_n}."}
    if market in {"btts_yes", "btts_no"}:
        selected = "BTTS Yes >=60% for both teams" if market == "btts_yes" else "BTTS No >=60% for both teams"
        return {"qualified": False, "route": None, "alternatives": [],
                "reason": f"No BTTS route passed. Need H2H >=4/5 or {selected}, with at least five recent games per team. Samples now: H2H={h2h_n}, teams={home_n}/{away_n}."}
    if market in FOOTBALL_SPREAD_MARKETS:
        selected_n = _safe_int(features.get("selected_spread_form_sample"))
        opponent_n = _safe_int(features.get("opponent_spread_form_sample"))
        return {"qualified": False, "route": None, "alternatives": [],
                "reason": f"No spread route passed at the exact quoted line. Need H2H >=4/5 plus recent form, or five samples with selected cover >=80% and opponent <=20%. Samples now: H2H={h2h_n}, form={selected_n}/{opponent_n}."}
    if re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market):
        return {"qualified": False, "route": None, "alternatives": [],
                "reason": f"No totals route passed at the exact line. Need H2H >=4/5 plus form, or five games per team with >=60% selected-line hits for each and mean >=70%. Samples now: H2H={h2h_n}, teams={home_n}/{away_n}."}
    return {"qualified": False, "route": None, "alternatives": [],
            "reason": "No football evidence rule is configured for this market."}

def _strategy_matches(fixture: dict[str, Any]) -> bool:
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    f = _features(fixture)

    if sport == "football":
        if market in FOOTBALL_SPREAD_MARKETS:
            market_name = str(fixture.get("market_name", "")).strip().lower()
            if "two-way" not in market_name or "european" in market_name:
                return False
        return market in FOOTBALL_MARKETS and _football_market_evidence(
            market,
            f,
            fixture.get("market_point"),
            fixture.get("selection_side"),
        )

    if sport == "basketball":
        if market == "home_moneyline":
            home_win_rate = _safe_float(f.get("home_win_rate"))
            away_loss_streak = _safe_int(f.get("away_away_losing_streak"))
            home_sample = _safe_int(f.get("home_home_games_sample"))
            away_sample = _safe_int(f.get("away_away_games_sample"))
            return (
                home_win_rate >= 0.80
                and away_loss_streak >= 5
                and home_sample >= 5
                and away_sample >= 5
            )

        if market in {"basketball_total_over", "basketball_total_under"}:
            home_rate = _safe_float(f.get("home_market_total_hit_rate"), -1)
            away_rate = _safe_float(f.get("away_market_total_hit_rate"), -1)
            home_sample = _safe_int(f.get("home_home_games_sample"))
            away_sample = _safe_int(f.get("away_away_games_sample"))
            if home_sample < 5 or away_sample < 5 or home_rate < 0 or away_rate < 0:
                return False
            if market == "basketball_total_over":
                return home_rate >= 0.70 and away_rate >= 0.70
            return home_rate >= 0.70 and away_rate >= 0.70

        if market in {"basketball_home_spread", "basketball_away_spread"}:
            selection_rate = _safe_float(f.get("selection_cover_rate"), -1)
            opponent_rate = _safe_float(f.get("opponent_cover_rate"), -1)
            selection_sample = _safe_int(f.get("selection_cover_sample"))
            opponent_sample = _safe_int(f.get("opponent_cover_sample"))
            return (
                selection_sample >= 5
                and opponent_sample >= 5
                and selection_rate >= 0.70
                and opponent_rate <= 0.30
            )
        return False

    if sport == "tennis" and market in TENNIS_MARKETS:
        favorite_rank = _safe_int(f.get("favorite_rank"), 999)
        opponent_rank = _safe_int(f.get("opponent_rank"))
        round_number = _safe_int(f.get("round_number"), 999)
        return (
            favorite_rank <= 15
            and opponent_rank > 75
            and f.get("preferred_surface") is True
            and round_number <= 2
        )
    return False


def _heuristic_score(fixture: dict[str, Any]) -> float:
    """A 0–100 ordering signal from a passing evidence route, not a probability."""
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    f = _features(fixture)

    if sport == "football":
        routes = _football_market_routes(
            market, f, fixture.get("market_point"), fixture.get("selection_side")
        )
        if not routes:
            return 0.0
        route = routes[0]
        if market == "double_chance_1x":
            if route.startswith("standings:"):
                position = _safe_int(f.get("home_table_position"), 3)
                return min(92.0, 78.0 + max(0, 3 - position) * 2.0)
            if route.startswith("H2H"):
                hits = _safe_int(f.get("historical_home_win_count")) + _safe_int(f.get("historical_draw_count"))
                return min(89.0, 70.0 + max(0, hits - 3) * 5.0)
            support = (
                (_valid_rate(f, "home_team_home_unbeaten_rate") or 0.0)
                + (_valid_rate(f, "away_team_away_loss_rate") or 0.0)
            ) / 2
            return min(89.0, 70.0 + max(0.0, support - 0.70) * 40.0)
        if market in FOOTBALL_1X2_MARKETS:
            count_key = {
                "home_win_1x2": "historical_home_win_count",
                "draw_1x2": "historical_draw_count",
                "away_win_1x2": "historical_away_win_count",
            }[market]
            if route.startswith("H2H"):
                hits = _safe_int(f.get(count_key))
                return min(89.0, 70.0 + max(0, hits - 3) * 5.0)
            rate_keys = {
                "home_win_1x2": ("home_team_home_win_rate", "away_team_away_loss_rate"),
                "away_win_1x2": ("away_team_away_win_rate", "home_team_home_loss_rate"),
                "draw_1x2": ("home_team_home_draw_rate", "away_team_away_draw_rate"),
            }[market]
            rates = [_valid_rate(f, key) for key in rate_keys]
            if any(rate is None for rate in rates):
                return 0.0
            support = sum(rate for rate in rates if rate is not None) / 2
            baseline = 0.60 if market == "draw_1x2" else 0.70
            return min(89.0, 70.0 + max(0.0, support - baseline) * 40.0)
        if market in FOOTBALL_SPREAD_MARKETS:
            selected_rate = _valid_rate(f, "selected_spread_form_rate")
            opponent_rate = _valid_rate(f, "opponent_spread_form_rate")
            if selected_rate is None or opponent_rate is None:
                return 0.0
            support = max(0.0, selected_rate - 0.70) + max(0.0, 0.30 - opponent_rate)
            h2h_bonus = max(0, _safe_int(f.get("historical_spread_cover_count")) - 3) * 5.0 if route.startswith("quoted-line H2H") else 0.0
            return min(89.0, 70.0 + h2h_bonus + support * 15.0)
        if market in {"btts_yes", "btts_no"}:
            if route.startswith("H2H"):
                sample = _safe_int(f.get("historical_btts_sample"))
                yes_count = _safe_int(f.get("historical_btts_yes_count"))
                hits = yes_count if market == "btts_yes" else sample - yes_count
                return min(89.0, 70.0 + max(0, hits - 3) * 5.0)
            rates = [_valid_rate(f, "home_form_btts_yes_rate"), _valid_rate(f, "away_form_btts_yes_rate")]
            if any(rate is None for rate in rates):
                return 0.0
            selected = [rate if market == "btts_yes" else 1.0 - rate for rate in rates if rate is not None]
            return min(89.0, 70.0 + max(0.0, sum(selected) / 2 - 0.60) * 40.0)
        match = re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market)
        if match:
            direction, line_tag = match.groups()
            over_count = _safe_int(f.get(f"historical_over_{line_tag}_count"), -1)
            sample = _safe_int(f.get("historical_total_goals_sample"))
            h2h_hits = over_count if direction == "over" else sample - over_count
            home_over = _valid_rate(f, f"home_form_over_{line_tag}_rate")
            away_over = _valid_rate(f, f"away_form_over_{line_tag}_rate")
            if home_over is None or away_over is None:
                return 0.0
            selected = (
                (home_over + away_over) / 2 if direction == "over"
                else (2.0 - home_over - away_over) / 2
            )
            h2h_bonus = max(0, h2h_hits - 3) * 5.0 if route.startswith("H2H") else 0.0
            return min(89.0, 70.0 + h2h_bonus + max(0.0, selected - 0.60) * 15.0)
        return 0.0

    if sport == "basketball":
        if market == "home_moneyline":
            win_rate = _safe_float(f.get("home_win_rate"))
            streak = _safe_int(f.get("away_away_losing_streak"))
            return min(99.0, 70.0 + max(0.0, win_rate - 0.80) * 60.0 + min(8, max(0, streak - 4)) * 1.5)
        if market in {"basketball_total_over", "basketball_total_under"}:
            rate = min(
                _safe_float(f.get("home_market_total_hit_rate")),
                _safe_float(f.get("away_market_total_hit_rate")),
            )
            return min(99.0, 70.0 + max(0.0, rate - 0.70) * 60.0)
        if market in {"basketball_home_spread", "basketball_away_spread"}:
            return min(99.0, 70.0 + max(0.0, _safe_float(f.get("selection_cover_rate")) - 0.70) * 60.0)

    if sport == "tennis":
        favorite_rank = _safe_int(f.get("favorite_rank"), 15)
        opponent_rank = _safe_int(f.get("opponent_rank"), 76)
        return min(99.0, 70.0 + max(0, 15 - favorite_rank) * 0.65 + min(12, max(0, opponent_rank - 75) / 5))
    return 0.0

def _iso_utc(value: Any) -> str:
    if not value:
        raise ValueError("match_time is required")
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def prepare_fixture(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a provider record and build a database-ready fixture row."""
    try:
        sport = str(raw.get("sport_type", "")).strip().lower()
        if sport not in ODDS_BANDS or str(raw.get("status", "pending")).lower() != "pending":
            return None
        odd = _decimal(raw.get("picked_odds"))
        low, high = ODDS_BANDS[sport]
        if odd < low or odd > high or not _strategy_matches(raw):
            return None
        match_name = str(raw.get("match_name", "")).strip()
        market_name = str(raw.get("market_name", "")).strip()
        market_key = _market_key(raw)
        if not match_name or not market_name or not market_key:
            return None
        features = _features(raw)
        supplied_score = raw.get("confidence_score", raw.get("analysis_score"))
        score = float(_decimal(supplied_score)) if supplied_score is not None else _heuristic_score(raw)
        if score < 0 or score > 100:
            return None
        point = raw.get("market_point")
        point_value = None if point in (None, "") else str(_decimal(point))
        note = str(raw.get("analysis_note", "")).strip()
        if sport == "football":
            routes = _football_market_routes(
                market_key, features, raw.get("market_point"), raw.get("selection_side")
            )
            if routes:
                route_note = "Evidence route: " + routes[0] + "."
                if len(routes) > 1:
                    route_note += " Also passed: " + "; ".join(routes[1:]) + "."
                note = (note + " " + route_note).strip()
        note = note or None
        source = str(raw.get("source", "licensed-feed")).strip() or "licensed-feed"
        return {
            "sport_type": sport,
            "match_name": match_name,
            "home_team": str(raw.get("home_team", "")).strip() or None,
            "away_team": str(raw.get("away_team", "")).strip() or None,
            "match_time": _iso_utc(raw.get("match_time")),
            "market_name": market_name,
            "market_key": market_key,
            "market_point": point_value,
            "selection_name": str(raw.get("selection_name", "")).strip() or None,
            "selection_side": str(raw.get("selection_side", "")).strip().lower() or None,
            "event_id": str(raw.get("event_id", "")).strip() or None,
            "sport_key": str(raw.get("sport_key", "")).strip() or None,
            "competition": str(raw.get("competition", "")).strip() or None,
            "odds_updated_at": _iso_utc(raw.get("odds_updated_at")) if raw.get("odds_updated_at") else None,
            "picked_odds": str(odd.quantize(Decimal("0.01"))),
            "confidence_score": round(score, 2),
            "status": "pending",
            "analysis_note": note,
            "source": source,
        }
    except (ValueError, TypeError, InvalidOperation):
        return None


def _event_identity(fixture: dict[str, Any]) -> tuple[str, str]:
    sport = str(fixture.get("sport_type", "")).lower()
    event_id = str(fixture.get("event_id", "")).strip()
    if event_id:
        return sport, event_id
    # Conservative fallback when the source does not expose an event ID.
    return sport, "|".join(
        str(fixture.get(key, "")).strip().lower()
        for key in ("match_name", "match_time")
    )


def _sort_key(fixture: dict[str, Any]) -> tuple[float, str]:
    return (
        -_safe_float(fixture.get("confidence_score")),
        str(fixture.get("match_time", "")),
    )


def build_accumulator(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank evidence-backed candidates, never using odds alone.

    At most one market is selected per real event to avoid stacking correlated
    outcomes from the same match. The total must reach 1.50 and remain strictly
    below 1.90; otherwise no ticket is marked ready.
    """
    candidates: list[dict[str, Any]] = []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            continue
        validated = prepare_fixture(fixture)
        if validated:
            candidates.append({**fixture, **validated})
    candidates.sort(key=_sort_key)

    picks: list[dict[str, Any]] = []
    picked_events: set[tuple[str, str]] = set()
    total = Decimal("1.00")
    for fixture in candidates:
        identity = _event_identity(fixture)
        if identity in picked_events:
            continue
        odd = _decimal(fixture["picked_odds"])
        candidate_total = total * odd
        if candidate_total >= TARGET_MAX:
            continue
        picks.append(fixture)
        picked_events.add(identity)
        total = candidate_total
        if TARGET_MIN <= total < TARGET_MAX:
            break
    return {
        "picks": picks,
        "total_odds": float(total),
        "in_range": TARGET_MIN <= total < TARGET_MAX,
    }
