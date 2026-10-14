from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from fixture_board import build_fixture_board
from providers.api_sports import normalise_schedule_fixtures


class FixtureBoardTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 10, 13)
        self.now = datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)
        self.requested = datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc)

    def test_provider_schedule_is_kept_even_when_odds_feed_has_no_fixture(self):
        normalized = [
            {
                "sport_type": "football",
                "provider_fixture_id": "101",
                "match_name": "Harbor FC vs Hill United",
                "home_team": "Harbor FC",
                "away_team": "Hill United",
                "match_time": "2026-10-13T15:00:00Z",
                "competition": "Coastal League",
                "fixture_state": "scheduled",
                "kickoff_time_known": True,
            }
        ]
        board = build_fixture_board(
            normalized, [], analysis_day=self.day, requested_at=self.requested, now=self.now
        )
        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["analysis_status"], "fixture_only_no_matched_quote")
        self.assertEqual(board[0]["market_options"], [])
        self.assertIsNone(board[0]["recommended_market"])
        self.assertIn("does not mean the match does not exist", board[0]["analysis_note"])

    def test_date_only_schedule_is_not_misreported_as_started_and_quote_time_can_enrich_it(self):
        raw = {
            "fixture": {"id": 103, "date": "2026-10-13", "status": {"short": "NS"}},
            "league": {"id": 39, "name": "Coastal League"},
            "teams": {"home": {"id": 10, "name": "Harbor FC"}, "away": {"id": 11, "name": "Hill United"}},
        }
        schedule = normalise_schedule_fixtures([raw], "football", self.day)
        self.assertEqual(len(schedule), 1)
        self.assertFalse(schedule[0]["kickoff_time_known"])
        unknown_board = build_fixture_board(
            schedule, [], analysis_day=self.day, requested_at=self.requested, now=self.now
        )
        self.assertEqual(unknown_board[0]["analysis_status"], "kickoff_time_unknown")

        quote = {
            "sport_type": "football",
            "provider_fixture_id": "103",
            "match_name": "Harbor FC vs Hill United",
            "home_team": "Harbor FC",
            "away_team": "Hill United",
            "match_time": "2026-10-13T15:00:00Z",
            "market_name": "Double Chance",
            "market_key": "double_chance_1x",
            "selection_name": "Harbor FC or Draw",
            "picked_odds": 1.35,
            "odds_updated_at": "2026-10-13T00:00:00Z",
            "features": {"league_table_size": 20, "home_league_matches": 10, "away_league_matches": 10, "home_table_position": 1, "away_bottom_five": True},
        }
        enriched_board = build_fixture_board(
            schedule, [quote], analysis_day=self.day, requested_at=self.requested, now=self.now
        )
        self.assertTrue(enriched_board[0]["kickoff_time_known"])
        self.assertEqual(enriched_board[0]["kickoff_time_source"], "the-odds-api-event")
        self.assertEqual(enriched_board[0]["match_time"], "2026-10-13T15:00:00Z")
        self.assertEqual(enriched_board[0]["analysis_status"], "evidence_qualified_market_available")

    def test_recommends_only_market_that_passes_existing_evidence_gate(self):
        schedule = [{
            "sport_type": "football",
            "provider_fixture_id": "101",
            "match_name": "Harbor FC vs Hill United",
            "home_team": "Harbor FC",
            "away_team": "Hill United",
            "match_time": "2026-10-13T15:00:00Z",
            "competition": "Coastal League",
            "fixture_state": "scheduled",
            "kickoff_time_known": True,
        }]
        qualified = {
            "sport_type": "football",
            "provider_fixture_id": "101",
            "match_name": "Harbor FC vs Hill United",
            "home_team": "Harbor FC",
            "away_team": "Hill United",
            "match_time": "2026-10-13T15:00:00Z",
            "market_name": "Double Chance",
            "market_key": "double_chance_1x",
            "selection_name": "Harbor FC or Draw",
            "selection_side": "home",
            "picked_odds": 1.35,
            "odds_updated_at": "2026-10-13T00:00:00Z",
            "status": "pending",
            "analysis_note": "Top-three home team; away side is bottom five.",
            "features": {
                "league_table_size": 20,
                "home_league_matches": 10,
                "away_league_matches": 10,
                "home_table_position": 1,
                "away_bottom_five": True,
            },
        }
        unqualified = {
            **qualified,
            "market_name": "Home win",
            "market_key": "home_win_1x2",
            "selection_name": "Harbor FC",
            "picked_odds": 1.80,
            "features": {},
        }
        board = build_fixture_board(
            schedule, [unqualified, qualified], analysis_day=self.day,
            requested_at=self.requested, now=self.now, ticket_picks=[qualified],
        )
        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["analysis_status"], "evidence_qualified_market_available")
        self.assertEqual(board[0]["recommended_market"]["market_key"], "double_chance_1x")
        self.assertEqual(board[0]["recommended_score"], 82.0)
        self.assertTrue(board[0]["selected_for_ticket"])
        self.assertEqual(len(board[0]["market_options"]), 2)
        self.assertEqual(
            sum(option["evidence_status"] == "passes_current_gate" for option in board[0]["market_options"]),
            1,
        )

    def test_provider_normalizer_retains_started_and_finished_schedule_rows(self):
        rows = [
            {
                "fixture": {
                    "id": 101,
                    "date": "2026-10-13T15:00:00+00:00",
                    "status": {"short": "NS", "long": "Not Started"},
                },
                "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2026, "round": "Week 1"},
                "teams": {"home": {"id": 1, "name": "Harbor FC"}, "away": {"id": 2, "name": "Hill United"}},
            },
            {
                "fixture": {
                    "id": 102,
                    "date": "2026-10-13T10:00:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished"},
                },
                "league": {"id": 39, "name": "Premier League", "country": "England", "season": 2026},
                "teams": {"home": {"id": 3, "name": "Bay FC"}, "away": {"id": 4, "name": "Vale Town"}},
            },
        ]
        normalized = normalise_schedule_fixtures(rows, "football", self.day)
        self.assertEqual(len(normalized), 2)
        self.assertEqual({row["fixture_state"] for row in normalized}, {"scheduled", "finished"})
        self.assertEqual(normalized[0]["competition"], "Premier League")
        self.assertEqual(normalized[0]["country"], "England")
        self.assertEqual(normalized[0]["analysis_date"], "2026-10-13")


if __name__ == "__main__":
    unittest.main()
