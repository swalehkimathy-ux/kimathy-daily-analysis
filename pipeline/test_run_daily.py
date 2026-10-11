from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from run_daily import _existing_ready_accumulator, main, reconcile_accumulator_results


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else []
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = ""

    def json(self):
        return self.payload


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
