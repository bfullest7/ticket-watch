# ticket-watch

Checks SeatGeek every 5 minutes, around the clock, for Noah Kahan at Fenway and sends a
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

## How the timing works
Each run is a "shift" of about 5½ hours that checks every 5 minutes. A new
shift is queued every hour, so when one ends the next starts right away. If
checks keep failing for 30 minutes, the shift stops with an error and GitHub
emails you.

## Reminders
If the price is still in budget, a reminder goes out about 15 minutes after
the first alert and again after an hour, then stops.

## Secrets (Settings → Secrets and variables → Actions)
- `SEATGEEK_CLIENT_ID`: from developer.seatgeek.com.
- `NTFY_TOPIC`: the channel name you subscribe to in the ntfy app.
- `ALERT_EMAIL` (optional): also email each alert. Several addresses can be
  separated by commas.
- `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`: the Gmail account that sends the
  emails, and a Google app password for it (myaccount.google.com/apppasswords).

## Test it
Actions → "Watch ticket prices" → Run workflow → tick "Send a test alert".

## Stop it
Actions → "Watch ticket prices" → ⋯ → Disable workflow.

Tests: `python3 -m unittest discover -s tests`
