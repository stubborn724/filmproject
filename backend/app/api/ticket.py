"""Ticket order input page and API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.direct_ticketing import CinemaApiClient, DirectTicketRunner, DirectTicketingError, criteria_from_order


router = APIRouter()

DEFAULT_CINEMA_CODE = "34025901"
DEFAULT_BASE_URL = "https://pandl.xyz"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.direct_ticketing.example.json"


class MemberCardRequest(BaseModel):
    cardCode: str | None = None
    password: str = Field(..., min_length=1)


class TicketOrderRequest(BaseModel):
    movieName: str = Field(..., min_length=1)
    showDate: str = Field(..., min_length=1)
    showTime: str = Field(..., min_length=1)
    seatPositions: list[str]
    openId: str | None = None
    cinemaCode: str = DEFAULT_CINEMA_CODE
    priceMax: float | None = None
    memberCard: MemberCardRequest | None = None


def load_ticket_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {
            "base_url": DEFAULT_BASE_URL,
            "headers": {},
            "timeout": 20,
            "lock_path": "/JavaWeb2/api/order/v1/lockSeat",
        }
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def order_to_criteria_payload(order: TicketOrderRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "movieName": order.movieName,
        "date": order.showDate,
        "expectedTime": order.showTime,
        "seat_positions": order.seatPositions,
        "ticket_count": len(order.seatPositions),
        "cinema_code": order.cinemaCode,
    }
    if order.openId:
        payload["openId"] = order.openId
    if order.priceMax is not None:
        payload["priceMax"] = order.priceMax
    return payload


def apply_configured_credentials(order_payload: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    # openId 和会员卡密码不暴露在页面上，统一从配置文件注入。
    configured_open_id = str(config.get("openId") or config.get("open_id") or "").strip()
    if configured_open_id:
        order_payload["openId"] = configured_open_id

    member_card = config.get("memberCard") or config.get("member_card")
    if isinstance(member_card, dict) and member_card.get("password"):
        return order_payload, {"password": str(member_card["password"])}
    return order_payload, None


def run_ticket_order(order: TicketOrderRequest, dry_run: bool) -> dict[str, Any]:
    config = load_ticket_config()
    criteria_payload, configured_member_card = apply_configured_credentials(order_to_criteria_payload(order), config)
    criteria = criteria_from_order(criteria_payload)
    client = CinemaApiClient(
        base_url=str(config.get("base_url", DEFAULT_BASE_URL)),
        cinema_code=criteria.cinema_code,
        headers=config.get("headers", {}),
        timeout=int(config.get("timeout", 20)),
        lock_path=str(config.get("lock_path", "/JavaWeb2/api/order/v1/lockSeat")),
    )
    try:
        member_card = configured_member_card or (order.memberCard.model_dump(exclude_none=True) if order.memberCard else None)
        # 预览只看匹配和锁座 payload，不调用会员支付接口。
        if dry_run:
            member_card = None
        return DirectTicketRunner(client).run(criteria, dry_run=dry_run, member_card=member_card)
    except (DirectTicketingError, ValueError) as exc:
        return {"success": False, "reason": str(exc), "trace": client.trace}


def ticket_error_response(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"success": False, "reason": str(exc)})


@router.get("/", response_class=HTMLResponse)
async def ticket_page() -> HTMLResponse:
    return HTMLResponse(TICKET_PAGE_HTML)


@router.post("/api/ticket/preview")
async def preview_ticket(order: TicketOrderRequest):
    try:
        return run_ticket_order(order, dry_run=True)
    except (DirectTicketingError, ValueError) as exc:
        return ticket_error_response(exc)


@router.post("/api/ticket/lock")
async def lock_ticket(order: TicketOrderRequest):
    try:
        return run_ticket_order(order, dry_run=False)
    except (DirectTicketingError, ValueError) as exc:
        return ticket_error_response(exc)


TICKET_PAGE_HTML = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>电影票锁座</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #667085;
      --line: #d7dce3;
      --primary: #0f766e;
      --primary-dark: #0b5f59;
      --danger: #b42318;
      --code-bg: #101828;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 Arial, "Microsoft YaHei", sans-serif;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: minmax(360px, 430px) 1fr;
      gap: 20px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    h1 {{
      margin: 0 0 14px;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    label {{
      display: block;
      margin: 12px 0 6px;
      color: #344054;
      font-weight: 600;
    }}
    input, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }}
    textarea {{
      min-height: 100px;
      resize: vertical;
    }}
    .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 16px;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      color: #fff;
      background: var(--primary);
    }}
    button:hover {{ background: var(--primary-dark); }}
    button.secondary {{
      background: #344054;
    }}
    button.danger {{
      background: var(--danger);
    }}
    pre {{
      min-height: 520px;
      margin: 0;
      padding: 14px;
      overflow: auto;
      border-radius: 8px;
      background: var(--code-bg);
      color: #e4e7ec;
      font: 13px/1.55 Consolas, "Courier New", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .status {{
      margin: 0 0 12px;
      color: var(--muted);
      min-height: 21px;
    }}
    .trace-list {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    summary {{
      cursor: pointer;
      padding: 10px 12px;
      font-weight: 700;
      color: #1d2939;
      background: #f8fafc;
    }}
    details pre {{
      min-height: 0;
      border-radius: 0;
      border-top: 1px solid var(--line);
    }}
    @media (max-width: 860px) {{
      main {{
        grid-template-columns: 1fr;
        width: min(100vw - 24px, 680px);
        margin: 12px auto;
      }}
      .row {{ grid-template-columns: 1fr; }}
      pre {{ min-height: 300px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>电影票锁座</h1>
      <label for="rawOrder">订单文本</label>
      <textarea id="rawOrder" placeholder="电影名: 给阿嬷的情书&#10;日期: 2026-06-14&#10;场次: 14:30&#10;座位: 5排9号"></textarea>
      <div class="actions">
        <button class="secondary" type="button" id="parseText">从文本填入</button>
      </div>

      <label for="movieName">电影名</label>
      <input id="movieName" value="给阿嬷的情书" autocomplete="off">

      <div class="row">
        <div>
          <label for="showDate">日期</label>
          <input id="showDate" type="date" value="2026-06-14">
        </div>
        <div>
          <label for="showTime">场次时间</label>
          <input id="showTime" type="time" value="14:30">
        </div>
      </div>

      <label for="seatPositions">seatPositions</label>
      <input id="seatPositions" value="5排9号" autocomplete="off">

      <div class="row">
        <div>
          <label for="cinemaCode">影院编码</label>
          <input id="cinemaCode" value="{DEFAULT_CINEMA_CODE}" autocomplete="off">
        </div>
        <div>
          <label for="priceMax">价格上限</label>
          <input id="priceMax" type="number" min="0" step="0.01" value="80">
        </div>
      </div>

      <div class="actions">
        <button type="button" id="preview">解析并预览</button>
        <button class="danger" type="button" id="lock">自动购票</button>
      </div>
    </section>

    <section>
      <h2>响应</h2>
      <p class="status" id="status"></p>
      <pre id="result">{{}}</pre>
      <h2 style="margin-top:16px;">请求日志</h2>
      <div class="trace-list" id="tracePanel"></div>
    </section>
  </main>

  <script>
    const fields = ["movieName", "showDate", "showTime", "seatPositions", "cinemaCode", "priceMax"];
    const result = document.getElementById("result");
    const tracePanel = document.getElementById("tracePanel");
    const statusLine = document.getElementById("status");

    function splitSeats(value) {{
      return value.split(/[,，、\\s]+/).map((item) => item.trim()).filter(Boolean);
    }}

    function payload() {{
      const data = Object.fromEntries(fields.map((id) => [id, document.getElementById(id).value.trim()]));
      const request = {{
        movieName: data.movieName,
        showDate: data.showDate,
        showTime: data.showTime,
        seatPositions: splitSeats(data.seatPositions),
        cinemaCode: data.cinemaCode,
        priceMax: data.priceMax ? Number(data.priceMax) : null
      }};
      return request;
    }}

    async function submit(path) {{
      statusLine.textContent = "请求中";
      result.textContent = "";
      tracePanel.innerHTML = "";
      const requestPayload = payload();
      try {{
        const response = await fetch(path, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(requestPayload)
        }});
        const json = await response.json();
        statusLine.textContent = response.ok ? "完成" : "失败";
        result.textContent = JSON.stringify(json, null, 2);
        renderTrace(json.payment_trace || json.trace || []);
      }} catch (error) {{
        statusLine.textContent = "失败";
        const failure = {{
          success: false,
          reason: String(error),
          browser_request: {{
            origin: window.location.origin,
            path,
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: requestPayload
          }}
        }};
        result.textContent = JSON.stringify(failure, null, 2);
        renderTrace([{{
          step: "browser_fetch",
          method: "POST",
          url: window.location.origin + path,
          request_headers: {{ "Content-Type": "application/json" }},
          request_body: requestPayload,
          response_status: null,
          response_headers: {{}},
          response_body: null,
          response_body_raw: null,
          duration_ms: null,
          error: String(error)
        }}]);
      }}
    }}

    function renderTrace(trace) {{
      tracePanel.innerHTML = "";
      if (!trace.length) {{
        tracePanel.textContent = "暂无请求日志";
        return;
      }}
      trace.forEach((entry, index) => {{
        const details = document.createElement("details");
        details.open = index === 0 || Boolean(entry.error);
        const summary = document.createElement("summary");
        const status = entry.response_status === null || entry.response_status === undefined ? "" : " HTTP " + entry.response_status;
        const duration = entry.duration_ms === null || entry.duration_ms === undefined ? "" : " " + entry.duration_ms + "ms";
        summary.textContent = `${{index + 1}}. ${{entry.step || ""}} ${{entry.method || ""}}${{status}}${{duration}}`;
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(entry, null, 2);
        details.appendChild(summary);
        details.appendChild(pre);
        tracePanel.appendChild(details);
      }});
    }}

    function fillFromText() {{
      const text = document.getElementById("rawOrder").value;
      const rules = [
        ["movieName", /(?:电影名|影片|电影|movie)\\s*[:：]\\s*(.+)/i],
        ["showDate", /(?:日期|观影日期|date)\\s*[:：]\\s*(\\d{{4}}[-/]\\d{{1,2}}[-/]\\d{{1,2}})/i],
        ["showTime", /(?:场次|时间|showTime|time)\\s*[:：]\\s*(\\d{{1,2}}:\\d{{2}})/i],
        ["seatPositions", /(?:座位|seatPositions|seats?)\\s*[:：]\\s*([^\\n]+)/i]
      ];
      for (const [id, pattern] of rules) {{
        const match = text.match(pattern);
        if (match) document.getElementById(id).value = match[1].trim();
      }}
    }}

    document.getElementById("parseText").addEventListener("click", fillFromText);
    document.getElementById("preview").addEventListener("click", () => submit("/api/ticket/preview"));
    document.getElementById("lock").addEventListener("click", () => submit("/api/ticket/lock"));
  </script>
</body>
</html>
"""
