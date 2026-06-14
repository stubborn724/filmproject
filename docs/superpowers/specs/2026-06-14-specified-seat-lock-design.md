# Specified Seat Lock Design

## Goal

Build a Python CLI flow that receives a movie ticket order with explicit seat labels such as `5排9号`, resolves each label to the cinema API `SeatCode`, and calls the real lock-seat endpoint.

## Requirements

- The order always includes specified seat positions.
- The script must query sessions through `POST /JavaWeb2/api/net/newQuerySession`.
- The script must match the requested movie, date, and time criteria against session response fields.
- The script must query seat data with the matched `PlanCode` and `ScreenCode`.
- The script must map each requested display seat position to the corresponding `SeatCode`.
- The lock request must use `SessionCode` with the matched session `PlanCode`.
- The lock request must include `openId`, `Count`, `distributorId`, and a `Seat` array.
- Each `Seat` item must include `PayPrice`, `Price`, `SeatCode`, `SeatPosition`, and `serviceFee`.
- The CLI must keep dry-run support so the lock payload can be inspected without calling the real lock endpoint.

## Architecture

The implementation stays in the existing backend CLI structure. `backend/app/direct_ticketing.py` owns normalization, matching, seat lookup, request construction, and runner behavior. `backend/scripts/lock_movie_ticket.py` remains a thin command-line wrapper that loads config and order JSON.

The old automatic seat-picking path will be removed from the active runner because orders always provide exact seat positions. Seat matching will be exact after normalizing whitespace and leading zeros, with a fallback from row/column fields when the API does not expose a display label.

## Data Flow

1. Load order JSON.
2. Convert order aliases into `MatchCriteria`, including `seat_positions` and `open_id`.
3. Query sessions for the configured date range.
4. Match and sort candidate sessions.
5. Query seat map by `ScreenCode` and seat status by `PlanCode`.
6. Resolve each requested `SeatPosition` to an available `SeatCode`.
7. Build the captured lock payload.
8. Return payload in dry-run mode or call `POST /JavaWeb2/api/order/v1/lockSeat` in execute mode.

## Error Handling

- Missing `openId` fails before calling lock.
- Missing `seat_positions` fails before querying lock.
- Unknown requested seat fails with a clear message.
- Sold or locked requested seat fails without calling lock.
- HTTP and invalid JSON errors surface as `DirectTicketingError`.

## Testing

Unit tests will cover order parsing, specified seat lookup, lock payload construction, dry-run behavior, and the blocked-seat failure path.
