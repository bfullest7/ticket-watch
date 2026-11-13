"""Ticket watch: checks SeatGeek prices and sends a phone alert (ntfy)
when the cheapest ticket for a chosen date is at or under the budget.

Python standard library only. Settings live in config.json.
Secrets (from GitHub Secrets): SEATGEEK_CLIENT_ID, NTFY_TOPIC.
"""
import datetime
import hashlib
import json
import os
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


def _post(topic, title, message, click_url, email):
    headers = {"Title": title, "Tags": "ticket", "Priority": "high"}
    if click_url:
        headers["Click"] = click_url
    if email:
        headers["Email"] = email
    req = urllib.request.Request(
        NTFY_URL + urllib.parse.quote(topic),
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def notify(topic, title, message, click_url):
    """Phone push via ntfy, plus email copies to ALERT_EMAIL (one address,
    or several separated by commas). ntfy takes one email per message, so
    extra addresses go through a second, unsubscribed topic: email only,
    no duplicate phone push. If an email is refused (ntfy limits free
    emails), the phone push still goes out."""
    emails = [e.strip() for e in os.environ.get("ALERT_EMAIL", "").split(",")
              if e.strip()]
    first = emails[0] if emails else None
    try:
        _post(topic, title, message, click_url, first)
    except urllib.error.HTTPError:
        if not first:
            raise
        print("Email copy refused; sending push only.")
        _post(topic, title, message, click_url, None)
    for extra in emails[1:]:
        try:
            _post(topic + "-email", title, message, click_url, extra)
        except urllib.error.HTTPError as err:
            print(f"Extra email copy refused ({err.code}).")


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
        emails = [e for e in os.environ.get("ALERT_EMAIL", "").split(",") if e.strip()]
        print(f"Email addresses set: {len(emails)}")
        reply = _post(topic, "Ticket watch is working",
                      "This is a test. You'll get alerts like this when prices drop.",
                      None, emails[0].strip() if emails else None)
        print(f"ntfy reply: id={reply.get('id')} event={reply.get('event')}")
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
        entry["last_seen"] = price

        if price is None or price > max_price:
            # Back over budget (or sold out): stop reminders, alert again next dip.
            entry.update(last_alerted=None, alerted_at=None, reminders_sent=0)
            continue
        n = cfg.get("tickets_needed", 2)
        body = (f"Cheapest ticket is ${price:.0f} (your limit ${max_price}). "
                f"Check there are {n} together. Tap to open SeatGeek.")
        if should_alert(price, max_price, entry["last_alerted"],
                        cfg.get("realert_drop", 10)):
            notify(topic, f"Noah Kahan {nice_date(day)}: ${price:.0f} a ticket",
                   body, info["url"])
            entry.update(last_alerted=price, alerted_at=now.isoformat(),
                         reminders_sent=0)
            print(f"{day}: alert sent")
        elif reminder_due(entry.get("alerted_at"), entry.get("reminders_sent", 0), now):
            notify(topic, f"Reminder: Noah Kahan {nice_date(day)} still ${price:.0f}",
                   body, info["url"])
            entry["reminders_sent"] = entry.get("reminders_sent", 0) + 1
            print(f"{day}: reminder {entry['reminders_sent']} sent")

    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
