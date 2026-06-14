# Ticket Input Web UI Design

## Goal

Add a lightweight browser page to the existing FastAPI backend so a user can enter a movie ticket order with explicit seats and preview or execute the lock-seat workflow.

## Scope

- Serve a single page from `GET /`.
- Provide `POST /api/ticket/preview` for dry-run parsing and payload preview.
- Provide `POST /api/ticket/lock` for real lock-seat execution.
- Reuse the existing `DirectTicketRunner`, `CinemaApiClient`, and `criteria_from_order`.
- Do not create a separate React/Vue frontend project.

## UI Fields

- Movie name.
- Show date.
- Show time.
- Seat positions, comma-separated such as `5排9号,5排10号`.
- OpenId, defaulted to the current captured value.
- Cinema code, defaulted to `34025901`.
- Price limit, optional.

The page will compute ticket count from the seat list before submitting to the API.

## Behavior

Preview returns matched session, resolved seats, and the full `lockSeat` payload without calling the real lock endpoint. Lock uses the same input and calls the real endpoint. Both endpoints return JSON; the page displays the JSON response in a readable output panel.

## Error Handling

Validation errors and ticketing errors return a JSON response with `success: false` and a readable `reason`. The page shows the returned JSON instead of hiding the failure.

## Testing

Tests will verify that `GET /` renders the expected form, preview calls the runner in dry-run mode, lock calls the runner in execute mode, and invalid input returns a controlled error.
