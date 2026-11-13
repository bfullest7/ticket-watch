"""Ticket watch: checks SeatGeek prices and sends a phone alert (ntfy) and
emails (through Gmail) when the cheapest ticket for a chosen date is at or
under the budget.

Python standard library only. Settings live in config.json.
Secrets (from GitHub Secrets): SEATGEEK_CLIENT_ID, NTFY_TOPIC, and for email
ALERT_EMAIL, GMAIL_ADDRESS, GMAIL_APP_PASSWORD.
"""
import datetime
import hashlib
import json
import os
import smtplib
from email.message import EmailMessage
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "state.json")
SEATGEEK_URL = "https://api.seatgeek.com/2/events"
NTFY_URL = "https://ntfy.sh/"


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def fetch_events(cfg, client_id):
    params = {
        "performers.slug": cfg["performer_slug"],
        "venue.city": cfg["city"],
        "per_page": 50,
        "client_id": client_id,
    }
    url = SEATGEEK_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ticket-watch"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("events", [])


def prices_by_date(events, dates):
    """Return {date: {"price": lowest or None, "url": ..., "count": ...}}."""
    found = {}
    for ev in events:
        day = (ev.get("datetime_local") or "")[:10]
        if day not in dates:
            continue
        stats = ev.get("stats") or {}
        price = stats.get("lowest_price")
        found[day] = {
            "price": price,
            "url": ev.get("url"),
            "count": stats.get("listing_count"),
            "title": ev.get("title"),
        }
    return found


def should_alert(price, max_price, last_alerted, drop):
    """Alert when the price is in budget and we haven't already alerted
    at this price (or one within `drop` dollars of it)."""
    if price is None or price > max_price:
        return False
    if last_alerted is None:
        return True
    return price <= last_alerted - drop


REMINDER_MINUTES = [15, 60]  # after the first alert, if the price is still good
GRACE_MINUTES = 2  # GitHub's 15-minute timer can run a little early or late


def reminder_due(alerted_at, reminders_sent, now):
    """True when the next follow-up reminder should go out."""
    if alerted_at is None or reminders_sent >= len(REMINDER_MINUTES):
        return False
    waited = (now - datetime.datetime.fromisoformat(alerted_at)).total_seconds() / 60
    return waited >= REMINDER_MINUTES[reminders_sent] - GRACE_MINUTES


def _post(topic, title, message, click_url):
    headers = {"Title": title, "Tags": "ticket", "Priority": "high"}
    if click_url:
        headers["Click"] = click_url
    req = urllib.request.Request(
        NTFY_URL + urllib.parse.quote(topic),
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def alert_emails():
    return [e.strip() for e in os.environ.get("ALERT_EMAIL", "").split(",")
            if e.strip()]


def send_email(title, message, click_url):
    """Email the alert from the Gmail account to every ALERT_EMAIL address.
    Returns a short status line; never raises, so the phone push still counts."""
    to = alert_emails()
    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not (to and sender and password):
        return "Email skipped (email secrets not all set)."
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = f"Ticket watch <{sender}>"
    msg["To"] = ", ".join(to)
    msg.set_content(message + (f"\n\n{click_url}" if click_url else ""))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
        return f"Email sent to {len(to)} address(es)."
    except (smtplib.SMTPException, OSError) as err:
        return f"Email failed: {err}"


def notify(topic, title, message, click_url):
    """Phone push via ntfy, plus an email copy through Gmail."""
    try:
        _post(topic, title, message, click_url)
    finally:
        print(send_email(title, message, click_url))


def with_quantity(url, n):
    """Open the SeatGeek page with the ticket count already chosen, so it
    lists only listings that sell at least that many seats together."""
    if not url or not n or n < 2:
        return url
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query["quantity"] = str(n)
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def nice_date(day):
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    y, m, d = day.split("-")
    return f"{months[int(m) - 1]} {int(d)}"


def main():
    cfg = load_json(CONFIG_PATH, None)
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    client_id = os.environ.get("SEATGEEK_CLIENT_ID", "").strip()
    if not topic:
        print("No NTFY_TOPIC secret yet; skipping until it's added.")
        return

    if os.environ.get("TEST_ALERT") == "true":
        # Safe clues for troubleshooting (never prints the topic itself).
        print(f"Topic length {len(topic)}, starts 'tw-': {topic.startswith('tw-')}, "
              f"fingerprint {hashlib.sha256(topic.encode()).hexdigest()[:8]}")
        title = "Ticket watch is working"
        text = "This is a test. You'll get alerts like this when prices drop."
        reply = _post(topic, title, text, None)
        print(f"ntfy reply: id={reply.get('id')} event={reply.get('event')}")
        print(send_email(title, text, None))
        print("Sent test alert.")
        return

    if not client_id:
        print("No SEATGEEK_CLIENT_ID secret yet; skipping until it's added.")
        return

    state = load_json(STATE_PATH, {})
    found = prices_by_date(fetch_events(cfg, client_id), cfg["dates"])
    max_price = cfg["max_price_per_ticket"]

    now = datetime.datetime.now(datetime.timezone.utc)
    today = datetime.date.today().isoformat()
    for day in cfg["dates"]:
        if day < today:
            continue  # show has passed
        info = found.get(day)
        if not info:
            print(f"{day}: not found on SeatGeek")
            continue
        price = info["price"]
        print(f"{day}: lowest ${price} ({info['count']} listings)")
        entry = state.setdefault(day, {"last_alerted": None})

        if price is None or price > max_price:
            # Back over budget (or sold out): stop reminders, alert again next dip.
            entry.update(last_alerted=None, alerted_at=None, reminders_sent=0)
            continue
        n = cfg.get("tickets_needed", 2)
        link = with_quantity(info["url"], n)
        body = (f"Cheapest single ticket is ${price:.0f} (your limit ${max_price}). "
                f"Tap to see SeatGeek listings for {n} tickets together; "
                f"a pair may cost a little more.")
        if should_alert(price, max_price, entry["last_alerted"],
                        cfg.get("realert_drop", 10)):
            notify(topic, f"Noah Kahan {nice_date(day)}: ${price:.0f} a ticket",
                   body, link)
            entry.update(last_alerted=price, alerted_at=now.isoformat(),
                         reminders_sent=0)
            print(f"{day}: alert sent")
        elif reminder_due(entry.get("alerted_at"), entry.get("reminders_sent", 0), now):
            notify(topic, f"Reminder: Noah Kahan {nice_date(day)} still ${price:.0f}",
                   body, link)
            entry["reminders_sent"] = entry.get("reminders_sent", 0) + 1
            print(f"{day}: reminder {entry['reminders_sent']} sent")

    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
