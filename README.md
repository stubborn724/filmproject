# Direct Film Ticket Tool

Python script for matching a movie ticket order to a cinema session, resolving specified seats, and locking those seats through captured cinema APIs.

This version does not use browser UI automation, WeChat UI automation, OCR, or a frontend.

## Main Files

- `backend/app/direct_ticketing.py`: session matching, specified seat resolution, API client, lock runner.
- `backend/scripts/lock_movie_ticket.py`: command line script.
- `backend/config.direct_ticketing.example.json`: API headers and endpoint config.
- `backend/order.example.json`: sample specified-seat order.
- `backend/tests/test_direct_ticketing.py`: core behavior tests.

## Quick Start

```powershell
cd E:\filmproject\backend
python -m unittest tests.test_direct_ticketing
python scripts\lock_movie_ticket.py --config config.direct_ticketing.example.json --order-json order.example.json --dry-run --pretty
```

Dry-run is the default. Add `--execute-lock` only when you want to call the real `lockSeat` endpoint.

## Web Input

```powershell
cd E:\filmproject\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` to enter the ticket order in a browser. `openId` and the member card password are read from `backend/config.direct_ticketing.example.json`; the card number is queried automatically from `batchMemberCard`.
