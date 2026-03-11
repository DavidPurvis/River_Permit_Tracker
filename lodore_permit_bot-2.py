#!/usr/bin/env python3
"""
Gates of Lodore Permit Availability Notification Bot
=====================================================
Monitors recreation.gov for permit cancellations on the
"Gates of Lodore, Green River" segment of Dinosaur National Monument.

Usage:
    # One-time check
    python lodore_permit_bot.py

    # Run on a cron schedule (e.g., every 5 minutes)
    */5 * * * * /usr/bin/python3 /path/to/lodore_permit_bot.py

Configuration:
    Set environment variables for notifications, or use a .env file (see .env.example).
"""

import json
import logging
import os
import sys

# Load .env from script directory (so .env works regardless of where you run the script from)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_SCRIPT_DIR, ".env")


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE from .env into os.environ. Used when python-dotenv is not installed."""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key:
                os.environ[key] = value


try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH, override=True)
except ImportError:
    _load_env_file(_ENV_PATH)
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# Recreation.gov permit details
PERMIT_ID = "250014"  # Dinosaur Green And Yampa River Permits
SEGMENT = "Gates of Lodore, Green River"
# Division ID for "Gates of Lodore, Green River" (sparse availability: e.g. May 13–15 then nothing till November).
# 1250014 = Lodore; 371/380 = other segment with more dates. API may return keys as str or int.
LODORE_DIVISION_IDS = {"380"}

# How many months ahead to check (from today)
MONTHS_AHEAD = 6

# State file to track previously-seen availability (avoids duplicate alerts)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lodore_state.json")

# Notification settings (set via environment variables)
# --- Email (SMTP) ---z
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", os.getenv("SMTP_USER"))
SMTP_PASS = os.environ.get("SMTP_PASS", os.getenv("SMTP_PASS"))
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", os.getenv("NOTIFY_EMAIL"))

# --- Discord webhook ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("lodore_bot")

# Recreation.gov API details
BASE_URL = "https://www.recreation.gov"
PERMIT_AVAILABILITY_URL = f"{BASE_URL}/api/permits/{{permit_id}}/availability/month"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": f"{BASE_URL}/permits/{PERMIT_ID}",
}

# ---------------------------------------------------------------------------
# API INTERACTION
# ---------------------------------------------------------------------------

def fetch_availability(permit_id: str, start_date: str) -> Optional[dict]:
    """
    Fetch permit availability for a given month.

    Args:
        permit_id: The recreation.gov permit facility ID.
        start_date: First day of the month in ISO format, e.g. "2026-03-01T00:00:00.000Z"

    Returns:
        JSON response dict or None on failure.
    """
    url = f"{BASE_URL}/api/permits/{permit_id}/availability/month?start_date={start_date}"
    log.debug(f"Fetching: {url}")

    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except HTTPError as e:
        log.error(f"HTTP error {e.code} fetching {url}: {e.reason}")
        # If the permit endpoint format is different, try alternate endpoints
        if e.code == 404:
            return _try_alternate_endpoints(permit_id, start_date)
        return None
    except URLError as e:
        log.error(f"URL error fetching {url}: {e.reason}")
        return None
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        return None


def _try_alternate_endpoints(permit_id: str, start_date: str) -> Optional[dict]:
    """Try alternate API URL patterns that recreation.gov has used."""
    alternates = [
        f"{BASE_URL}/api/permitinyo/{permit_id}/availability?start_date={start_date}",
        f"{BASE_URL}/api/permits/{permit_id}/availability?start_date={start_date}",
        f"{BASE_URL}/api/permitavailability/month?permit_id={permit_id}&start_date={start_date}",
    ]
    for alt_url in alternates:
        log.debug(f"Trying alternate: {alt_url}")
        req = Request(alt_url, headers=HEADERS)
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                log.info(f"Alternate endpoint worked: {alt_url}")
                return data
        except Exception:
            continue
    return None


def find_available_dates(months_ahead: int = MONTHS_AHEAD, debug: bool = False) -> list[dict]:
    """
    Check availability across multiple months and return available dates
    for the Gates of Lodore segment.

    Returns:
        List of dicts with keys: date, segment, remaining (slots), total
    """
    available = []
    now = datetime.now(timezone.utc)

    for month_offset in range(months_ahead + 1):
        # Calculate the first day of each month to query
        year = now.year + (now.month + month_offset - 1) // 12
        month = (now.month + month_offset - 1) % 12 + 1
        start = f"{year}-{month:02d}-01T00:00:00.000Z"

        log.info(f"Checking {year}-{month:02d}...")
        data = fetch_availability(PERMIT_ID, start)

        if not data:
            log.warning(f"No data returned for {year}-{month:02d}")
            continue

        # Debug: dump raw response so we can inspect the API format
        if debug and month_offset == 0:
            debug_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"debug_response_{year}_{month:02d}.json",
            )
            with open(debug_file, "w") as f:
                json.dump(data, f, indent=2)
            log.info(f"Raw API response saved to {debug_file}")

            # Also log the top-level keys for quick inspection
            if isinstance(data, dict):
                log.debug(f"Top-level keys: {list(data.keys())}")
                for k, v in data.items():
                    if isinstance(v, dict):
                        log.debug(f"  '{k}' has {len(v)} entries, sub-keys sample: {list(v.keys())[:3]}")
                    elif isinstance(v, list):
                        log.debug(f"  '{k}' is a list with {len(v)} items")
                    else:
                        log.debug(f"  '{k}' = {repr(v)[:100]}")

        available.extend(_parse_availability(data, year, month))

        # Be nice to the API
        time.sleep(1)

    return available


def _is_lodore_division(div_id) -> bool:
    """True if div_id is Gates of Lodore (excludes Yampa/Deerlodge, e.g. 1250014). API may use str or int."""
    return str(div_id).strip() in LODORE_DIVISION_IDS


def _parse_availability(data: dict, year: int, month: int) -> list[dict]:
    """
    Parse the API response for Gates of Lodore availability only.
    Uses payload.availability filtered by LODORE_DIVISION_IDS so Yampa dates are excluded.
    """
    results = []

    # Only use payload.availability with division filter — Gates of Lodore only.
    # Do NOT use top-level "availability"; it can be aggregate (Lodore + Yampa).
    if "payload" in data:
        payload = data["payload"]
        if isinstance(payload.get("availability"), dict):
            for div_id, div_data in payload["availability"].items():
                if not _is_lodore_division(div_id):
                    continue
                if isinstance(div_data, dict) and "date_availability" in div_data:
                    for date_str, slots in div_data["date_availability"].items():
                        avail = _check_slot_entry(date_str, slots, SEGMENT)
                        if avail:
                            results.append(avail)
        else:
            # Legacy: payload segment-keyed by name
            for segment_key, segment_data in payload.items():
                if not _matches_segment(segment_key, segment_data):
                    continue
                if isinstance(segment_data, dict) and "date_availability" in segment_data:
                    for date_str, slots in segment_data["date_availability"].items():
                        avail = _check_slot_entry(date_str, slots, segment_key)
                        if avail:
                            results.append(avail)

    # Format 3: Flat list of entries
    if isinstance(data, list):
        for entry in data:
            if _matches_segment(entry.get("segment", ""), entry):
                date_str = entry.get("date", entry.get("start_date", ""))
                remaining = entry.get("remaining", entry.get("available", 0))
                if remaining and (remaining == "Available" or (isinstance(remaining, (int, float)) and remaining > 0)):
                    results.append({
                        "date": date_str,
                        "segment": entry.get("segment", SEGMENT),
                        "remaining": remaining,
                        "total": entry.get("total", "?"),
                    })

    # Format 4: Nested under divisions/segments
    for key in ("divisions", "segments", "entrance_quotas"):
        if key in data and isinstance(data.get(key), dict):
            for div_id, div_data in data[key].items():
                seg_name = div_data.get("name", div_data.get("description", div_id)) if isinstance(div_data, dict) else div_id
                if not _matches_segment(seg_name, div_data):
                    continue
                avails = div_data.get("date_availability", div_data.get("availabilities", {})) if isinstance(div_data, dict) else {}
                for date_str, slot_info in (avails.items() if isinstance(avails, dict) else []):
                    avail = _check_slot_entry(date_str, slot_info, seg_name)
                    if avail:
                        results.append(avail)

    # Deduplicate by date (API may return same date from multiple divisions)
    seen_dates = set()
    unique = []
    for r in results:
        # Normalize to YYYY-MM-DD for dedup
        d = r["date"].split("T")[0] if "T" in r["date"] else r["date"]
        if d not in seen_dates:
            seen_dates.add(d)
            unique.append(r)
    return unique


def _matches_segment(name: str, data: dict = None) -> bool:
    """Check if a segment name matches our target (Gates of Lodore)."""
    name_lower = (name or "").lower()
    target_terms = ["lodore", "gates of lodore", "green river"]
    # If there's only one segment or we can't tell, include it
    if not name:
        return True
    return any(term in name_lower for term in target_terms)


def _check_date_entry(date_str: str, info) -> Optional[dict]:
    """Check a single date entry for availability."""
    if isinstance(info, str):
        if info.lower() in ("available", "open"):
            return {
                "date": date_str,
                "segment": SEGMENT,
                "remaining": "Available",
                "total": "?",
            }

    elif isinstance(info, dict):
        remaining = info.get("remaining", info.get("available", 0))
        status = str(info.get("status", "")).lower()

        try:
            remaining_int = int(remaining)
        except (TypeError, ValueError):
            remaining_int = 0

        if remaining_int > 0 or status in ("available", "open"):
            return {
                "date": date_str,
                "segment": info.get("segment", SEGMENT),
                "remaining": remaining if remaining_int > 0 else "Available",
                "total": info.get("total", "?"),
            }

    return None


def _check_slot_entry(date_str: str, slots, segment_name: str) -> Optional[dict]:
    """Check a slot/quota entry for availability."""
    if isinstance(slots, dict):
        remaining = slots.get("remaining", slots.get("available", 0))
        total = slots.get("total", slots.get("capacity", "?"))
        if remaining and int(remaining) > 0:
            return {
                "date": date_str,
                "segment": segment_name,
                "remaining": remaining,
                "total": total,
            }
    elif isinstance(slots, (int, float)) and slots > 0:
        return {
            "date": date_str,
            "segment": segment_name,
            "remaining": int(slots),
            "total": "?",
        }
    return None


# ---------------------------------------------------------------------------
# STATE MANAGEMENT (to avoid duplicate notifications)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load previously seen available dates."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"seen_dates": [], "last_check": None}
    return {"seen_dates": [], "last_check": None}


def save_state(state: dict):
    """Persist state to disk."""
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_new_dates(available: list[dict], state: dict) -> list[dict]:
    """Filter out dates we've already notified about."""
    seen = set(state.get("seen_dates", []))
    new = [d for d in available if d["date"] not in seen]
    return new


# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------

def _format_date_readable(date_str: str) -> str:
    """Convert ISO date to readable e.g. Saturday, March 15, 2026."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %d, %Y")
    except Exception:
        return date_str


def format_message(new_dates: list[dict]) -> str:
    """Format a human-readable notification message (plain text for Slack, etc.)."""
    lines = [
        "🚨 GATES OF LODORE PERMIT ALERT! 🚨",
        "",
        f"Found {len(new_dates)} new available date(s):",
        "",
    ]
    for d in sorted(new_dates, key=lambda x: x["date"]):
        lines.append(f"  📅 {_format_date_readable(d['date'])}  —  Remaining: {d['remaining']}")
    lines.extend([
        "",
        f"🔗 Book now: {BASE_URL}/permits/{PERMIT_ID}",
        "",
        "⚡ Cancelled permits go fast — book ASAP!",
    ])
    return "\n".join(lines)


def format_message_html(new_dates: list[dict]) -> str:
    """Format a styled HTML email with links."""
    book_url = f"{BASE_URL}/permits/{PERMIT_ID}"
    permit_info_url = f"{BASE_URL}/permits/{PERMIT_ID}/permit-details"
    sorted_dates = sorted(new_dates, key=lambda x: x["date"])

    rows = "".join(
        f"""
        <tr>
            <td style="padding:12px 16px; border-bottom:1px solid #e5e7eb; color:#1f2937;">
                {_format_date_readable(d["date"])}
            </td>
            <td style="padding:12px 16px; border-bottom:1px solid #e5e7eb; text-align:center;">
                <span style="background:#10b981; color:white; padding:4px 10px; border-radius:6px; font-weight:600;">
                    {d["remaining"]} available
                </span>
            </td>
        </tr>"""
        for d in sorted_dates
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gates of Lodore Permit Alert</title>
</head>
<body style="margin:0; padding:0; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color:#f3f4f6;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6; padding:24px 16px;">
        <tr>
            <td align="center" style="padding:20px 0;">
                <table role="presentation" width="100%" style="max-width:520px; margin:0 auto; background:white; border-radius:12px; box-shadow:0 1px 3px rgba(0,0,0,0.08); overflow:hidden;">
                    <tr>
                        <td style="background:linear-gradient(135deg, #047857 0%, #065f46 100%); padding:28px 32px; text-align:center;">
                            <h1 style="margin:0; color:white; font-size:22px; font-weight:700; letter-spacing:0.5px;">
                                🏕️ Gates of Lodore Permit Alert
                            </h1>
                            <p style="margin:10px 0 0; color:rgba(255,255,255,0.9); font-size:14px;">
                                New availability on the Green River — Dinosaur National Monument
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:28px 32px;">
                            <p style="margin:0 0 16px; color:#374151; font-size:15px; line-height:1.5;">
                                <strong>{len(new_dates)} new date(s)</strong> with permits available. Cancellations go fast — book soon.
                            </p>
                            <table role="presentation" width="100%" cellspacing="0" style="border:1px solid #e5e7eb; border-radius:8px; margin:20px 0;">
                                <thead>
                                    <tr style="background:#f9fafb;">
                                        <th style="padding:12px 16px; text-align:left; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; color:#6b7280;">Date</th>
                                        <th style="padding:12px 16px; text-align:center; font-size:12px; text-transform:uppercase; letter-spacing:0.5px; color:#6b7280;">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows}
                                </tbody>
                            </table>
                            <p style="margin:24px 0 16px; color:#6b7280; font-size:14px;">
                                Use the links below to book or learn more:
                            </p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding:8px 0;">
                                        <a href="{book_url}" style="display:inline-block; background:#059669; color:white; text-decoration:none; padding:14px 24px; border-radius:8px; font-weight:600; font-size:15px;">
                                            Book permit on Recreation.gov →
                                        </a>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding:8px 0;">
                                        <a href="{permit_info_url}" style="color:#059669; text-decoration:none; font-size:14px;">
                                            Permit details &amp; availability calendar
                                        </a>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding:8px 0;">
                                        <a href="{BASE_URL}" style="color:#6b7280; text-decoration:none; font-size:14px;">
                                            Recreation.gov home
                                        </a>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin:28px 0 0; padding-top:20px; border-top:1px solid #e5e7eb; color:#9ca3af; font-size:12px;">
                                You received this because you’re running the Gates of Lodore permit tracker. Permits are limited; book as soon as you can.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def notify_email(message: str, new_dates: list[dict] | None = None):
    """Send notification via email (SMTP). Uses HTML body with links when new_dates provided."""
    missing = []
    if not SMTP_USER:
        missing.append("SMTP_USER")
    if not SMTP_PASS:
        missing.append("SMTP_PASS")
    if not NOTIFY_EMAIL:
        missing.append("NOTIFY_EMAIL")
    if missing:
        log.info("Email not sent: missing %s (set in .env or environment)", ", ".join(missing))
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = "🚨 Gates of Lodore Permit Available!"
    msg.attach(MIMEText(message, "plain", "utf-8"))
    if new_dates:
        html = format_message_html(new_dates)
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log.info("Email sent to %s", NOTIFY_EMAIL)
        return True
    except Exception as e:
        log.error("Email failed: %s", e)
        return False


def notify_discord(message: str):
    """Send notification via Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        log.debug("Discord not configured, skipping.")
        return

    # Discord limits content to 2000 chars; requires a User-Agent or some clients get 403
    content = message[:2000] if len(message) > 2000 else message
    payload = json.dumps({"content": content}).encode("utf-8")
    req = Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "LodorePermitBot/1.0",
        },
        method="POST",
    )
    try:
        urlopen(req, timeout=10)
        log.info("Discord notification sent.")
    except Exception as e:
        log.error("Discord failed: %s", e)


def send_notifications(message: str, new_dates: list[dict] | None = None):
    """Send notification through all configured channels."""
    notify_email(message, new_dates=new_dates)
    notify_discord(message)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    debug = "--debug" in sys.argv

    if debug:
        logging.getLogger("lodore_bot").setLevel(logging.DEBUG)

    log.info("=" * 60)
    log.info("Gates of Lodore Permit Bot — Starting check")
    log.info(f"Permit ID: {PERMIT_ID} | Segment: {SEGMENT}")
    log.info("=" * 60)

    # Load previous state
    state = load_state()

    # Fetch current availability
    available = find_available_dates(debug=debug)

    if not available:
        log.info("No available dates found. All booked up.")
        if debug:
            log.info("Check the debug_response_*.json files to inspect raw API output.")
        save_state(state)
        return

    log.info(f"Found {len(available)} total available date(s).")
    for d in available:
        log.info(f"  Available: {d['date']} — Remaining: {d['remaining']}")

    # Determine which dates are NEW (not previously seen)
    new_dates = get_new_dates(available, state)

    if new_dates:
        log.info(f"🚨 {len(new_dates)} NEW date(s) found!")
        message = format_message(new_dates)
        print(message)
        send_notifications(message, new_dates=new_dates)

        # Update state with newly seen dates
        state["seen_dates"] = list(
            set(state.get("seen_dates", []) + [d["date"] for d in new_dates])
        )
    else:
        log.info("No new dates since last check.")

    # Prune state: drop past dates and dates that are no longer available (so we re-alert if they open again)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _norm(s: str) -> str:
        return s.split("T")[0] if "T" in s else s

    current_available = {_norm(d["date"]) for d in available}
    state["seen_dates"] = [
        d for d in state["seen_dates"]
        if _norm(d) >= today and _norm(d) in current_available
    ]

    save_state(state)
    log.info("Check complete.")


def main_test_email():
    """Send a single test email to verify SMTP config. Usage: python lodore_permit_bot-2.py --test-email"""
    if not all([SMTP_USER, SMTP_PASS, NOTIFY_EMAIL]):
        missing = [n for n, v in [("SMTP_USER", SMTP_USER), ("SMTP_PASS", SMTP_PASS), ("NOTIFY_EMAIL", NOTIFY_EMAIL)] if not v]
        print(f"Missing: {', '.join(missing)}. Set them in .env or environment and try again.")
        sys.exit(1)
    msg = "This is a test from the Gates of Lodore Permit Bot. If you got this, email notifications are working."
    log.info("Sending test email to %s...", NOTIFY_EMAIL)
    if notify_email(msg):
        print("Test email sent. Check your inbox (and spam folder).")
    else:
        print("Sending failed. Check the log messages above for details.")
        sys.exit(1)


if __name__ == "__main__":
    if "--test-email" in sys.argv:
        main_test_email()
    else:
        main()
