"""Direct cinema API session matching and specified-seat locking."""

from __future__ import annotations

import json
import re
import time as perf_time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time
from html import escape as xml_escape
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKET_PICTURE_DIR = PROJECT_ROOT / "picture"
# 默认微信小程序 UA，请求影院接口时需要模拟小程序环境
DEFAULT_WECHAT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf2541a1f) XWEB/19921"
)
# 影院接口公共请求头，后续锁座、查价、会员支付都复用
DEFAULT_CINEMA_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "xweb_xhr": "1",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://servicewechat.com/wx52420337e5796bd6/15/page-frame.html",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "User-Agent": DEFAULT_WECHAT_USER_AGENT,
}


AVAILABLE_WORDS = ("可销售", "可售", "可用", "available", "AVAILABLE", "0")
BLOCKED_WORDS = ("已售", "售出", "已锁", "锁定", "不可售", "disabled", "sold", "lock", "LOCK", "1", "2")


@dataclass(frozen=True)
class ResolvedSeat:
    code: str
    position: str
    row: int | None = None
    col: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchCriteria:
    # 用户下单时的匹配条件：影片、日期、座位、openId、影厅偏好等
    movie_name: str
    start_date: str
    end_date: str
    ticket_count: int
    seat_positions: list[str]
    open_id: str
    time_start: str | None = None
    time_end: str | None = None
    expected_time: str | None = None
    hall_keywords: list[str] = field(default_factory=list)
    language_keywords: list[str] = field(default_factory=list)
    show_type_keywords: list[str] = field(default_factory=list)
    price_limit: float | None = None
    cinema_code: str = ""
    distributor_id: str = ""


class DirectTicketingError(RuntimeError):
    """Base error for direct ticketing failures."""


class SeatUnavailableError(DirectTicketingError):
    """Raised when a requested seat cannot be locked."""


def _first_value(data: dict[str, Any], names: tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        if name in data and data[name] not in (None, ""):
            return data[name]
    lower = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        value = lower.get(name.lower())
        if value not in (None, ""):
            return value
    return default


def _extract_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "Data", "rows", "Rows", "result", "Result", "list", "List"):
        value = payload.get(key)
        nested = _extract_list(value)
        if nested:
            return nested

    collected: list[dict[str, Any]] = []
    for value in payload.values():
        if isinstance(value, list):
            collected.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            collected.extend(_extract_list(value))
    return collected


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    return None


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else default


def _money(value: Any, default: str = "0.00") -> str:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            return f"{float(match.group()):.2f}"
        return default
    return f"{float(value):.2f}"


def _api_success(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    code = _first_value(response, ("code", "Code", "status", "Status"), None)
    if code is not None:
        return str(code).lower() in ("000", "0", "200", "success", "true", "ok")
    success = _first_value(response, ("success", "Success", "isSuccess", "IsSuccess"), None)
    if success is not None:
        return success is True or str(success).lower() in ("true", "success", "ok", "1")
    return True


def _contains_any(text: Any, keywords: list[str]) -> bool:
    if not keywords:
        return True
    source = str(text or "").lower()
    return any(keyword.lower() in source for keyword in keywords if keyword)


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _normalize_position(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    match = re.search(r"0*(\d+)排0*(\d+)号", text)
    if match:
        return f"{int(match.group(1))}排{int(match.group(2))}号"
    return text


def _row_col_position(row: Any, col: Any) -> str:
    if row in (None, "") or col in (None, ""):
        return ""
    return f"{int(float(row))}排{int(float(col))}号"


def criteria_from_order(order: dict[str, Any]) -> MatchCriteria:
    """Build match criteria from order aliases."""
    time_range = _first_value(order, ("timeRange", "time_range"), None)
    time_start = _first_value(order, ("time_start", "timeStart"), None)
    time_end = _first_value(order, ("time_end", "timeEnd"), None)
    if isinstance(time_range, list) and len(time_range) >= 2:
        time_start = str(time_range[0])
        time_end = str(time_range[1])

    start_date = str(_first_value(order, ("start_date", "startDate", "date", "show_date"), ""))
    end_date = str(_first_value(order, ("end_date", "endDate"), start_date))
    seat_positions = _as_list(_first_value(order, ("seat_positions", "seatPositions", "seats", "SeatPosition", "seat"), []))
    open_id = str(_first_value(order, ("openId", "open_id", "openid"), ""))
    ticket_count = int(_first_value(order, ("ticket_count", "ticketCount", "tickets", "count", "Count"), len(seat_positions) or 1))

    if not seat_positions:
        raise DirectTicketingError("order must include specified seat_positions, for example ['5排9号']")
    if ticket_count != len(seat_positions):
        raise DirectTicketingError("ticket_count must equal the number of specified seat_positions")
    if not open_id:
        raise DirectTicketingError("order must include openId")

    cinema_code = str(_first_value(order, ("cinema_code", "cinemaCode"), "")).strip()
    if not cinema_code:
        raise DirectTicketingError("order must include cinemaCode")

    return MatchCriteria(
        movie_name=str(_first_value(order, ("movie_name", "movieName", "filmName", "film_name"), "")),
        start_date=start_date,
        end_date=end_date,
        ticket_count=ticket_count,
        seat_positions=seat_positions,
        open_id=open_id,
        time_start=str(time_start) if time_start else None,
        time_end=str(time_end) if time_end else None,
        expected_time=str(_first_value(order, ("expected_time", "expectedTime", "show_time", "showTime"), "")) or None,
        hall_keywords=_as_list(_first_value(order, ("hall_keywords", "hallKeywords", "hallPreference", "hall_preference"), [])),
        language_keywords=_as_list(_first_value(order, ("language_keywords", "languageKeywords", "language"), [])),
        show_type_keywords=_as_list(_first_value(order, ("show_type_keywords", "showTypeKeywords", "showType", "movie_format"), [])),
        price_limit=_to_float(_first_value(order, ("price_limit", "priceLimit", "priceMax", "max_price"), None), 0)
        if _first_value(order, ("price_limit", "priceLimit", "priceMax", "max_price"), None) is not None
        else None,
        cinema_code=cinema_code,
        distributor_id=str(_first_value(order, ("distributorId", "distributor_id"), "")),
    )


class SessionMatcher:
    # 根据用户条件筛选和排序可用场次
    def __init__(self, criteria: MatchCriteria, now: datetime | None = None):
        self.criteria = criteria
        self.now = now or datetime.now()

    def match(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = [session for session in sessions if self._is_candidate(session)]
        return sorted(filtered, key=self._sort_key)

    def _is_candidate(self, session: dict[str, Any]) -> bool:
        film_name = str(_first_value(session, ("filmName", "FilmName", "movieName"), ""))
        if self.criteria.movie_name and self.criteria.movie_name.lower() not in film_name.lower():
            return False

        status = str(_first_value(session, ("status", "Status"), ""))
        if status and any(word in status for word in ("不可售", "停售", "stopped", "disabled")):
            return False

        start_time = _parse_datetime(_first_value(session, ("StartTime", "startTime")))
        if not start_time:
            return False

        start_date = _parse_date(self.criteria.start_date)
        end_date = _parse_date(self.criteria.end_date)
        if start_date and start_time.date() < start_date:
            return False
        if end_date and start_time.date() > end_date:
            return False

        stop_time = _parse_datetime(_first_value(session, ("NetSaleStopTime", "netSaleStopTime")))
        if stop_time and self.now >= stop_time:
            return False

        start_limit = _parse_time(self.criteria.time_start)
        end_limit = _parse_time(self.criteria.time_end)
        expected = _parse_time(self.criteria.expected_time)
        if expected and (start_time.hour, start_time.minute) != (expected.hour, expected.minute):
            return False
        if start_limit and start_time.time() < start_limit:
            return False
        if end_limit and start_time.time() > end_limit:
            return False

        price = _to_float(_first_value(session, ("channelPrice", "WxPayPrice", "LowestPrice", "price", "Price")), 0)
        if self.criteria.price_limit is not None and price > self.criteria.price_limit:
            return False

        if not _contains_any(_first_value(session, ("Language", "language"), ""), self.criteria.language_keywords):
            return False
        if not _contains_any(_first_value(session, ("ShowType", "showType"), ""), self.criteria.show_type_keywords):
            return False
        return True

    def _sort_key(self, session: dict[str, Any]) -> tuple[float, float, float, str]:
        hall = str(_first_value(session, ("hallName", "HallName", "hall"), ""))
        hall_score = 0 if any(keyword.lower() in hall.lower() for keyword in self.criteria.hall_keywords) else 1

        start_time = _parse_datetime(_first_value(session, ("StartTime", "startTime"))) or self.now
        expected = _parse_time(self.criteria.expected_time)
        if expected:
            expected_dt = start_time.replace(hour=expected.hour, minute=expected.minute, second=expected.second, microsecond=0)
            time_score = abs((start_time - expected_dt).total_seconds()) / 60
        else:
            time_score = start_time.timestamp()

        price = _to_float(_first_value(session, ("channelPrice", "WxPayPrice", "LowestPrice", "price", "Price")), 0)
        return (hall_score, time_score, price, str(_first_value(session, ("PlanCode", "planCode"), "")))


class SpecifiedSeatResolver:
    # 根据用户指定的“几排几号”，从座位图中找到真实 seatCode 
    #  并结合座位状态判断该座位是否可锁
    def resolve(
        self,
        requested_positions: list[str],
        seat_map: list[dict[str, Any]],
        seat_status: list[dict[str, Any]],
    ) -> list[ResolvedSeat]:
        seats_by_position = self._index_seats(seat_map)
        status_by_code = {
            str(_first_value(item, ("SeatCode", "seatCode", "Code", "code", "SeatNo"), "")): str(
                _first_value(item, ("SeatStatus", "seatStatus", "Status", "status"), "")
            )
            for item in seat_status
            if _first_value(item, ("SeatCode", "seatCode", "Code", "code", "SeatNo"), "")
        }

        resolved: list[ResolvedSeat] = []
        for requested in requested_positions:
            key = _normalize_position(requested)
            seat = seats_by_position.get(key)
            if not seat:
                raise SeatUnavailableError(f"requested seat not found: {requested}")
            status = " ".join(
                part
                for part in (
                    str(_first_value(seat.raw, ("Status", "status", "SeatStatus", "seatStatus"), "")),
                    status_by_code.get(seat.code, ""),
                )
                if part
            )
            if self._is_blocked(status):
                raise SeatUnavailableError(f"requested seat is not available: {requested}")
            resolved.append(ResolvedSeat(code=seat.code, position=str(requested), row=seat.row, col=seat.col, raw=seat.raw))
        return resolved

    def _index_seats(self, seat_map: list[dict[str, Any]]) -> dict[str, ResolvedSeat]:
        indexed: dict[str, ResolvedSeat] = {}
        for item in seat_map:
            code = str(_first_value(item, ("SeatCode", "seatCode", "Code", "code", "SeatNo"), ""))
            row = _first_value(item, ("RowNum", "rowNum", "RowNo", "row", "GraphRow"))
            col = _first_value(item, ("ColNum", "colNum", "ColumnNum", "columnNum", "ColumnNo", "col", "GraphCol"))
            positions = [
                _first_value(item, ("SeatPosition", "seatPosition", "SeatName", "seatName", "name", "SeatNo"), ""),
                _row_col_position(row, col),
            ]
            if not code:
                continue
            resolved = ResolvedSeat(
                code=code,
                position=_normalize_position(positions[0] or positions[1]),
                row=int(float(row)) if row not in (None, "") else None,
                col=int(float(col)) if col not in (None, "") else None,
                raw=item,
            )
            for position in positions:
                normalized = _normalize_position(position)
                if normalized:
                    indexed[normalized] = resolved
        return indexed

    def _is_blocked(self, status: str) -> bool:
        text = str(status or "").strip()
        if not text:
            return False
        lowered = text.lower()
        blocked_words = [word.lower() for word in BLOCKED_WORDS]
        available_words = [word.lower() for word in AVAILABLE_WORDS]
        if any(word in lowered for word in blocked_words):
            return True
        return not any(word in lowered for word in available_words)


class CinemaApiClient:
    def __init__(
        self,
        base_url: str,
        cinema_code: str,
        headers: dict[str, str] | None = None,
        timeout: int = 20,
        lock_path: str = "/JavaWeb2/api/order/v1/lockSeat",
        ticket_picture_dir: Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.cinema_code = cinema_code
        self.headers = {**DEFAULT_CINEMA_HEADERS, **(headers or {})}
        self.timeout = timeout
        self.lock_path = lock_path
        self.ticket_picture_dir = Path(ticket_picture_dir) if ticket_picture_dir is not None else DEFAULT_TICKET_PICTURE_DIR
        self.trace: list[dict[str, Any]] = []
# 查询指定日期范围内的电影场次
    def query_sessions(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        payload = self._request_json(
            "POST",
            "/JavaWeb2/api/net/newQuerySession",
            body={"StartDate": start_date, "EndDate": end_date},
            headers={"cinemaCode": self.cinema_code},
            step="query_sessions",
        )
        return _extract_list(payload)
# 查询某个场次下每个座位的实时状态，例如可售、已售、已锁
    def query_session_seats(self, plan_code: str) -> list[dict[str, Any]]:
        path = f"/JavaWeb2/api/net/QuerySessionSeat?PlanCode={urllib.parse.quote(plan_code)}"
        items = _extract_list(self._request_json("GET", path, headers={"cinemaCode": self.cinema_code}, step="query_session_seats"))
        if len(items) == 1 and isinstance(items[0].get("Seats"), list):
            return [seat for seat in items[0]["Seats"] if isinstance(seat, dict)]
        return items
# 查询影厅座位图，用于把“7排11号”解析成真实 seatCode
    def query_seat_map(self, screen_code: str) -> list[dict[str, Any]]:
        path = f"/JavaWeb2/api/net/QuerySeat?ScreenCode={urllib.parse.quote(screen_code)}"
        return _extract_list(self._request_json("GET", path, headers={"cinemaCode": self.cinema_code}, step="query_seat_map"))
# 调用锁座接口，成功后会返回 orderCode、channelOrderCode、座位信息和自动解锁时间
    def lock_seats(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request_json("POST", self.lock_path, body=payload, headers={"cinemaCode": self.cinema_code}, step="lock_seats")
        return self._normalize_lock_response(response)

    # 会员价接口的参数名叫 orderNo，实际要传锁座返回的 channelOrderCode。
    def query_member_price_by_order_no(self, order_no: str, card_code: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"orderNo": order_no, "cardCode": card_code})
        return self._request_json(
            "GET",
            f"/JavaWeb2/api/order/v1/queryPriceByOderNo?{query}",
            headers={"cinemaCode": self.cinema_code},
            step="query_member_price",
        )

    # 用 openId 查询绑定的会员卡号，页面不再让用户手填 cardCode。
    def query_member_cards(self, open_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"openId": open_id})
        return self._request_json(
            "GET",
            f"/JavaWeb2/api/member/v1/batchMemberCard?{query}",
            headers={"cinemaCode": self.cinema_code},
            step="batch_member_card",
        )

    # 这里只做会员卡验密和余额查询，不代表已经完成支付。
    def query_member_card_info(self, card_code: str, password: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/JavaWeb2/api/member/v1/queryMemberCardInfo",
            body={"cardCode": card_code, "password": password},
            headers={"cinemaCode": self.cinema_code},
            step="query_member_card_info",
        )

    # 真正扣款支付接口，必须在查价和验卡成功之后调用。
    def member_order_confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/JavaWeb2/api/order/v1/memberOrderConfirm",
            body=payload,
            headers={"cinemaCode": self.cinema_code},
            step="member_order_confirm",
        )

    # 支付成功后用数字 orderCode 查询出票信息、取票号和验证码。
    def query_order(self, order_code: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"orderCode": order_code})
        return self._request_json(
            "GET",
            f"/JavaWeb2/api/order/v1/queryOrder?{query}",
            headers={"cinemaCode": self.cinema_code},
            step="query_order",
        )

    async def payByMemberCard(self, lockSeatResult: dict[str, Any], memberCard: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        return self.pay_by_member_card(lockSeatResult, memberCard, user)

    def pay_by_member_card(self, lock_seat_result: dict[str, Any], member_card: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        member_card = member_card or {}
        user = user or {}
        lock_data = self._extract_lock_data(lock_seat_result)
        # channelOrderCode 是支付链路使用的 orderNo；orderCode 是支付成功后查出票用的数字订单号。
        payment_order_no = str(lock_data.get("channelOrderCode") or "")
        ticket_order_code = str(lock_data.get("orderCode") or "")
        seats = lock_data.get("seats") if isinstance(lock_data.get("seats"), list) else []
        seat = seats[0] if seats else None
        card_code = str(member_card.get("cardCode") or "")
        password = str(member_card.get("password") or "")
        open_id = str(user.get("openId") or "")

        if not payment_order_no:
            return self._member_payment_failure("lock_seat_result", "missing channelOrderCode in lock response", lock_seat_result)
        if not seat:
            return self._member_payment_failure("lock_seat_result", "missing seats in lock response", lock_seat_result)
        if not password or not open_id:
            return self._member_payment_failure("member_payment_input", "password and openId are required", None)
        if self._lock_expired(lock_data):
            return self._member_payment_failure("lock_seat_result", "autoUnlockDatetime has expired before member payment", lock_seat_result)

        card_list_result = None
        if not card_code:
            # 配置里只保存 openId 和密码，cardCode 每次从会员卡列表接口取。
            try:
                card_list_result = self.query_member_cards(open_id)
            except DirectTicketingError as exc:
                return self._member_payment_failure("batch_member_card", str(exc), None)
            card_code = self._first_member_card_code(card_list_result)
            if not card_code:
                return self._member_payment_failure("batch_member_card", self._response_reason(card_list_result), card_list_result)

        try:
            price_result = self.query_member_price_by_order_no(payment_order_no, card_code)
        except DirectTicketingError as exc:
            return self._member_payment_failure("query_member_price", str(exc), None)
        price_payload = price_result.get("data") if isinstance(price_result, dict) else None
        price_items = price_payload.get("data") if isinstance(price_payload, dict) else None
        if not _api_success(price_result) or not isinstance(price_items, list) or not price_items:
            return self._member_payment_failure("query_member_price", self._response_reason(price_result), price_result)
        # memberOrderConfirm.orders 完全复用查价接口返回项，避免自己拼错座位或价格。
        orders = [
            {
                "sessionCode": price_item.get("sessionCode"),
                "seatCode": price_item.get("seatCode"),
                "memberPrice": price_item.get("memberPrice"),
                "serviceFee": price_item.get("serviceFee"),
            }
            for price_item in price_items
        ]
        # 多座位时余额要按所有座位的会员价和服务费合计校验。
        total_sales = sum(_to_float(item.get("memberPrice"), 0) + _to_float(item.get("serviceFee"), 0) for item in price_items)
        confirmation = {
            "orderNo": payment_order_no,
            "orderCode": ticket_order_code,
            "channelOrderCode": payment_order_no,
            "cardCode": card_code,
            "seat": seat,
            "memberPrice": price_items[0].get("memberPrice"),
            "serviceFee": price_items[0].get("serviceFee"),
            "totalSales": total_sales,
            "orders": orders,
        }

        try:
            member_result = self.query_member_card_info(card_code, password)
        except DirectTicketingError as exc:
            return self._member_payment_failure("query_member_card_info", str(exc), None, confirmation)
        if not isinstance(member_result, dict) or member_result.get("code") != "000":
            return self._member_payment_failure("query_member_card_info", self._response_reason(member_result), member_result, confirmation)
        member_data = member_result.get("data") if isinstance(member_result.get("data"), dict) else {}
        order_phone = member_data.get("memberPhone")
        balance = _to_float(member_data.get("balance"), 0)
        if balance < total_sales:
            return self._member_payment_failure(
                "query_member_card_info",
                f"member card balance {balance:.2f} is less than totalSales {total_sales:.2f}",
                member_result,
                confirmation,
            )
        if self._lock_expired(lock_data):
            return self._member_payment_failure("member_order_confirm", "autoUnlockDatetime has expired before confirm payment", lock_seat_result, confirmation)

        # 到这里才发起真实支付；queryMemberCardInfo 只是前置校验。
        confirm_payload = {
            "openId": open_id,
            "orderNo": payment_order_no,
            "password": password,
            "orderPhone": order_phone,
            "cardCode": card_code,
            "orders": orders,
        }
        try:
            confirm_result = self.member_order_confirm(confirm_payload)
        except DirectTicketingError as exc:
            return self._member_payment_failure("member_order_confirm", str(exc), None, confirmation)
        if not _api_success(confirm_result):
            return self._member_payment_failure("member_order_confirm", self._response_reason(confirm_result), confirm_result, confirmation)
        if not ticket_order_code:
            return self._member_payment_failure("query_order", "missing orderCode in lock response", lock_seat_result, confirmation)
        try:
            # 支付后立即查出票信息，并将取票码保存为本地 SVG 图片。
            order_result = self.query_order(ticket_order_code)
        except DirectTicketingError as exc:
            return self._member_payment_failure("query_order", str(exc), None, confirmation)
        if not _api_success(order_result):
            return self._member_payment_failure("query_order", self._response_reason(order_result), order_result, confirmation)
        ticket_picture_path = self.save_ticket_picture(order_result)
        return {
            "success": True,
            "confirmation": confirmation,
            "raw_card_list_result": card_list_result,
            "raw_price_result": price_result,
            "raw_member_result": member_result,
            "raw_confirm_result": confirm_result,
            "raw_order_result": order_result,
            "ticket_picture_path": ticket_picture_path,
        }

    def _first_member_card_code(self, response: Any) -> str:
        if not _api_success(response) or not isinstance(response, dict):
            return ""
        cards = response.get("data")
        if not isinstance(cards, list):
            return ""
        for card in cards:
            if isinstance(card, dict) and card.get("cardCode"):
                return str(card["cardCode"])
        return ""

    def save_ticket_picture(self, order_result: dict[str, Any]) -> str:
        data = order_result.get("data") if isinstance(order_result.get("data"), dict) else {}
        order_code = str(data.get("orderCode") or "ticket")
        safe_order_code = re.sub(r"[^A-Za-z0-9_-]+", "_", order_code).strip("_") or "ticket"
        output_dir = Path(getattr(self, "ticket_picture_dir", DEFAULT_TICKET_PICTURE_DIR))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"ticket_{safe_order_code}.svg"
        # SVG 是图片文件，浏览器可直接打开；避免为取票码图片额外引入图像库。
        path.write_text(self._ticket_svg(data), encoding="utf-8")
        return str(path)

    def _ticket_svg(self, data: dict[str, Any]) -> str:
        film = {}
        films = data.get("films")
        if isinstance(films, list) and films and isinstance(films[0], dict):
            film = films[0]
        seats = data.get("seats") if isinstance(data.get("seats"), list) else []
        ticket_codes = [
            str(seat.get("filmTicketCode"))
            for seat in seats
            if isinstance(seat, dict) and seat.get("filmTicketCode")
        ]
        seat_text = " / ".join(
            f"{seat.get('rowNum', '')}排{seat.get('columnNum', '')}座"
            for seat in seats
            if isinstance(seat, dict)
        )
        fields = [
            ("影片", film.get("name", "")),
            ("影院", data.get("cinemaName", "")),
            ("影厅", data.get("screenName", "")),
            ("场次", data.get("startTime", "")),
            ("座位", seat_text),
            ("订单号", data.get("orderCode", "")),
            ("取票号", data.get("printNo", "")),
            ("验证码", data.get("verifyCode", "")),
            ("票码", " / ".join(ticket_codes)),
        ]
        rows = []
        y = 72
        for label, value in fields:
            rows.append(
                f'<text x="40" y="{y}" font-size="24" fill="#334155">{xml_escape(str(label))}: '
                f'<tspan font-weight="700" fill="#0f172a">{xml_escape(str(value))}</tspan></text>'
            )
            y += 42
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">'
            '<rect width="900" height="520" rx="24" fill="#f8fafc"/>'
            '<rect x="24" y="24" width="852" height="472" rx="18" fill="#ffffff" stroke="#cbd5e1"/>'
            '<text x="40" y="46" font-size="28" font-weight="700" fill="#0f766e">电影票取票信息</text>'
            + "".join(rows)
            + '<rect x="616" y="314" width="220" height="118" rx="10" fill="#ecfeff" stroke="#67e8f9"/>'
            '<text x="640" y="360" font-size="22" fill="#155e75">请凭取票号和验证码</text>'
            '<text x="682" y="398" font-size="22" fill="#155e75">到影院取票</text>'
            "</svg>"
        )

    def _extract_lock_data(self, lock_seat_result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(lock_seat_result, dict):
            return {}
        data = lock_seat_result.get("data")
        if isinstance(data, dict):
            return data
        raw = lock_seat_result.get("raw")
        if isinstance(raw, dict):
            return self._extract_lock_data(raw)
        return lock_seat_result

    def _lock_expired(self, lock_data: dict[str, Any]) -> bool:
        auto_unlock = _parse_datetime(lock_data.get("autoUnlockDatetime"))
        return bool(auto_unlock and datetime.now() >= auto_unlock)

    def _member_payment_failure(
        self,
        step: str,
        reason: str,
        raw_result: Any,
        confirmation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "success": False,
            "step": step,
            "reason": reason,
            "raw_result": raw_result,
        }
        if confirmation is not None:
            result["confirmation"] = confirmation
        return result

    def _response_reason(self, response: Any) -> str:
        if not isinstance(response, dict):
            return f"unexpected response: {response!r}"
        return str(_first_value(response, ("message", "Message", "msg", "Msg", "reason"), "interface returned failure"))

    def _normalize_lock_response(self, response: Any) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {"success": False, "reason": f"lock response is not a JSON object: {response!r}", "raw": response}
        success_value = _first_value(response, ("success", "Success", "isSuccess", "IsSuccess", "status", "Status", "code", "Code"))
        success = success_value is True or str(success_value).lower() in ("true", "success", "ok", "000", "0", "200")
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        return {
            "success": success,
            "order_no": _first_value(data, ("channelOrderCode", "orderNo", "OrderNo", "lockOrderNo", "LockOrderNo", "order_no"))
            or _first_value(response, ("orderNo", "OrderNo", "lockOrderNo", "LockOrderNo", "order_no")),
            "expire_time": _first_value(data, ("autoUnlockDatetime", "expireTime", "ExpireTime", "lockExpireTime", "LockExpireTime"))
            or _first_value(response, ("expireTime", "ExpireTime", "lockExpireTime", "LockExpireTime")),
            "reason": _first_value(response, ("message", "Message", "msg", "Msg", "reason"), ""),
            "raw": response,
        }

    def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        step: str | None = None,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        request_headers = {"Accept": "application/json", **self.headers, **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        trace_entry: dict[str, Any] = {
            "step": step or path,
            "method": method,
            "url": url,
            "request_headers": dict(request_headers),
            "request_body": body,
            "response_status": None,
            "response_headers": {},
            "response_body_raw": None,
            "response_body": None,
            "duration_ms": None,
            "error": None,
        }
        started = perf_time.perf_counter()
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                trace_entry["response_status"] = response.status
                trace_entry["response_headers"] = dict(response.headers.items())
                trace_entry["response_body_raw"] = raw
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            trace_entry["response_status"] = exc.code
            trace_entry["response_headers"] = dict(exc.headers.items()) if exc.headers else {}
            trace_entry["response_body_raw"] = detail
            trace_entry["error"] = f"HTTP {exc.code} {url}: {detail}"
            trace_entry["duration_ms"] = round((perf_time.perf_counter() - started) * 1000, 2)
            self.trace.append(trace_entry)
            raise DirectTicketingError(f"HTTP {exc.code} {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            trace_entry["error"] = f"request failed {url}: {exc}"
            trace_entry["duration_ms"] = round((perf_time.perf_counter() - started) * 1000, 2)
            self.trace.append(trace_entry)
            raise DirectTicketingError(f"request failed {url}: {exc}") from exc
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            trace_entry["error"] = f"invalid JSON response: {exc}"
            trace_entry["duration_ms"] = round((perf_time.perf_counter() - started) * 1000, 2)
            self.trace.append(trace_entry)
            raise DirectTicketingError(f"invalid JSON response {url}: {exc}") from exc
        trace_entry["response_body"] = parsed
        trace_entry["duration_ms"] = round((perf_time.perf_counter() - started) * 1000, 2)
        self.trace.append(trace_entry)
        return parsed


class DirectTicketRunner:
    def __init__(self, client: Any, now: datetime | None = None):
        self.client = client
        self.now = now or datetime.now()
# 主运行流程： # 1. 查询场次 # 2. 匹配符合条件的场次 # 3. 查询座位图和座位状态 # 4. 解析指定座位 # 5. 构造锁座参数 # 6. 非 dry_run 时调用锁座 # 7. 如果传了 member_card，则继续执行会员卡支付
    def run(self, criteria: MatchCriteria, dry_run: bool = True, member_card: dict[str, Any] | None = None) -> dict[str, Any]:
        query_start_date, query_end_date = self._validate_criteria_dates(criteria)
        sessions = self.client.query_sessions(query_start_date, query_end_date)
        candidates = SessionMatcher(criteria, now=self.now).match(sessions)
        attempted_sessions = [self._session_summary(session) for session in candidates]

        for session in candidates:
            plan_code = str(_first_value(session, ("PlanCode", "planCode"), ""))
            screen_code = str(_first_value(session, ("ScreenCode", "screenCode"), ""))
            seat_map = self.client.query_seat_map(screen_code)
            seat_status = self.client.query_session_seats(plan_code)
            seats = SpecifiedSeatResolver().resolve(criteria.seat_positions, seat_map, seat_status)
            payload = self.build_lock_payload(criteria, session, seats)
            self._append_trace(
                {
                    "step": "build_lock_payload",
                    "method": "LOCAL",
                    "url": "lockSeat payload builder",
                    "request_headers": {},
                    "request_body": payload,
                    "response_status": None,
                    "response_headers": {},
                    "response_body_raw": None,
                    "response_body": payload,
                    "duration_ms": 0,
                    "error": None,
                }
            )
# dry_run 只构造参数和模拟结果，不真正锁座、不支付
            if dry_run:
                return self._success_result(session, seats, payload, {"order_no": "DRY-RUN", "expire_time": None, "raw": None}, True)

            lock_result = self.client.lock_seats(payload)
            # 锁座成功后，如果提供了会员卡信息，则继续走会员支付
            if lock_result.get("success"):
                result = self._success_result(session, seats, payload, lock_result, False)
                if member_card:
                    payment_trace_start = len(self._trace())
                    payment_result = self.client.pay_by_member_card(lock_result.get("raw") or lock_result, member_card, {"openId": criteria.open_id})
                    payment_trace = self._trace()[payment_trace_start:]
                    result["member_payment"] = payment_result
                    result["payment_trace"] = payment_trace
                    result["trace"] = payment_trace
                    if not payment_result.get("success"):
                        result["success"] = False
                        result["reason"] = payment_result.get("reason", "member card payment failed")
                return result

        return {
            "success": False,
            "reason": "no matching session with the requested seats could be locked",
            "attempted_sessions": attempted_sessions,
            "trace": self._trace(),
        }
# 根据场次和座位生成锁座接口 body # SeatCode 来自座位图解析结果 # SessionCode 使用场次 PlanCode # openId 使用用户传入的 openId
    def build_lock_payload(self, criteria: MatchCriteria, session: dict[str, Any], seats: list[ResolvedSeat]) -> dict[str, Any]:
        return {
            "Count": len(seats),
            "SessionCode": _first_value(session, ("PlanCode", "planCode")),
            "openId": criteria.open_id,
            "distributorId": criteria.distributor_id,
            "Seat": [
                {
                    "PayPrice": _money(_first_value(session, ("channelPrice", "WxPayPrice", "LowestPrice", "PayPrice"), "0.00")),
                    "Price": _money(_first_value(session, ("StandardPrice", "standardPrice", "Price"), "0.00")),
                    "SeatCode": seat.code,
                    "SeatPosition": seat.position,
                    "serviceFee": _money(_first_value(session, ("subFee", "serviceFee", "ServiceFee"), "0.00")),
                }
                for seat in seats
            ],
        }

    def _success_result(
        self,
        session: dict[str, Any],
        seats: list[ResolvedSeat],
        payload: dict[str, Any],
        lock_result: dict[str, Any],
        dry_run: bool,
    ) -> dict[str, Any]:
        result = {
            "success": True,
            "dry_run": dry_run,
            "movie_name": _first_value(session, ("filmName", "FilmName", "movieName")),
            "hall_name": _first_value(session, ("hallName", "HallName", "hall")),
            "plan_code": _first_value(session, ("PlanCode", "planCode")),
            "screen_code": _first_value(session, ("ScreenCode", "screenCode")),
            "start_time": _first_value(session, ("StartTime", "startTime")),
            "seats": [{"code": seat.code, "position": seat.position, "row": seat.row, "col": seat.col} for seat in seats],
            "lock_payload": payload,
            "lock_order_no": lock_result.get("order_no"),
            "lock_expire_time": lock_result.get("expire_time"),
            "raw_lock_result": lock_result.get("raw"),
        }
        result["trace"] = self._trace()
        return result

    def _session_summary(self, session: dict[str, Any]) -> dict[str, Any]:
        return {
            "film_name": _first_value(session, ("filmName", "FilmName", "movieName")),
            "plan_code": _first_value(session, ("PlanCode", "planCode")),
            "screen_code": _first_value(session, ("ScreenCode", "screenCode")),
            "hall_name": _first_value(session, ("hallName", "HallName", "hall")),
            "start_time": _first_value(session, ("StartTime", "startTime")),
            "price": _first_value(session, ("channelPrice", "WxPayPrice", "LowestPrice", "price", "Price")),
        }

    def _validate_criteria_dates(self, criteria: MatchCriteria) -> tuple[str, str]:
        start_date = _parse_date(criteria.start_date)
        end_date = _parse_date(criteria.end_date)
        if not start_date:
            raise DirectTicketingError(f"invalid start_date: {criteria.start_date}")
        if not end_date:
            raise DirectTicketingError(f"invalid end_date: {criteria.end_date}")
        if start_date > end_date:
            raise DirectTicketingError(f"start_date {criteria.start_date} is after end_date {criteria.end_date}")
        return start_date.isoformat(), end_date.isoformat()

    def _trace(self) -> list[dict[str, Any]]:
        return list(getattr(self.client, "trace", []))

    def _append_trace(self, entry: dict[str, Any]) -> None:
        trace = getattr(self.client, "trace", None)
        if isinstance(trace, list):
            trace.append(entry)
