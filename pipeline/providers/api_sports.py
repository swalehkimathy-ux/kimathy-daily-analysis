"""API-Sports schedule discovery and statistics enrichment for Odds API quotes.

The date-based provider schedule is retained as the fixture universe even when
there are no matching Odds API candidates. Only independently sourced,
sufficiently complete evidence is attached to candidates. This
module does not turn odds into a win probability and does not fabricate stats.
Requests are bounded per API product, checked against the provider status
endpoint before data calls, and all errors are sanitized so API keys never
appear in logs.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

import requests

FOOTBALL_BASE = "https://v3.football.api-sports.io"
BASKETBALL_BASE = "https://v1.basketball.api-sports.io"
EAT = ZoneInfo("Africa/Dar_es_Salaam")
DEFAULT_RUN_LIMIT = 60
# API-FOOTBALL Free-plan rate limit is 10 requests/minute. Pace the production
# client at a 6.2-second minimum start-to-start interval (including /status).
FREE_PLAN_MIN_REQUEST_INTERVAL_SECONDS = 6.2
FOOTBALL_STANDINGS_LIMIT = 8
# Reserve within the 60-call enrichment ceiling: one schedule + up to 8 standings
# + 27 H2H + 24 recent-team-form calls. Provider quota may lower this further.
FOOTBALL_H2H_LIMIT = 27
FOOTBALL_FORM_LIMIT = 24
BASKETBALL_TEAM_HISTORY_LIMIT = 40
FOOTBALL_SPREAD_MARKETS = {"football_home_spread", "football_away_spread"}
FOOTBALL_TOTAL_MARKETS = {
    "over_0_5_goals", "over_1_5_goals", "over_2_5_goals",
    "under_0_5_goals", "under_1_5_goals", "under_2_5_goals",
}
FOOTBALL_BTTS_MARKETS = {"btts_yes", "btts_no"}
FOOTBALL_VENUE_FORM_MARKETS = {"home_win_1x2", "draw_1x2", "away_win_1x2", "double_chance_1x"}
FOOTBALL_FORM_MARKETS = (
    FOOTBALL_TOTAL_MARKETS | FOOTBALL_SPREAD_MARKETS
    | FOOTBALL_BTTS_MARKETS | FOOTBALL_VENUE_FORM_MARKETS
)
FOOTBALL_H2H_MARKETS = {
    "btts_yes", "btts_no", *FOOTBALL_TOTAL_MARKETS,
    "home_win_1x2", "draw_1x2", "away_win_1x2", "double_chance_1x", *FOOTBALL_SPREAD_MARKETS,
}
MIN_STANDINGS_MATCHES = 5
MIN_STANDINGS_TEAMS = 10

# Verified provider display-name variant observed in the live fixture join log.
# Canonicalize only this explicit alias; do not relax the 0.86 fuzzy threshold.
TEAM_NAME_ALIASES = {
    "lask": "lask linz",
    "lask linz": "lask linz",
}

FINAL_FOOTBALL_STATUSES = {"ft", "aet", "pen", "awd", "wo", "finished", "final"}
FINAL_BASKETBALL_STATUSES = {"ft", "aot", "finished", "final", "completed", "3"}


class APISportsError(RuntimeError):
    """Sanitized API-Sports failure that never contains the API key or URL."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APISportsQuotaError(APISportsError):
    """Raised when the local/account quota guard declines another call."""


def _safe_error_text(value: Any, limit: int = 180) -> str:
    """Keep useful provider diagnostics while redacting credentials and URLs."""
    text = str(value or "")
    text = re.sub(r"https?://\S+", "<url>", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?i)\b(x-apisports-key|api[\s_-]*key|authorization)\b\s*[:=]\s*[^,;\s]+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(r"(?i)\b(bearer|token)\s+[^,;\s]{12,}", r"\1 <redacted>", text)
    # Also remove credential-like opaque strings if a provider echoes one without
    # a label. Normal fixture IDs and short team IDs are unaffected.
    text = re.sub(r"(?<![A-Za-z0-9])[A-Za-z0-9._~+/=-]{32,}(?![A-Za-z0-9])", "<redacted>", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text[:limit] or "unspecified provider error"


def _safe_error_summary(errors: Any) -> str:
    """Summarize API-Sports errors without logging request headers or secrets."""
    if isinstance(errors, dict):
        entries = list(errors.items())[:5]
        parts = []
        for key, value in entries:
            field_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(key)).strip("_")[:32] or "field"
            parts.append(f"{field_name}: {_safe_error_text(value, 120)}")
        return "; ".join(parts)[:500] or "unspecified provider error"
    if isinstance(errors, (list, tuple)):
        return "; ".join(_safe_error_text(value, 120) for value in list(errors)[:4])[:500]
    return _safe_error_text(errors, 500)


@dataclass
class APISportsEnrichment:
    fixtures: list[dict[str, Any]]
    football_calls: int = 0
    basketball_calls: int = 0
    football_remaining: int | None = None
    basketball_remaining: int | None = None
    football_enriched: int = 0
    basketball_enriched: int = 0
    football_schedule: list[dict[str, Any]] = field(default_factory=list)
    basketball_schedule: list[dict[str, Any]] = field(default_factory=list)
    football_join_diagnostics: dict[str, int] = field(default_factory=dict)
    basketball_join_diagnostics: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)




@dataclass
class APISportsSettlement:
    """Verified final-score updates for previously published fixtures."""

    updates: list[dict[str, Any]] = field(default_factory=list)
    football_calls: int = 0
    basketball_calls: int = 0
    football_candidates: int = 0
    basketball_candidates: int = 0
    football_settled: int = 0
    basketball_settled: int = 0
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
        min_request_interval_seconds: float | None = None,
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
        if min_request_interval_seconds is None:
            # Dependency-injected fake sessions are used in offline tests, where
            # waiting would only slow the suite. The live runner uses requests.
            min_request_interval_seconds = (
                0.0 if session is not None else FREE_PLAN_MIN_REQUEST_INTERVAL_SECONDS
            )
        self.min_request_interval_seconds = max(0.0, float(min_request_interval_seconds))
        self._last_request_started_at: float | None = None
        self.calls_used = 0
        self.account_remaining: int | None = None
        self.call_budget = self.max_run_calls
        self.status_checked = False

    def _pace_request(self) -> None:
        """Keep requests below the API-Sports Free-plan 10/minute ceiling."""
        now = time.monotonic()
        if self._last_request_started_at is not None:
            remaining = self.min_request_interval_seconds - (now - self._last_request_started_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_started_at = time.monotonic()

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

        self._pace_request()
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
                provider_details = ""
                try:
                    error_payload = response.json()
                    if isinstance(error_payload, dict) and error_payload.get("errors"):
                        provider_details = _safe_error_summary(error_payload.get("errors"))
                except Exception:
                    provider_details = ""
                message = (
                    f"API-Sports {self.product} rejected the request (HTTP 429); "
                    f"sanitized provider details: {provider_details}."
                    if provider_details else
                    f"API-Sports {self.product} rate/daily quota was reached (HTTP 429)."
                )
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
            safe_summary = _safe_error_summary(errors)
            raise APISportsError(
                f"API-Sports {self.product} reported a data/request error for {endpoint}; "
                f"sanitized provider details: {safe_summary}."
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
    normalized = " ".join(token for token in text.split() if token not in ignored)
    return TEAM_NAME_ALIASES.get(normalized, normalized)


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


def normalise_schedule_fixtures(
    rows: list[dict[str, Any]], sport_type: str, analysis_day: date
) -> list[dict[str, Any]]:
    """Normalize a provider's date-schedule rows into a complete fixture board.

    The board deliberately includes started/finished fixtures from the requested
    EAT date; the picker separately rejects anything that is no longer upcoming.
    """
    sport = str(sport_type or "").strip().lower()
    if sport not in {"football", "basketball"}:
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        parts = _game_parts(row)
        home = str(parts.get("home_name") or "").strip()
        away = str(parts.get("away_name") or "").strip()
        if not home or not away:
            continue
        kickoff = parts.get("time")
        date_only = bool(parts.get("date_only"))
        if kickoff is None:
            continue
        if kickoff.astimezone(EAT).date() != analysis_day:
            continue
        fixture_id = str(parts.get("id") or "").strip()
        if not fixture_id:
            fixture_id = "|".join((sport, analysis_day.isoformat(), home.casefold(), away.casefold()))
        if fixture_id in seen:
            continue
        seen.add(fixture_id)
        raw_status = parts.get("status")
        if isinstance(raw_status, dict):
            status_short = str(raw_status.get("short") or "").strip().upper()
            status_long = str(raw_status.get("long") or raw_status.get("name") or "").strip()
        else:
            status_short = str(raw_status or "").strip().upper()
            status_long = str(raw_status or "").strip()
        final = _final_status(raw_status, sport)
        live_codes = {"1H", "HT", "2H", "ET", "P", "LIVE", "Q1", "Q2", "Q3", "Q4", "OT", "INPLAY"}
        if final:
            state = "finished"
        elif status_short in live_codes or "in play" in status_long.lower():
            state = "live"
        elif status_short in {"PST", "POSTPONED"} or "postpon" in status_long.lower():
            state = "postponed"
        elif status_short in {"CANC", "CANCELLED", "CANCELED"} or "cancel" in status_long.lower():
            state = "cancelled"
        elif status_short in {"ABD", "ABANDONED"} or "abandon" in status_long.lower():
            state = "abandoned"
        else:
            state = "scheduled"
        league = row.get("league") or row.get("leagueData") or {}
        if not isinstance(league, dict):
            league = {}
        normalized.append({
            "sport_type": sport,
            "provider_fixture_id": fixture_id,
            "provider_home_team_id": str(parts.get("home_id") or "") or None,
            "provider_away_team_id": str(parts.get("away_id") or "") or None,
            "provider_league_id": str(parts.get("league_id") or "") or None,
            "provider_season": str(parts.get("season") or "") or None,
            "match_name": f"{home} vs {away}",
            "home_team": home,
            "away_team": away,
            "match_time": kickoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "kickoff_time_known": not date_only,
            "kickoff_time_source": "api-sports" if not date_only else "api-sports-date-only",
            "competition": str(parts.get("league_name") or "Unknown competition").strip(),
            "country": str(league.get("country") or "").strip() or None,
            "round": str(league.get("round") or row.get("round") or "").strip() or None,
            "provider_status": status_short or status_long or "unknown",
            "fixture_state": state,
            "analysis_date": analysis_day.isoformat(),
            "source": "api-sports",
        })
    return sorted(normalized, key=lambda item: (item["match_time"], item["competition"], item["match_name"]))


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


def _best_match_with_reason(
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
    target_day: date,
    tolerance_hours: int = 4,
) -> tuple[dict[str, Any] | None, str]:
    """Conservative fixture join plus a safe reason code for diagnostics."""
    if not rows:
        return None, "provider_schedule_empty"
    candidate_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
    if candidate_time is None:
        return None, "invalid_candidate_time"
    matches: list[tuple[float, float, dict[str, Any]]] = []
    saw_team_pair = False
    for row in rows:
        parts = _game_parts(row)
        home_score = _name_similarity(candidate.get("home_team"), parts.get("home_name"))
        away_score = _name_similarity(candidate.get("away_team"), parts.get("away_name"))
        if home_score < 0.86 or away_score < 0.86:
            continue
        saw_team_pair = True
        game_time = parts.get("time")
        if game_time is None:
            continue
        if parts.get("date_only"):
            if game_time.astimezone(EAT).date() != target_day:
                continue
            delta_minutes = 0.0
        else:
            delta_minutes = abs((game_time - candidate_time).total_seconds()) / 60
            if delta_minutes > tolerance_hours * 60:
                continue
        matches.append((home_score + away_score, delta_minutes, parts))
    if not matches:
        return None, "kickoff_time_mismatch" if saw_team_pair else "team_names_not_matched"
    matches.sort(key=lambda item: (-item[0], item[1], item[2].get("id", "")))
    if len(matches) > 1:
        first, second = matches[0], matches[1]
        if abs(first[0] - second[0]) < 0.01 and abs(first[1] - second[1]) < 1:
            return None, "ambiguous_fixture_match"
    return matches[0][2], "matched"


def _best_match(
    candidate: dict[str, Any],
    rows: list[dict[str, Any]],
    target_day: date,
    tolerance_hours: int = 4,
) -> dict[str, Any] | None:
    return _best_match_with_reason(candidate, rows, target_day, tolerance_hours)[0]


def _reset_join_diagnostics(diagnostics: dict[str, int] | None, candidate_count: int) -> None:
    if diagnostics is None:
        return
    diagnostics.clear()
    diagnostics.update({
        "candidate_count": candidate_count,
        "same_day_future_candidates": 0,
        "provider_schedule_rows": 0,
        "matched_candidates": 0,
        "out_of_scope": 0,
        "provider_schedule_empty": 0,
        "team_names_not_matched": 0,
        "kickoff_time_mismatch": 0,
        "ambiguous_fixture_match": 0,
        "invalid_candidate_time": 0,
    })


def _closest_fixture_join_sample(
    candidate: dict[str, Any], rows: list[dict[str, Any]]
) -> str | None:
    """Return a short public-name comparison for a failed team-name join."""
    best: tuple[float, float, float, str, str] | None = None
    for row in rows:
        parts = _game_parts(row)
        api_home = str(parts.get("home_name", "")).strip()
        api_away = str(parts.get("away_name", "")).strip()
        home_score = _name_similarity(candidate.get("home_team"), api_home)
        away_score = _name_similarity(candidate.get("away_team"), api_away)
        total = home_score + away_score
        if best is None or total > best[0]:
            best = (total, home_score, away_score, api_home, api_away)
    if best is None:
        return None

    def compact(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:55]

    _, home_score, away_score, api_home, api_away = best
    candidate_name = (
        f"{compact(candidate.get('home_team'))} vs {compact(candidate.get('away_team'))}"
    )
    provider_name = f"{compact(api_home)} vs {compact(api_away)}"
    return f"{candidate_name} <> {provider_name} (name scores {home_score:.2f}/{away_score:.2f})"


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


def _football_h2h_evidence(
    payload: dict[str, Any],
    target_time: datetime,
    fixture_home_id: str | None = None,
    fixture_away_id: str | None = None,
    selected_team_id: str | None = None,
    market_point: Any = None,
) -> dict[str, Any] | None:
    future_home, future_away = _id(fixture_home_id), _id(fixture_away_id)
    results: list[tuple[datetime, int, int, str, str]] = []
    for row in _response_rows(payload):
        parts = _game_parts(row)
        score = _goals(row)
        game_time = parts.get("time")
        historical_home, historical_away = parts.get("home_id", ""), parts.get("away_id", "")
        if not score or not game_time or game_time >= target_time:
            continue
        if not _final_status(parts.get("status"), "football"):
            continue
        if future_home and future_away and not (
            {historical_home, historical_away} == {future_home, future_away}
        ):
            continue
        results.append((game_time, score[0], score[1], historical_home, historical_away))
    results.sort(key=lambda item: item[0], reverse=True)
    sample = results[:5]
    if not sample:
        return None

    totals = [home + away for _, home, away, _, _ in sample]
    btts_yes_count = sum(1 for _, home, away, _, _ in sample if home > 0 and away > 0)
    evidence: dict[str, Any] = {
        "historical_total_goals_sample": len(sample),
        "historical_btts_sample": len(sample),
        "historical_btts_yes_count": btts_yes_count,
        "historical_h2h_latest_game_at": sample[0][0].isoformat(),
    }
    for tag, threshold in (("0_5", 1), ("1_5", 2), ("2_5", 3)):
        evidence[f"historical_over_{tag}_count"] = sum(1 for total in totals if total >= threshold)
    evidence["historical_high_goal_match"] = evidence["historical_over_2_5_count"] >= 4
    evidence["historical_high_goal_sample"] = len(sample)

    if future_home and future_away:
        outcomes: list[str] = []
        for _, score_home, score_away, historical_home, historical_away in sample:
            if historical_home == future_home and historical_away == future_away:
                outcomes.append("home" if score_home > score_away else "away" if score_home < score_away else "draw")
            elif historical_home == future_away and historical_away == future_home:
                outcomes.append("away" if score_home > score_away else "home" if score_home < score_away else "draw")
        evidence["historical_1x2_sample"] = len(outcomes)
        evidence["historical_home_win_count"] = outcomes.count("home")
        evidence["historical_draw_count"] = outcomes.count("draw")
        evidence["historical_away_win_count"] = outcomes.count("away")

    selected_id = _id(selected_team_id)
    if selected_id and future_home and future_away:
        try:
            line = Decimal(str(market_point))
        except (InvalidOperation, TypeError, ValueError):
            line = None
        if (
            line is not None
            and line.is_finite()
            and abs(line) <= Decimal("5")
            and line * 2 == (line * 2).to_integral_value()
        ):
            covers: list[bool] = []
            for _, score_home, score_away, historical_home, historical_away in sample:
                if historical_home == selected_id:
                    selected_score, opponent_score = score_home, score_away
                elif historical_away == selected_id:
                    selected_score, opponent_score = score_away, score_home
                else:
                    continue
                covers.append(Decimal(selected_score) + line > Decimal(opponent_score))
            evidence["historical_spread_sample"] = len(covers)
            evidence["historical_spread_cover_count"] = sum(covers)
            evidence["historical_spread_line"] = str(line)
    return evidence


def _football_team_form_records(
    payload: dict[str, Any],
    team_id: str,
    target_time: datetime,
    venue: str | None = None,
) -> list[tuple[datetime, int, int]]:
    """Return up to five latest completed scorelines before kickoff.

    With ``venue="home"`` or ``venue="away"``, restrict the list to the
    team's corresponding home/away fixtures. Venue samples remain separate
    from the all-competition recent-form samples.
    """
    requested_team = _id(team_id)
    requested_venue = str(venue or "").strip().lower()
    if requested_venue not in {"", "home", "away"}:
        raise ValueError("venue must be home, away, or None")
    records: list[tuple[datetime, int, int]] = []
    if not requested_team:
        return records
    for row in _response_rows(payload):
        parts = _game_parts(row)
        game_time = parts.get("time")
        score = _goals(row)
        home_id, away_id = parts.get("home_id", ""), parts.get("away_id", "")
        if (
            not game_time
            or game_time >= target_time
            or not score
            or not _final_status(parts.get("status"), "football")
        ):
            continue
        if home_id == requested_team and requested_venue in {"", "home"}:
            goals_for, goals_against = score
        elif away_id == requested_team and requested_venue in {"", "away"}:
            goals_for, goals_against = score[1], score[0]
        else:
            continue
        records.append((game_time, goals_for, goals_against))
    records.sort(key=lambda item: item[0], reverse=True)
    return records[:5]


def _football_form_features(
    home_records: list[tuple[datetime, int, int]],
    away_records: list[tuple[datetime, int, int]],
    market_key: str,
    market_point: Any,
    selection_side: Any,
    home_venue_records: list[tuple[datetime, int, int]] | None = None,
    away_venue_records: list[tuple[datetime, int, int]] | None = None,
) -> dict[str, Any]:
    """Summarize recent overall and venue-split football form, with sample sizes."""
    features: dict[str, Any] = {}
    for role, records in (("home", home_records), ("away", away_records)):
        features[f"{role}_form_matches_sample"] = len(records)
        if not records:
            continue
        features[f"{role}_form_latest_game_at"] = records[0][0].isoformat()
        features[f"{role}_form_goals_for_average"] = round(
            sum(goals_for for _, goals_for, _ in records) / len(records), 3
        )
        features[f"{role}_form_goals_against_average"] = round(
            sum(goals_against for _, _, goals_against in records) / len(records), 3
        )
        features[f"{role}_form_btts_yes_rate"] = round(
            sum(goals_for > 0 and goals_against > 0 for _, goals_for, goals_against in records)
            / len(records), 4
        )
        totals = [goals_for + goals_against for _, goals_for, goals_against in records]
        for tag, threshold in (("0_5", 1), ("1_5", 2), ("2_5", 3)):
            features[f"{role}_form_over_{tag}_rate"] = round(
                sum(total >= threshold for total in totals) / len(totals), 4
            )

    venue_splits = (
        ("home_team_home", home_venue_records or []),
        ("away_team_away", away_venue_records or []),
    )
    for prefix, records in venue_splits:
        features[f"{prefix}_games_sample"] = len(records)
        if not records:
            continue
        features[f"{prefix}_latest_game_at"] = records[0][0].isoformat()
        wins = sum(goals_for > goals_against for _, goals_for, goals_against in records)
        draws = sum(goals_for == goals_against for _, goals_for, goals_against in records)
        losses = sum(goals_for < goals_against for _, goals_for, goals_against in records)
        count = len(records)
        features[f"{prefix}_win_rate"] = round(wins / count, 4)
        features[f"{prefix}_draw_rate"] = round(draws / count, 4)
        features[f"{prefix}_loss_rate"] = round(losses / count, 4)
        if prefix == "home_team_home":
            features[f"{prefix}_unbeaten_rate"] = round((wins + draws) / count, 4)

    if market_key in FOOTBALL_SPREAD_MARKETS:
        try:
            line = Decimal(str(market_point))
        except (InvalidOperation, TypeError, ValueError):
            return features
        side = str(selection_side or "").strip().lower()
        if (
            not line.is_finite()
            or abs(line) > Decimal("5")
            or line * 2 != (line * 2).to_integral_value()
            or side not in {"home", "away"}
        ):
            return features
        selected_records, opponent_records = (
            (home_records, away_records) if side == "home" else (away_records, home_records)
        )
        selected_hits = sum(
            Decimal(goals_for) + line > Decimal(goals_against)
            for _, goals_for, goals_against in selected_records
        )
        opponent_line = -line
        opponent_hits = sum(
            Decimal(goals_for) + opponent_line > Decimal(goals_against)
            for _, goals_for, goals_against in opponent_records
        )
        features.update({
            "selected_spread_form_line": str(line),
            "selected_spread_form_sample": len(selected_records),
            "selected_spread_form_cover_count": selected_hits,
            "selected_spread_form_rate": round(selected_hits / len(selected_records), 4) if selected_records else None,
            "opponent_spread_form_sample": len(opponent_records),
            "opponent_spread_form_cover_count": opponent_hits,
            "opponent_spread_form_rate": round(opponent_hits / len(opponent_records), 4) if opponent_records else None,
        })
    return features

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
    diagnostics: dict[str, int] | None = None,
    schedule_rows_out: list[dict[str, Any]] | None = None,
) -> tuple[int, int, int | None]:
    _reset_join_diagnostics(diagnostics, len(candidates))
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
    if schedule_rows_out is not None:
        schedule_rows_out.extend(dict(row) for row in provider_fixtures)
    if diagnostics is not None:
        diagnostics["provider_schedule_rows"] = len(provider_fixtures)
    matches: dict[int, dict[str, Any]] = {}
    unmatched_samples: list[str] = []
    for index, candidate in enumerate(candidates):
        candidate_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
        if (
            not candidate_time
            or candidate_time <= now_utc
            or candidate_time.astimezone(EAT).date() != day
        ):
            if diagnostics is not None:
                diagnostics["out_of_scope"] += 1
            continue
        if diagnostics is not None:
            diagnostics["same_day_future_candidates"] += 1
        matched, reason = _best_match_with_reason(candidate, provider_fixtures, day)
        if diagnostics is not None and reason != "matched":
            diagnostics[reason] = diagnostics.get(reason, 0) + 1
        if reason == "team_names_not_matched" and len(unmatched_samples) < 3:
            sample = _closest_fixture_join_sample(candidate, provider_fixtures)
            if sample:
                unmatched_samples.append(sample)
        if matched:
            matches[index] = matched
            candidates[index]["provider_fixture_id"] = matched.get("id") or None
            candidates[index]["provider_home_team_id"] = matched.get("home_id") or None
            candidates[index]["provider_away_team_id"] = matched.get("away_id") or None
            candidates[index]["provider_league_id"] = matched.get("league_id") or None
            candidates[index]["provider_season"] = matched.get("season")
    if unmatched_samples:
        warnings.append(
            "API-Sports fixture join unmatched examples (Odds API <> API-Sports): "
            + " | ".join(unmatched_samples)
        )
    if diagnostics is not None:
        diagnostics["matched_candidates"] = len(matches)

    standings_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    standings_calls = 0
    h2h_calls = 0
    form_calls = 0
    # Count attempted calls too, because provider-side errors may still consume
    # quota even when the client cannot count a successful response.
    core_requests_used = client.calls_used  # includes the successful schedule request
    enriched_count = 0
    h2h_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    team_history_cache: dict[str, dict[str, Any] | None] = {}
    working_features = {
        index: dict(candidates[index].get("features") or {}) for index in matches
    }
    notes_by_index: dict[int, list[str]] = {index: [] for index in matches}

    def enrichment_priority(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, _ = item
        market = str(candidates[index].get("market_key", "")).lower()
        if market in FOOTBALL_FORM_MARKETS:
            priority = 0
        elif market in FOOTBALL_H2H_MARKETS:
            priority = 1
        else:
            priority = 2
        return priority, index

    ordered_matches = sorted(matches.items(), key=enrichment_priority)
    # Hold room for up to 24 recent-team-form calls while reserving the rest for
    # schedule, standings and H2H. At low account quota the reserve scales down.
    form_reserve = min(
        FOOTBALL_FORM_LIMIT,
        max(0, ((client.call_budget - 1) // 3) * 2),
    )
    core_budget = max(1, client.call_budget - form_reserve)

    for index, provider_game in ordered_matches:
        candidate = candidates[index]
        league_id = provider_game.get("league_id")
        season = provider_game.get("season")
        home_id, away_id = provider_game.get("home_id"), provider_game.get("away_id")
        features = working_features[index]
        market_key = str(candidate.get("market_key", "")).lower()

        if market_key == "double_chance_1x" and league_id and season and home_id and away_id:
            league_key = (str(league_id), str(season))
            if league_key not in standings_cache:
                standings_cache[league_key] = None
                if standings_calls < FOOTBALL_STANDINGS_LIMIT and core_requests_used < core_budget:
                    standings_payload = _safe_get(
                        client,
                        "standings",
                        {"league": league_id, "season": season},
                        warnings,
                    )
                    standings_calls += 1
                    core_requests_used += 1
                    if standings_payload:
                        standings_cache[league_key] = standings_payload
            standings_payload = standings_cache.get(league_key)
            if standings_payload:
                evidence = _standings_values(standings_payload, str(home_id), str(away_id))
                if evidence:
                    home_position, away_bottom, table_size, home_played, away_played = evidence
                    features["home_table_position"] = home_position
                    features["away_bottom_five"] = away_bottom
                    features["league_table_size"] = table_size
                    features["home_league_matches"] = home_played
                    features["away_league_matches"] = away_played
                    notes_by_index[index].append(
                        f"API-Football standings: home rank {home_position}; "
                        f"away bottom-five={away_bottom} in {table_size}-team table "
                        f"({home_played}/{away_played} league matches played)."
                    )

        if market_key not in FOOTBALL_H2H_MARKETS or not home_id or not away_id:
            continue
        pair_key = (str(home_id), str(away_id))
        if pair_key not in h2h_cache:
            if h2h_calls < FOOTBALL_H2H_LIMIT and core_requests_used < core_budget:
                h2h_payload = _safe_get(
                    client,
                    "fixtures/headtohead",
                    # Free API-Sports plans reject the `last` filter. Retrieve the
                    # provider-allowed H2H set and keep the most recent five locally
                    # in _football_h2h_evidence, strictly before kickoff.
                    {"h2h": f"{home_id}-{away_id}"},
                    warnings,
                )
                h2h_cache[pair_key] = h2h_payload
                h2h_calls += 1
                core_requests_used += 1
        h2h_payload = h2h_cache.get(pair_key)
        if not h2h_payload:
            continue
        target_time, _ = _parse_time(
            candidate.get("match_time"), assume_timezone=timezone.utc
        )
        if not target_time:
            continue
        side = str(candidate.get("selection_side", "")).strip().lower()
        selected_id = (
            str(home_id) if side == "home"
            else str(away_id) if side == "away"
            else None
        )
        h2h_result = _football_h2h_evidence(
            h2h_payload,
            target_time,
            str(home_id),
            str(away_id),
            selected_id,
            candidate.get("market_point"),
        )
        if h2h_result is None:
            continue
        features.update(h2h_result)
        h2h_n = h2h_result.get("historical_total_goals_sample", 0)
        notes_by_index[index].append(
            f"API-Football latest completed head-to-head sample ({h2h_n}/5 available before kickoff): "
            f"1+/2+/3+ goals in {h2h_result['historical_over_0_5_count']}/"
            f"{h2h_result['historical_over_1_5_count']}/"
            f"{h2h_result['historical_over_2_5_count']}; "
            f"BTTS Yes in {h2h_result['historical_btts_yes_count']}/{h2h_result.get('historical_btts_sample', 0)}; "
            f"upcoming-home wins/draws/away wins "
            f"{h2h_result.get('historical_home_win_count', 0)}/"
            f"{h2h_result.get('historical_draw_count', 0)}/"
            f"{h2h_result.get('historical_away_win_count', 0)} "
            f"from {h2h_result.get('historical_1x2_sample', 0)} team-ID-matched games."
        )
        if market_key in FOOTBALL_SPREAD_MARKETS and "historical_spread_sample" in h2h_result:
            notes_by_index[index].append(
                f"At quoted two-way spread line {candidate.get('market_point')}: "
                f"selected side covered {h2h_result['historical_spread_cover_count']}/"
                f"{h2h_result['historical_spread_sample']} completed H2Hs."
            )

    # Gather recent records for each relevant football market independently of
    # H2H availability. Team endpoints are cached, and venue splits are derived
    # locally from the same bounded pre-kickoff histories.
    form_limit = min(FOOTBALL_FORM_LIMIT, max(0, client.call_budget - core_requests_used))
    for index, provider_game in ordered_matches:
        candidate = candidates[index]
        market_key = str(candidate.get("market_key", "")).lower()
        if market_key not in FOOTBALL_FORM_MARKETS:
            continue
        target_time, _ = _parse_time(
            candidate.get("match_time"), assume_timezone=timezone.utc
        )
        home_id, away_id = provider_game.get("home_id"), provider_game.get("away_id")
        if not target_time or not home_id or not away_id:
            continue
        team_ids = list(dict.fromkeys((str(home_id), str(away_id))))
        uncached_ids = [team_id for team_id in team_ids if team_id not in team_history_cache]
        if form_calls + len(uncached_ids) > form_limit:
            continue
        if core_requests_used + form_calls + len(uncached_ids) > client.call_budget:
            continue
        for team_id in uncached_ids:
            form_end_day = target_time.astimezone(EAT).date()
            form_start_day = form_end_day - timedelta(days=365)
            # The Free plan rejects `last`; use its date-window filters and
            # select the latest five completed scorelines locally.
            team_history_cache[team_id] = _safe_get(
                client,
                "fixtures",
                {
                    "team": team_id,
                    "from": form_start_day.isoformat(),
                    "to": form_end_day.isoformat(),
                    "timezone": "Africa/Dar_es_Salaam",
                },
                warnings,
            )
            form_calls += 1

        home_payload = team_history_cache.get(str(home_id))
        away_payload = team_history_cache.get(str(away_id))
        if not home_payload or not away_payload:
            continue
        home_records = _football_team_form_records(home_payload, str(home_id), target_time)
        away_records = _football_team_form_records(away_payload, str(away_id), target_time)
        home_venue_records = _football_team_form_records(
            home_payload, str(home_id), target_time, venue="home"
        )
        away_venue_records = _football_team_form_records(
            away_payload, str(away_id), target_time, venue="away"
        )
        form_features = _football_form_features(
            home_records,
            away_records,
            market_key,
            candidate.get("market_point"),
            candidate.get("selection_side"),
            home_venue_records,
            away_venue_records,
        )
        if not form_features:
            continue
        features = working_features[index]
        features.update(form_features)

        home_n = form_features.get("home_form_matches_sample", 0)
        away_n = form_features.get("away_form_matches_sample", 0)
        form_note = (
            "Recent team scorelines before kickoff (API-Football, all competitions): "
            f"home sample {home_n}/5, away sample {away_n}/5."
        )
        if home_records:
            form_note += (
                f" Home {form_features['home_form_goals_for_average']:.2f} goals for/"
                f"{form_features['home_form_goals_against_average']:.2f} against; "
                f"BTTS Yes {form_features['home_form_btts_yes_rate']:.0%}."
            )
        if away_records:
            form_note += (
                f" Away {form_features['away_form_goals_for_average']:.2f} goals for/"
                f"{form_features['away_form_goals_against_average']:.2f} against; "
                f"BTTS Yes {form_features['away_form_btts_yes_rate']:.0%}."
            )
        home_venue_n = form_features.get("home_team_home_games_sample", 0)
        away_venue_n = form_features.get("away_team_away_games_sample", 0)
        form_note += f" Venue samples: home team at home {home_venue_n}/5; away team away {away_venue_n}/5."
        if home_venue_records:
            form_note += (
                f" Home-at-home W/D/L {form_features['home_team_home_win_rate']:.0%}/"
                f"{form_features['home_team_home_draw_rate']:.0%}/"
                f"{form_features['home_team_home_loss_rate']:.0%}."
            )
        if away_venue_records:
            form_note += (
                f" Away-away W/D/L {form_features['away_team_away_win_rate']:.0%}/"
                f"{form_features['away_team_away_draw_rate']:.0%}/"
                f"{form_features['away_team_away_loss_rate']:.0%}."
            )

        if market_key in FOOTBALL_SPREAD_MARKETS:
            selected_n = form_features.get("selected_spread_form_sample", 0)
            opponent_n = form_features.get("opponent_spread_form_sample", 0)
            selected_rate = form_features.get("selected_spread_form_rate")
            opponent_rate = form_features.get("opponent_spread_form_rate")
            selected_label = f"{selected_rate:.0%}" if isinstance(selected_rate, (int, float)) else "unavailable"
            opponent_label = f"{opponent_rate:.0%}" if isinstance(opponent_rate, (int, float)) else "unavailable"
            form_note += (
                f" At exact quoted two-way spread line {candidate.get('market_point')}, "
                f"selected cover {selected_label} ({selected_n}/5); opponent cover "
                f"{opponent_label} ({opponent_n}/5)."
            )
        elif market_key in FOOTBALL_TOTAL_MARKETS:
            match = re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market_key)
            if match:
                direction, line_tag = match.groups()
                home_over = form_features.get(f"home_form_over_{line_tag}_rate")
                away_over = form_features.get(f"away_form_over_{line_tag}_rate")
                if isinstance(home_over, (int, float)) and isinstance(away_over, (int, float)):
                    home_rate = home_over if direction == "over" else 1.0 - home_over
                    away_rate = away_over if direction == "over" else 1.0 - away_over
                    form_note += (
                        f" For quoted {direction} {line_tag.replace('_', '.')} goals, "
                        f"selected-direction rates: home {home_rate:.0%}, away {away_rate:.0%}."
                    )
                else:
                    form_note += f" Quoted {direction} {line_tag.replace('_', '.')} form rate unavailable."
        elif market_key in FOOTBALL_BTTS_MARKETS:
            home_rate = form_features.get("home_form_btts_yes_rate")
            away_rate = form_features.get("away_form_btts_yes_rate")
            if isinstance(home_rate, (int, float)) and isinstance(away_rate, (int, float)):
                if market_key == "btts_no":
                    home_rate, away_rate = 1.0 - home_rate, 1.0 - away_rate
                form_note += (
                    f" For quoted {market_key.removeprefix('btts_').upper()}, "
                    f"recent selected-outcome rates: home {home_rate:.0%}, away {away_rate:.0%}."
                )
        notes_by_index[index].append(form_note)

    for index, features in working_features.items():
        if features == dict(candidates[index].get("features") or {}):
            continue
        candidates[index]["features"] = features
        note = " ".join(notes_by_index[index]) or "Football evidence enriched."
        _append_note(candidates[index], note)
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


def _basketball_history_records(
    games: list[dict[str, Any]],
    team_id: str,
    role: str,
    target_time: datetime,
) -> list[tuple[datetime, int, int]]:
    records: list[tuple[datetime, int, int]] = []
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
            records.append((game_time, home_score, away_score))
        elif role == "away" and away_id == team_id:
            records.append((game_time, home_score, away_score))
    records.sort(key=lambda item: item[0], reverse=True)
    return records[:10]


def _rate(hits: list[bool]) -> float | None:
    return sum(1 for hit in hits if hit) / len(hits) if hits else None


def _basketball_history_metrics(
    games: list[dict[str, Any]],
    team_id: str,
    role: str,
    target_time: datetime,
) -> tuple[float | None, int, int, int]:
    """Backwards-compatible summary used by existing tests and diagnostics."""
    records = _basketball_history_records(games, team_id, role, target_time)
    if role == "home":
        wins = [home_score > away_score for _, home_score, away_score in records]
        return _rate(wins), 0, len(records), 0
    losses = [away_score < home_score for _, home_score, away_score in records]
    streak = 0
    for lost in losses:
        if not lost:
            break
        streak += 1
    return None, streak, 0, len(records)

def _basketball_enrich(
    candidates: list[dict[str, Any]],
    api_key: str,
    day: date,
    now_utc: datetime,
    warnings: list[str],
    session: Any = None,
    diagnostics: dict[str, int] | None = None,
    schedule_rows_out: list[dict[str, Any]] | None = None,
) -> tuple[int, int, int | None]:
    _reset_join_diagnostics(diagnostics, len(candidates))
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
    if schedule_rows_out is not None:
        schedule_rows_out.extend(dict(row) for row in provider_games)
    if diagnostics is not None:
        diagnostics["provider_schedule_rows"] = len(provider_games)
    matches: dict[int, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        candidate_time, _ = _parse_time(candidate.get("match_time"), assume_timezone=timezone.utc)
        if (
            not candidate_time
            or candidate_time <= now_utc
            or candidate_time.astimezone(EAT).date() != day
        ):
            if diagnostics is not None:
                diagnostics["out_of_scope"] += 1
            continue
        if diagnostics is not None:
            diagnostics["same_day_future_candidates"] += 1
        matched, reason = _best_match_with_reason(candidate, provider_games, day)
        if diagnostics is not None and reason != "matched":
            diagnostics[reason] = diagnostics.get(reason, 0) + 1
        if matched and matched.get("home_id") and matched.get("away_id"):
            matches[index] = matched
            candidates[index]["provider_fixture_id"] = matched.get("id") or None
            candidates[index]["provider_home_team_id"] = matched.get("home_id") or None
            candidates[index]["provider_away_team_id"] = matched.get("away_id") or None
            candidates[index]["provider_league_id"] = matched.get("league_id") or None
            candidates[index]["provider_season"] = matched.get("season")
    if diagnostics is not None:
        diagnostics["matched_candidates"] = len(matches)

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
        home_records = _basketball_history_records(
            history_cache.get((home_id, str(league_id), str(season))) or [], home_id, "home", target_time
        )
        away_records = _basketball_history_records(
            history_cache.get((away_id, str(league_id), str(season))) or [], away_id, "away", target_time
        )
        if len(home_records) >= 5:
            home_win_rate = _rate([home_score > away_score for _, home_score, away_score in home_records])
            features["home_win_rate"] = round(home_win_rate or 0.0, 4)
            features["home_home_games_sample"] = len(home_records)
            notes.append(
                f"API-Basketball last {len(home_records)} home games: home win rate {home_win_rate:.1%}."
            )
        if len(away_records) >= 5:
            away_losses = [away_score < home_score for _, home_score, away_score in away_records]
            away_loss_streak = 0
            for lost in away_losses:
                if not lost:
                    break
                away_loss_streak += 1
            features["away_away_losing_streak"] = away_loss_streak
            features["away_away_games_sample"] = len(away_records)
            notes.append(
                f"API-Basketball last {len(away_records)} away games: "
                f"current away losing streak {away_loss_streak}."
            )

        market_key = str(candidate.get("market_key", "")).lower()
        point_raw = candidate.get("market_point")
        try:
            market_point = float(point_raw) if point_raw is not None else None
        except (TypeError, ValueError):
            market_point = None
        if market_key in {"basketball_total_over", "basketball_total_under"} and market_point is not None:
            over = market_key == "basketball_total_over"
            home_hits = [
                ((home_score + away_score) > market_point if over else (home_score + away_score) < market_point)
                for _, home_score, away_score in home_records
                if (home_score + away_score) != market_point
            ]
            away_hits = [
                ((home_score + away_score) > market_point if over else (home_score + away_score) < market_point)
                for _, home_score, away_score in away_records
                if (home_score + away_score) != market_point
            ]
            if len(home_hits) >= 5 and len(away_hits) >= 5:
                features["home_market_total_hit_rate"] = round(_rate(home_hits) or 0.0, 4)
                features["away_market_total_hit_rate"] = round(_rate(away_hits) or 0.0, 4)
                features["home_home_games_sample"] = len(home_hits)
                features["away_away_games_sample"] = len(away_hits)
                side = "Over" if over else "Under"
                notes.append(
                    f"API-Basketball recent totals at {side} {market_point:g}: "
                    f"home-form {sum(home_hits)}/{len(home_hits)}, away-form {sum(away_hits)}/{len(away_hits)}."
                )

        if market_key in {"basketball_home_spread", "basketball_away_spread"} and market_point is not None:
            selected_side = str(candidate.get("selection_side", "")).lower()
            home_line = market_point if selected_side == "home" else -market_point
            away_line = market_point if selected_side == "away" else -market_point
            home_covers = [
                home_score + home_line > away_score
                for _, home_score, away_score in home_records
                if home_score + home_line != away_score
            ]
            away_covers = [
                away_score + away_line > home_score
                for _, home_score, away_score in away_records
                if away_score + away_line != home_score
            ]
            if len(home_covers) >= 5 and len(away_covers) >= 5:
                home_rate = _rate(home_covers) or 0.0
                away_rate = _rate(away_covers) or 0.0
                if selected_side == "home":
                    selection_rate, opponent_rate = home_rate, away_rate
                    selection_sample, opponent_sample = len(home_covers), len(away_covers)
                else:
                    selection_rate, opponent_rate = away_rate, home_rate
                    selection_sample, opponent_sample = len(away_covers), len(home_covers)
                features["selection_cover_rate"] = round(selection_rate, 4)
                features["opponent_cover_rate"] = round(opponent_rate, 4)
                features["selection_cover_sample"] = selection_sample
                features["opponent_cover_sample"] = opponent_sample
                notes.append(
                    f"API-Basketball recent handicap evidence at {market_point:+g}: "
                    f"selected-side cover {selection_rate:.1%} ({selection_sample}); "
                    f"opponent cover {opponent_rate:.1%} ({opponent_sample})."
                )
        if features != dict(candidate.get("features") or {}):
            candidate["features"] = features
            if notes:
                _append_note(candidate, " ".join(notes))
            enriched_count += 1
    return client.calls_used, enriched_count, client.remaining_estimate


def _result_outcome(row: dict[str, Any], sport: str) -> str | None:
    """Resolve only explicitly supported markets from a completed score."""
    market = str(row.get("market_key", "")).strip().lower()
    if sport == "football":
        goals = _goals(row)
        if goals is None:
            return None
        home_goals, away_goals = goals
        total = home_goals + away_goals
        if market == "home_win_1x2":
            return "win" if home_goals > away_goals else "loss"
        if market == "draw_1x2":
            return "win" if home_goals == away_goals else "loss"
        if market == "away_win_1x2":
            return "win" if away_goals > home_goals else "loss"
        if market == "double_chance_1x":
            return "win" if home_goals >= away_goals else "loss"
        if market in FOOTBALL_SPREAD_MARKETS:
            try:
                point = Decimal(str(row.get("market_point")))
            except (InvalidOperation, TypeError, ValueError):
                return None
            side = str(row.get("selection_side", "")).strip().lower()
            expected_side = "home" if market == "football_home_spread" else "away"
            if (
                side != expected_side
                or not point.is_finite()
                or abs(point) > Decimal("5")
                or point * 2 != (point * 2).to_integral_value()
            ):
                return None
            if side == "home":
                adjusted = Decimal(home_goals) + point
                opponent = Decimal(away_goals)
            else:
                adjusted = Decimal(away_goals) + point
                opponent = Decimal(home_goals)
            if adjusted == opponent:
                return "void"
            return "win" if adjusted > opponent else "loss"
        if market in {"btts_yes", "btts_no"}:
            both_scored = home_goals > 0 and away_goals > 0
            won = both_scored if market == "btts_yes" else not both_scored
            return "win" if won else "loss"
        match = re.fullmatch(r"(over|under)_(0_5|1_5|2_5)_goals", market)
        if match:
            try:
                point = Decimal(str(row.get("market_point")))
            except (InvalidOperation, TypeError, ValueError):
                point = Decimal(match.group(2).replace("_", "."))
            if Decimal(total) == point:
                return "void"
            won = Decimal(total) > point if match.group(1) == "over" else Decimal(total) < point
            return "win" if won else "loss"
        return None

    if sport == "basketball":
        home_score = _basketball_score(row, "home")
        away_score = _basketball_score(row, "away")
        if home_score is None or away_score is None:
            return None
        if market == "home_moneyline":
            return "win" if home_score > away_score else "loss"
        if market in {"basketball_total_over", "basketball_total_under"}:
            try:
                point = Decimal(str(row.get("market_point")))
            except (InvalidOperation, TypeError, ValueError):
                return None
            total = Decimal(home_score + away_score)
            if total == point:
                return "void"
            won = total > point if market == "basketball_total_over" else total < point
            return "win" if won else "loss"
        if market in {"basketball_home_spread", "basketball_away_spread"}:
            try:
                point = Decimal(str(row.get("market_point")))
            except (InvalidOperation, TypeError, ValueError):
                return None
            side = str(row.get("selection_side", "")).strip().lower()
            if side == "home" or market == "basketball_home_spread":
                adjusted = Decimal(home_score) + point
                opponent = Decimal(away_score)
            elif side == "away" or market == "basketball_away_spread":
                adjusted = Decimal(away_score) + point
                opponent = Decimal(home_score)
            else:
                return None
            if adjusted == opponent:
                return "void"
            return "win" if adjusted > opponent else "loss"
    return None


def _candidate_for_result_match(row: dict[str, Any]) -> dict[str, Any]:
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    if not home or not away:
        parts = str(row.get("match_name", "")).split(" vs ", 1)
        if len(parts) == 2:
            home, away = parts[0].strip(), parts[1].strip()
    return {
        "home_team": home,
        "away_team": away,
        "match_time": row.get("match_time"),
    }


def settle_pending_fixtures(
    fixtures: list[dict[str, Any]],
    *,
    api_sports_key: str = "",
    football_key: str = "",
    basketball_key: str = "",
    now: datetime | None = None,
    sessions: dict[str, Any] | None = None,
    max_days_back: int = 7,
) -> APISportsSettlement:
    """Settle supported prior picks only when an API-Sports final score matches.

    This uses at most one schedule request per sport/date (capped at seven
    dates per sport) and never treats missing or ambiguous data as a loss.
    """
    result = APISportsSettlement()
    now_utc = _as_utc(now)
    sessions = sessions or {}
    shared_key = str(api_sports_key or "").strip()
    keys = {
        "football": str(football_key or shared_key).strip(),
        "basketball": str(basketball_key or shared_key).strip(),
    }
    cutoff = now_utc.timestamp() - max(1, int(max_days_back)) * 86400
    grouped: dict[tuple[str, date], list[dict[str, Any]]] = {}
    for row in fixtures:
        if not isinstance(row, dict) or str(row.get("status", "pending")).lower() != "pending":
            continue
        sport = str(row.get("sport_type", "")).strip().lower()
        if sport not in keys or not keys[sport]:
            continue
        match_time, _ = _parse_time(row.get("match_time"), assume_timezone=timezone.utc)
        if not match_time or match_time >= now_utc or match_time.timestamp() < cutoff:
            continue
        day = match_time.astimezone(EAT).date()
        grouped.setdefault((sport, day), []).append(row)

    result.football_candidates = sum(len(rows) for (sport, _), rows in grouped.items() if sport == "football")
    result.basketball_candidates = sum(len(rows) for (sport, _), rows in grouped.items() if sport == "basketball")
    clients: dict[str, APISportsClient] = {}
    for (sport, day), candidates in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        if sport not in clients:
            client = APISportsClient(
                sport, keys[sport], max_run_calls=20, session=sessions.get(sport)
            )
            try:
                client.inspect_quota()
            except APISportsError as exc:
                if len(result.warnings) < 12:
                    result.warnings.append(str(exc))
                continue
            clients[sport] = client
        client = clients.get(sport)
        if client is None or client.calls_used >= client.call_budget:
            continue
        endpoint = "fixtures" if sport == "football" else "games"
        payload = _safe_get(
            client,
            endpoint,
            {"date": day.isoformat(), "timezone": "Africa/Dar_es_Salaam"},
            result.warnings,
        )
        if sport == "football":
            result.football_calls = client.calls_used
        else:
            result.basketball_calls = client.calls_used
        if not payload:
            continue
        provider_rows = _response_rows(payload)
        for candidate in candidates:
            join_candidate = _candidate_for_result_match(candidate)
            matched, _reason = _best_match_with_reason(
                join_candidate, provider_rows, day, tolerance_hours=8
            )
            if not matched or not _final_status(matched.get("status"), sport):
                continue
            # _game_parts keeps the provider row under raw; pass the stored
            # selection/line into the market resolver.
            resolution_row = dict(matched.get("raw", {}))
            resolution_row.update({
                "market_key": candidate.get("market_key"),
                "market_point": candidate.get("market_point"),
                "selection_side": candidate.get("selection_side"),
            })
            outcome = _result_outcome(resolution_row, sport)
            if outcome is None:
                continue
            result.updates.append({
                "id": candidate.get("id"),
                "status": outcome,
                "updated_at": now_utc.isoformat().replace("+00:00", "Z"),
            })
            if sport == "football":
                result.football_settled += 1
            else:
                result.basketball_settled += 1
    return result


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
    # Discover the provider's full same-day schedule even when the Odds API
    # returned no candidates. Odds are enrichment inputs, not the fixture universe.
    if f_key:
        result.football_calls, result.football_enriched, result.football_remaining = _football_enrich(
            football_candidates, f_key, day, now_utc, result.warnings, sessions.get("football"),
            result.football_join_diagnostics, result.football_schedule,
        )
    if b_key:
        result.basketball_calls, result.basketball_enriched, result.basketball_remaining = _basketball_enrich(
            basketball_candidates, b_key, day, now_utc, result.warnings, sessions.get("basketball"),
            result.basketball_join_diagnostics, result.basketball_schedule,
        )
    return result
