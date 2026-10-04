"""Fetch The Odds API v4 (or a normalized-feed fallback), filter candidates,
and build today's ticket.

The Odds API supplies odds/events only. Candidates still require independent
form/statistics evidence in order to pass the eligibility engine; no confidence
is invented when that evidence is absent.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests

from engine import TARGET_MAX, TARGET_MIN, build_accumulator, prepare_fixture
from providers.api_sports import enrich_odds_candidates
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
        body = response.text[:800]
        fail(f"{label} failed ({response.status_code}): {body}")
    return response


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
    end_eat = datetime.combine(analysis_date, time.max, tzinfo=EAT)
    start_utc = start_eat.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    end_utc = end_eat.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    now_utc = datetime.now(timezone.utc)

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

    # API-Sports adds independent football standings/head-to-head evidence and
    # basketball home/away form. No key means no calls and no inferred features.
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
        for warning in enrichment.warnings[:8]:
            print(f"API-Sports note: {warning}")

    evidence_count = sum(bool(raw.get("features")) for raw in incoming)
    prepared: list[dict] = []
    for raw in incoming:
        row = prepare_fixture(raw)
        if row is None:
            continue
        event_time = fixture_time(row)
        if not event_time or event_time.astimezone(EAT).date() != analysis_date or event_time < now_utc:
            continue
        prepared.append(row)

    print(
        f"Pipeline filter: provider_candidates={len(incoming)}; "
        f"with_feature_evidence={evidence_count}; eligible_for_today={len(prepared)}."
    )
    if odds_feed is not None and not evidence_count:
        print(
            "No picks will be inferred from odds alone. Add a permitted form/statistics "
            "source before expecting recommendations."
        )

    base = f"{supabase_url}/rest/v1"
    headers = supabase_headers(service_key)

    # Remove stale pending records from earlier days. Settled records are retained.
    stale_response = requests.delete(
        f"{base}/daily_fixtures",
        params={"status": "eq.pending", "match_time": f"lt.{start_utc}"},
        headers=headers,
        timeout=TIMEOUT,
    )
    request_ok(stale_response, "Stale pending fixture cleanup")

    # Rebuild today's pending Odds API rows from the fresh snapshot so an event
    # or quote that disappeared from the provider is not left as an old pick.
    if odds_feed is not None:
        odds_snapshot_cleanup = requests.delete(
            f"{base}/daily_fixtures",
            params=[
                ("status", "eq.pending"),
                ("source", "like.the-odds-api*"),
                ("match_time", f"gte.{start_utc}"),
                ("match_time", f"lte.{end_utc}"),
            ],
            headers=headers,
            timeout=TIMEOUT,
        )
        request_ok(odds_snapshot_cleanup, "Today's stale Odds API snapshot cleanup")

    if prepared:
        upsert_response = requests.post(
            f"{base}/daily_fixtures",
            params={"on_conflict": "sport_type,match_name,match_time,market_name"},
            headers=supabase_headers(service_key, "resolution=merge-duplicates,return=minimal"),
            json=prepared,
            timeout=TIMEOUT,
        )
        request_ok(upsert_response, "Fixture upsert")

    query = [
        ("select", "id,sport_type,match_name,match_time,market_name,picked_odds,confidence_score,status,source"),
        ("match_time", f"gte.{start_utc}"),
        ("match_time", f"lte.{end_utc}"),
        ("status", "eq.pending"),
        ("order", "confidence_score.desc"),
    ]
    rows_response = requests.get(
        f"{base}/daily_fixtures", params=query, headers=headers, timeout=TIMEOUT
    )
    request_ok(rows_response, "Today's pending fixture query")
    today_rows = rows_response.json()
    if not isinstance(today_rows, list):
        fail("Supabase returned an unexpected fixture payload.")
    # Synthetic demo rows are intentionally retained in Supabase for the UI check,
    # but must never participate in a real daily accumulator.
    today_rows = [
        row for row in today_rows
        if row.get("source") not in {"interface-test", "sample-feed"}
        and (row_time := fixture_time(row)) is not None
        and row_time >= now_utc
    ]

    result = build_accumulator(today_rows)
    valid = bool(result["in_range"])
    total = Decimal(str(result["total_odds"]))
    payload = {
        "analysis_date": analysis_date.isoformat(),
        "status": "ready" if valid else "no_ticket",
        "total_odds": float(total if valid else Decimal("1.0000")),
        "target_min": float(TARGET_MIN),
        "target_max": float(TARGET_MAX),
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
        params={"accumulator_id": f"eq.{accumulator_id}"},
        headers=headers,
        timeout=TIMEOUT,
    )
    request_ok(delete_legs, "Previous accumulator leg cleanup")

    if valid:
        by_identity = {
            (r["sport_type"], r["match_name"], r["market_name"]): r for r in today_rows
        }
        legs = []
        for index, pick in enumerate(result["picks"], start=1):
            # Rows returned by Supabase carry their UUID; the identity fallback is
            # defensive in case the provider normalizes string values differently.
            db_row = next((r for r in today_rows if str(r.get("id")) == str(pick.get("id"))), None)
            if db_row is None:
                db_row = by_identity.get((pick.get("sport_type"), pick.get("match_name"), pick.get("market_name")))
            if not db_row or not db_row.get("id"):
                fail(f"Could not resolve fixture id for selected leg {pick.get('match_name')!r}.")
            legs.append({
                "accumulator_id": accumulator_id,
                "fixture_id": db_row["id"],
                "leg_order": index,
                "odds_at_build": float(pick["picked_odds"]),
                "score_at_build": float(pick["confidence_score"]),
            })
        if legs:
            legs_response = requests.post(
                f"{base}/daily_accumulator_legs",
                headers=supabase_headers(service_key, "return=minimal"),
                json=legs,
                timeout=TIMEOUT,
            )
            request_ok(legs_response, "Accumulator leg insert")

    if valid:
        names = ", ".join(p["match_name"] for p in result["picks"])
        print(f"Built {analysis_date} accumulator: odds={float(total):.4f}; legs={len(result['picks'])}; {names}")
    else:
        print(f"No valid {analysis_date} accumulator. Eligible pending fixtures={len(today_rows)}; candidate odds={float(total):.4f}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
