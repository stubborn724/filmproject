# Flatten and Clean Ticket Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the ticketing engine and its tests to the project root, remove the entire backend tree, and delete all approved historical/runtime clutter without changing CLI behavior.

**Architecture:** `movie_ticket_cli.py` imports a sibling `direct_ticketing.py`. All tests live under root `tests/`; no package or virtual environment remains under `backend/`. Runtime output continues to resolve relative to the configuration file.

**Tech Stack:** Python 3.11 standard library and `unittest`.

---

### Task 1: Specify the flattened structure with a failing test

**Files:**
- Modify: `tests/test_movie_ticket_cli.py`

- [ ] Add assertions that `direct_ticketing.py` exists at project root and `backend/` does not exist:

```python
self.assertTrue((PROJECT_ROOT / "direct_ticketing.py").exists())
self.assertFalse((PROJECT_ROOT / "backend").exists())
```

- [ ] Run `python -m unittest tests.test_movie_ticket_cli.ProjectStructureTests -v` and confirm it fails because the engine is still under `backend/`.

### Task 2: Move engine and tests to the root

**Files:**
- Move: `backend/app/direct_ticketing.py` to `direct_ticketing.py`
- Move: `backend/tests/test_direct_ticketing.py` to `tests/test_direct_ticketing.py`
- Modify: `movie_ticket_cli.py`
- Modify: `tests/test_movie_ticket_cli.py`
- Modify: `tests/test_direct_ticketing.py`

- [ ] Change imports to `from direct_ticketing import ...`.
- [ ] Change the engine root constant to:

```python
PROJECT_ROOT = Path(__file__).resolve().parent
```

- [ ] Run `python -m unittest discover -v`; all 29 tests must pass before deleting runtime clutter.

### Task 3: Delete approved clutter

**Files/directories:**
- Delete: `backend/`
- Delete: `docs/`
- Delete: `uploads/`
- Delete: all `__pycache__/` and `.pyc`
- Delete: existing `picture/*.svg`

- [ ] Resolve and verify each recursive deletion target is inside `E:\filmproject`, then delete only the listed targets.
- [ ] Confirm `config.local.json`, `config.example.json`, both root Python files, README, requirements, and tests remain.

### Task 4: Verify runtime behavior

**Files:**
- Verify the remaining project tree.

- [ ] Run `python -m py_compile movie_ticket_cli.py direct_ticketing.py`.
- [ ] Run `python -m unittest discover -v`; expect 29 passing tests.
- [ ] Run `python movie_ticket_cli.py --check-only`, capture JSON, and confirm steps contain only `query_sessions`, `query_seat_map`, `query_session_seats`, and `build_lock_payload`.
- [ ] Run `git diff --check` and confirm `config.local.json` remains ignored.
- [ ] Commit the flattened cleanup without staging `config.local.json`.
