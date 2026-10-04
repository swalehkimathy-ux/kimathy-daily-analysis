from __future__ import annotations

import unittest
from datetime import datetime, timezone

from engine import prepare_fixture
from providers.api_sports import enrich_odds_candidates


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        call = {
            "url": url,
            "params": params or {},
            "headers": headers or {},
            "timeout": timeout,
        }
        self.calls.append(call)
        return self.handler(call)


def football_candidate():
    return {
        "sport_type": "football",
        "home_team": "Premier Home FC",
        "away_team": "Premier Away FC",
        "match_name": "Premier Home FC vs Premier Away FC",
        "match_time": "2026-10-04T12:00:00Z",
        "market_name": "Over 0.5 Goals",
        "market_key": "over_0_5_goals",
        "picked_odds": "1.14",
        "features": {},
        "analysis_note": "Current quote. The odds feed does not include the form/ranking evidence required for a recommendation.",
        "source": "the-odds-api",
    }


def football_schedule_payload():
    return {
        "response": [
            {
                "fixture": {
                    "id": 9001,
                    "date": "2026-10-04T15:00:00+03:00",
                    "status": {"short": "NS", "long": "Not Started"},
                },
                "league": {"id": 39, "name": "Example League", "season": 2026},
                "teams": {
                    "home": {"id": 1, "name": "Premier Home FC"},
                    "away": {"id": 2, "name": "Premier Away FC"},
                },
            }
        ]
    }


def football_standings_payload():
    table = []
    for rank in range(1, 21):
        team_id = 1 if rank == 2 else 2 if rank == 18 else 100 + rank
        table.append(
            {
                "rank": rank,
                "team": {"id": team_id, "name": f"Team {team_id}"},
                "all": {"played": 10, "win": 6, "draw": 2, "lose": 2},
            }
        )
    return {"response": [{"league": {"standings": [table]}}]}


def football_h2h_payload():
    response = []
    for index in range(5):
        response.append(
            {
                "fixture": {
                    "id": 8000 + index,
                    "date": f"2025-09-{20 + index:02d}T15:00:00Z",
                    "status": {"short": "FT", "long": "Match Finished"},
                },
                "goals": {"home": 2, "away": 1} if index < 4 else {"home": 0, "away": 0},
            }
        )
    return {"response": response}


def basketball_candidate():
    return {
        "sport_type": "basketball",
        "home_team": "Home Lions",
        "away_team": "Away Eagles",
        "match_name": "Home Lions vs Away Eagles",
        "match_time": "2026-10-04T15:00:00Z",
        "market_name": "Home Moneyline",
        "market_key": "home_moneyline",
        "picked_odds": "1.15",
        "features": {},
        "analysis_note": "Current quote. The odds feed does not include the form/ranking evidence required for a recommendation.",
        "source": "the-odds-api",
    }


def basketball_game(game_id, game_date, home_id, away_id, home_points, away_points, status="Finished"):
    return {
        "id": game_id,
        "date": game_date,
        "status": {"short": "FT", "long": status},
        "league": {"id": 7, "name": "Example Basketball League", "season": "2026"},
        "teams": {
            "home": {"id": home_id, "name": "Home Lions" if home_id == 10 else f"Team {home_id}"},
            "away": {"id": away_id, "name": "Away Eagles" if away_id == 20 else f"Team {away_id}"},
        },
        "scores": {"home": {"total": home_points}, "away": {"total": away_points}},
    }


def basketball_schedule_payload():
    return {
        "response": [
            {
                "id": 7001,
                "date": "2026-10-04T18:00:00+03:00",
                "status": {"short": "NS", "long": "Not Started"},
                "league": {"id": 7, "name": "Example Basketball League", "season": "2026"},
                "teams": {
                    "home": {"id": 10, "name": "Home Lions"},
                    "away": {"id": 20, "name": "Away Eagles"},
                },
                "scores": {"home": {"total": None}, "away": {"total": None}},
            }
        ]
    }


def basketball_history_payloads():
    home_history = []
    for index in range(10):
        home_points, away_points = (102, 91) if index < 9 else (88, 94)
        home_history.append(
            basketball_game(
                6000 + index,
                f"2026-09-{10 + index:02d}T18:00:00Z",
                10,
                100 + index,
                home_points,
                away_points,
            )
        )
    away_history = []
    for index in range(5):
        away_history.append(
            basketball_game(
                5000 + index,
                f"2026-09-{20 + index:02d}T18:00:00Z",
                200 + index,
                20,
                103,
                90,
            )
        )
    away_history.append(basketball_game(4999, "2026-09-10T18:00:00Z", 201, 20, 90, 100))
    return {"10": {"response": home_history}, "20": {"response": away_history}}


class APISportsEnrichmentTests(unittest.TestCase):
    NOW = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)

    def test_football_standings_and_h2h_enrich_a_qualified_candidate(self):
        def handler(call):
            url = call["url"]
            if url.endswith("/status"):
                return FakeResponse({"response": {"requests": {"current": 2, "limit_day": 100}}})
            if url.endswith("/fixtures"):
                return FakeResponse(football_schedule_payload())
            if url.endswith("/standings"):
                return FakeResponse(football_standings_payload())
            if url.endswith("/fixtures/headtohead"):
                return FakeResponse(football_h2h_payload())
            self.fail(f"Unexpected request path: {url}")

        session = FakeSession(handler)
        result = enrich_odds_candidates(
            [football_candidate()],
            football_key="offline-test-key",
            analysis_day="2026-10-04",
            now=self.NOW,
            sessions={"football": session},
        )

        self.assertEqual(result.football_calls, 3)
        self.assertEqual(result.football_enriched, 1)
        row = result.fixtures[0]
        self.assertEqual(row["features"]["home_table_position"], 2)
        self.assertTrue(row["features"]["away_bottom_five"])
        self.assertEqual(row["features"]["league_table_size"], 20)
        self.assertEqual(row["features"]["home_league_matches"], 10)
        self.assertEqual(row["features"]["away_league_matches"], 10)
        self.assertTrue(row["features"]["historical_high_goal_match"])
        self.assertEqual(row["features"]["historical_high_goal_sample"], 5)
        self.assertIn("api-sports", row["source"])
        self.assertNotIn("does not include the form/ranking evidence", row["analysis_note"])
        self.assertIsNotNone(prepare_fixture(row))
        self.assertTrue(all(c["headers"].get("x-apisports-key") == "offline-test-key" for c in session.calls))

    def test_basketball_recent_home_form_and_away_loss_streak_enrich(self):
        history = basketball_history_payloads()

        def handler(call):
            url, params = call["url"], call["params"]
            if url.endswith("/status"):
                return FakeResponse({"response": {"requests": {"current": 0, "limit_day": 100}}})
            if url.endswith("/games") and "date" in params:
                return FakeResponse(basketball_schedule_payload())
            if url.endswith("/games") and "team" in params:
                return FakeResponse(history[str(params["team"])])
            self.fail(f"Unexpected request: {url} {params}")

        session = FakeSession(handler)
        result = enrich_odds_candidates(
            [basketball_candidate()],
            basketball_key="offline-test-key",
            analysis_day="2026-10-04",
            now=self.NOW,
            sessions={"basketball": session},
        )

        self.assertEqual(result.basketball_calls, 3)
        self.assertEqual(result.basketball_enriched, 1)
        row = result.fixtures[0]
        self.assertEqual(row["features"]["home_win_rate"], 0.9)
        self.assertEqual(row["features"]["home_home_games_sample"], 10)
        self.assertEqual(row["features"]["away_away_losing_streak"], 5)
        self.assertEqual(row["features"]["away_away_games_sample"], 6)
        self.assertIsNotNone(prepare_fixture(row))

    def test_team_name_mismatch_does_not_attach_another_fixture_statistics(self):
        schedule = football_schedule_payload()
        schedule["response"][0]["teams"]["home"]["name"] = "Unrelated City FC"
        schedule["response"][0]["teams"]["away"]["name"] = "Different United FC"

        def handler(call):
            if call["url"].endswith("/status"):
                return FakeResponse({"response": {"requests": {"current": 0, "limit_day": 100}}})
            if call["url"].endswith("/fixtures"):
                return FakeResponse(schedule)
            self.fail("Standings/H2H must not be queried if the fixture did not match")

        session = FakeSession(handler)
        result = enrich_odds_candidates(
            [football_candidate()],
            football_key="offline-test-key",
            analysis_day="2026-10-04",
            now=self.NOW,
            sessions={"football": session},
        )
        self.assertEqual(result.football_calls, 1)
        self.assertEqual(result.football_enriched, 0)
        self.assertEqual(result.fixtures[0]["features"], {})

    def test_account_quota_guard_skips_all_data_calls(self):
        session = FakeSession(
            lambda call: FakeResponse(
                {"response": {"requests": {"current": 99, "limit_day": 100}}}
            )
        )
        result = enrich_odds_candidates(
            [football_candidate()],
            football_key="offline-test-key",
            analysis_day="2026-10-04",
            now=self.NOW,
            sessions={"football": session},
        )
        self.assertEqual(result.football_calls, 0)
        self.assertEqual(len(session.calls), 1)  # status only
        self.assertEqual(result.fixtures[0]["features"], {})
        self.assertTrue(any("quota" in warning.lower() or "budget" in warning.lower() for warning in result.warnings))

    def test_invalid_key_error_is_sanitized(self):
        secret = "key-that-must-never-be-logged"

        def handler(call):
            if call["url"].endswith("/status"):
                return FakeResponse({"errors": {"token": "invalid"}, "response": None})
            self.fail("Data request must not follow a failed status check")

        result = enrich_odds_candidates(
            [football_candidate()],
            football_key=secret,
            analysis_day="2026-10-04",
            now=self.NOW,
            sessions={"football": FakeSession(handler)},
        )
        self.assertTrue(result.warnings)
        self.assertNotIn(secret, " ".join(result.warnings))
        self.assertEqual(result.football_calls, 0)
        self.assertEqual(result.fixtures[0]["features"], {})

    def test_no_key_makes_no_calls_or_inferred_evidence(self):
        result = enrich_odds_candidates(
            [football_candidate(), basketball_candidate()],
            analysis_day="2026-10-04",
            now=self.NOW,
        )
        self.assertEqual(result.football_calls, 0)
        self.assertEqual(result.basketball_calls, 0)
        self.assertEqual(result.fixtures[0]["features"], {})
        self.assertEqual(result.fixtures[1]["features"], {})


if __name__ == "__main__":
    unittest.main()
