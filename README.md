# ticket-watch

Checks SeatGeek about every 15 minutes for Noah Kahan at Fenway and sends a
phone notification (via the free **ntfy** app) when the cheapest ticket for a
chosen date is at or under the budget.

## Settings (`config.json`)
- `dates`: show dates to watch (YYYY-MM-DD).
- `max_price_per_ticket`: budget per ticket, fees included.
- `tickets_needed`: shown in the alert as a reminder (SeatGeek only reports
  the single cheapest ticket, so check that enough seats are together).
- Dates that have passed are skipped. The monthly keep-alive runs through June 2027.
- `realert_drop`: after an alert, alert again only if the price falls this
  many more dollars. If the price goes back over budget, the next dip alerts again.

## Reminders
If the price is still in budget, a reminder goes out about 15 minutes after
the first alert and again after an hour, then stops.

## Secrets (Settings → Secrets and variables → Actions)
- `SEATGEEK_CLIENT_ID`: from developer.seatgeek.com.
- `NTFY_TOPIC`: the channel name you subscribe to in the ntfy app.
- `ALERT_EMAIL` (optional): also email each alert to this address.

## Test it
Actions → "Watch ticket prices" → Run workflow → tick "Send a test alert".

## Stop it
Actions → "Watch ticket prices" → ⋯ → Disable workflow.

Tests: `python3 -m unittest discover -s tests`
