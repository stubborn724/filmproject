"""Command line entry for direct specified-seat movie ticket locking."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.direct_ticketing import CinemaApiClient, DirectTicketRunner, criteria_from_order


def load_json_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def parse_order_text(text: str) -> dict[str, Any]:
    """Parse simple pasted order text.

    JSON is preferred. This parser supports the common fields needed for the
    specified-seat workflow.
    """
    order: dict[str, Any] = {}
    patterns = {
        "movie_name": r"(?:电影名|影片|电影|movie)\s*[:：]\s*(.+)",
        "date": r"(?:日期|观影日期|date)\s*[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        "ticket_count": r"(?:票数|张数|tickets?)\s*[:：]\s*(\d+)",
        "expected_time": r"(?:场次|时间|showTime|time)\s*[:：]\s*(\d{1,2}:\d{2})",
        "openId": r"(?:openId|openid|open_id)\s*[:：]\s*([A-Za-z0-9_-]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order[key] = match.group(1).strip()

    seats_match = re.search(r"(?:座位|seats?|seat_positions?)\s*[:：]\s*([0-9排号,\s，、]+)", text, re.IGNORECASE)
    if seats_match:
        order["seat_positions"] = [part.strip() for part in re.split(r"[,，、\s]+", seats_match.group(1)) if part.strip()]

    range_match = re.search(r"(?:时间范围|timeRange)\s*[:：]\s*(\d{1,2}:\d{2})\s*[-~至到]\s*(\d{1,2}:\d{2})", text, re.IGNORECASE)
    if range_match:
        order["timeRange"] = [range_match.group(1), range_match.group(2)]

    return order


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Match a movie session, resolve specified seats, and lock them through cinema APIs.")
    parser.add_argument("--config", help="JSON config file. See config.direct_ticketing.example.json.")
    parser.add_argument("--order-json", help="Order criteria JSON file.")
    parser.add_argument("--order-json-inline", help="Order criteria as inline JSON.")
    parser.add_argument("--order-text", help="Plain order text with labels like 电影名: / 日期: / 座位:.")
    parser.add_argument("--base-url", help="Cinema API base URL, for example https://pandl.xyz")
    parser.add_argument("--cinema-code", default=None, help="Cinema code. Defaults to 34025901.")
    parser.add_argument("--execute-lock", action="store_true", help="Actually call the lock-seat API. Default is dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Keep dry-run mode. This is the default.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print output JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_json_file(args.config)

    order: dict[str, Any] = {}
    order.update(config.get("order_defaults", {}))
    order.update(load_json_file(args.order_json))
    if args.order_json_inline:
        order.update(json.loads(args.order_json_inline))
    if args.order_text:
        order.update(parse_order_text(args.order_text))
    # openId 和会员卡密码集中放在配置文件里，避免在订单文件或命令行反复暴露。
    if config.get("openId") or config.get("open_id"):
        order["openId"] = config.get("openId") or config.get("open_id")
    if config.get("memberCard") or config.get("member_card"):
        order["memberCard"] = config.get("memberCard") or config.get("member_card")

    if not order:
        raise SystemExit("No order input. Use --order-json, --order-json-inline, or --order-text.")

    base_url = args.base_url or config.get("base_url")
    if not base_url:
        raise SystemExit("Missing base URL. Pass --base-url or set base_url in config.")

    if args.cinema_code:
        order["cinema_code"] = args.cinema_code
    criteria = criteria_from_order(order)
    member_card = order.get("memberCard") or order.get("member_card")

    client = CinemaApiClient(
        base_url=base_url,
        cinema_code=criteria.cinema_code,
        headers=config.get("headers", {}),
        timeout=int(config.get("timeout", 20)),
        lock_path=str(config.get("lock_path", "/JavaWeb2/api/order/v1/lockSeat")),
    )
    result = DirectTicketRunner(client).run(criteria, dry_run=not args.execute_lock, member_card=member_card if args.execute_lock else None)

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
