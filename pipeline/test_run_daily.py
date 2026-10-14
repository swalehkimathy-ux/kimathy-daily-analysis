from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from run_daily import _existing_ready_accumulator, main, parse_analysis_requested_at, persist_analysis_snapshot, reconcile_accumulator_results


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else []
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = ""

    def json(self):
        return self.payload


class RequestTimeAnchorTests(unittest.TestCase):
    def test_request_time_controls_eat_slate_across_midnight(self):
        now = datetime(2026, 10, 14, 0, 10, tzinfo=timezone.utc)
        requested = parse_analysis_requested_at("2026-10-13T23:50:00+03:00", now)
        self.assertEqual(requested, datetime(2026, 10, 13, 20, 50, tzinfo=timezone.utc))
        from zoneinfo import ZoneInfo
        self.assertEqual(requested.astimezone(ZoneInfo("Africa/Dar_es_Salaam")).date().isoformat(), "2026-10-13")

    def test_request_time_must_include_offset_and_not_be_far_future(self):
        now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "timezone offset"):
            parse_analysis_requested_at("2026-10-13T12:00:00", now)
        with self.assertRaisesRegex(ValueError, "future"):
            parse_analysis_requested_at("2026-10-13T12:06:00Z", now)


class AnalysisSnapshotPersistenceTests(unittest.TestCase):
    def test_persists_schedule_only_fixtures_and_completes_run_after_board(self):
        board = [{
            "sport_type": "football",
            "provider_fixture_id": "fixture-101",
            "match_name": "Harbor FC vs Hill United",
            "home_team": "Harbor FC",
            "away_team": "Hill United",
            "match_time": "2026-10-13T15:00:00Z",
            "kickoff_time_known": True,
            "competition": "Coastal League",
            "fixture_state": "scheduled",
            "analysis_status": "fixture_only_no_matched_quote",
            "market_options": [],
            "recommended_market": None,
            "analysis_note": "No quote from selected markets.",
            "statistics_summary": {"h2h_sample": 0},
        }]
        post_responses = [FakeResponse([{"id": "run-101"}]), FakeResponse([])]
        with patch("run_daily.requests.post", side_effect=post_responses) as post_mock, \
             patch("run_daily.requests.patch", return_value=FakeResponse()) as patch_mock:
            run_id = persist_analysis_snapshot(
                "https://example.supabase.co/rest/v1",
                {"apikey": "service", "Authorization": "Bearer service"},
                date(2026, 10, 13),
                datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc),
                board,
                coverage={"normalized_schedule_fixtures": 1},
                warnings=["diagnostic"],
            )
        self.assertEqual(run_id, "run-101")
        self.assertEqual(post_mock.call_count, 2)
        run_payload = post_mock.call_args_list[0].kwargs["json"]
        self.assertEqual(run_payload["status"], "running")
        self.assertEqual(run_payload["fixture_count"], 1)
        fixture_payload = post_mock.call_args_list[1].kwargs["json"]
        self.assertEqual(fixture_payload[0]["market_options"], [])
        self.assertEqual(fixture_payload[0]["analysis_status"], "fixture_only_no_matched_quote")
        self.assertEqual(patch_mock.call_args.kwargs["json"]["status"], "completed")


class AccumulatorSettlementHistoryTests(unittest.TestCase):
    def test_win_with_void_leg_uses_only_winning_leg_odds_for_paper_return(self):
        responses = [
            FakeResponse([{"id": "acc-1", "analysis_date": "2026-10-03", "status": "ready", "settlement_status": "pending"}]),
            FakeResponse([
                {"accumulator_id": "acc-1", "fixture_id": "fixture-1", "odds_at_build": 1.20},
                {"accumulator_id": "acc-1", "fixture_id": "fixture-2", "odds_at_build": 1.30},
            ]),
            FakeResponse([
                {"id": "fixture-1", "status": "win"},
                {"id": "fixture-2", "status": "void"},
            ]),
        ]
        with patch("run_daily.requests.get", side_effect=responses) as get_mock, \
             patch("run_daily.requests.patch", return_value=FakeResponse()) as patch_mock:
            changed = reconcile_accumulator_results(
                "https://example.supabase.co/rest/v1", {"apikey": "test", "Authorization": "Bearer test"},
                datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc), lookback_days=90,
            )
        self.assertEqual(changed, 1)
        self.assertEqual(get_mock.call_count, 3)
        patch_call = patch_mock.call_args
        self.assertIn("/daily_accumulators", patch_call.args[0])
        self.assertEqual(patch_call.kwargs["json"]["settlement_status"], "won")
        self.assertAlmostEqual(patch_call.kwargs["json"]["settled_total_odds"], 1.2)
        self.assertAlmostEqual(patch_call.kwargs["json"]["net_units"], 0.2)

    def test_any_losing_leg_marks_ticket_lost_even_if_another_is_pending(self):
        responses = [
            FakeResponse([{"id": "acc-2", "analysis_date": "2026-10-03", "status": "ready", "settlement_status": "pending"}]),
            FakeResponse([
                {"accumulator_id": "acc-2", "fixture_id": "fixture-1", "odds_at_build": 1.20},
                {"accumulator_id": "acc-2", "fixture_id": "fixture-2", "odds_at_build": 1.30},
            ]),
            FakeResponse([
                {"id": "fixture-1", "status": "loss"},
                {"id": "fixture-2", "status": "pending"},
            ]),
        ]
        with patch("run_daily.requests.get", side_effect=responses), \
             patch("run_daily.requests.patch", return_value=FakeResponse()) as patch_mock:
            changed = reconcile_accumulator_results(
                "https://example.supabase.co/rest/v1", {"apikey": "test", "Authorization": "Bearer test"},
                datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc), lookback_days=90,
            )
        self.assertEqual(changed, 1)
        payload = patch_mock.call_args.kwargs["json"]
        self.assertEqual(payload["settlement_status"], "lost")
        self.assertEqual(payload["net_units"], -1.0)
        self.assertEqual(payload["settled_total_odds"], 0.0)

    def test_main_freezes_existing_ready_ticket_before_odds_refresh(self):
        with patch.dict("run_daily.os.environ", {
            "SUPABASE_URL": "https://project.example",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "THE_ODDS_API_KEY": "test-odds-key",
        }, clear=True), \
             patch("run_daily.requests.get", side_effect=[
                 FakeResponse([]),
                 FakeResponse([]),
                 FakeResponse([{"id": "acc-today", "status": "ready", "total_odds": 1.62, "settlement_status": "pending"}]),
             ]) as get_mock, \
             patch("run_daily.fetch_odds_api_feed") as odds_mock, \
             patch("run_daily.requests.post", return_value=FakeResponse({
                 "allowed": True,
                 "next_allowed_at": "2026-10-05T12:00:00Z",
             })) as post_mock, \
             patch("run_daily.requests.delete") as delete_mock:
            result = main()
        self.assertEqual(result, 0)
        self.assertEqual(get_mock.call_count, 3)
        odds_mock.assert_not_called()
        post_mock.assert_called_once()
        self.assertIn("/rpc/kimathy_claim_manual_run", post_mock.call_args.args[0])
        delete_mock.assert_not_called()

    def test_manual_cooldown_stops_before_provider_or_database_pipeline_calls(self):
        with patch.dict("run_daily.os.environ", {
            "SUPABASE_URL": "https://project.example",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "THE_ODDS_API_KEY": "test-odds-key",
        }, clear=True), \
             patch("run_daily.requests.post", return_value=FakeResponse({
                 "allowed": False,
                 "reason": "cooldown",
                 "next_allowed_at": "2026-10-05T12:00:00Z",
             })) as post_mock, \
             patch("run_daily.requests.get") as get_mock, \
             patch("run_daily.fetch_odds_api_feed") as odds_mock:
            result = main()
        self.assertEqual(result, 0)
        post_mock.assert_called_once()
        get_mock.assert_not_called()
        odds_mock.assert_not_called()

    def test_no_ticket_record_does_not_freeze_a_later_rerun(self):
        with patch("run_daily.requests.get", return_value=FakeResponse([
            {"id": "acc-today", "status": "no_ticket", "total_odds": 1.0}
        ])):
            result = _existing_ready_accumulator(
                "https://example.supabase.co/rest/v1",
                {"apikey": "test", "Authorization": "Bearer test"},
                "2026-10-04",
            )
        self.assertIsNone(result)

    def test_unchanged_pending_ticket_is_not_patched(self):
        responses = [
            FakeResponse([{"id": "acc-3", "analysis_date": "2026-10-03", "status": "ready", "settlement_status": "pending"}]),
            FakeResponse([{"accumulator_id": "acc-3", "fixture_id": "fixture-3", "odds_at_build": 1.25}]),
            FakeResponse([{"id": "fixture-3", "status": "pending"}]),
        ]
        with patch("run_daily.requests.get", side_effect=responses), \
             patch("run_daily.requests.patch", return_value=FakeResponse()) as patch_mock:
            changed = reconcile_accumulator_results(
                "https://example.supabase.co/rest/v1", {"apikey": "test", "Authorization": "Bearer test"},
                datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc), lookback_days=90,
            )
        self.assertEqual(changed, 0)
        patch_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
