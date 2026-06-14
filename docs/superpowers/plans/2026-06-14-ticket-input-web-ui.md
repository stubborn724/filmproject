# Ticket Input Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI-served web form for entering specified-seat movie ticket orders and previewing or executing lock-seat requests.

**Architecture:** Create a focused ticket API router that converts form JSON into existing direct-ticketing criteria and runner calls. Serve a single static HTML/CSS/JS page from the backend root. Keep dependencies within FastAPI and the Python standard library.

**Tech Stack:** FastAPI, Pydantic, standard browser HTML/CSS/JavaScript, Python `unittest`.

---

## File Structure

- Create `backend/app/api/ticket.py`: ticket page route and preview/lock JSON endpoints.
- Modify `backend/app/main.py`: include the ticket router.
- Create `backend/tests/test_ticket_api.py`: API and UI route tests.
- Modify `backend/README.md`: document browser usage.

### Task 1: API/UI Route Tests

**Files:**
- Create: `backend/tests/test_ticket_api.py`

- [ ] **Step 1: Write failing tests**

Add tests that:

```python
def test_home_page_contains_order_fields():
    response = client.get("/")
    assert response.status_code == 200
    assert "电影名" in response.text
    assert "seatPositions" in response.text
```

```python
def test_preview_endpoint_runs_dry_run():
    response = client.post("/api/ticket/preview", json={...})
    assert response.json()["dry_run"] is True
```

```python
def test_lock_endpoint_runs_execute_mode():
    response = client.post("/api/ticket/lock", json={...})
    assert response.json()["dry_run"] is False
```

- [ ] **Step 2: Run tests**

Run `python -m unittest tests.test_ticket_api`.

Expected: FAIL because the router does not exist.

### Task 2: Ticket Router

**Files:**
- Create: `backend/app/api/ticket.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Implement request model**

Fields: `movieName`, `showDate`, `showTime`, `seatPositions`, `openId`, `cinemaCode`, `priceMax`.

- [ ] **Step 2: Implement endpoints**

Preview calls `DirectTicketRunner(client).run(criteria, dry_run=True)`.

Lock calls `DirectTicketRunner(client).run(criteria, dry_run=False)`.

- [ ] **Step 3: Run tests**

Run `python -m unittest tests.test_ticket_api`.

Expected: PASS.

### Task 3: Browser Form

**Files:**
- Modify: `backend/app/api/ticket.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Add HTML form**

The form posts JSON to preview or lock endpoints and displays the response JSON.

- [ ] **Step 2: Verify full suite**

Run:

```powershell
python -m unittest tests.test_direct_ticketing tests.test_ticket_api
python -m compileall app scripts tests
```

Expected: PASS.

## Self-Review

- Spec coverage: page route, preview endpoint, lock endpoint, validation, and docs are covered.
- Placeholder scan: no deferred implementation placeholders remain.
- Type consistency: field names are consistent across UI, Pydantic model, tests, and order conversion.
