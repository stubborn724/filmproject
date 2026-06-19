# Specified Seat Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace automatic seat selection with exact order seat locking through the captured `lockSeat` API.

**Architecture:** Keep the existing Python CLI shape. Simplify `direct_ticketing.py` around exact seat-position resolution, a small API client, and a runner that builds the real lock payload. Preserve dry-run so the lock payload can be verified without side effects.

**Tech Stack:** Python 3, standard library `unittest`, `urllib.request`, JSON config files.

---

## File Structure

- Modify `backend/app/direct_ticketing.py`: criteria parsing, session matching, specified seat resolution, API client, runner.
- Modify `backend/scripts/lock_movie_ticket.py`: CLI argument semantics and order/config loading.
- Modify `backend/tests/test_direct_ticketing.py`: focused tests for the new exact-seat flow.
- Modify `backend/config.direct_ticketing.example.json`: real default paths and captured headers shape.
- Modify `backend/order.example.json`: specified-seat order example.
- Modify `backend/README.md` and root `README.md`: updated usage.

### Task 1: Tests For Exact Seat Orders

**Files:**
- Modify: `backend/tests/test_direct_ticketing.py`

- [ ] **Step 1: Write failing tests**

Cover these behaviors:

```python
def test_criteria_from_order_requires_specified_seats_and_open_id():
    criteria = criteria_from_order({
        "filmName": "Target Movie",
        "date": "2026-06-14",
        "showTime": "14:30",
        "seat_positions": ["5排9号"],
        "openId": "OPEN-1",
    })
    assert criteria.seat_positions == ["5排9号"]
    assert criteria.open_id == "OPEN-1"
```

```python
def test_runner_dry_run_resolves_requested_seat_and_builds_lock_payload():
    result = DirectTicketRunner(FakeClient()).run(criteria, dry_run=True)
    assert result["success"] is True
    assert result["lock_payload"]["SessionCode"] == "P1"
    assert result["lock_payload"]["Seat"][0]["SeatCode"] == "S-5-9"
```

```python
def test_runner_does_not_lock_when_requested_seat_is_blocked():
    client = FakeClient(blocked=True)
    result = DirectTicketRunner(client).run(criteria)
    assert result["success"] is False
    assert client.lock_calls == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_direct_ticketing`

Expected: FAIL because the old implementation has no required `seat_positions` criteria and still auto-selects seats.

### Task 2: Implement Exact Seat Resolution

**Files:**
- Modify: `backend/app/direct_ticketing.py`

- [ ] **Step 1: Add model fields and alias parsing**

Add `seat_positions` and `open_id` to `MatchCriteria`. Parse aliases `seat_positions`, `seatPositions`, `seats`, `SeatPosition`, `openId`, and `open_id`.

- [ ] **Step 2: Add seat normalization**

Normalize `5排09号`, `5 排 9 号`, and API row/column fields to the comparable key `5排9号`.

- [ ] **Step 3: Add specified seat resolver**

Resolve requested seat positions from seat map and seat status. Return `ResolvedSeat` values with `SeatCode` and requested display position. Raise `DirectTicketingError` for missing or blocked seats.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_direct_ticketing`

Expected: tests progress to lock payload failures if payload work is still missing.

### Task 3: Implement Captured Lock Payload

**Files:**
- Modify: `backend/app/direct_ticketing.py`
- Modify: `backend/config.direct_ticketing.example.json`

- [ ] **Step 1: Build the payload**

Construct:

```python
{
    "Count": len(seats),
    "SessionCode": plan_code,
    "openId": criteria.open_id,
    "distributorId": distributor_id,
    "Seat": [
        {
            "PayPrice": channel_price,
            "Price": standard_price,
            "SeatCode": seat.code,
            "SeatPosition": seat.position,
            "serviceFee": sub_fee,
        }
    ],
}
```

- [ ] **Step 2: Set default lock endpoint**

Use `/JavaWeb2/api/order/v1/lockSeat` as the default path in config.

- [ ] **Step 3: Run tests**

Run: `python -m unittest tests.test_direct_ticketing`

Expected: PASS.

### Task 4: CLI And Documentation

**Files:**
- Modify: `backend/scripts/lock_movie_ticket.py`
- Modify: `backend/order.example.json`
- Modify: `backend/README.md`
- Modify: `README.md`

- [ ] **Step 1: Update CLI help**

Make dry-run the safe default through a `--execute-lock` flag.

- [ ] **Step 2: Update examples**

Show `seat_positions` and `openId`.

- [ ] **Step 3: Final verification**

Run:

```powershell
cd backend
python -m unittest tests.test_direct_ticketing
python scripts\lock_movie_ticket.py --config config.direct_ticketing.example.json --order-json order.example.json --dry-run --pretty
```

Expected: unit tests pass; the CLI may fail against the live API only if the sample order does not match current sessions.

## Self-Review

- Spec coverage: all requirements map to Tasks 1-4.
- Placeholder scan: no deferred implementation placeholders remain.
- Type consistency: `seat_positions`, `open_id`, `ResolvedSeat`, and `lock_payload` are used consistently.
