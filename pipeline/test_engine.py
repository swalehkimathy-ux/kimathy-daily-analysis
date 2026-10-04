import unittest

from engine import build_accumulator, prepare_fixture


class EligibilityTests(unittest.TestCase):
    def test_football_extreme_mismatch_within_odds_band_is_eligible(self):
        raw = {
            "sport_type": "football",
            "match_name": "Harbor FC vs Valley Rovers",
            "match_time": "2026-10-04T15:30:00+03:00",
            "market_name": "Double Chance 1X",
            "market_key": "double_chance_1x",
            "picked_odds": 1.12,
            "features": {
                "home_table_position": 2,
                "away_bottom_five": True,
                "league_table_size": 20,
                "home_league_matches": 10,
                "away_league_matches": 9,
            },
        }
        row = prepare_fixture(raw)
        self.assertIsNotNone(row)
        self.assertEqual(row["sport_type"], "football")
        self.assertGreaterEqual(row["confidence_score"], 0)
        raw["features"].pop("home_league_matches")
        self.assertIsNone(prepare_fixture(raw))

    def test_basketball_requires_minimum_home_and_away_samples(self):
        raw = {
            "sport_type": "basketball",
            "match_name": "Home vs Away",
            "match_time": "2026-10-04T10:00:00Z",
            "market_name": "Home Moneyline",
            "market_key": "home_moneyline",
            "picked_odds": 1.15,
            "features": {"home_win_rate": 0.91, "away_away_losing_streak": 5},
        }
        self.assertIsNone(prepare_fixture(raw))
        raw["features"].update({"home_home_games_sample": 8, "away_away_games_sample": 6})
        self.assertIsNotNone(prepare_fixture(raw))

    def test_football_high_goal_flag_requires_a_five_match_sample(self):
        raw = {
            "sport_type": "football",
            "match_name": "Home vs Away",
            "match_time": "2026-10-04T10:00:00Z",
            "market_name": "Over 0.5 Goals",
            "market_key": "over_0_5_goals",
            "picked_odds": 1.14,
            "features": {"historical_high_goal_match": True, "historical_high_goal_sample": 4},
        }
        self.assertIsNone(prepare_fixture(raw))
        raw["features"]["historical_high_goal_sample"] = 5
        self.assertIsNotNone(prepare_fixture(raw))

    def test_tennis_outside_top_75_opponent_and_preferred_surface_required(self):
        raw = {
            "sport_type": "tennis",
            "match_name": "A. Player vs B. Player",
            "match_time": "2026-10-04T12:00:00Z",
            "market_name": "Match Winner",
            "market_key": "match_winner",
            "picked_odds": 1.14,
            "features": {"favorite_rank": 8, "opponent_rank": 92, "preferred_surface": True, "round_number": 1},
        }
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"]["preferred_surface"] = False
        self.assertIsNone(prepare_fixture(raw))

    def test_odds_outside_sport_band_are_rejected(self):
        raw = {
            "sport_type": "basketball",
            "match_name": "Home vs Away",
            "match_time": "2026-10-04T10:00:00Z",
            "market_name": "Home Moneyline",
            "market_key": "home_moneyline",
            "picked_odds": 1.25,
            "features": {"home_win_rate": 0.91, "away_away_losing_streak": 7},
        }
        self.assertIsNone(prepare_fixture(raw))


class AccumulatorTests(unittest.TestCase):
    def row(self, name, odd, score):
        return {
            "sport_type": "football",
            "match_name": name,
            "match_time": "2026-10-04T10:00:00Z",
            "market_name": "Double Chance 1X",
            "picked_odds": odd,
            "confidence_score": score,
            "status": "pending",
        }

    def test_ranks_by_score_and_stops_immediately_in_range(self):
        rows = [
            self.row("fourth", 1.11, 88.9),
            self.row("second", 1.14, 91.2),
            self.row("first", 1.12, 93.4),
            self.row("third", 1.13, 89.8),
            self.row("fifth", 1.15, 87.1),
            self.row("out-of-band", 1.21, 99.9),
        ]
        result = build_accumulator(rows)
        self.assertTrue(result["in_range"])
        self.assertEqual([x["match_name"] for x in result["picks"]], ["first", "second", "third", "fourth"])
        self.assertGreaterEqual(result["total_odds"], 1.5)
        self.assertLess(result["total_odds"], 1.9)
        self.assertEqual(len(result["picks"]), 4)

    def test_does_not_claim_target_when_available_legs_are_insufficient(self):
        result = build_accumulator([self.row("one", 1.12, 90), self.row("two", 1.13, 80)])
        self.assertFalse(result["in_range"])
        self.assertEqual(len(result["picks"]), 2)


if __name__ == "__main__":
    unittest.main()
