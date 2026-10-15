"""Build an auditable full-fixture board from provider schedule rows.

The schedule is the fixture universe; Odds API rows only add market quotes. This
module intentionally keeps missing quotes/statistics visible instead of
silently dropping a fixture or turning absence into a prediction.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from engine import football_evidence_assessment, prepare_fixture

FOREBET_FIXTURES_URL = "https://www.forebet.com/en/football-tips-and-predictions-for-today"
FOREBET_INJURIES_URL = "https://www.forebet.com/en/injured-players"
STATAREA_COMPARE_URL = "https://www.statarea.com/compare"


def _utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _event_key(row: dict[str, Any]) -> tuple[str, str]:
    sport = str(row.get("sport_type", "")).strip().lower()
    fixture_id = str(row.get("provider_fixture_id") or "").strip()
    return sport, fixture_id


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _option(raw: dict[str, Any], now_utc: datetime) -> dict[str, Any]:
    validated = prepare_fixture(raw)
    sport = str(raw.get("sport_type") or "").strip().lower()
    assessment = football_evidence_assessment(raw) if sport == "football" else {
        "qualified": False,
        "route": None,
        "alternatives": [],
        "reason": "This market uses its sport-specific evidence gate; no football route details apply.",
    }
    odd_value = raw.get("picked_odds")
    try:
        odd = float(odd_value)
    except (TypeError, ValueError, OverflowError):
        odd = None
    updated_at = raw.get("odds_updated_at")
    quote_time = _utc(updated_at)
    stale_quote = bool(quote_time and (now_utc - quote_time).total_seconds() > 6 * 60 * 60)
    evidence_reason = str(assessment.get("reason") or "")
    if assessment.get("qualified") and not validated:
        evidence_reason += " Evidence passed, but full fixture validation failed (check quote band, status, and required fields)."
    return {
        "market_key": str(raw.get("market_key") or ""),
        "market_name": str(raw.get("market_name") or "Unknown market"),
        "selection_name": str(raw.get("selection_name") or ""),
        "selection_side": str(raw.get("selection_side") or "") or None,
        "market_point": raw.get("market_point"),
        "picked_odds": odd,
        "bookmaker_name": str(raw.get("bookmaker_name") or "") or None,
        "odds_updated_at": updated_at,
        "quote_stale_over_6h": stale_quote,
        "evidence_status": "passes_current_gate" if validated else "not_qualified",
        "evidence_route": assessment.get("route"),
        "evidence_alternatives": assessment.get("alternatives", []),
        "evidence_reason": evidence_reason[:1200],
        "evidence_snapshot": dict(raw.get("features")) if isinstance(raw.get("features"), dict) else {},
        "analysis_score": validated.get("confidence_score") if validated else None,
        "score_interpretation": "heuristic evidence rank, not a calibrated win probability",
        "analysis_note": str(raw.get("analysis_note") or "").strip()[:2400],
    }


def build_fixture_board(
    schedule_rows: list[dict[str, Any]],
    odds_candidates: list[dict[str, Any]],
    *,
    analysis_day: date,
    requested_at: datetime,
    now: datetime,
    ticket_picks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return one board row for every normalized provider schedule fixture.

    Only quotes explicitly joined to the provider fixture ID are attached. The
    API-Sports name/time join remains the single authority; this layer never
    invents a match identity from similar names.
    """
    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    request_utc = requested_at.astimezone(timezone.utc) if requested_at.tzinfo else requested_at.replace(tzinfo=timezone.utc)
    candidates_by_fixture: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in odds_candidates:
        if not isinstance(raw, dict):
            continue
        key = (str(raw.get("sport_type", "")).strip().lower(), str(raw.get("provider_fixture_id") or "").strip())
        if not key[1]:
            continue
        candidates_by_fixture.setdefault(key, []).append(raw)

    ticket_keys = {
        (str(row.get("sport_type", "")).strip().lower(), str(row.get("provider_fixture_id") or "").strip(),
         str(row.get("market_key", "")).strip().lower(), str(row.get("selection_name", "")).strip().lower())
        for row in (ticket_picks or [])
    }
    board: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for fixture in schedule_rows:
        if not isinstance(fixture, dict):
            continue
        key = _event_key(fixture)
        if not key[1] or key in seen:
            continue
        seen.add(key)
        raw_options = candidates_by_fixture.get(key, [])
        kickoff = _utc(fixture.get("match_time"))
        kickoff_known = bool(fixture.get("kickoff_time_known", True))
        kickoff_source = str(fixture.get("kickoff_time_source") or ("api-sports" if kickoff_known else "api-sports-date-only"))
        if not kickoff_known:
            quoted_times = {
                quote_time
                for raw in raw_options
                if (quote_time := _utc(raw.get("match_time"))) is not None
                and quote_time.astimezone(ZoneInfo("Africa/Dar_es_Salaam")).date() == analysis_day
            }
            if len(quoted_times) == 1:
                kickoff = next(iter(quoted_times))
                kickoff_known = True
                kickoff_source = "the-odds-api-event"
        if kickoff is None:
            continue
        if kickoff.astimezone(ZoneInfo("Africa/Dar_es_Salaam")).date() != analysis_day:
            continue
        state = str(fixture.get("fixture_state") or "scheduled").lower()
        upcoming = kickoff_known and state == "scheduled" and kickoff > now_utc
        options = [_option(row, now_utc) for row in raw_options]
        options_with_raw = list(zip(options, raw_options))
        eligible = [
            pair for pair in options_with_raw
            if pair[0]["evidence_status"] == "passes_current_gate" and upcoming
        ]
        eligible.sort(key=lambda pair: (
            -float(pair[0].get("analysis_score") or 0),
            float(pair[0].get("picked_odds") or 99),
            str(pair[0].get("market_key") or ""),
        ))
        options_with_raw.sort(key=lambda pair: (
            pair[0]["evidence_status"] != "passes_current_gate",
            -(float(pair[0].get("analysis_score") or 0)),
            float(pair[0].get("picked_odds") or 99),
            str(pair[0].get("market_name") or ""),
        ))
        options = [pair[0] for pair in options_with_raw]
        best_option = eligible[0][0] if eligible else None
        best_raw = eligible[0][1] if eligible else None
        if not kickoff_known:
            analysis_status = "kickoff_time_unknown"
            note = "API-Sports supplied a date but no kickoff time, and no single matched Odds API event time was available. The fixture remains visible but is not pickable."
        elif state != "scheduled" or kickoff <= now_utc:
            analysis_status = "not_upcoming"
            note = "Fixture is listed in today's schedule, but it is live, started, finished, postponed, cancelled, or no longer future at run time. It cannot enter today's accumulator."
        elif best_option:
            analysis_status = "evidence_qualified_market_available"
            note = str(best_raw.get("analysis_note") or "An available quote passed the current market-specific evidence gate.")[:2400]
        elif options:
            analysis_status = "odds_available_evidence_not_qualified"
            note = "One or more quotes were returned, but none passed the current market-specific evidence/validation gate. No pick was forced."
        else:
            analysis_status = "fixture_only_no_matched_quote"
            note = "Fixture is present in the API-Sports schedule. No matching quote was returned among the competitions/markets queried by The Odds API; this does not mean the match does not exist."
        market_options = []
        for option, raw in zip(options, [pair[1] for pair in options_with_raw]):
            option = dict(option)
            option_key = (
                str(raw.get("sport_type", "")).strip().lower(),
                str(raw.get("provider_fixture_id") or "").strip(),
                str(raw.get("market_key", "")).strip().lower(),
                str(raw.get("selection_name", "")).strip().lower(),
            )
            option["selected_for_ticket"] = option_key in ticket_keys
            option["recommended_market"] = bool(best_raw is raw)
            market_options.append(option)
        features = {}
        if best_raw and isinstance(best_raw.get("features"), dict):
            features = best_raw["features"]
        elif raw_options:
            richest = max(raw_options, key=lambda row: len(row.get("features") or {}) if isinstance(row.get("features"), dict) else 0)
            if isinstance(richest.get("features"), dict):
                features = richest["features"]
        h2h_sample = max(
            _count(features.get("historical_total_goals_sample")),
            _count(features.get("historical_1x2_sample")),
            _count(features.get("historical_btts_sample")),
            _count(features.get("historical_spread_sample")),
        )
        home_form = _count(features.get("home_form_matches_sample"))
        away_form = _count(features.get("away_form_matches_sample"))
        home_venue_form = _count(features.get("home_team_home_games_sample"))
        away_venue_form = _count(features.get("away_team_away_games_sample"))
        selected_for_ticket = any(
            str(row.get("sport_type", "")).strip().lower() == key[0]
            and str(row.get("provider_fixture_id") or "").strip() == key[1]
            for row in (ticket_picks or [])
        )
        row = dict(fixture)
        row.update({
            "match_time": kickoff.isoformat().replace("+00:00", "Z"),
            "kickoff_time_known": kickoff_known,
            "kickoff_time_source": kickoff_source,
            "requested_at": request_utc.isoformat().replace("+00:00", "Z"),
            "analysis_status": analysis_status,
            "market_options": market_options,
            "recommended_market": best_option,
            "recommended_score": best_option.get("analysis_score") if best_option else None,
            "selected_for_ticket": selected_for_ticket,
            "analysis_note": note,
            "statistics_summary": {
                "h2h_sample": h2h_sample,
                "home_form_sample": home_form,
                "away_form_sample": away_form,
                "home_venue_form_sample": home_venue_form,
                "away_venue_form_sample": away_venue_form,
                "h2h_latest_game_at": features.get("historical_h2h_latest_game_at"),
                "home_form_latest_game_at": features.get("home_form_latest_game_at"),
                "away_form_latest_game_at": features.get("away_form_latest_game_at"),
                "home_venue_form_latest_game_at": features.get("home_team_home_latest_game_at"),
                "away_venue_form_latest_game_at": features.get("away_team_away_latest_game_at"),
                "league_position_available": features.get("home_table_position") is not None,
                "injury_data_available": False,
            },
            "forebet_url": FOREBET_FIXTURES_URL if key[0] == "football" else None,
            "forebet_injuries_url": FOREBET_INJURIES_URL if key[0] == "football" else None,
            "statarea_url": STATAREA_COMPARE_URL if key[0] == "football" else None,
            "source": "api-sports-schedule",
        })
        board.append(row)
    return sorted(board, key=lambda row: (row.get("match_time", ""), row.get("competition", ""), row.get("match_name", "")))
