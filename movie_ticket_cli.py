"""Configuration-driven command line entry point for direct movie ticketing."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from backend.app.direct_ticketing import (
    CinemaApiClient,
    DirectTicketRunner,
    DirectTicketingError,
    criteria_from_order,
)


@dataclass(frozen=True)
class MiniProgramSettings:
    base_url: str
    cinema_code: str
    referer: str
    distributor_id: str
    headers: dict[str, str]


@dataclass(frozen=True)
class PurchaseSettings:
    mini_program: MiniProgramSettings
    order: dict[str, Any]
    member_card: dict[str, str]
    timeout: int
    output_dir: Path


def _object(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DirectTicketingError(f"config field {name} must be an object")
    return value


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DirectTicketingError(f"config field {name} must be a non-empty string")
    return value.strip()


def _valid_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(word in lowered for word in ("填写", "占位", "placeholder", "example"))


def load_purchase_settings(config_path: str | Path, check_only: bool = False) -> PurchaseSettings:
    path = Path(config_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DirectTicketingError(f"config file not found: {path}") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirectTicketingError(f"cannot read config file {path}: {error}") from error
    if not isinstance(payload, dict):
        raise DirectTicketingError("config root must be an object")

    mini = _object(payload, "miniProgram")
    account = _object(payload, "account")
    order_source = _object(payload, "order")
    runtime = _object(payload, "runtime")

    base_url = _required_text(mini, "baseUrl")
    referer = _required_text(mini, "referer")
    cinema_code = _required_text(mini, "cinemaCode")
    if not _valid_http_url(base_url):
        raise DirectTicketingError("config field miniProgram.baseUrl must be an HTTP URL")
    if not _valid_http_url(referer):
        raise DirectTicketingError("config field miniProgram.referer must be an HTTP URL")

    open_id = _required_text(account, "openId")
    password = _required_text(account, "memberCardPassword")
    if not check_only and _is_placeholder(open_id):
        raise DirectTicketingError("config field account.openId must contain a real value")
    if not check_only and _is_placeholder(password):
        raise DirectTicketingError("config field account.memberCardPassword must contain a real value")

    seats = order_source.get("seatNames")
    if not isinstance(seats, list) or not seats or not all(isinstance(item, str) and item.strip() for item in seats):
        raise DirectTicketingError("config field order.seatNames must be a non-empty string array")

    headers = mini.get("headers", {})
    if not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items()):
        raise DirectTicketingError("config field miniProgram.headers must contain string values")

    output_value = runtime.get("outputDir", "picture")
    if not isinstance(output_value, str) or not output_value.strip():
        raise DirectTicketingError("config field runtime.outputDir must be a non-empty string")
    output_dir = Path(output_value).expanduser()
    if not output_dir.is_absolute():
        output_dir = path.parent / output_dir

    timeout = runtime.get("timeout", 20)
    if type(timeout) is not int or timeout <= 0:
        raise DirectTicketingError("config field runtime.timeout must be a positive integer")

    hall = str(order_source.get("hallName") or "").strip()
    language = str(order_source.get("filmLanguage") or "").strip()
    show_type = str(order_source.get("showType") or "").strip()
    order = {
        "movie_name": _required_text(order_source, "movieName"),
        "date": _required_text(order_source, "showDate"),
        "expectedTime": _required_text(order_source, "startTime"),
        "seat_positions": [item.strip() for item in seats],
        "ticket_count": len(seats),
        "priceMax": order_source.get("priceMax"),
        "hall_keywords": [hall] if hall else [],
        "language_keywords": [language] if language else [],
        "show_type_keywords": [show_type] if show_type else [],
        "openId": open_id,
        "cinema_code": cinema_code,
        "distributorId": str(mini.get("distributorId") or ""),
    }
    return PurchaseSettings(
        mini_program=MiniProgramSettings(
            base_url=base_url.rstrip("/"),
            cinema_code=cinema_code,
            referer=referer,
            distributor_id=order["distributorId"],
            headers=dict(headers),
        ),
        order=order,
        member_card={"password": password},
        timeout=timeout,
        output_dir=output_dir,
    )


def run_from_config(config_path: str | Path, check_only: bool = False) -> dict[str, Any]:
    settings = load_purchase_settings(config_path, check_only=check_only)
    client = CinemaApiClient(
        base_url=settings.mini_program.base_url,
        cinema_code=settings.mini_program.cinema_code,
        headers={
            **settings.mini_program.headers,
            "Referer": settings.mini_program.referer,
        },
        timeout=settings.timeout,
        ticket_picture_dir=settings.output_dir,
    )
    criteria = criteria_from_order(settings.order)
    runner = DirectTicketRunner(client)
    return runner.run(
        criteria,
        dry_run=check_only,
        member_card=None if check_only else settings.member_card,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read one config file and purchase specified cinema seats."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().with_name("config.local.json"),
        help="JSON configuration file (default: config.local.json beside this script)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check the matching session and seats without locking or paying",
    )
    return parser


def redact_for_output(value: Any) -> Any:
    sensitive_keys = {
        "authorization",
        "cardcode",
        "membercardpassword",
        "memberphone",
        "openid",
        "password",
        "token",
    }
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            redacted[key] = "[REDACTED]" if normalized in sensitive_keys else redact_for_output(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_output(item) for item in value]
    if isinstance(value, tuple):
        return [redact_for_output(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_from_config(args.config, check_only=args.check_only)
    except DirectTicketingError as error:
        result = {"success": False, "reason": str(error)}
    print(json.dumps(redact_for_output(result), ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 2


if __name__ == "__main__":
    sys.exit(main())
