# Config-Driven Ticket CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the FastAPI/browser workflow with a root-level CLI that reads one local JSON file, checks or purchases specified cinema seats, and keeps all same-system mini-program parameters configurable.

**Architecture:** Keep `backend/app/direct_ticketing.py` as the tested ticketing engine and add `movie_ticket_cli.py` as the only user entry point. The CLI validates and flattens the nested configuration into existing engine inputs; `CinemaApiClient` remains responsible for HTTP calls and receives configured headers, cinema code, timeout, and relative output directory.

**Tech Stack:** Python 3.11 standard library, `unittest`, `unittest.mock`, `qrcode` for pickup images.

---

## File Map

- Create `movie_ticket_cli.py`: argument parsing, config loading/validation, relative-path resolution, and orchestration.
- Create `config.example.json`: sanitized but concrete order example.
- Create ignored `config.local.json`: local runnable configuration with the provided fixed credentials.
- Create `tests/test_movie_ticket_cli.py`: CLI/config behavior tests.
- Modify `backend/app/direct_ticketing.py`: remove cinema-specific defaults and accept a configured ticket-picture directory.
- Modify `backend/tests/test_direct_ticketing.py`: preserve existing regression tests and assert configured request headers/output path.
- Modify `README.md`, `requirements.txt`, and `.gitignore`: document the CLI and remove server dependencies.
- Delete `backend/app/main.py`, `backend/app/api/`, `backend/app/core/`, `backend/scripts/`, `backend/tests/test_ticket_api.py`, and obsolete backend config/order documentation.

### Task 1: Add nested config parsing and safe CLI mode selection

**Files:**
- Create: `tests/test_movie_ticket_cli.py`
- Create: `movie_ticket_cli.py`

- [ ] **Step 1: Write failing tests for the desired configuration API**

Add tests that call `load_purchase_settings(path, check_only)` with a temporary JSON file and assert:

```python
self.assertEqual(settings.mini_program.cinema_code, "34025901")
self.assertEqual(settings.order["openId"], "OPEN-1")
self.assertEqual(settings.order["seat_positions"], ["5排9号"])
self.assertEqual(settings.output_dir, config_path.parent / "picture")
```

Also assert a real-purchase configuration with placeholder credentials raises `DirectTicketingError`, while `check_only=True` accepts placeholder account values.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m unittest tests.test_movie_ticket_cli -v`

Expected: import failure because `movie_ticket_cli.py` does not exist.

- [ ] **Step 3: Implement the minimal configuration loader**

Create dataclasses for mini-program and purchase settings, load UTF-8 JSON, require the `miniProgram`, `account`, `order`, and `runtime` objects, map the concrete order keys to engine aliases, derive ticket count from `seatNames`, and resolve `runtime.outputDir` against the configuration file directory.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python -m unittest tests.test_movie_ticket_cli -v`

Expected: all config-loading tests pass.

### Task 2: Make all HTTP requests use configured tenant parameters

**Files:**
- Modify: `backend/tests/test_direct_ticketing.py`
- Modify: `backend/app/direct_ticketing.py`

- [ ] **Step 1: Write failing request-construction tests**

Use an injected transport to call representative session, seat, lock, member-card, member-price, confirm, and order methods. For each captured request assert:

```python
self.assertEqual(request.get_header("Cinemacode"), "21010931")
self.assertEqual(
    request.get_header("Referer"),
    "https://servicewechat.com/wxe12fb00c6ff657c2/25/page-frame.html",
)
```

Add a test proving no `34025901` fallback is accepted when the constructor is called without a cinema code.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest backend.tests.test_direct_ticketing -v`

Expected: failure from the current cinema-code default or missing assertions.

- [ ] **Step 3: Remove hardcoded tenant defaults**

Make `MatchCriteria.cinema_code` and `CinemaApiClient.cinema_code` required non-empty values, remove the hardcoded default from `criteria_from_order`, and retain the existing merge of standard headers with configured overrides. Preserve the uncommitted date validation and payment/order-number correction.

- [ ] **Step 4: Run engine tests and verify GREEN**

Run: `python -m unittest backend.tests.test_direct_ticketing -v`

Expected: all direct-ticketing tests pass.

### Task 3: Wire check-only and real-purchase orchestration

**Files:**
- Modify: `tests/test_movie_ticket_cli.py`
- Modify: `movie_ticket_cli.py`
- Modify: `backend/app/direct_ticketing.py`

- [ ] **Step 1: Write failing orchestration tests**

Patch `CinemaApiClient` and `DirectTicketRunner`; assert `run_from_config(..., check_only=True)` calls:

```python
runner.run(criteria, dry_run=True, member_card=None)
```

and default execution calls:

```python
runner.run(criteria, dry_run=False, member_card={"password": "240279"})
```

Assert the configured relative output directory is assigned to the client and the result is printed as UTF-8 JSON.

- [ ] **Step 2: Run orchestration tests and verify RED**

Run: `python -m unittest tests.test_movie_ticket_cli -v`

Expected: failures because orchestration and `--check-only` are not implemented.

- [ ] **Step 3: Implement CLI orchestration**

Add `--config` defaulting to `config.local.json` beside the script and `--check-only`. Instantiate `CinemaApiClient`, call `criteria_from_order`, run `DirectTicketRunner` with the correct dry-run/payment arguments, redact sensitive values from errors, and return exit code `0` for success or `2` for a handled failure.

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run: `python -m unittest tests.test_movie_ticket_cli -v`

Expected: all CLI tests pass.

### Task 4: Add concrete configuration files and relative paths

**Files:**
- Modify: `.gitignore`
- Create: `config.example.json`
- Create locally but do not stage: `config.local.json`
- Modify: `backend/tests/test_direct_ticketing.py`
- Modify: `backend/app/direct_ticketing.py`

- [ ] **Step 1: Write a failing relative output-path test**

Set `client.ticket_picture_dir` through the constructor, patch QR generation, and assert saved output is under the configured directory rather than a drive-specific path.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest backend.tests.test_direct_ticketing -v`

Expected: constructor rejects `ticket_picture_dir` or still uses the old default.

- [ ] **Step 3: Implement relative path support and configs**

Accept `ticket_picture_dir: Path` in `CinemaApiClient`. Add a sanitized `config.example.json` with `给阿姨的情书`, `2026-06-19`, `14:30`, `2号厅`, `国语`, `普通2D`, `5排9号`, and price `80`. Add ignored `config.local.json` with cinema code `34025901`, the `wx52420337e5796bd6/15` referer, fixed `openId`, and password `240279`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m unittest backend.tests.test_direct_ticketing tests.test_movie_ticket_cli -v`

Expected: all tests pass and `git status --short` does not list `config.local.json`.

### Task 5: Remove the web stack and update documentation

**Files:**
- Delete: `backend/app/main.py`
- Delete: `backend/app/api/health.py`
- Delete: `backend/app/api/ticket.py`
- Delete: `backend/app/api/__init__.py`
- Delete: `backend/app/core/config.py`
- Delete: `backend/app/core/__init__.py`
- Delete: `backend/scripts/lock_movie_ticket.py`
- Delete: `backend/tests/test_ticket_api.py`
- Delete: `backend/config.direct_ticketing.example.json`
- Delete: `backend/order.example.json`
- Delete: `backend/README.md`
- Modify: `README.md`
- Modify: `requirements.txt`

- [ ] **Step 1: Write a structural test**

Add a test asserting the supported entry point exists and the removed FastAPI entry point does not:

```python
self.assertTrue((PROJECT_ROOT / "movie_ticket_cli.py").exists())
self.assertFalse((PROJECT_ROOT / "backend/app/main.py").exists())
```

- [ ] **Step 2: Remove web-only files and dependencies**

Delete the listed files. Keep only runtime dependencies used by the CLI. Rewrite README commands using relative paths:

```powershell
python -m pip install -r requirements.txt
python .\movie_ticket_cli.py --check-only
python .\movie_ticket_cli.py
```

- [ ] **Step 3: Scan for stale absolute paths and web references**

Run PowerShell `Select-String` over tracked source/docs for `E:\\filmproject`, `E:\\filmproject2`, `uvicorn`, `FastAPI`, and `http://127.0.0.1:8000`.

Expected: no matches in active README, code, or configuration files; historical design documents may describe removed behavior but must not contain machine-specific runtime paths.

- [ ] **Step 4: Run the complete test suite**

Run: `python -m unittest discover -v`

Expected: all tests pass without network access.

### Task 6: Final verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Validate both JSON files**

Run Python JSON parsing for `config.example.json` and ignored `config.local.json`.

Expected: both parse as JSON objects.

- [ ] **Step 2: Exercise CLI help and safe check mode parsing**

Run: `python movie_ticket_cli.py --help`

Expected: help lists `--config` and `--check-only`.

Run the automated CLI tests rather than a real network purchase. Do not run default purchase against the live API during verification.

- [ ] **Step 3: Run the complete suite again**

Run: `python -m unittest discover -v`

Expected: all tests pass with zero failures and errors.

- [ ] **Step 4: Review the diff and sensitive-file boundary**

Run: `git diff --check`, `git status --short`, and inspect the staged/unstaged diff. Confirm `config.local.json` remains ignored and neither the fixed `openId` nor member password appears in tracked files.
