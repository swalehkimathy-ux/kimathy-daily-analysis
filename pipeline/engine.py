"""Eligibility, heuristic scoring, and greedy accumulator construction.

The score in this module is only a ranking heuristic (0–100), not a calibrated
probability. Inputs must come from a lawful, licensed or otherwise permitted
sports data source and should include the feature evidence described below.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

ODDS_BANDS = {
    "football": (Decimal("1.08"), Decimal("1.20")),
    "basketball": (Decimal("1.10"), Decimal("1.18")),
    "tennis": (Decimal("1.08"), Decimal("1.15")),
}
TARGET_MIN = Decimal("1.50")
TARGET_MAX = Decimal("1.90")

FOOTBALL_MARKETS = {"over_0_5_goals", "double_chance_1x"}
BASKETBALL_MARKETS = {"home_moneyline", "home_plus_12_5"}
TENNIS_MARKETS = {"match_winner", "to_win_a_set"}


def _decimal(value: Any) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {value!r}") from exc
    if not out.is_finite():
        raise ValueError(f"Non-finite numeric value: {value!r}")
    return out


def _features(fixture: dict[str, Any]) -> dict[str, Any]:
    value = fixture.get("features", {})
    return value if isinstance(value, dict) else {}


def _market_key(fixture: dict[str, Any]) -> str:
    key = fixture.get("market_key") or _features(fixture).get("market_key")
    return str(key or "").strip().lower()


def _strategy_matches(fixture: dict[str, Any]) -> bool:
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    f = _features(fixture)

    if sport == "football":
        try:
            home_position = int(f.get("home_table_position", 999))
        except (TypeError, ValueError):
            home_position = 999
        try:
            table_size = int(f.get("league_table_size", 0))
            home_played = int(f.get("home_league_matches", 0))
            away_played = int(f.get("away_league_matches", 0))
            h2h_sample = int(f.get("historical_high_goal_sample", 0))
        except (TypeError, ValueError):
            table_size = home_played = away_played = h2h_sample = 0
        standings_complete = table_size >= 10 and home_played >= 5 and away_played >= 5
        extreme_mismatch = (
            standings_complete and home_position <= 3 and f.get("away_bottom_five") is True
        )
        high_goal_safe_market = (
            f.get("historical_high_goal_match") is True
            and h2h_sample >= 5
            and market in FOOTBALL_MARKETS
        )
        return extreme_mismatch or high_goal_safe_market

    if sport == "basketball":
        try:
            home_win_rate = float(f.get("home_win_rate", 0))
            away_loss_streak = int(f.get("away_away_losing_streak", 0))
            home_sample = int(f.get("home_home_games_sample", 0))
            away_sample = int(f.get("away_away_games_sample", 0))
        except (TypeError, ValueError):
            return False
        return (
            home_win_rate > 0.80
            and away_loss_streak >= 5
            and home_sample >= 5
            and away_sample >= 5
            and market in BASKETBALL_MARKETS
        )

    if sport == "tennis":
        try:
            favorite_rank = int(f.get("favorite_rank", 999))
            opponent_rank = int(f.get("opponent_rank", 0))
            round_number = int(f.get("round_number", 999))
        except (TypeError, ValueError):
            return False
        return (
            favorite_rank <= 15
            and opponent_rank > 75
            and f.get("preferred_surface") is True
            and round_number <= 2
            and market in TENNIS_MARKETS
        )
    return False


def _heuristic_score(fixture: dict[str, Any]) -> float:
    """Return a transparent 0–100 sorting score from the supplied features."""
    sport = str(fixture.get("sport_type", "")).strip().lower()
    market = _market_key(fixture)
    f = _features(fixture)
    if sport == "football":
        try:
            position = int(f.get("home_table_position", 3))
        except (TypeError, ValueError):
            position = 3
        score = 70.0 + max(0, 3 - position) * 2.5
        if f.get("away_bottom_five") is True:
            score += 8.0
        if f.get("historical_high_goal_match") is True and market in FOOTBALL_MARKETS:
            score += 7.0
        return min(99.0, score)
    if sport == "basketball":
        try:
            win_rate = float(f.get("home_win_rate", 0.81))
            streak = int(f.get("away_away_losing_streak", 5))
        except (TypeError, ValueError):
            win_rate, streak = 0.81, 5
        return min(99.0, 70.0 + max(0.0, win_rate - 0.80) * 60.0 + min(8, streak - 4) * 1.5)
    if sport == "tennis":
        try:
            favorite_rank = int(f.get("favorite_rank", 15))
            opponent_rank = int(f.get("opponent_rank", 76))
        except (TypeError, ValueError):
            favorite_rank, opponent_rank = 15, 76
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
        # Feed adapters must ideally send an explicit offset; naive values are
        # interpreted as UTC rather than silently inheriting runner-local time.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def prepare_fixture(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Validate an incoming provider record and convert it to a DB row.

    Feed feature fields:
      football: home_table_position, away_bottom_five, league_table_size,
                home_league_matches, away_league_matches, historical_high_goal_match,
                historical_high_goal_sample
      basketball: home_win_rate, home_home_games_sample,
                  away_away_losing_streak, away_away_games_sample
      tennis: favorite_rank, opponent_rank, preferred_surface, round_number
    `market_key` must be one of the documented allowed keys in this module.
    """
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
        if not match_name or not market_name:
            return None
        features = _features(raw)
        supplied_score = raw.get("confidence_score", raw.get("analysis_score"))
        score = float(_decimal(supplied_score)) if supplied_score is not None else _heuristic_score(raw)
        if score < 0 or score > 100:
            return None
        return {
            "sport_type": sport,
            "match_name": match_name,
            "match_time": _iso_utc(raw.get("match_time")),
            "market_name": market_name,
            "picked_odds": str(odd.quantize(Decimal("0.01"))),
            "confidence_score": round(score, 2),
            "status": "pending",
            "analysis_note": str(raw.get("analysis_note", "")).strip() or None,
            "source": str(raw.get("source", "licensed-feed")).strip() or "licensed-feed",
        }
    except (ValueError, TypeError, InvalidOperation):
        return None


def _sort_key(fixture: dict[str, Any]) -> tuple[float, str]:
    try:
        score = float(fixture.get("confidence_score", 0))
    except (TypeError, ValueError):
        score = 0.0
    return (-score, str(fixture.get("match_time", "")))


def build_accumulator(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """Greedily add score-ranked pending picks until the target band is reached.

    The maximum is exclusive (total odds must stay strictly below 1.90). A
    candidate that would breach the cap is skipped. If available legs cannot
    reach 1.50, picks are returned with `in_range=False` so the caller can
    avoid publishing the incomplete ticket as a recommended accumulator.
    """
    candidates: list[dict[str, Any]] = []
    for fixture in fixtures:
        sport = str(fixture.get("sport_type", "")).lower()
        if str(fixture.get("status", "pending")).lower() != "pending" or sport not in ODDS_BANDS:
            continue
        try:
            odd = _decimal(fixture.get("picked_odds"))
        except ValueError:
            continue
        low, high = ODDS_BANDS[sport]
        if low <= odd <= high:
            candidates.append(fixture)
    candidates.sort(key=_sort_key)
    picks: list[dict[str, Any]] = []
    total = Decimal("1.00")
    for fixture in candidates:
        try:
            odd = _decimal(fixture.get("picked_odds"))
        except ValueError:
            continue
        candidate_total = total * odd
        if candidate_total >= TARGET_MAX:
            continue
        picks.append(fixture)
        total = candidate_total
        if TARGET_MIN <= total < TARGET_MAX:
            break
    return {
        "picks": picks,
        "total_odds": float(total),
        "in_range": TARGET_MIN <= total < TARGET_MAX,
    }
