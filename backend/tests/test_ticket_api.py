import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class TicketApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.order_payload = {
            "movieName": "给阿嬷的情书",
            "showDate": "2026-06-14",
            "showTime": "14:30",
            "seatPositions": ["5排9号"],
            "cinemaCode": "34025901",
            "priceMax": 80,
        }

    def test_home_page_contains_order_fields(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("电影名", response.text)
        self.assertIn("seatPositions", response.text)
        self.assertIn("自动购票", response.text)
        self.assertNotIn("执行锁座", response.text)
        self.assertIn("请求日志", response.text)
        self.assertIn("tracePanel", response.text)
        self.assertNotIn("memberCardCode", response.text)
        self.assertNotIn("memberCardPassword", response.text)
        self.assertNotIn('id="openId"', response.text)

    @patch("app.api.ticket.DirectTicketRunner")
    @patch("app.api.ticket.CinemaApiClient")
    def test_preview_endpoint_runs_dry_run(self, _client_cls, runner_cls):
        runner_cls.return_value.run.return_value = {
            "success": True,
            "dry_run": True,
            "lock_payload": {"Count": 1},
            "trace": [{"step": "query_sessions", "url": "https://example.test"}],
        }

        response = self.client.post("/api/ticket/preview", json=self.order_payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["dry_run"])
        self.assertEqual(response.json()["trace"][0]["step"], "query_sessions")
        args, kwargs = runner_cls.return_value.run.call_args
        self.assertTrue(kwargs["dry_run"])
        self.assertEqual(args[0].seat_positions, ["5排9号"])
        self.assertEqual(args[0].open_id, "oiQcn5AJxwoWAya8SNqBXDVXwZNA")

    @patch("app.api.ticket.DirectTicketRunner")
    @patch("app.api.ticket.CinemaApiClient")
    def test_lock_endpoint_runs_execute_mode(self, _client_cls, runner_cls):
        runner_cls.return_value.run.return_value = {"success": True, "dry_run": False, "lock_order_no": "LOCK-1"}

        response = self.client.post("/api/ticket/lock", json=self.order_payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["dry_run"])
        args, kwargs = runner_cls.return_value.run.call_args
        self.assertFalse(kwargs["dry_run"])
        self.assertEqual(kwargs["member_card"], {"password": "240279"})
        self.assertEqual(args[0].expected_time, "14:30")
        self.assertEqual(args[0].open_id, "oiQcn5AJxwoWAya8SNqBXDVXwZNA")

    def test_invalid_input_returns_controlled_error(self):
        payload = dict(self.order_payload)
        payload["seatPositions"] = []

        response = self.client.post("/api/ticket/preview", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("reason", response.json())


if __name__ == "__main__":
    unittest.main()
