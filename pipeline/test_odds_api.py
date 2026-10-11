import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import requests

from engine import prepare_fixture
from providers.odds_api import (
    MAX_MARKET_CREDITS_PER_RUN,
    OddsAPIError,
    TheOddsAPIClient,
    fetch_odds_api_feed,
    markets_for_sport,
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
    def test_auto_selection_uses_active_soccer_and_basketball_up_to_ten_keys(self):
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
                "soccer_france_ligue_one",
                "basketball_nba",
                "basketball_euroleague",
            ],
        )
        self.assertEqual(warnings, [])
        self.assertLessEqual(len(selected), 10)
        self.assertNotIn("tennis_atp_shanghai", selected)  # Paused until stats coverage exists.

    def test_two_soccer_market_families_rotate_within_credit_budget(self):
        soccer_day_one = [markets_for_sport(f"soccer_league_{i}", i, 739893) for i in range(8)]
        soccer_day_two = [markets_for_sport(f"soccer_league_{i}", i, 739894) for i in range(8)]
        expected = {"totals", "btts", "double_chance", "h2h", "spreads"}
        self.assertTrue(all(len(pair) == 2 for pair in soccer_day_one))
        self.assertEqual({market for pair in soccer_day_one for market in pair}, expected)
        self.assertNotEqual(soccer_day_one, soccer_day_two)
        basketball_markets = markets_for_sport("basketball_nba", 0, 739893)
        self.assertEqual(basketball_markets, ("h2h", "totals", "spreads"))
        planned_credits = sum(map(len, soccer_day_one)) + 2 * len(basketball_markets)
        self.assertEqual(planned_credits, 22)
        self.assertLessEqual(planned_credits, MAX_MARKET_CREDITS_PER_RUN)

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
            for index in range(12)
        ]
        selected, warnings = select_active_sport_keys(
            catalog, ",".join(f"soccer_league_{index}" for index in range(12))
        )
        self.assertEqual(len(selected), 8)
        self.assertTrue(any("per-sport competition cap" in note for note in warnings))


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
        self.assertEqual({row["market_key"] for row in rows}, {"over_0_5_goals", "over_2_5_goals"})
        over_half = next(row for row in rows if row["market_key"] == "over_0_5_goals")
        self.assertEqual(Decimal(over_half["picked_odds"]), Decimal("1.11"))
        self.assertEqual(over_half["source"], "the-odds-api")
        self.assertEqual(over_half["features"], {})
        self.assertEqual(over_half["event_id"], "match-1")

    def test_football_preserves_the_exact_different_totals_line(self):
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
        rows = normalize_event(event, "soccer_epl", now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market_key"], "over_1_5_goals")
        self.assertEqual(rows[0]["market_point"], "1.5")

    def test_football_maps_three_way_h2h_to_direct_1x2_not_double_chance(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [bookmaker("book-one", "Book One", [market("h2h", [
                {"name": "Home FC", "price": 1.55},
                {"name": "Away FC", "price": 1.72},
                {"name": "Draw", "price": 1.68},
            ])])],
        }
        rows = normalize_event(event, "soccer_epl", now=NOW)
        self.assertEqual({row["market_key"] for row in rows}, {
            "home_win_1x2", "draw_1x2", "away_win_1x2"
        })
        self.assertNotIn("double_chance_1x", {row["market_key"] for row in rows})
        home = next(row for row in rows if row["market_key"] == "home_win_1x2")
        self.assertEqual(home["selection_side"], "home")
        self.assertEqual(home["market_name"], "1X2 · Home Win")

    def test_football_rejects_incomplete_two_way_h2h_as_1x2(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [bookmaker("book-one", "Book One", [market("h2h", [
                {"name": "Home FC", "price": 1.55},
                {"name": "Away FC", "price": 1.72},
            ])])],
        }
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])

    def test_soccer_spreads_are_labeled_two_way_and_keep_each_signed_line(self):
        event = {
            "id": "soccer-spread-1",
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [bookmaker("book-one", "Book One", [
                market("spreads", [
                    {"name": "Home FC", "price": 1.62, "point": -0.5},
                    {"name": "Away FC", "price": 1.58, "point": 0.5},
                ]),
            ])],
        }
        rows = normalize_event(event, "soccer_epl", now=NOW)
        self.assertEqual({row["market_key"] for row in rows}, {
            "football_home_spread", "football_away_spread"
        })
        home = next(row for row in rows if row["market_key"] == "football_home_spread")
        away = next(row for row in rows if row["market_key"] == "football_away_spread")
        self.assertEqual(home["market_point"], "-0.5")
        self.assertEqual(away["market_point"], "0.5")
        self.assertEqual(home["selection_side"], "home")
        self.assertTrue(home["market_name"].startswith("Two-way Soccer Spread"))
        self.assertIsNone(prepare_fixture(home))  # The quote alone is not a qualified pick.
        self.assertIn("not a European three-way handicap", home["analysis_note"])
        self.assertNotIn("European 3-way", home["market_name"])

    def test_soccer_spreads_require_a_complete_pair_and_ignore_quarter_lines(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [bookmaker("book-one", "Book One", [
                market("spreads", [
                    {"name": "Home FC", "price": 1.62, "point": -0.25},
                    {"name": "Away FC", "price": 1.58, "point": 0.25},
                ]),
            ])],
        }
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])

        event["bookmakers"][0]["markets"][0]["outcomes"] = [
            {"name": "Home FC", "price": 1.62, "point": -0.5}
        ]
        self.assertEqual(normalize_event(event, "soccer_epl", now=NOW), [])

    def test_soccer_european_three_way_handicap_is_not_inferred_from_match_winner(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [bookmaker("book-one", "Book One", [
                market("h2h_3_way", [
                    {"name": "Home FC", "price": 1.55},
                    {"name": "Away FC", "price": 1.72},
                    {"name": "Draw", "price": 1.68},
                ]),
            ])],
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

    def test_soccer_btts_and_direct_double_chance_are_normalized_separately(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [bookmaker("book-one", "Book One", [
                market("btts", [{"name": "Yes", "price": 1.55}, {"name": "No", "price": 2.4}]),
                market("double_chance", [
                    {"name": "Home FC or Draw", "price": 1.18},
                    {"name": "Away FC or Draw", "price": 1.9},
                ]),
            ])],
        }
        rows = normalize_event(event, "soccer_epl", now=NOW)
        self.assertEqual({row["market_key"] for row in rows}, {"btts_yes", "double_chance_1x"})
        double_chance = next(row for row in rows if row["market_key"] == "double_chance_1x")
        self.assertEqual(double_chance["picked_odds"], "1.18")

    def test_basketball_totals_and_spreads_keep_exact_lines_and_sides(self):
        event = {
            "commence_time": FUTURE,
            "home_team": "Home Lions",
            "away_team": "Away Eagles",
            "bookmakers": [bookmaker("book-one", "Book One", [
                market("totals", [{"name": "Over", "price": 1.50, "point": 220.5}, {"name": "Under", "price": 1.50, "point": 220.5}]),
                market("spreads", [{"name": "Home Lions", "price": 1.50, "point": -4.5}, {"name": "Away Eagles", "price": 1.50, "point": 4.5}]),
            ])],
        }
        rows = normalize_event(event, "basketball_nba", now=NOW)
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["market_key"] for row in rows}, {
            "basketball_total_over", "basketball_total_under", "basketball_home_spread", "basketball_away_spread"
        })
        home_spread = next(row for row in rows if row["market_key"] == "basketball_home_spread")
        self.assertEqual(home_spread["market_point"], "-4.5")
        self.assertEqual(home_spread["selection_side"], "home")

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
        self.assertEqual(session.calls[1][1]["markets"], "h2h,totals,spreads")

    def test_quota_guard_spends_only_remaining_single_market_credit(self):
        session = FakeSession(
            [
                FakeResponse(
                    [{"key": "basketball_nba", "active": True}],
                    headers={"x-requests-used": "499", "x-requests-remaining": "1"},
                ),
                FakeResponse([], headers={"x-requests-used": "500", "x-requests-remaining": "0"}),
            ]
        )
        feed = fetch_odds_api_feed("unit-test-secret", now=NOW, session=session)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[1][1]["markets"], "h2h")
        self.assertEqual(feed.fixtures, [])
        self.assertEqual(feed.requests_remaining, 0)
        self.assertTrue(any("below the full-market cost" in warning for warning in feed.warnings))

    def test_runtime_market_requests_stay_within_22_credit_cap(self):
        soccer_keys = [
            "soccer_epl",
            "soccer_uefa_champs_league",
            "soccer_spain_la_liga",
            "soccer_germany_bundesliga",
            "soccer_italy_serie_a",
            "soccer_france_ligue_one",
            "soccer_england_efl_champ",
            "soccer_uefa_europa_league",
        ]
        catalog = [{"key": key, "active": True} for key in soccer_keys]
        catalog.extend([
            {"key": "basketball_nba", "active": True},
            {"key": "basketball_euroleague", "active": True},
        ])
        session = FakeSession([
            FakeResponse(catalog, headers={"x-requests-used": "0", "x-requests-remaining": "500"}),
            *[FakeResponse([]) for _ in range(10)],
        ])
        feed = fetch_odds_api_feed("unit-test-secret", now=NOW, session=session)
        requested_credits = sum(
            len(call[1]["markets"].split(",")) for call in session.calls[1:]
        )
        self.assertEqual(len(session.calls), 11)
        self.assertEqual(requested_credits, 22)
        self.assertLessEqual(requested_credits, MAX_MARKET_CREDITS_PER_RUN)
        self.assertEqual(len(feed.sport_keys), 10)

    def test_unsupported_market_retries_still_obey_hard_run_cap(self):
        soccer_keys = [
            "soccer_epl",
            "soccer_uefa_champs_league",
            "soccer_spain_la_liga",
            "soccer_germany_bundesliga",
            "soccer_italy_serie_a",
            "soccer_france_ligue_one",
            "soccer_england_efl_champ",
            "soccer_uefa_europa_league",
        ]
        catalog = [{"key": key, "active": True} for key in soccer_keys]
        catalog.extend([
            {"key": "basketball_nba", "active": True},
            {"key": "basketball_euroleague", "active": True},
        ])
        responses = [
            FakeResponse(catalog, headers={"x-requests-used": "0", "x-requests-remaining": "500"})
        ]
        for competition_index in range(4):
            responses.append(FakeResponse({"error": "unsupported"}, status_code=422))
            responses.extend(FakeResponse([]) for _ in range(3 if competition_index < 3 else 1))
        session = FakeSession(responses)
        with patch("providers.odds_api.markets_for_sport", return_value=("h2h", "totals", "spreads")):
            fetch_odds_api_feed("unit-test-secret", now=NOW, session=session)
        requested_credits = sum(
            len(call[1]["markets"].split(",")) for call in session.calls[1:]
        )
        self.assertEqual(requested_credits, MAX_MARKET_CREDITS_PER_RUN)
        self.assertLessEqual(requested_credits, 22)

    def test_unsupported_combined_market_retries_supported_markets_separately(self):
        event = {
            "id": "soccer-1", "sport_key": "soccer_epl", "sport_title": "EPL",
            "commence_time": FUTURE, "home_team": "Home FC", "away_team": "Away FC",
            "bookmakers": [bookmaker("book", "Book", [market("btts", [
                {"name": "Yes", "price": 1.55}, {"name": "No", "price": 2.4}
            ])])],
        }
        session = FakeSession([
            FakeResponse([{"key": "soccer_epl", "active": True}], headers={"x-requests-used": "20", "x-requests-remaining": "480"}),
            FakeResponse({"error": "one market is not supported"}, status_code=422),
            FakeResponse([], headers={"x-requests-used": "21", "x-requests-remaining": "479"}),
            FakeResponse([event], headers={"x-requests-used": "22", "x-requests-remaining": "478"}),
            FakeResponse({"error": "unsupported"}, status_code=422),
        ])
        with patch("providers.odds_api.markets_for_sport", return_value=("totals", "btts", "double_chance")):
            feed = fetch_odds_api_feed("unit-test-secret", now=NOW, session=session)
        self.assertEqual(len(session.calls), 5)
        self.assertEqual([call[1]["markets"] for call in session.calls[1:]], [
            "totals,btts,double_chance", "totals", "btts", "double_chance"
        ])
        self.assertIn("btts_yes", {row["market_key"] for row in feed.fixtures})
        self.assertEqual(feed.requests_remaining, 478)
        self.assertTrue(any("combined request was not supported" in warning for warning in feed.warnings))

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
