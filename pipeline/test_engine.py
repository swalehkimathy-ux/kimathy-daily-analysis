import unittest

from engine import build_accumulator, prepare_fixture


def football_candidate(name, odd=1.12, market="double_chance_1x", features=None, event_id=None):
    return {
        "sport_type": "football",
        "match_name": name,
        "home_team": name.split(" vs ")[0],
        "away_team": name.split(" vs ")[1] if " vs " in name else "Away",
        "match_time": "2026-10-04T15:30:00+03:00",
        "market_name": market.replace("_", " ").title(),
        "market_key": market,
        "market_point": (
            1.5 if market.startswith(("over_", "under_"))
            else -0.5 if market == "football_home_spread"
            else 0.5 if market == "football_away_spread"
            else None
        ),
        "selection_side": (
            "home" if market == "football_home_spread"
            else "away" if market == "football_away_spread"
            else None
        ),
        "picked_odds": odd,
        "event_id": event_id or name,
        "features": features or {
            "home_table_position": 2,
            "away_bottom_five": True,
            "league_table_size": 20,
            "home_league_matches": 10,
            "away_league_matches": 9,
        },
    }


class EligibilityTests(unittest.TestCase):
    def test_football_double_chance_requires_complete_extreme_standings(self):
        raw = football_candidate("Harbor FC vs Valley Rovers")
        row = prepare_fixture(raw)
        self.assertIsNotNone(row)
        self.assertEqual(row["market_key"], "double_chance_1x")
        raw["features"].pop("home_league_matches")
        self.assertIsNone(prepare_fixture(raw))

    def test_football_direct_1x2_winner_requires_four_of_five_h2h_results(self):
        raw = football_candidate(
            "Home vs Away", 1.62, "home_win_1x2",
            {"historical_1x2_sample": 5, "historical_home_win_count": 4},
        )
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"]["historical_home_win_count"] = 3
        self.assertIsNone(prepare_fixture(raw))
        raw["features"]["historical_home_win_count"] = 4
        raw["picked_odds"] = 1.81
        self.assertIsNone(prepare_fixture(raw))

    def test_football_two_way_spread_needs_five_h2h_and_recent_cover_form(self):
        raw = football_candidate(
            "Home vs Away", 1.05, "football_home_spread",
            {
                "historical_spread_sample": 5,
                "historical_spread_cover_count": 4,
                "historical_spread_line": "-0.5",
                "selected_spread_form_sample": 5,
                "selected_spread_form_rate": 0.80,
                "opponent_spread_form_sample": 5,
                "opponent_spread_form_rate": 0.20,
            },
        )
        raw["market_name"] = "Two-way Soccer Spread · Home (-0.5)"
        self.assertIsNotNone(prepare_fixture(raw))
        raw["market_point"] = -1.0  # Evidence must match the quoted handicap line.
        self.assertIsNone(prepare_fixture(raw))
        raw["market_point"] = -0.5
        raw["market_name"] = "European Handicap · Home (-0.5)"
        self.assertIsNone(prepare_fixture(raw))
        raw["market_name"] = "Two-way Soccer Spread · Home (-0.5)"
        raw["selection_side"] = "away"
        self.assertIsNone(prepare_fixture(raw))
        raw["selection_side"] = "home"
        raw["picked_odds"] = 1.04
        self.assertIsNone(prepare_fixture(raw))

    def test_football_btts_requires_five_h2h_matches_and_market_specific_hit_rate(self):
        raw = football_candidate(
            "Home vs Away", 1.55, "btts_yes",
            {"historical_btts_sample": 4, "historical_btts_yes_count": 4},
        )
        self.assertIsNone(prepare_fixture(raw))
        raw["features"] = {"historical_btts_sample": 5, "historical_btts_yes_count": 4}
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"]["historical_btts_yes_count"] = 2
        self.assertIsNone(prepare_fixture(raw))

    def test_football_totals_require_line_specific_h2h_evidence(self):
        raw = football_candidate(
            "Home vs Away", 1.48, "over_1_5_goals",
            {
                "historical_total_goals_sample": 5,
                "historical_over_1_5_count": 4,
                "home_form_matches_sample": 5,
                "away_form_matches_sample": 5,
                "home_form_over_1_5_rate": 0.80,
                "away_form_over_1_5_rate": 0.60,
            },
        )
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"].pop("away_form_over_1_5_rate")
        self.assertIsNone(prepare_fixture(raw))
        raw["features"]["away_form_over_1_5_rate"] = 0.20
        self.assertIsNone(prepare_fixture(raw))
        raw["features"]["away_form_over_1_5_rate"] = 0.60
        raw["market_key"] = "over_2_5_goals"
        raw["features"]["historical_over_2_5_count"] = 3
        self.assertIsNone(prepare_fixture(raw))

    def test_standings_evidence_does_not_pass_a_goal_market(self):
        raw = football_candidate("Home vs Away", 1.20, "over_0_5_goals")
        self.assertIsNone(prepare_fixture(raw))

    def test_basketball_moneyline_requires_home_away_samples_and_streak(self):
        raw = {
            "sport_type": "basketball", "match_name": "Home vs Away",
            "home_team": "Home", "away_team": "Away",
            "match_time": "2026-10-04T10:00:00Z", "market_name": "Home Moneyline",
            "market_key": "home_moneyline", "picked_odds": 1.15,
            "features": {"home_win_rate": 0.9, "away_away_losing_streak": 5,
                         "home_home_games_sample": 8, "away_away_games_sample": 6},
        }
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"]["away_away_games_sample"] = 4
        self.assertIsNone(prepare_fixture(raw))

    def test_basketball_totals_require_both_relevant_samples(self):
        raw = {
            "sport_type": "basketball", "match_name": "Home vs Away",
            "match_time": "2026-10-04T10:00:00Z", "market_name": "Over 220.5 Total Points",
            "market_key": "basketball_total_over", "market_point": 220.5,
            "picked_odds": 1.55,
            "features": {"home_market_total_hit_rate": 0.8, "away_market_total_hit_rate": 0.7,
                         "home_home_games_sample": 8, "away_away_games_sample": 7},
        }
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"]["away_market_total_hit_rate"] = 0.6
        self.assertIsNone(prepare_fixture(raw))

    def test_basketball_spread_requires_selected_side_and_opponent_support(self):
        raw = {
            "sport_type": "basketball", "match_name": "Home vs Away",
            "match_time": "2026-10-04T10:00:00Z", "market_name": "Home Handicap -4.5",
            "market_key": "basketball_home_spread", "market_point": -4.5,
            "selection_side": "home", "picked_odds": 1.55,
            "features": {"selection_cover_rate": 0.8, "opponent_cover_rate": 0.2,
                         "selection_cover_sample": 10, "opponent_cover_sample": 10},
        }
        self.assertIsNotNone(prepare_fixture(raw))
        raw["features"]["opponent_cover_rate"] = 0.4
        self.assertIsNone(prepare_fixture(raw))

    def test_odds_outside_expanded_per_leg_band_are_rejected(self):
        raw = football_candidate("Home vs Away", 1.81)
        self.assertIsNone(prepare_fixture(raw))


class AccumulatorTests(unittest.TestCase):
    def row(self, name, odd, score, event_id=None):
        item = football_candidate(name, odd=odd, event_id=event_id)
        item["confidence_score"] = score
        return item

    def test_ranks_by_score_and_stops_inside_combined_target(self):
        rows = [
            self.row("fourth vs Away 4", 1.11, 88.9),
            self.row("second vs Away 2", 1.14, 91.2),
            self.row("first vs Away 1", 1.12, 93.4),
            self.row("third vs Away 3", 1.13, 89.8),
            self.row("fifth vs Away 5", 1.15, 87.1),
            self.row("out-of-band vs Away", 1.81, 99.9),
        ]
        result = build_accumulator(rows)
        self.assertTrue(result["in_range"])
        self.assertEqual([x["match_name"] for x in result["picks"]], [
            "first vs Away 1", "second vs Away 2", "third vs Away 3", "fourth vs Away 4"
        ])
        self.assertGreaterEqual(result["total_odds"], 1.5)
        self.assertLess(result["total_odds"], 1.9)

    def test_does_not_claim_target_when_evidence_backed_legs_are_insufficient(self):
        result = build_accumulator([self.row("one vs Away 1", 1.12, 90), self.row("two vs Away 2", 1.13, 80)])
        self.assertFalse(result["in_range"])
        self.assertEqual(len(result["picks"]), 2)

    def test_never_puts_two_markets_from_same_event_in_one_ticket(self):
        first = self.row("Home vs Away", 1.30, 90, event_id="same-event")
        second = football_candidate(
            "Home vs Away", 1.30, "over_1_5_goals",
            {
                "historical_total_goals_sample": 5,
                "historical_over_1_5_count": 4,
                "home_form_matches_sample": 5,
                "away_form_matches_sample": 5,
                "home_form_over_1_5_rate": 0.80,
                "away_form_over_1_5_rate": 0.60,
            },
            event_id="same-event",
        )
        second["confidence_score"] = 95
        result = build_accumulator([first, second])
        self.assertEqual(len(result["picks"]), 1)
        self.assertEqual(result["picks"][0]["market_key"], "over_1_5_goals")

    def test_single_market_without_independent_evidence_is_never_selected(self):
        raw = football_candidate("Home vs Away", 1.6, "btts_yes", {})
        result = build_accumulator([raw])
        self.assertFalse(result["in_range"])
        self.assertEqual(result["picks"], [])


if __name__ == "__main__":
    unittest.main()
