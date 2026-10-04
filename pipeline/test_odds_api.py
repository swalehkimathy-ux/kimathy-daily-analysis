import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import requests

from engine import prepare_fixture
from providers.odds_api import (
    OddsAPIError,
    TheOddsAPIClient,
    fetch_odds_api_feed,
    normalize_event,
    select_active_sport_keys,
)


NOW = datetime(2026, 10, 4, 5, 30, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
FUTURE = (NOW + timedelta(hours=6)).isoformat().replace("+00:00", "Z")


def bookmaker(key, title, markets, updated=FRESH):
    return {
        "key": key,
        "title": title,
        "last_update": updated,
        "markets": markets,
    }


def market(key, outcomes, updated=FRESH):
    return {"key": key, "last_update": updated, "outcomes": outcomes}


class SportSelectionTests(unittest.TestCase):
    def test_auto_selection_caps_categories_and_includes_both_tennis_tours(self):
        catalog = [
            {"key": "soccer_epl", "active": True, "has_outrights": False},
            {"key": "soccer_spain_la_liga", "active": True, "has_outrights": False},
            {"key": "soccer_germany_bundesliga", "active": True, "has_outrights": False},
            {"key": "soccer_italy_serie_a", "active": True, "has_outrights": False},
            {"key": "soccer_france_ligue_one", "active": True, "has_outrights": False},
            {"key": "basketball_nba", "active": True, "has_outrights": False},
            {"key": "basketball_euroleague", "active": True, "has_outrights": False},
            {"key": "basketball_wnba", "active": True, "has_outrights": False},
            {"key": "tennis_atp_shanghai", "active": True, "has_outrights": False},
            {"key": "tennis_wta_wuhan", "active": True, "has_outrights": False},
            {"key": "tennis_atp_future", "active": False, "has_outrights": False},
            {"key": "soccer_epl_winner", "active": True, "has_outrights": True},
        ]
        selected, warnings = select_active_sport_keys(catalog)
        self.assertEqual(
            selected,
            [
                "soccer_epl",
                "soccer_spain_la_liga",
                "soccer_germany_bundesliga",
                "soccer_italy_serie_a",
                "basketball_nba",
                "basketball_euroleague",
                "tennis_atp_shanghai",
                "tennis_wta_wuhan",
            ],
        )
        self.assertEqual(warnings, [])
        self.assertLessEqual(len(selected), 8)

    def test_explicit_keys_ignore_inactive_and_unknown_entries(self):
        catalog = [
            {"key": f"soccer_league_{index}", "active": True}
            for index in range(10)
        ]
        selected, warnings = select_active_sport_keys(
            catalog, "soccer_league_1,soccer_league_3,unknown_key"
        )
        self.assertEqual(selected, ["soccer_league_1", "soccer_league_3"])
        self.assertTrue(any("unknown_key" in note for note in warnings))

    def test_explicit_sport_list_obeys_per_sport_caps(self):
        catalog = [
            {"key": f"soccer_league_{index}", "active": True}
            for index in range(5)
        ]
        selected, warnings = select_active_sport_keys(
            catalog, ",".join(f"soccer_league_{index}" for index in range(5))
        )
        self.assertEqual(len(selected), 4)
        self.assertTrue(any("per-sport free-tier cap" in note for note in warnings))


class EventNormalizationTests(unittest.TestCase):
    def test_football_maps_only_exact_over_half_line(self):
        event = {
            "id": "match-1",
            "sport_title": "Test League",
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [
                bookmaker(
                    "book-one",
                    "Book One",
                    [
                        market(
                            "totals",
                            [
                                {"name": "Over", "price": 1.11, "point": 0.5},
                                {"name": "Under", "price": 8.5, "point": 0.5},
                                {"name": "Over", "price": 1.22, "point": 2.5},
                            ],
                        )
                    ],
                )
            ],
        }
        rows = normalize_event(event, "soccer_epl", now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market_key"], "over_0_5_goals")
        self.assertEqual(Decimal(rows[0]["picked_odds"]), Decimal("1.11"))
        self.assertEqual(rows[0]["source"], "the-odds-api")
        self.assertEqual(rows[0]["features"], {})
        self.assertEqual(rows[0]["event_id"], "match-1")

    def test_football_does_not_rename_a_different_totals_line(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [
                bookmaker(
                    "book-one",
                    "Book One",
                    [market("totals", [{"name": "Over", "price": 1.12, "point": 1.5}])],
                )
            ],
        }
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])

    def test_football_does_not_call_three_way_moneyline_double_chance(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [
                bookmaker(
                    "book-one",
                    "Book One",
                    [
                        market(
                            "h2h",
                            [
                                {"name": "Home FC", "price": 1.12},
                                {"name": "Away FC", "price": 8.0},
                                {"name": "Draw", "price": 5.5},
                            ],
                        )
                    ],
                )
            ],
        }
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])

    def test_basketball_maps_fresh_home_moneyline_in_engine_band(self):
        event = {
            "id": "nba-1",
            "commence_time": FUTURE,
            "home_team": "Dar Falcons",
            "away_team": "Dodoma Titans",
            "bookmakers": [
                bookmaker(
                    "book-one",
                    "Book One",
                    [
                        market(
                            "h2h",
                            [
                                {"name": "Dar Falcons", "price": 1.14},
                                {"name": "Dodoma Titans", "price": 5.3},
                            ],
                        )
                    ],
                )
            ],
        }
        rows = normalize_event(event, "basketball_nba", now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market_key"], "home_moneyline")
        self.assertEqual(Decimal(rows[0]["picked_odds"]), Decimal("1.14"))
        self.assertIsNone(prepare_fixture(rows[0]))  # Odds alone cannot pass the evidence filters.

    def test_tennis_uses_bookmaker_consensus_favorite_and_best_fresh_quote(self):
        event = {
            "id": "tennis-1",
            "commence_time": FUTURE,
            "home_team": "A. Player",
            "away_team": "B. Player",
            "bookmakers": [
                bookmaker(
                    "book-one",
                    "Book One",
                    [market("h2h", [
                        {"name": "A. Player", "price": 1.10},
                        {"name": "B. Player", "price": 7.2},
                    ])],
                ),
                bookmaker(
                    "book-two",
                    "Book Two",
                    [market("h2h", [
                        {"name": "A. Player", "price": 1.13},
                        {"name": "B. Player", "price": 6.9},
                    ])],
                ),
            ],
        }
        rows = normalize_event(event, "tennis_atp_example", now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market_key"], "match_winner")
        self.assertEqual(rows[0]["selection_name"], "A. Player")
        self.assertEqual(Decimal(rows[0]["picked_odds"]), Decimal("1.13"))
        self.assertEqual(rows[0]["bookmaker_key"], "book-two")

    def test_stale_quotes_and_started_events_are_skipped(self):
        stale = (NOW - timedelta(hours=7)).isoformat().replace("+00:00", "Z")
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [
                bookmaker(
                    "book-one",
                    "Book One",
                    [market("totals", [{"name": "Over", "price": 1.11, "point": 0.5}], updated=stale)],
                    updated=stale,
                )
            ],
        }
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])
        event["commence_time"] = (NOW - timedelta(minutes=1)).isoformat()
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses=None, exception=None):
        self.responses = list(responses or [])
        self.exception = exception
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if self.exception:
            raise self.exception
        return self.responses.pop(0)


class APIClientTests(unittest.TestCase):
    def test_fetch_uses_decimal_odds_and_reports_quota_without_logging_key(self):
        event = {
            "id": "nba-2",
            "sport_key": "basketball_nba",
            "sport_title": "NBA",
            "commence_time": FUTURE,
            "home_team": "Home Team",
            "away_team": "Away Team",
            "bookmakers": [
                bookmaker("book-one", "Book One", [market("h2h", [
                    {"name": "Home Team", "price": 1.16},
                    {"name": "Away Team", "price": 4.2},
                ])]),
            ],
        }
        session = FakeSession(
            [
                FakeResponse(
                    [{"key": "basketball_nba", "active": True}],
                    headers={"x-requests-used": "10", "x-requests-remaining": "490"},
                ),
                FakeResponse(
                    [event],
                    headers={"x-requests-used": "11", "x-requests-remaining": "489", "x-requests-last": "1"},
                ),
            ]
        )
        feed = fetch_odds_api_feed("unit-test-secret", now=NOW, session=session)
        self.assertEqual(feed.sport_keys, ["basketball_nba"])
        self.assertEqual(feed.event_count, 1)
        self.assertEqual(len(feed.fixtures), 1)
        self.assertEqual(feed.requests_used, 11)
        self.assertEqual(feed.requests_remaining, 489)
        self.assertNotIn("unit-test-secret", repr(feed))
        self.assertEqual(session.calls[1][1]["oddsFormat"], "decimal")
        self.assertEqual(session.calls[1][1]["regions"], "eu")
        self.assertEqual(session.calls[1][1]["markets"], "h2h")

    def test_quota_guard_skips_odds_request_before_spending_below_estimated_cost(self):
        session = FakeSession(
            [
                FakeResponse(
                    [{"key": "soccer_epl", "active": True}],
                    headers={"x-requests-used": "499", "x-requests-remaining": "1"},
                )
            ]
        )
        feed = fetch_odds_api_feed("unit-test-secret", now=NOW, session=session)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(feed.fixtures, [])
        self.assertTrue(any("remaining credits" in warning for warning in feed.warnings))

    def test_connection_error_does_not_leak_query_key(self):
        secret = "should-never-appear-in-error"
        session = FakeSession(exception=requests.ConnectionError(f"failed URL apiKey={secret}"))
        client = TheOddsAPIClient(secret, session=session)
        with self.assertRaises(OddsAPIError) as context:
            client.list_active_sports()
        self.assertNotIn(secret, str(context.exception))

    def test_http_error_does_not_include_response_body_or_key(self):
        secret = "another-dummy-secret"
        session = FakeSession(
            [FakeResponse({"message": f"invalid key {secret}"}, status_code=401)]
        )
        client = TheOddsAPIClient(secret, session=session)
        with self.assertRaises(OddsAPIError) as context:
            client.list_active_sports()
        self.assertNotIn(secret, str(context.exception))
        self.assertNotIn("invalid key", str(context.exception))

    def test_bad_region_and_missing_key_fail_before_network(self):
        with self.assertRaises(OddsAPIError):
            TheOddsAPIClient("")
        with self.assertRaises(OddsAPIError):
            TheOddsAPIClient("dummy", region="eu,uk")


if __name__ == "__main__":
    unittest.main()
