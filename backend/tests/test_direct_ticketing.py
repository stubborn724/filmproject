from datetime import datetime
import asyncio
from pathlib import Path
import tempfile
import unittest

from app.direct_ticketing import (
    CinemaApiClient,
    DirectTicketRunner,
    MatchCriteria,
    SeatUnavailableError,
    SpecifiedSeatResolver,
    SessionMatcher,
    criteria_from_order,
)


class DirectTicketingTests(unittest.TestCase):
    def test_criteria_from_order_accepts_specified_seats_and_open_id(self):
        criteria = criteria_from_order(
            {
                "filmName": "Target Movie",
                "date": "2026-06-14",
                "showTime": "14:30",
                "tickets": 1,
                "seat_positions": ["5排9号"],
                "openId": "OPEN-1",
            }
        )

        self.assertEqual(criteria.movie_name, "Target Movie")
        self.assertEqual(criteria.start_date, "2026-06-14")
        self.assertEqual(criteria.end_date, "2026-06-14")
        self.assertEqual(criteria.expected_time, "14:30")
        self.assertEqual(criteria.ticket_count, 1)
        self.assertEqual(criteria.seat_positions, ["5排9号"])
        self.assertEqual(criteria.open_id, "OPEN-1")

    def test_session_matcher_filters_and_sorts_candidate_sessions(self):
        sessions = [
            {
                "filmName": "Target Movie",
                "PlanCode": "P2",
                "status": "可销售",
                "StartTime": "2026-06-14 19:20:00",
                "NetSaleStopTime": "2026-06-14 19:10:00",
                "channelPrice": "45.00",
                "hallName": "2号激光厅",
                "Language": "普通话",
                "ShowType": "2D",
            },
            {
                "filmName": "Target Movie",
                "PlanCode": "P1",
                "status": "可销售",
                "StartTime": "2026-06-14 14:30:00",
                "NetSaleStopTime": "2026-06-14 14:25:00",
                "channelPrice": "35.00",
                "hallName": "2号激光厅",
                "Language": "普通话",
                "ShowType": "2D",
            },
            {
                "filmName": "Other Movie",
                "PlanCode": "P0",
                "status": "可销售",
                "StartTime": "2026-06-14 14:30:00",
                "NetSaleStopTime": "2026-06-14 14:25:00",
                "channelPrice": "35.00",
            },
        ]
        criteria = MatchCriteria(
            movie_name="Target Movie",
            start_date="2026-06-14",
            end_date="2026-06-14",
            ticket_count=1,
            expected_time="14:30",
            seat_positions=["5排9号"],
            open_id="OPEN-1",
        )

        matched = SessionMatcher(criteria, now=datetime(2026, 6, 14, 12, 0, 0)).match(sessions)

        self.assertEqual([session["PlanCode"] for session in matched], ["P1"])

    def test_runner_dry_run_resolves_requested_seat_and_builds_lock_payload(self):
        client = FakeClient()
        criteria = MatchCriteria(
            movie_name="Target Movie",
            start_date="2026-06-14",
            end_date="2026-06-14",
            ticket_count=1,
            expected_time="14:30",
            seat_positions=["5排9号"],
            open_id="OPEN-1",
        )

        result = DirectTicketRunner(client, now=datetime(2026, 6, 14, 12, 0, 0)).run(criteria, dry_run=True)

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(client.lock_calls, [])
        self.assertEqual(result["plan_code"], "P1")
        self.assertEqual(result["seats"], [{"code": "S-5-9", "position": "5排9号", "row": 5, "col": 9}])
        self.assertEqual(
            result["lock_payload"],
            {
                "Count": 1,
                "SessionCode": "P1",
                "openId": "OPEN-1",
                "distributorId": "",
                "Seat": [
                    {
                        "PayPrice": "35.00",
                        "Price": "60.00",
                        "SeatCode": "S-5-9",
                        "SeatPosition": "5排9号",
                        "serviceFee": "1.00",
                    }
                ],
            },
        )
        self.assertIn("trace", result)
        self.assertEqual(result["trace"][-1]["step"], "build_lock_payload")
        self.assertEqual(result["trace"][-1]["request_body"], result["lock_payload"])

    def test_runner_calls_lock_endpoint_when_execute_mode_is_enabled(self):
        client = FakeClient()
        criteria = MatchCriteria(
            movie_name="Target Movie",
            start_date="2026-06-14",
            end_date="2026-06-14",
            ticket_count=1,
            expected_time="14:30",
            seat_positions=["5排9号"],
            open_id="OPEN-1",
        )

        result = DirectTicketRunner(client, now=datetime(2026, 6, 14, 12, 0, 0)).run(criteria, dry_run=False)

        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(len(client.lock_calls), 1)
        self.assertEqual(client.lock_calls[0]["SessionCode"], "P1")
        self.assertEqual(result["lock_order_no"], "LOCK-1")

    def test_runner_does_not_lock_when_requested_seat_is_blocked(self):
        client = FakeClient(blocked=True)
        criteria = MatchCriteria(
            movie_name="Target Movie",
            start_date="2026-06-14",
            end_date="2026-06-14",
            ticket_count=1,
            expected_time="14:30",
            seat_positions=["5排9号"],
            open_id="OPEN-1",
        )

        with self.assertRaises(SeatUnavailableError):
            DirectTicketRunner(client, now=datetime(2026, 6, 14, 12, 0, 0)).run(criteria, dry_run=False)

        self.assertEqual(client.lock_calls, [])

    def test_resolver_accepts_live_api_code_and_column_num_fields(self):
        seat_map = [{"Code": "LIVE-5-9", "RowNum": "5", "ColumnNum": "9", "Status": "Available"}]
        seat_status = [{"Code": "LIVE-5-9", "Status": "Available"}]

        seats = SpecifiedSeatResolver().resolve(["5排9号"], seat_map, seat_status)

        self.assertEqual(seats[0].code, "LIVE-5-9")
        self.assertEqual(seats[0].row, 5)
        self.assertEqual(seats[0].col, 9)

    def test_client_query_session_seats_flattens_nested_seats_payload(self):
        client = NestedSeatClient()

        seats = client.query_session_seats("P1")

        self.assertEqual(seats, [{"Code": "LIVE-5-9", "Status": "Available"}])

    def test_pay_by_member_card_uses_channel_order_code_for_price_and_confirm(self):
        client = FakeMemberPaymentClient()
        lock_seat_result = {
            "code": "000",
            "data": {
                "channelOrderCode": "GP26061414282490067",
                "orderCode": "26061414282490067",
                "autoUnlockDatetime": "2099-06-14 14:35:00",
                "seats": [{"seatCode": "S-5-9", "seatName": "5排9号"}],
            },
        }

        result = asyncio.run(
            client.payByMemberCard(
                lock_seat_result,
                {"cardCode": "CARD-1", "password": "PWD-1"},
                {"openId": "OPEN-1"},
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(client.price_queries, [{"orderNo": "26061414282490067", "cardCode": "CARD-1"}])
        self.assertEqual(client.confirm_calls[0]["orderNo"], "26061414282490067")
        self.assertNotEqual(client.confirm_calls[0]["orderNo"], "GP26061414282490067")
        self.assertEqual(client.confirm_calls[0]["orderPhone"], "13800000000")
        self.assertEqual(
            client.confirm_calls[0]["orders"],
            [
                {
                    "sessionCode": "SESSION-1",
                    "seatCode": "S-5-9",
                    "memberPrice": 35,
                    "serviceFee": 1,
                }
            ],
        )
        self.assertEqual(result["confirmation"]["orderNo"], "26061414282490067")
        self.assertEqual(result["confirmation"]["channelOrderCode"], "GP26061414282490067")
        self.assertEqual(result["confirmation"]["memberPrice"], 35)
        self.assertEqual(result["confirmation"]["serviceFee"], 1)
        self.assertEqual(result["confirmation"]["totalSales"], 36)

    def test_pay_by_member_card_queries_card_code_by_open_id_when_only_password_is_provided(self):
        client = FakeMemberPaymentClient()
        lock_seat_result = {
            "code": "000",
            "data": {
                "channelOrderCode": "CHANNEL-1",
                "orderCode": "26061414282490067",
                "autoUnlockDatetime": "2099-06-14 14:35:00",
                "seats": [{"seatCode": "S-5-9", "seatName": "5排9号"}],
            },
        }

        result = client.pay_by_member_card(
            lock_seat_result,
            {"password": "PWD-1"},
            {"openId": "OPEN-1"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(client.card_list_queries, ["OPEN-1"])
        self.assertEqual(client.price_queries, [{"orderNo": "26061414282490067", "cardCode": "CARD-1"}])
        self.assertEqual(client.member_queries, [{"cardCode": "CARD-1", "password": "PWD-1"}])
        self.assertEqual(client.confirm_calls[0]["cardCode"], "CARD-1")
        self.assertEqual(result["confirmation"]["cardCode"], "CARD-1")

    def test_pay_by_member_card_uses_all_price_items_checks_sum_and_saves_ticket_picture(self):
        with tempfile.TemporaryDirectory() as picture_dir:
            client = FakeMemberPaymentClient(
                balance=80,
                price_items=[
                    {
                        "sessionCode": "SESSION-1",
                        "seatCode": "S-5-9",
                        "memberPrice": 35,
                        "serviceFee": 1,
                    },
                    {
                        "sessionCode": "SESSION-1",
                        "seatCode": "S-5-10",
                        "memberPrice": 35,
                        "serviceFee": 1,
                    },
                ],
                picture_dir=picture_dir,
            )
            lock_seat_result = {
                "code": "000",
                "data": {
                    "channelOrderCode": "GP26061414282490067",
                    "orderCode": "26061414282490067",
                    "autoUnlockDatetime": "2099-06-14 14:35:00",
                    "seats": [{"seatCode": "S-5-9", "seatName": "5排9号"}, {"seatCode": "S-5-10", "seatName": "5排10号"}],
                },
            }

            result = client.pay_by_member_card(
                lock_seat_result,
                {"password": "PWD-1"},
                {"openId": "OPEN-1"},
            )

            self.assertTrue(result["success"])
            self.assertEqual(client.price_queries, [{"orderNo": "26061414282490067", "cardCode": "CARD-1"}])
            self.assertEqual(client.order_queries, ["26061414282490067"])
            self.assertEqual(
                client.confirm_calls[0]["orders"],
                [
                    {"sessionCode": "SESSION-1", "seatCode": "S-5-9", "memberPrice": 35, "serviceFee": 1},
                    {"sessionCode": "SESSION-1", "seatCode": "S-5-10", "memberPrice": 35, "serviceFee": 1},
                ],
            )
            self.assertEqual(result["confirmation"]["totalSales"], 72)
            picture_path = Path(result["ticket_picture_path"])
            self.assertTrue(picture_path.exists())
            self.assertEqual(picture_path.parent, Path(picture_dir))
            picture_text = picture_path.read_text(encoding="utf-8")
            self.assertIn("0000000000499966", picture_text)
            self.assertIn("0000000000204498", picture_text)
            self.assertIn("340259010W691pL", picture_text)

    def test_pay_by_member_card_stops_before_confirm_when_balance_is_below_price_item_sum(self):
        client = FakeMemberPaymentClient(
            balance=70,
            price_items=[
                {"sessionCode": "SESSION-1", "seatCode": "S-5-9", "memberPrice": 35, "serviceFee": 1},
                {"sessionCode": "SESSION-1", "seatCode": "S-5-10", "memberPrice": 35, "serviceFee": 1},
            ],
        )
        lock_seat_result = {
            "code": "000",
            "data": {
                "channelOrderCode": "GP26061414282490067",
                "orderCode": "26061414282490067",
                "autoUnlockDatetime": "2099-06-14 14:35:00",
                "seats": [{"seatCode": "S-5-9", "seatName": "5排9号"}, {"seatCode": "S-5-10", "seatName": "5排10号"}],
            },
        }

        result = client.pay_by_member_card(lock_seat_result, {"password": "PWD-1"}, {"openId": "OPEN-1"})

        self.assertFalse(result["success"])
        self.assertEqual(result["step"], "query_member_card_info")
        self.assertIn("72.00", result["reason"])
        self.assertEqual(client.confirm_calls, [])
        self.assertEqual(client.order_queries, [])

    def test_pay_by_member_card_stops_before_confirm_when_balance_is_insufficient(self):
        client = FakeMemberPaymentClient(balance=20)
        lock_seat_result = {
            "code": "000",
            "data": {
                "channelOrderCode": "CHANNEL-1",
                "orderCode": "CINEMA-1",
                "autoUnlockDatetime": "2099-06-14 14:35:00",
                "seats": [{"seatCode": "S-5-9", "seatName": "5排9号"}],
            },
        }

        result = client.pay_by_member_card(
            lock_seat_result,
            {"cardCode": "CARD-1", "password": "PWD-1"},
            {"openId": "OPEN-1"},
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["step"], "query_member_card_info")
        self.assertIn("balance", result["reason"])
        self.assertEqual(client.confirm_calls, [])

    def test_runner_pays_by_member_card_after_successful_lock(self):
        client = FakeClient()
        criteria = MatchCriteria(
            movie_name="Target Movie",
            start_date="2026-06-14",
            end_date="2026-06-14",
            ticket_count=1,
            expected_time="14:30",
            seat_positions=["5排9号"],
            open_id="OPEN-1",
        )

        result = DirectTicketRunner(client, now=datetime(2026, 6, 14, 12, 0, 0)).run(
            criteria,
            dry_run=False,
            member_card={"cardCode": "CARD-1", "password": "PWD-1"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(client.member_payment_calls[0]["member_card"]["cardCode"], "CARD-1")
        self.assertEqual(client.member_payment_calls[0]["user"], {"openId": "OPEN-1"})
        self.assertEqual(result["member_payment"]["confirmation"]["orderNo"], "CHANNEL-1")
        self.assertEqual([entry["step"] for entry in result["payment_trace"]], ["batch_member_card", "member_order_confirm"])
        self.assertEqual(result["trace"], result["payment_trace"])
        self.assertNotIn("query_sessions", [entry["step"] for entry in result["trace"]])


class FakeClient:
    def __init__(self, blocked=False):
        self.blocked = blocked
        self.lock_calls = []
        self.member_payment_calls = []
        self.trace = [
            {
                "step": "query_sessions",
                "method": "POST",
                "url": "https://example.test/JavaWeb2/api/net/newQuerySession",
                "request_headers": {"cinemaCode": "34025901"},
                "request_body": {"StartDate": "2026-06-14", "EndDate": "2026-06-14"},
                "response_status": 200,
                "response_body": {"code": "SUCCESS"},
                "duration_ms": 1,
            }
        ]

    def query_sessions(self, start_date: str, end_date: str):
        return [
            {
                "filmName": "Target Movie",
                "FilmCode": "F1",
                "PlanCode": "P1",
                "ScreenCode": "SCREEN-1",
                "hallName": "2号激光厅",
                "StartTime": "2026-06-14 14:30:00",
                "NetSaleStopTime": "2026-06-14 14:25:00",
                "status": "可销售",
                "channelPrice": "35.00",
                "StandardPrice": "60.00",
                "subFee": "1.00",
                "channelCode": "Cx007",
            }
        ]

    def query_seat_map(self, screen_code: str):
        return [
            {
                "SeatCode": "S-5-9",
                "SeatName": "5排9号",
                "SeatPosition": "5排9号",
                "RowNum": 5,
                "ColNum": 9,
                "Status": "available",
            }
        ]

    def query_session_seats(self, plan_code: str):
        if not self.blocked:
            return [{"SeatCode": "S-5-9", "SeatStatus": "available"}]
        return [{"SeatCode": "S-5-9", "SeatStatus": "lock"}]

    def lock_seats(self, payload: dict):
        self.lock_calls.append(payload)
        return {
            "success": True,
            "order_no": "LOCK-1",
            "expire_time": "2026-06-14 14:40:00",
            "raw": {
                "code": "000",
                "data": {
                    "channelOrderCode": "CHANNEL-1",
                    "orderCode": "CINEMA-1",
                    "autoUnlockDatetime": "2099-06-14 14:35:00",
                    "seats": [{"seatCode": "S-5-9", "seatName": "5排9号"}],
                },
            },
        }

    def pay_by_member_card(self, lock_seat_result: dict, member_card: dict, user: dict):
        self.member_payment_calls.append(
            {
                "lock_seat_result": lock_seat_result,
                "member_card": member_card,
                "user": user,
            }
        )
        self.trace.extend(
            [
                {"step": "batch_member_card", "method": "GET", "url": "https://example.test/cards"},
                {"step": "member_order_confirm", "method": "POST", "url": "https://example.test/pay"},
            ]
        )
        return {
            "success": True,
            "confirmation": {
                "orderNo": "CHANNEL-1",
                "seat": {"seatCode": "S-5-9", "seatName": "5排9号"},
                "memberPrice": 35,
                "serviceFee": 1,
                "totalSales": 36,
            },
            "raw_confirm_result": {"code": "000"},
        }


class FakeMemberPaymentClient(CinemaApiClient):
    def __init__(self, balance=100, price_items=None, picture_dir=None):
        super().__init__("https://example.invalid")
        self.balance = balance
        self.price_items = price_items or [
            {
                "sessionCode": "SESSION-1",
                "seatCode": "S-5-9",
                "memberPrice": 35,
                "serviceFee": 1,
            }
        ]
        if picture_dir:
            self.ticket_picture_dir = Path(picture_dir)
        self.price_queries = []
        self.member_queries = []
        self.confirm_calls = []
        self.card_list_queries = []
        self.order_queries = []

    def query_member_cards(self, open_id: str):
        self.card_list_queries.append(open_id)
        return {
            "msg": "操作成功",
            "code": "000",
            "data": [
                {
                    "cardCode": "CARD-1",
                    "balance": str(self.balance),
                    "memberPhone": "13800000000",
                    "openId": open_id,
                }
            ],
        }

    def query_member_price_by_order_no(self, order_no: str, card_code: str):
        self.price_queries.append({"orderNo": order_no, "cardCode": card_code})
        return {
            "code": "000",
            "data": {
                "totalSales": sum(float(item["memberPrice"]) + float(item["serviceFee"]) for item in self.price_items),
                "data": list(self.price_items),
            },
        }

    def query_member_card_info(self, card_code: str, password: str):
        self.member_queries.append({"cardCode": card_code, "password": password})
        return {
            "code": "000",
            "data": {
                "memberPhone": "13800000000",
                "balance": self.balance,
            },
        }

    def member_order_confirm(self, payload: dict):
        self.confirm_calls.append(payload)
        return {"code": "000", "data": {"payStatus": "success"}}

    def query_order(self, order_code: str):
        self.order_queries.append(order_code)
        return {
            "msg": "查询订单信息成功",
            "code": "SUCCESS",
            "data": {
                "films": [{"name": "给阿嬷的情书"}],
                "seats": [{"seatCode": "S-5-9", "filmTicketCode": "340259010W691pL", "rowNum": "7", "columnNum": "10"}],
                "orderCode": order_code,
                "printNo": "0000000000499966",
                "verifyCode": "0000000000204498",
                "cinemaName": "上影国际影城正嘉广场店",
                "screenName": "6号激光巨幕厅",
                "startTime": "2026-06-14T21:30:00",
            },
        }


class NestedSeatClient(CinemaApiClient):
    def __init__(self):
        super().__init__("https://example.invalid")

    def _request_json(self, method: str, path: str, body=None, headers=None, step=None):
        return {"data": [{"PlanCode": "P1", "Seats": [{"Code": "LIVE-5-9", "Status": "Available"}]}]}


if __name__ == "__main__":
    unittest.main()
