"""Ticket watch: checks SeatGeek prices and sends a phone alert (ntfy)
when the cheapest ticket for a chosen date is at or under the budget.

Python standard library only. Settings live in config.json.
Secrets (from GitHub Secrets): SEATGEEK_CLIENT_ID, NTFY_TOPIC.
"""
import datetime
import json
import os
import sys
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


def notify(topic, title, message, click_url):
    req = urllib.request.Request(
        NTFY_URL + urllib.parse.quote(topic),
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Tags": "ticket",
            "Priority": "high",
            **({"Click": click_url} if click_url else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


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
        notify(topic, "Ticket watch is working",
               "This is a test. You'll get alerts like this when prices drop.",
               None)
        print("Sent test alert.")
        return

    if not client_id:
        print("No SEATGEEK_CLIENT_ID secret yet; skipping until it's added.")
        return

    state = load_json(STATE_PATH, {})
    found = prices_by_date(fetch_events(cfg, client_id), cfg["dates"])
    max_price = cfg["max_price_per_ticket"]

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

        if price is not None and price > max_price:
            entry["last_alerted"] = None  # back over budget: alert again next dip
            continue
        if should_alert(price, max_price, entry["last_alerted"],
                        cfg.get("realert_drop", 10)):
            n = cfg.get("tickets_needed", 2)
            notify(
                topic,
                f"Noah Kahan {nice_date(day)}: ${price:.0f} a ticket",
                f"Cheapest ticket is ${price:.0f} (your limit ${max_price}). "
                f"Check there are {n} together. Tap to open SeatGeek.",
                info["url"],
            )
            entry["last_alerted"] = price
            print(f"{day}: alert sent")

    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
