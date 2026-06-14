# Direct Ticket Backend

Python CLI for matching a movie session, resolving specified seat labels such as `5排9号` to `SeatCode`, and calling the captured lock-seat API.

## Commands

```powershell
cd E:\filmproject\backend
python -m unittest tests.test_direct_ticketing
python scripts\lock_movie_ticket.py --config config.direct_ticketing.example.json --order-json order.example.json --dry-run --pretty
```

Dry-run is the default and prints the matched session, resolved seat, and lock payload without calling `lockSeat`.

## Browser Input Page

Start the FastAPI app:

```powershell
cd E:\filmproject\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`.

The page accepts movie name, date, show time, specified seats such as `5排9号`, cinema code, and optional max price. `openId` and the member card password are read from `config.direct_ticketing.example.json`. `解析并预览` runs dry-run mode. `自动购票` calls the real `lockSeat` endpoint and then pays by member card. The card number is queried through `GET /JavaWeb2/api/member/v1/batchMemberCard?openId=...`. The page request log shows only the member payment stage after automatic purchase.

To actually lock the seat:

```powershell
python scripts\lock_movie_ticket.py --config config.direct_ticketing.example.json --order-json order.example.json --execute-lock --pretty
```

## Order JSON

```json
{
  "movie_name": "给阿嬷的情书",
  "date": "2026-06-14",
  "ticket_count": 1,
  "expectedTime": "14:30",
  "seat_positions": ["5排9号"],
  "priceMax": 80
}
```

The order must include exact `seat_positions`. The script maps each position to `SeatCode` through the seat APIs before building the lock request.

## Lock Payload

The script builds the captured payload shape:

```json
{
  "Count": 1,
  "SessionCode": "0526061100171947",
  "openId": "用自己的openid",
  "distributorId": "",
  "Seat": [
    {
      "PayPrice": "35.00",
      "Price": "60.00",
      "SeatCode": "0300000100800501",
      "SeatPosition": "5排9号",
      "serviceFee": "1.00"
    }
  ]
}
```

`SessionCode` is the matched session `PlanCode`.
