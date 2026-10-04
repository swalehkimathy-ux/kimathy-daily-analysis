"""API-Sports form/statistics enrichment for The Odds API candidates.

Only independently sourced, sufficiently complete evidence is attached. This
module does not turn odds into a win probability and does not fabricate stats.
Requests are bounded per API product, checked against the provider status
endpoint before data calls, and all errors are sanitized so API keys never
appear in logs.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

import requests

FOOTBALL_BASE = "https://v3.football.api-sports.io"
BASKETBALL_BASE = "https://v1.basketball.api-sports.io"
EAT = ZoneInfo("Africa/Dar_es_Salaam")
DEFAULT_RUN_LIMIT = 60
FOOTBALL_STANDINGS_LIMIT = 12
FOOTBALL_H2H_LIMIT = 30
BASKETBALL_TEAM_HISTORY_LIMIT = 40
MIN_STANDINGS_MATCHES = 5
MIN_STANDINGS_TEAMS = 10

FINAL_FOOTBALL_STATUSES = {"ft", "aet", "pen", "awd", "wo", "finished", "final"}
FINAL_BASKETBALL_STATUSES = {"ft", "aot", "finished", "final", "completed", "3"}


class APISportsError(RuntimeError):
    """Sanitized API-Sports failure that never contains the API key or URL."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APISportsQuotaError(APISportsError):
    """Raised when the local/account quota guard declines another call."""


@dataclass
class APISportsEnrichment:
    fixtures: list[dict[str, Any]]
    football_calls: int = 0
    basketball_calls: int = 0
    football_remaining: int | None = None
    basketball_remaining: int | None = None
    football_enriched: int = 0
    basketball_enriched: int = 0
    warnings: list[str] = field(default_factory=list)


class APISportsClient:
    """Small quota-aware client for one API-Sports product."""

    def __init__(
        self,
        product: str,
        api_key: str,
        max_run_calls: int = DEFAULT_RUN_LIMIT,
        timeout: int = 30,
        session: Any = None,
    ):
        product = str(product or "").strip().lower()
        if product not in {"football", "basketball"}:
            raise APISportsError("Unsupported API-Sports product.")
        key = str(api_key or "").strip()
        if not key:
            raise APISportsError(f"API key for API-Sports {product} is not configured.")
        self.product = product
        self.base_url = FOOTBALL_BASE if product == "football" else BASKETBALL_BASE
        self._api_key = key
        self.max_run_calls = max(1, int(max_run_calls))
        self.timeout = max(1, int(timeout))
        self.session = session if session is not None else requests
        self.calls_used = 0
        self.account_remaining: int | None = None
        self.call_budget = self.max_run_calls
        self.status_checked = False

    def _request_json(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        billable: bool,
    ) -> dict[str, Any]:
        if billable:
            if not self.status_checked:
                raise APISportsQuotaError(
                    f"API-Sports {self.product}: quota status was not checked; skipping data requests."
                )
            if self.calls_used >= self.call_budget:
                raise APISportsQuotaError(
                    f"API-Sports {self.product}: safe per-run/daily request budget is exhausted."
                )

        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=params or {},
                headers={"x-apisports-key": self._api_key, "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException:
            raise APISportsError(
                f"API-Sports {self.product} could not be reached; request details were suppressed."
            ) from None
        except Exception:
            raise APISportsError(
                f"API-Sports {self.product} request failed unexpectedly; details were suppressed."
            ) from None

        status = int(getattr(response, "status_code", 0) or 0)
        if status < 200 or status >= 300:
            if status in {401, 403}:
                message = f"API-Sports {self.product} rejected the key/access (HTTP {status}); check the provider dashboard privately."
            elif status == 429:
                message = f"API-Sports {self.product} rate/daily quota was reached (HTTP 429)."
            else:
                message = f"API-Sports {self.product} request failed (HTTP {status}); response details were suppressed."
            raise APISportsError(message, status_code=status)
        if billable:
            # Count every successful HTTP response, including a provider-level
            # data error returned with HTTP 200.
            self.calls_used += 1
        try:
            payload = response.json()
        except Exception:
            raise APISportsError(
                f"API-Sports {self.product} returned unreadable JSON; response details were suppressed."
            ) from None
        if not isinstance(payload, dict):
            raise APISportsError(
                f"API-Sports {self.product} returned an unexpected response structure."
            )
        errors = payload.get("errors")
        if errors:
            raise APISportsError(
                f"API-Sports {self.product} reported a data/request error for {endpoint}; details were suppressed."
            )
        return payload

    def inspect_quota(self) -> int:
        """Read the non-quota status endpoint and reserve one call for safety."""
        payload = self._request_json("status", billable=False)
        response = payload.get("response")
        if not isinstance(response, dict):
            raise APISportsError(
                f"API-Sports {self.product} status response did not include account quota data."
            )
        requests_info = response.get("requests")
        if not isinstance(requests_info, dict):
            raise APISportsError(
                f"API-Sports {self.product} status response did not include request limits."
            )
        current = _to_int(requests_info.get("current"))
        limit_day = _to_int(requests_info.get("limit_day"))
        if current is None or limit_day is None:
            raise APISportsError(
                f"API-Sports {self.product} status response did not include usable daily limits."
            )
        # Keep one extra request in reserve in case status accounting is delayed.
        self.account_remaining = max(0, limit_day - current - 1)
        self.call_budget = min(self.max_run_calls, self.account_remaining)
        self.status_checked = True
        return self.account_remaining

    @property
    def remaining_estimate(self) -> int | None:
        if self.account_remaining is None:
            return None
        return max(0, self.account_remaining - self.calls_used)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request_json(endpoint, params=params, billable=True)


def _to_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_time(value: Any, *, assume_timezone=EAT) -> tuple[datetime | None, bool]:
    """Return an aware UTC time and whether the source supplied date only."""
    if value is None:
        return None, False
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc), False
        except (OverflowError, OSError, ValueError):
            return None, False
    if isinstance(value, dict):
        value = value.get("date") or value.get("start") or value.get("datetime")
    if not value:
        return None, False
    text = str(value).strip()
    date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
    try:
        if date_only:
            parsed = datetime.fromisoformat(text).replace(tzinfo=assume_timezone)
        else:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=assume_timezone)
        return parsed.astimezone(timezone.utc), date_only
    except (TypeError, ValueError):
        return None, date_only


def _name_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    ignored = {"fc", "cf", "sc", "afc", "club", "basketball", "bc"}
    return " ".join(token for token in text.split() if token not in ignored)


def _name_similarity(first: Any, second: Any) -> float:
    left, right = _name_key(first), _name_key(second)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens, right_tokens = set(left.split()), set(right.split())
    common = left_tokens & right_tokens
    if len(common) >= 2 and (left_tokens <= right_tokens or right_tokens <= left_tokens):
        return 0.93
    return SequenceMatcher(None, left, right).ratio()


def _response_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", [])
    if isinstance(response, dict):
        return [response]
    if not isinstance(response, list):
        return []
    return [row for row in response if isinstance(row, dict)]


def _id(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _game_parts(row: dict[str, Any]) -> dict[str, Any]:
    """Read the common API-Football/API-Basketball event shape."""
    fixture = row.get("fixture") or row.get("game") or row
    if not isinstance(fixture, dict):
        fixture = row
    teams = row.get("teams") or fixture.get("teams") or {}
    if not isinstance(teams, dict):
        teams = {}
    home = teams.get("home") or row.get("home") or {}
    away = teams.get("away") or row.get("away") or {}
    if not isinstance(home, dict):
        home = {}
    if not isinstance(away, dict):
        away = {}
    league = row.get("league") or fixture.get("league") or {}
    if not isinstance(league, dict):
        league = {}
    raw_time = (
        fixture.get("date")
        or row.get("date")
        or fixture.get("timestamp")
        or row.get("timestamp")
    )
    event_time, date_only = _parse_time(raw_time)
    return {
        "id": _id(fixture.get("id") or row.get("id")),
        "time": event_time,
        "date_only": date_only,
        "home_id": _id(home.get("id")),
        "away_id": _id(away.get("id")),
        "home_name": str(home.get("name") or home.get("nickname") or "").strip(),
        "away_name": str(away.get("name") or away.get("nickname") or "").strip(),
        "league_id": _id(league.get("id")),
        "league_name": str(league.get("name") or league.get("league") or "").strip(),
        "season": league.get("season") or row.get("season") or fixture.get("season"),
        "status": fixture.get("status") or row.get("status"),
        "raw": row,
    }


def _candidate_matches_game(
    candidate: dict[str, Any], game: dict[str, Any], target_day: date, tolerance_hours: int = 4
) -> tuple[float, float] | None:
    home_score = _name_similarity(candidate.get("home_team"), game.get("home_name"))
    away_score = _name_similarity(candidate.get("away_team"), game.get("away_name"))
    if home_score < 0.86 or away_score < 0.86:
        return None
    game_time = game.get("time")
    candidate_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
    if candidate_time is None:
        return None
    if game_time is None:
        return None
    if game.get("date_only"):
        if game_time.astimezone(EAT).date() != target_day:
            return None
        delta_minutes = 0.0
    else:
        delta_minutes = abs((game_time - candidate_time).total_seconds()) / 60
        if delta_minutes > tolerance_hours * 60:
            return None
    return home_score + away_score, delta_minutes


def _best_match(
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
    target_day: date,
    tolerance_hours: int = 4,
) -> dict[str, Any] | None:
    matches: list[tuple[float, float, dict[str, Any]]] = []
    for row in rows:
        parts = _game_parts(row)
        comparison = _candidate_matches_game(candidate, parts, target_day, tolerance_hours)
        if comparison is not None:
            score, delta = comparison
            matches.append((score, delta, parts))
    if not matches:
        return None
    matches.sort(key=lambda item: (-item[0], item[1], item[2].get("id", "")))
    if len(matches) > 1:
        first, second = matches[0], matches[1]
        if abs(first[0] - second[0]) < 0.01 and abs(first[1] - second[1]) < 1:
            return None  # Ambiguous mapping: refuse to attach possibly wrong stats.
    return matches[0][2]


def _played_count(row: dict[str, Any]) -> int | None:
    for parent in (row.get("all"), row.get("home"), row.get("games"), row):
        if isinstance(parent, dict):
            for key in ("played", "games", "total"):
                value = _to_int(parent.get(key))
                if value is not None:
                    return value
    return None


def _standings_values(
    payload: dict[str, Any], home_id: str, away_id: str
) -> tuple[int, bool, int, int, int] | None:
    for league_row in _response_rows(payload):
        league = league_row.get("league", {})
        if not isinstance(league, dict):
            continue
        tables = league.get("standings", [])
        if isinstance(tables, list) and tables and all(isinstance(row, dict) for row in tables):
            tables = [tables]
        if not isinstance(tables, list):
            continue
        for table in tables:
            if not isinstance(table, list):
                continue
            home_row = away_row = None
            for standing in table:
                if not isinstance(standing, dict):
                    continue
                team = standing.get("team", {})
                team_id = _id(team.get("id")) if isinstance(team, dict) else ""
                if team_id == home_id:
                    home_row = standing
                if team_id == away_id:
                    away_row = standing
            if home_row is None or away_row is None:
                continue
            home_rank = _to_int(home_row.get("rank"))
            away_rank = _to_int(away_row.get("rank"))
            home_played = _played_count(home_row)
            away_played = _played_count(away_row)
            size = len(table)
            if None in (home_rank, away_rank, home_played, away_played):
                continue
            if size < MIN_STANDINGS_TEAMS or home_played < MIN_STANDINGS_MATCHES or away_played < MIN_STANDINGS_MATCHES:
                continue
            away_bottom_five = away_rank >= size - 4
            return home_rank, away_bottom_five, size, home_played, away_played
    return None


def _final_status(status: Any, sport: str) -> bool:
    if isinstance(status, dict):
        values = [status.get("short"), status.get("long"), status.get("name")]
    else:
        values = [status]
    normalized = {str(value).strip().lower() for value in values if value is not None}
    allowed = FINAL_FOOTBALL_STATUSES if sport == "football" else FINAL_BASKETBALL_STATUSES
    return any(value in allowed or "match finished" in value for value in normalized)


def _goals(row: dict[str, Any]) -> tuple[int, int] | None:
    goals = row.get("goals")
    if isinstance(goals, dict):
        home, away = _to_int(goals.get("home")), _to_int(goals.get("away"))
        if home is not None and away is not None:
            return home, away
    return None


def _football_h2h_high_goal(
    payload: dict[str, Any], target_time: datetime
) -> tuple[bool, int, int] | None:
    results: list[tuple[datetime, int]] = []
    for row in _response_rows(payload):
        parts = _game_parts(row)
        score = _goals(row)
        if not score or not parts.get("time") or parts["time"] >= target_time:
            continue
        if not _final_status(parts.get("status"), "football"):
            continue
        results.append((parts["time"], score[0] + score[1]))
    results.sort(key=lambda item: item[0], reverse=True)
    sample = results[:5]
    if len(sample) < 5:
        return None
    high_goal_count = sum(total >= 3 for _, total in sample)
    return high_goal_count >= 4, high_goal_count, len(sample)


def _append_note(candidate: dict[str, Any], note: str, add_source: bool = True) -> None:
    existing = str(candidate.get("analysis_note", "")).strip()
    stale = " The odds feed does not include the form/ranking evidence required for a recommendation."
    if stale in existing:
        existing = existing.replace(stale, "")
    candidate["analysis_note"] = (existing + " Evidence: " + note).strip()
    if add_source:
        source = str(candidate.get("source", "")).strip()
        if source and "api-sports" not in source:
            candidate["source"] = source + "+api-sports"
        elif not source:
            candidate["source"] = "api-sports"


def _safe_get(
    client: APISportsClient,
    endpoint: str,
    params: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any] | None:
    try:
        return client.get(endpoint, params)
    except APISportsQuotaError as exc:
        if len(warnings) < 12:
            warnings.append(str(exc))
        return None
    except APISportsError as exc:
        if len(warnings) < 12:
            warnings.append(str(exc))
        return None


def _football_enrich(
    candidates: list[dict[str, Any]],
    api_key: str,
    day: date,
    now_utc: datetime,
    warnings: list[str],
    session: Any = None,
) -> tuple[int, int, int | None]:
    client = APISportsClient("football", api_key, session=session)
    try:
        client.inspect_quota()
    except APISportsError as exc:
        warnings.append(str(exc))
        return 0, 0, client.account_remaining
    fixtures_payload = _safe_get(
        client,
        "fixtures",
        {"date": day.isoformat(), "timezone": "Africa/Dar_es_Salaam"},
        warnings,
    )
    if not fixtures_payload:
        return client.calls_used, 0, client.remaining_estimate
    provider_fixtures = _response_rows(fixtures_payload)
    matches: dict[int, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        candidate_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
        if (
            not candidate_time
            or candidate_time <= now_utc
            or candidate_time.astimezone(EAT).date() != day
        ):
            continue
        matched = _best_match(candidate, provider_fixtures, day)
        if matched:
            matches[index] = matched

    standings_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    standings_calls = 0
    h2h_calls = 0
    enriched_count = 0
    h2h_cache: dict[tuple[str, str], tuple[bool, int, int] | None] = {}
    for index, provider_game in matches.items():
        candidate = candidates[index]
        league_id = provider_game.get("league_id")
        season = provider_game.get("season")
        home_id, away_id = provider_game.get("home_id"), provider_game.get("away_id")
        features = dict(candidate.get("features") or {})
        notes: list[str] = []
        if league_id and season and home_id and away_id:
            league_key = (str(league_id), str(season))
            if league_key not in standings_cache:
                standings_cache[league_key] = None
                if standings_calls < FOOTBALL_STANDINGS_LIMIT and client.calls_used < client.call_budget:
                    standings_payload = _safe_get(
                        client,
                        "standings",
                        {"league": league_id, "season": season},
                        warnings,
                    )
                    standings_calls += 1
                    if standings_payload:
                        standings_cache[league_key] = standings_payload
            standings_payload = standings_cache.get(league_key)
            if standings_payload:
                evidence = _standings_values(standings_payload, home_id, away_id)
                if evidence:
                    home_position, away_bottom, table_size, home_played, away_played = evidence
                    features["home_table_position"] = home_position
                    features["away_bottom_five"] = away_bottom
                    features["league_table_size"] = table_size
                    features["home_league_matches"] = home_played
                    features["away_league_matches"] = away_played
                    notes.append(
                        f"API-Football standings: home rank {home_position}; "
                        f"away bottom-five={away_bottom} in {table_size}-team table "
                        f"({home_played}/{away_played} league matches played)."
                    )

        market_key = str(candidate.get("market_key", "")).lower()
        if (
            market_key in {"over_0_5_goals", "double_chance_1x"}
            and home_id
            and away_id
            and h2h_calls < FOOTBALL_H2H_LIMIT
        ):
            pair_key = tuple(sorted((home_id, away_id)))
            if pair_key not in h2h_cache:
                h2h_cache[pair_key] = None
                if client.calls_used < client.call_budget:
                    h2h_payload = _safe_get(
                        client,
                        "fixtures/headtohead",
                        {"h2h": f"{home_id}-{away_id}", "last": 5},
                        warnings,
                    )
                    if h2h_payload:
                        target_time, _ = _parse_time(
                            candidate.get("match_time"), assume_timezone=timezone.utc
                        )
                        if target_time:
                            h2h_cache[pair_key] = _football_h2h_high_goal(
                                h2h_payload, target_time
                            )
                    h2h_calls += 1
            h2h_result = h2h_cache.get(pair_key)
            if h2h_result is not None:
                high_goal, high_count, sample_size = h2h_result
                features["historical_high_goal_match"] = high_goal
                features["historical_high_goal_sample"] = sample_size
                notes.append(
                    f"API-Football last {sample_size} head-to-head matches: "
                    f"{high_count}/{sample_size} had 3+ goals; high-goal flag={high_goal}."
                )
        if features != dict(candidate.get("features") or {}):
            candidate["features"] = features
            _append_note(candidate, " ".join(notes) if notes else "Football evidence enriched.")
            enriched_count += 1
    return client.calls_used, enriched_count, client.remaining_estimate


def _basketball_score(row: dict[str, Any], side: str) -> int | None:
    scores = row.get("scores")
    if not isinstance(scores, dict):
        return None
    value = scores.get(side)
    if not isinstance(value, dict):
        return None
    for key in ("total", "points", "score"):
        parsed = _to_int(value.get(key))
        if parsed is not None:
            return parsed
    return None


def _basketball_history_metrics(
    games: list[dict[str, Any]],
    team_id: str,
    role: str,
    target_time: datetime,
) -> tuple[float | None, int, int, int]:
    home_results: list[tuple[datetime, bool]] = []
    away_results: list[tuple[datetime, bool]] = []
    for row in games:
        parts = _game_parts(row)
        game_time = parts.get("time")
        if not game_time or game_time >= target_time:
            continue
        if not _final_status(parts.get("status"), "basketball"):
            continue
        home_id, away_id = parts.get("home_id"), parts.get("away_id")
        home_score, away_score = _basketball_score(row, "home"), _basketball_score(row, "away")
        if home_score is None or away_score is None:
            continue
        if role == "home" and home_id == team_id:
            home_results.append((game_time, home_score > away_score))
        if role == "away" and away_id == team_id:
            away_results.append((game_time, away_score < home_score))
    home_results.sort(key=lambda item: item[0], reverse=True)
    away_results.sort(key=lambda item: item[0], reverse=True)

    recent_home = home_results[:10]
    home_rate = None
    if len(recent_home) >= 5:
        home_rate = sum(1 for _, won in recent_home if won) / len(recent_home)

    streak = 0
    for _, lost in away_results:
        if not lost:
            break
        streak += 1
    return home_rate, streak, len(recent_home), len(away_results)


def _basketball_enrich(
    candidates: list[dict[str, Any]],
    api_key: str,
    day: date,
    now_utc: datetime,
    warnings: list[str],
    session: Any = None,
) -> tuple[int, int, int | None]:
    client = APISportsClient("basketball", api_key, session=session)
    try:
        client.inspect_quota()
    except APISportsError as exc:
        warnings.append(str(exc))
        return 0, 0, client.account_remaining
    games_payload = _safe_get(
        client,
        "games",
        {"date": day.isoformat(), "timezone": "Africa/Dar_es_Salaam"},
        warnings,
    )
    if not games_payload:
        return client.calls_used, 0, client.remaining_estimate
    provider_games = _response_rows(games_payload)
    matches: dict[int, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        candidate_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
        if (
            not candidate_time
            or candidate_time <= now_utc
            or candidate_time.astimezone(EAT).date() != day
        ):
            continue
        matched = _best_match(candidate, provider_games, day)
        if matched and matched.get("home_id") and matched.get("away_id"):
            matches[index] = matched

    history_cache: dict[tuple[str, str, str], list[dict[str, Any]] | None] = {}
    history_calls = 0
    enriched_count = 0
    for index, provider_game in matches.items():
        candidate = candidates[index]
        league_id = provider_game.get("league_id")
        season = provider_game.get("season")
        home_id, away_id = provider_game.get("home_id"), provider_game.get("away_id")
        target_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
        if not league_id or not season or not home_id or not away_id or not target_time:
            continue
        features = dict(candidate.get("features") or {})
        notes: list[str] = []
        metrics: dict[str, tuple[float | None, int, int, int]] = {}
        for team_id, role in ((home_id, "home"), (away_id, "away")):
            cache_key = (team_id, str(league_id), str(season))
            if cache_key not in history_cache:
                history_cache[cache_key] = None
                if history_calls < BASKETBALL_TEAM_HISTORY_LIMIT and client.calls_used < client.call_budget:
                    history_payload = _safe_get(
                        client,
                        "games",
                        {"team": team_id, "league": league_id, "season": season},
                        warnings,
                    )
                    history_calls += 1
                    if history_payload:
                        history_cache[cache_key] = _response_rows(history_payload)
            history = history_cache.get(cache_key)
            if history is not None:
                metrics[role] = _basketball_history_metrics(history, team_id, role, target_time)
        home_stats = metrics.get("home")
        away_stats = metrics.get("away")
        if home_stats and home_stats[0] is not None:
            features["home_win_rate"] = round(home_stats[0], 4)
            features["home_home_games_sample"] = home_stats[2]
            notes.append(
                f"API-Basketball last {home_stats[2]} home games: "
                f"home win rate {home_stats[0]:.1%}."
            )
        if away_stats and away_stats[3] >= 5:
            features["away_away_losing_streak"] = away_stats[1]
            features["away_away_games_sample"] = away_stats[3]
            notes.append(
                f"API-Basketball last {away_stats[3]} away games: "
                f"current away losing streak {away_stats[1]}."
            )
        if features != dict(candidate.get("features") or {}):
            candidate["features"] = features
            if notes:
                _append_note(candidate, " ".join(notes))
            enriched_count += 1
    return client.calls_used, enriched_count, client.remaining_estimate


def enrich_odds_candidates(
    candidates: list[dict[str, Any]],
    *,
    api_sports_key: str = "",
    football_key: str = "",
    basketball_key: str = "",
    analysis_day: date | str | None = None,
    now: datetime | None = None,
    sessions: dict[str, Any] | None = None,
) -> APISportsEnrichment:
    """Add verified API-Sports evidence to odds candidates where joins succeed.

    A shared dashboard key may be passed in ``api_sports_key``. Product-specific
    keys take precedence when the dashboard supplies separate credentials.
    """
    rows = [dict(candidate) for candidate in candidates if isinstance(candidate, dict)]
    for row in rows:
        existing_features = row.get("features")
        row["features"] = dict(existing_features) if isinstance(existing_features, dict) else {}
    now_utc = _as_utc(now)
    if isinstance(analysis_day, str):
        try:
            day = date.fromisoformat(analysis_day)
        except ValueError:
            raise APISportsError("Analysis date must use YYYY-MM-DD format.") from None
    else:
        day = analysis_day or now_utc.astimezone(EAT).date()

    shared_key = str(api_sports_key or "").strip()
    f_key = str(football_key or shared_key).strip()
    b_key = str(basketball_key or shared_key).strip()
    result = APISportsEnrichment(fixtures=rows)
    sessions = sessions or {}

    football_candidates = [row for row in rows if str(row.get("sport_type", "")).lower() == "football"]
    basketball_candidates = [row for row in rows if str(row.get("sport_type", "")).lower() == "basketball"]
    if football_candidates and f_key:
        result.football_calls, result.football_enriched, result.football_remaining = _football_enrich(
            football_candidates, f_key, day, now_utc, result.warnings, sessions.get("football")
        )
    if basketball_candidates and b_key:
        result.basketball_calls, result.basketball_enriched, result.basketball_remaining = _basketball_enrich(
            basketball_candidates, b_key, day, now_utc, result.warnings, sessions.get("basketball")
        )
    return result
