"""Fetch licensed odds/stats, settle prior outcomes, and persist one daily ticket."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from engine import TARGET_MAX, TARGET_MIN, build_accumulator, prepare_fixture
from providers.api_sports import enrich_odds_candidates, settle_pending_fixtures
from providers.opinions_rss import enrich_with_rss_opinions
from providers.odds_api import OddsAPIError, fetch_odds_api_feed

EAT = ZoneInfo("Africa/Dar_es_Salaam")
TIMEOUT = 45


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def supabase_headers(service_key: str, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def request_ok(response: requests.Response, label: str) -> requests.Response:
    if not response.ok:
        # Supabase error bodies may contain schema details but never API secrets.
        body = response.text[:800]
        fail(f"{label} failed ({response.status_code}): {body}")
    return response


def supabase_get(base: str, table: str, params: list[tuple[str, str]], headers: dict[str, str], label: str) -> list[dict]:
    response = requests.get(
        f"{base}/{table}", params=params, headers=headers, timeout=TIMEOUT
    )
    request_ok(response, label)
    payload = response.json()
    if not isinstance(payload, list):
        fail(f"{label} returned an unexpected payload.")
    return [row for row in payload if isinstance(row, dict)]


def claim_manual_analysis_window(base: str, headers: dict[str, str]) -> bool:
    """Atomically enforce one server-side analysis start per Tanzania calendar day."""
    response = requests.post(
        f"{base}/rpc/kimathy_claim_manual_run",
        headers=headers,
        json={},
        timeout=TIMEOUT,
    )
    request_ok(response, "Manual analysis daily-limit check")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("allowed"), bool):
        fail("Manual analysis daily limit returned an unexpected response; no sports API requests were made.")
    if not payload["allowed"]:
        next_allowed = payload.get("next_allowed_at") or "after the next EAT midnight"
        print(
            "Manual analysis blocked: one request per Tanzania calendar day (EAT); no Odds API/API-Sports "
            f"requests were made. Try again after {next_allowed}."
        )
        return False
    next_allowed = payload.get("next_allowed_at") or "after the next EAT midnight"
    print(f"Manual analysis window claimed; next request is allowed after {next_allowed}.")
    return True


def fetch_provider_feed(feed_url: str, token: str | None) -> list[dict]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(feed_url, headers=headers, timeout=TIMEOUT)
    request_ok(response, "Sports feed request")
    payload = response.json()
    fixtures = payload.get("fixtures", []) if isinstance(payload, dict) else payload
    if not isinstance(fixtures, list):
        fail("Sports feed must be a JSON object with a fixtures array, or a JSON array.")
    return [row for row in fixtures if isinstance(row, dict)]


def fixture_time(row: dict) -> datetime | None:
    value = row.get("match_time")
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _identity(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("sport_type", "")).lower(),
        str(row.get("match_name", "")).strip(),
        str(row.get("market_name", "")).strip(),
    )


def _ids_filter(values: list[str]) -> str:
    safe = [str(value).strip() for value in values if str(value).strip()]
    return "in.(" + ",".join(safe) + ")"


def persist_settlement_updates(
    base: str, headers: dict[str, str], updates: list[dict[str, str]]
) -> int:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in updates:
        if row.get("id") and row.get("status") in {"win", "loss", "void"}:
            grouped[str(row["status"])].append(str(row["id"]))
    changed = 0
    for status, ids in grouped.items():
        for offset in range(0, len(ids), 100):
            batch = ids[offset:offset + 100]
            response = requests.patch(
                f"{base}/daily_fixtures",
                params={"id": _ids_filter(batch)},
                headers=supabase_headers(headers["apikey"], "return=minimal"),
                json={"status": status, "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
                timeout=TIMEOUT,
            )
            request_ok(response, f"Fixture settlement ({status})")
            changed += len(batch)
    return changed


def reconcile_accumulator_results(
    base: str, headers: dict[str, str], today: datetime, lookback_days: int = 90
) -> int:
    """Summarize verified leg outcomes and one-unit paper return per ticket."""
    since = (today.astimezone(EAT).date() - timedelta(days=lookback_days)).isoformat()
    accumulators = supabase_get(
        base,
        "daily_accumulators",
        [
            ("select", "id,analysis_date,status,settlement_status"),
            ("analysis_date", f"gte.{since}"),
            ("analysis_date", f"lte.{today.astimezone(EAT).date().isoformat()}"),
            ("status", "eq.ready"),
            ("order", "analysis_date.desc"),
        ],
        headers,
        "Accumulator history query",
    )
    if not accumulators:
        return 0
    accumulator_ids = [str(row["id"]) for row in accumulators if row.get("id")]
    legs = supabase_get(
        base,
        "daily_accumulator_legs",
        [
            ("select", "accumulator_id,fixture_id,odds_at_build"),
            ("accumulator_id", _ids_filter(accumulator_ids)),
        ],
        headers,
        "Accumulator legs query",
    )
    fixture_ids = list(dict.fromkeys(str(row["fixture_id"]) for row in legs if row.get("fixture_id")))
    if not fixture_ids:
        return 0
    fixtures = supabase_get(
        base,
        "daily_fixtures",
        [("select", "id,status"), ("id", _ids_filter(fixture_ids))],
        headers,
        "Settled fixture statuses query",
    )
    status_by_id = {str(row.get("id")): str(row.get("status", "pending")).lower() for row in fixtures}
    legs_by_accumulator: dict[str, list[dict]] = defaultdict(list)
    for leg in legs:
        legs_by_accumulator[str(leg.get("accumulator_id", ""))].append(leg)

    changed = 0
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for accumulator in accumulators:
        accumulator_id = str(accumulator.get("id", ""))
        ticket_legs = legs_by_accumulator.get(accumulator_id, [])
        if not ticket_legs:
            continue
        statuses = [status_by_id.get(str(leg.get("fixture_id", "")), "pending") for leg in ticket_legs]
        if "loss" in statuses:
            settlement_status = "lost"
            settled_odds = Decimal("0")
            net_units = Decimal("-1")
        elif all(status in {"win", "void"} for status in statuses):
            won_legs = [leg for leg, status in zip(ticket_legs, statuses) if status == "win"]
            if not won_legs:
                settlement_status = "void"
                settled_odds = Decimal("1")
                net_units = Decimal("0")
            else:
                settlement_status = "won"
                settled_odds = Decimal("1")
                for leg in won_legs:
                    settled_odds *= Decimal(str(leg.get("odds_at_build", "1")))
                net_units = settled_odds - Decimal("1")
        else:
            settlement_status = "pending"
            settled_odds = None
            net_units = None

        values = {
            "settlement_status": settlement_status,
            "settled_at": now_iso if settlement_status != "pending" else None,
            "settled_total_odds": float(settled_odds) if settled_odds is not None else None,
            "net_units": float(net_units) if net_units is not None else None,
            "updated_at": now_iso,
        }
        if accumulator.get("settlement_status") == settlement_status:
            continue
        response = requests.patch(
            f"{base}/daily_accumulators",
            params={"id": f"eq.{quote(accumulator_id, safe='-') }"},
            headers=supabase_headers(headers["apikey"], "return=minimal"),
            json=values,
            timeout=TIMEOUT,
        )
        request_ok(response, "Accumulator settlement update")
        changed += 1
    return changed


def _join_text(diagnostics: dict[str, int], label: str) -> str:
    return (
        f"{label}_candidates={diagnostics.get('candidate_count', 0)}; "
        f"{label}_same_day_future={diagnostics.get('same_day_future_candidates', 0)}; "
        f"{label}_schedule_rows={diagnostics.get('provider_schedule_rows', 0)}; "
        f"{label}_matched={diagnostics.get('matched_candidates', 0)}; "
        f"{label}_team_misses={diagnostics.get('team_names_not_matched', 0)}; "
        f"{label}_time_misses={diagnostics.get('kickoff_time_mismatch', 0)}; "
        f"{label}_ambiguous={diagnostics.get('ambiguous_fixture_match', 0)}; "
        f"{label}_out_of_scope={diagnostics.get('out_of_scope', 0)}"
    )


def _existing_ready_accumulator(base: str, headers: dict[str, str], analysis_date: str) -> dict | None:
    rows = supabase_get(
        base,
        "daily_accumulators",
        [("select", "id,status,total_odds,settlement_status"), ("analysis_date", f"eq.{analysis_date}")],
        headers,
        "Existing daily accumulator query",
    )
    if rows and rows[0].get("status") == "ready":
        return rows[0]
    return None


def main() -> int:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    odds_api_key = os.getenv("THE_ODDS_API_KEY", "").strip()
    odds_region = os.getenv("ODDS_API_REGION", "eu").strip().lower()
    odds_sport_keys = os.getenv("ODDS_API_SPORT_KEYS", "").strip()
    feed_url = os.getenv("SPORTS_FEED_URL", "").strip()
    feed_token = os.getenv("SPORTS_FEED_TOKEN", "")
    api_sports_key = os.getenv("API_SPORTS_KEY", "").strip()
    api_football_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    api_basketball_key = os.getenv("API_BASKETBALL_KEY", "").strip()
    try:
        odds_max_age = int(os.getenv("ODDS_API_MAX_AGE_MINUTES", "360"))
    except ValueError:
        fail("ODDS_API_MAX_AGE_MINUTES must be a whole number of minutes.")
    if not 1 <= odds_max_age <= 1440:
        fail("ODDS_API_MAX_AGE_MINUTES must be between 1 and 1440.")
    if not supabase_url or not service_key:
        fail("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the runner environment.")
    if not odds_api_key and not feed_url:
        fail("Set THE_ODDS_API_KEY, or provide SPORTS_FEED_URL as a normalized-feed fallback.")

    now_eat = datetime.now(EAT)
    analysis_date = now_eat.date()
    start_eat = datetime.combine(analysis_date, time.min, tzinfo=EAT)
    end_eat = datetime.combine(analysis_date + timedelta(days=1), time.min, tzinfo=EAT)
    start_utc = start_eat.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end_utc = end_eat.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    now_utc = datetime.now(timezone.utc)
    base = f"{supabase_url}/rest/v1"
    headers = supabase_headers(service_key)

    # Claim first so even result-enrichment calls are covered by the per-calendar-day limit.
    if not claim_manual_analysis_window(base, headers):
        return 0

    # Settle older published legs before constructing today's snapshot.
    cutoff_eat = datetime.combine(analysis_date - timedelta(days=7), time.min, tzinfo=EAT)
    cutoff_utc = cutoff_eat.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    pending = supabase_get(
        base,
        "daily_fixtures",
        [
            ("select", "id,sport_type,match_name,home_team,away_team,match_time,market_key,market_point,selection_side,status"),
            ("status", "eq.pending"),
            ("match_time", f"gte.{cutoff_utc}"),
            ("match_time", f"lt.{now_utc.isoformat().replace('+00:00', 'Z')}"),
        ],
        headers,
        "Pending result lookup",
    )
    if pending and (api_sports_key or api_football_key or api_basketball_key):
        settlement = settle_pending_fixtures(
            pending,
            api_sports_key=api_sports_key,
            football_key=api_football_key,
            basketball_key=api_basketball_key,
            now=now_utc,
        )
        changed = persist_settlement_updates(base, headers, settlement.updates)
        print(
            "API-Sports result settlement: "
            f"pending_candidates={len(pending)}; football_settled={settlement.football_settled}; "
            f"basketball_settled={settlement.basketball_settled}; database_updates={changed}; "
            f"football_calls={settlement.football_calls}; basketball_calls={settlement.basketball_calls}."
        )
        for warning in settlement.warnings[:8]:
            print(f"API-Sports settlement note: {warning}")
    elif pending:
        print(f"Result settlement skipped: {len(pending)} past fixture(s) pending; API-Sports key is not configured.")
    history_changes = reconcile_accumulator_results(base, headers, now_eat, lookback_days=90)
    print(f"Accumulator history: settlement records refreshed={history_changes}.")

    # A ready ticket is an immutable daily snapshot: a manual rerun must not
    # replace the odds/results record after the user may already have acted on it.
    existing = _existing_ready_accumulator(base, headers, analysis_date.isoformat())
    if existing:
        print(
            f"Today's accumulator is already published and frozen: "
            f"status={existing.get('settlement_status', 'pending')}; odds={existing.get('total_odds')}. "
            "No replacement ticket was built."
        )
        return 0

    odds_feed = None
    if odds_api_key:
        try:
            odds_feed = fetch_odds_api_feed(
                api_key=odds_api_key,
                region=odds_region,
                explicit_sport_keys=odds_sport_keys or None,
                max_age_minutes=odds_max_age,
                now=now_utc,
            )
        except OddsAPIError as exc:
            fail(str(exc))
        incoming = odds_feed.fixtures
        used = odds_feed.requests_used if odds_feed.requests_used is not None else "unknown"
        remaining = odds_feed.requests_remaining if odds_feed.requests_remaining is not None else "unknown"
        print(
            f"The Odds API: selected_sports={len(odds_feed.sport_keys)}; "
            f"events={odds_feed.event_count}; supported_odds_candidates={len(incoming)}; "
            f"credits_used={used}; credits_remaining={remaining}."
        )
        for warning in odds_feed.warnings[:8]:
            print(f"The Odds API note: {warning}")
    else:
        incoming = fetch_provider_feed(feed_url, feed_token)

    sports_counts = Counter(str(row.get("sport_type", "unknown")).lower() for row in incoming)
    print(
        "Provider candidates by sport: "
        f"football={sports_counts.get('football', 0)}; "
        f"basketball={sports_counts.get('basketball', 0)}; "
        f"tennis={sports_counts.get('tennis', 0)}."
    )

    football_odds_candidates = sum(1 for row in incoming if str(row.get("sport_type", "")).lower() == "football")
    basketball_odds_candidates = sum(1 for row in incoming if str(row.get("sport_type", "")).lower() == "basketball")
    football_key_configured = bool(api_sports_key or api_football_key)
    basketball_key_configured = bool(api_sports_key or api_basketball_key)
    print(
        "API-Sports enrichment inputs: "
        f"football_odds_candidates={football_odds_candidates}; "
        f"football_key_configured={'yes' if football_key_configured else 'no'}; "
        f"basketball_odds_candidates={basketball_odds_candidates}; "
        f"basketball_key_configured={'yes' if basketball_key_configured else 'no'}."
    )
    if api_sports_key or api_football_key or api_basketball_key:
        enrichment = enrich_odds_candidates(
            incoming,
            api_sports_key=api_sports_key,
            football_key=api_football_key,
            basketball_key=api_basketball_key,
            analysis_day=analysis_date,
            now=now_utc,
        )
        incoming = enrichment.fixtures
        print(
            "API-Sports enrichment: "
            f"football_calls={enrichment.football_calls}; "
            f"football_candidates_enriched={enrichment.football_enriched}; "
            f"football_quota_remaining_estimate={enrichment.football_remaining}; "
            f"basketball_calls={enrichment.basketball_calls}; "
            f"basketball_candidates_enriched={enrichment.basketball_enriched}; "
            f"basketball_quota_remaining_estimate={enrichment.basketball_remaining}."
        )
        if enrichment.football_join_diagnostics:
            print("API-Sports fixture join: " + _join_text(enrichment.football_join_diagnostics, "football") + ".")
        if enrichment.basketball_join_diagnostics:
            print("API-Sports fixture join: " + _join_text(enrichment.basketball_join_diagnostics, "basketball") + ".")
        for warning in enrichment.warnings[:8]:
            print(f"API-Sports note: {warning}")
    else:
        print("API-Sports enrichment skipped: no product key is configured; no statistics evidence was inferred.")

    # RSS contributes only attributed context. It never changes evidence gates,
    # odds, eligibility, or the ranking score. Article pages are not fetched.
    opinion_enrichment = enrich_with_rss_opinions(incoming, now=now_utc)
    incoming = opinion_enrichment.fixtures
    print(
        "RSS news/opinion context: "
        f"feeds_checked={opinion_enrichment.feeds_checked}; "
        f"recent_items_read={opinion_enrichment.feed_items_read}; "
        f"fixtures_with_matches={opinion_enrichment.matched_fixtures}; "
        f"matched_articles={opinion_enrichment.matched_articles}. "
        "This context does not affect pick eligibility or ranking."
    )
    for warning in opinion_enrichment.warnings[:8]:
        print(f"RSS source note: {warning}")

    eligible_candidates: list[dict] = []
    prepared: list[dict] = []
    candidates_by_sport: Counter[str] = Counter()
    evidence_rejections_by_sport: Counter[str] = Counter()
    time_rejections_by_sport: Counter[str] = Counter()
    eligible_by_sport: Counter[str] = Counter()
    for raw in incoming:
        sport = str(raw.get("sport_type", "unknown")).strip().lower() or "unknown"
        candidates_by_sport[sport] += 1
        row = prepare_fixture(raw)
        if row is None:
            evidence_rejections_by_sport[sport] += 1
            continue
        event_time = fixture_time(row)
        if not event_time or event_time.astimezone(EAT).date() != analysis_date or event_time < now_utc:
            time_rejections_by_sport[sport] += 1
            continue
        eligible_candidates.append(raw)
        row["updated_at"] = now_utc.isoformat().replace("+00:00", "Z")
        prepared.append(row)
        eligible_by_sport[sport] += 1

    print(
        f"Pipeline filter: provider_candidates={len(incoming)}; "
        f"with_market_specific_evidence={len(eligible_candidates)}; "
        f"eligible_for_today={len(prepared)}."
    )
    for sport in sorted(candidates_by_sport):
        print(
            f"Eligibility counts {sport}: candidates={candidates_by_sport[sport]}; "
            f"market_evidence_or_validation_rejected={evidence_rejections_by_sport[sport]}; "
            f"date_or_time_rejected={time_rejections_by_sport[sport]}; "
            f"eligible_today={eligible_by_sport[sport]}."
        )
    if odds_feed is not None and not eligible_candidates:
        print(
            "No picks will be inferred from odds alone. No candidate currently has "
            "a matched, market-specific statistics threshold."
        )

    # Persist only candidates that passed the same evidence rules used by the
    # optimizer. The private dashboard never receives unsupported odds-only rows.
    persisted_rows: list[dict] = []
    if prepared:
        upsert_response = requests.post(
            f"{base}/daily_fixtures",
            params={"on_conflict": "sport_type,match_name,match_time,market_name"},
            headers=supabase_headers(service_key, "resolution=merge-duplicates,return=representation"),
            json=prepared,
            timeout=TIMEOUT,
        )
        request_ok(upsert_response, "Fixture upsert")
        payload = upsert_response.json()
        persisted_rows = payload if isinstance(payload, list) else []

    # Use only this run's eligible candidates; stale/legacy/demo rows can never
    # enter a published ticket. The database rows provide IDs for accumulator legs.
    valid_identities = {_identity(raw) for raw in eligible_candidates}
    persisted_rows = [
        row for row in persisted_rows
        if _identity(row) in valid_identities
        and (row_time := fixture_time(row)) is not None
        and row_time.astimezone(EAT).date() == analysis_date
        and row_time >= now_utc
        and str(row.get("status", "pending")).lower() == "pending"
    ]
    result = build_accumulator(eligible_candidates)
    valid = bool(result["in_range"])
    total = Decimal(str(result["total_odds"]))
    payload = {
        "analysis_date": analysis_date.isoformat(),
        # Create/update as no_ticket first. A crash before the legs are inserted
        # must never leave a half-published accumulator marked ready.
        "status": "no_ticket",
        "total_odds": 1.0000,
        "target_min": float(TARGET_MIN),
        "target_max": float(TARGET_MAX),
        "settlement_status": "not_applicable",
        "settled_at": None,
        "settled_total_odds": None,
        "net_units": None,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    accumulator_response = requests.post(
        f"{base}/daily_accumulators",
        params={"on_conflict": "analysis_date"},
        headers=supabase_headers(service_key, "resolution=merge-duplicates,return=representation"),
        json=payload,
        timeout=TIMEOUT,
    )
    request_ok(accumulator_response, "Daily accumulator upsert")
    accumulator_rows = accumulator_response.json()
    if not accumulator_rows:
        fail("Supabase did not return the daily accumulator id.")
    accumulator_id = accumulator_rows[0]["id"]

    delete_legs = requests.delete(
        f"{base}/daily_accumulator_legs",
        params={"accumulator_id": f"eq.{quote(str(accumulator_id), safe='-')}"},
        headers=headers,
        timeout=TIMEOUT,
    )
    request_ok(delete_legs, "Previous accumulator leg cleanup")

    if valid:
        by_identity = {_identity(row): row for row in persisted_rows}
        legs = []
        for index, pick in enumerate(result["picks"], start=1):
            db_row = by_identity.get(_identity(pick))
            if not db_row or not db_row.get("id"):
                fail(f"Could not resolve fixture id for selected leg {pick.get('match_name')!r}.")
            validated_pick = prepare_fixture(pick)
            if not validated_pick:
                fail(f"Selected leg {pick.get('match_name')!r} failed the final evidence check.")
            legs.append({
                "accumulator_id": accumulator_id,
                "fixture_id": db_row["id"],
                "leg_order": index,
                "odds_at_build": float(pick["picked_odds"]),
                "score_at_build": float(validated_pick["confidence_score"]),
            })
        if legs:
            legs_response = requests.post(
                f"{base}/daily_accumulator_legs",
                headers=supabase_headers(service_key, "return=minimal"),
                json=legs,
                timeout=TIMEOUT,
            )
            request_ok(legs_response, "Accumulator leg insert")
        ready_response = requests.patch(
            f"{base}/daily_accumulators",
            params={"id": f"eq.{quote(str(accumulator_id), safe='-')}"},
            headers=supabase_headers(service_key, "return=minimal"),
            json={
                "status": "ready",
                "total_odds": float(total),
                "settlement_status": "pending",
                "settled_at": None,
                "settled_total_odds": None,
                "net_units": None,
                "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
            timeout=TIMEOUT,
        )
        request_ok(ready_response, "Daily accumulator publish")

    if valid:
        names = ", ".join(p["match_name"] for p in result["picks"])
        print(f"Built {analysis_date} accumulator: odds={float(total):.4f}; legs={len(result['picks'])}; {names}")
    else:
        print(
            f"No valid {analysis_date} accumulator. Eligible pending fixtures={len(persisted_rows)}; "
            f"candidate odds={float(total):.4f}. No ticket was forced."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
