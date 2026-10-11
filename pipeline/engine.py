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
FOOTBALL_MARKETS = {
    "double_chance_1x",
    *FOOTBALL_1X2_MARKETS,
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


def _football_market_evidence(market: str, features: dict[str, Any]) -> bool:
    if market == "double_chance_1x":
        table_size = _safe_int(features.get("league_table_size"))
        home_played = _safe_int(features.get("home_league_matches"))
        away_played = _safe_int(features.get("away_league_matches"))
        home_position = _safe_int(features.get("home_table_position"), 999)
        return (
            table_size >= 10
            and home_played >= 5
            and away_played >= 5
            and home_position <= 3
            and features.get("away_bottom_five") is True
        )

    if market in FOOTBALL_1X2_MARKETS:
        count_key = {
            "home_win_1x2": "historical_home_win_count",
            "draw_1x2": "historical_draw_count",
            "away_win_1x2": "historical_away_win_count",
        }[market]
        sample = _safe_int(features.get("historical_1x2_sample"))
        hits = _safe_int(features.get(count_key), -1)
        return sample >= 5 and 0 <= hits <= sample and hits >= 4

    if market in {"btts_yes", "btts_no"}:
        sample = _safe_int(features.get("historical_btts_sample"))
        yes_count = _safe_int(features.get("historical_btts_yes_count"), -1)
        if sample < 5 or yes_count < 0 or yes_count > sample:
            return False
        hits = yes_count if market == "btts_yes" else sample - yes_count
        return hits >= 4

    match = re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market)
    if not match:
        return False
    direction, line_tag = match.groups()
    sample = _safe_int(features.get("historical_total_goals_sample"))
    over_count = _safe_int(features.get(f"historical_over_{line_tag}_count"), -1)
    if sample < 5 or over_count < 0 or over_count > sample:
        # Backwards compatibility for the old, stricter 3+ goal flag on O0.5.
        if market == "over_0_5_goals":
            return (
                features.get("historical_high_goal_match") is True
                and _safe_int(features.get("historical_high_goal_sample")) >= 5
            )
        return False
    hits = over_count if direction == "over" else sample - over_count
    return hits >= 4


def _strategy_matches(fixture: dict[str, Any]) -> bool:
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    f = _features(fixture)

    if sport == "football":
        return market in FOOTBALL_MARKETS and _football_market_evidence(market, f)

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
    """A 0–100 ordering signal based on supplied sample evidence only."""
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    f = _features(fixture)

    if sport == "football":
        if market == "double_chance_1x":
            position = _safe_int(f.get("home_table_position"), 3)
            return min(99.0, 78.0 + max(0, 3 - position) * 2.0)
        if market in FOOTBALL_1X2_MARKETS:
            count_key = {
                "home_win_1x2": "historical_home_win_count",
                "draw_1x2": "historical_draw_count",
                "away_win_1x2": "historical_away_win_count",
            }[market]
            hits = _safe_int(f.get(count_key))
            sample = _safe_int(f.get("historical_1x2_sample"), 5)
            return min(99.0, 70.0 + max(0, hits - 3) * 5.0 + max(0, sample - 5))
        if market in {"btts_yes", "btts_no"}:
            sample = max(1, _safe_int(f.get("historical_btts_sample"), 5))
            count = _safe_int(f.get("historical_btts_yes_count"))
            hits = count if market == "btts_yes" else sample - count
            return min(99.0, 70.0 + max(0, hits - 3) * 5.0 + max(0, sample - 5))
        match = re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market)
        if match:
            direction, line_tag = match.groups()
            sample = max(1, _safe_int(f.get("historical_total_goals_sample"), 5))
            count = _safe_int(f.get(f"historical_over_{line_tag}_count"))
            hits = count if direction == "over" else sample - count
            return min(99.0, 70.0 + max(0, hits - 3) * 5.0 + max(0, sample - 5))
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
        note = str(raw.get("analysis_note", "")).strip() or None
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
