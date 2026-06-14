"""
747 Movements Check — runs on GitHub Actions, posts to Slack.

What it does (once per run):
  1. Asks the AeroDataBox API for the next ~24 hours of flights at AKL and SYD
     (arrivals + departures, both directions).
  2. Filters to Boeing 747 variants using the aircraft model field.
  3. Posts a single summary message to a Slack incoming webhook.

Environment variables expected (set as GitHub Action secrets):
  RAPIDAPI_KEY        — your RapidAPI key after subscribing to AeroDataBox
  SLACK_WEBHOOK_URL   — Slack incoming webhook URL for the channel where alerts should land

Run locally for testing:
  RAPIDAPI_KEY=... SLACK_WEBHOOK_URL=... python check_747s.py
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------- configuration ----------

# AeroDataBox returns flights in chunks of up to 12 hours. We do 2 chunks per
# airport per run for a 24 h lookahead. With the free RapidAPI BASIC tier
# (~100 calls/month) twice-daily runs at 4 calls/run = ~240 calls/month, you
# will need the PRO plan (~$10/month). Drop to LOOK_AHEAD_HOURS=12 to halve it.
LOOK_AHEAD_HOURS = 24
CHUNK_HOURS = 12

AIRPORTS = [
    # Airport local time offsets are used because AeroDataBox accepts naive
    # local times in the URL path. NZ is UTC+12 (NZST) / +13 (NZDT in summer).
    # SYD is UTC+10 (AEST) / +11 (AEDT in summer). Adjust if you care about
    # daylight-saving precision; an hour off the window edge is harmless.
    {"name": "Auckland (AKL)", "icao": "NZAA", "flag": "\U0001F1F3\U0001F1FF", "tz_offset_hours": 12},
    {"name": "Sydney (SYD)",   "icao": "YSSY", "flag": "\U0001F1E6\U0001F1FA", "tz_offset_hours": 10},
]

# Match every known 747 aircraft code (IATA + ICAO + bare-number):
#   B741..B748, B74F, B74R, B74S       (ICAO style)
#   74A..74Z, 741..748                 (IATA style — 74Y, 74N, 74E, etc.)
#   747                                 (generic)
SEVEN_FOUR_SEVEN_RE = re.compile(r"\b(?:B?74[A-Z0-9]|747)\b", re.IGNORECASE)

RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"


# ---------- API call ----------

def fetch_window(icao: str, dt_from_local: datetime, dt_to_local: datetime) -> dict:
    """Fetch arrivals + departures at one airport for one local-time window.

    AeroDataBox endpoint:
      GET /flights/airports/icao/{icao}/{fromLocal}/{toLocal}
    """
    fmt = "%Y-%m-%dT%H:%M"
    path = f"/flights/airports/icao/{icao}/{dt_from_local.strftime(fmt)}/{dt_to_local.strftime(fmt)}"
    query = urllib.parse.urlencode({
        "withLeg": "true",
        "direction": "Both",
        "withCancelled": "false",
        "withCodeshared": "false",
        "withCargo": "true",
        "withPrivate": "false",
        "withLocation": "false",
    })
    url = f"https://{RAPIDAPI_HOST}{path}?{query}"

    req = urllib.request.Request(url, headers={
        "X-RapidAPI-Key": os.environ["RAPIDAPI_KEY"],
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ---------- 747 detection ----------

def flight_aircraft_text(flight: dict) -> str:
    """Pull every string that might describe the aircraft into one blob."""
    aircraft = flight.get("aircraft") or {}
    return " ".join(filter(None, [
        aircraft.get("model"),       # e.g. "Boeing 747-400F"
        aircraft.get("reg"),         # e.g. "9V-SFI"
        aircraft.get("modeS"),       # mode-S hex
    ]))


def is_747(flight: dict) -> bool:
    blob = flight_aircraft_text(flight)
    return bool(SEVEN_FOUR_SEVEN_RE.search(blob))


# ---------- formatting ----------

def parse_iso(s: str) -> datetime | None:
    """Parse an AeroDataBox time string like '2026-05-20 02:30+12:00'."""
    if not s:
        return None
    # AeroDataBox sometimes returns space separators; normalise.
    iso = s.replace(" ", "T")
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def flight_row(flight: dict, direction: str) -> str:
    """One Markdown table row for one matched flight."""
    number = flight.get("number") or "?"
    airline = (flight.get("airline") or {}).get("name") or "?"
    aircraft = flight.get("aircraft") or {}
    model = aircraft.get("model") or "?"
    reg = aircraft.get("reg") or "—"
    status = flight.get("status") or "?"

    if direction == "arr":
        other = flight.get("departure") or {}
        other_label = "from"
    else:
        other = flight.get("arrival") or {}
        other_label = "to"
    other_airport = (other.get("airport") or {}).get("name") or "?"

    times = flight.get("movement") or flight  # fallback in case of shape differences
    sched = parse_iso(((times.get("scheduledTime") or {}).get("local")
                       if isinstance(times.get("scheduledTime"), dict) else None))
    when = sched.strftime("%a %d %b %H:%M") if sched else "?"

    return f"| {when} | {number} | {other_label} {other_airport} | {airline} | {model} | {reg} | {status} |"


def format_message(results: dict) -> str:
    """Build the full Slack message from the per-airport results."""
    now_nz = datetime.now(timezone(timedelta(hours=12))).strftime("%a %d %b %H:%M NZST")
    total = sum(len(v["arrivals"]) + len(v["departures"]) for v in results.values())

    lines = [f"*747 movements check* — {now_nz}", f"*Total 747 movements detected: {total}*", ""]

    for ap_name, data in results.items():
        flag = data["flag"]
        lines.append(f"{flag} *{ap_name}* — window {data['window']}")
        for direction, label in (("arrivals", "Arrivals"), ("departures", "Departures")):
            flights = data[direction]
            if not flights:
                lines.append(f"  • {label}: _No 747 movements in this window._")
            else:
                lines.append(f"  • {label}: *{len(flights)} match(es)*")
                lines.append("")
                lines.append("| When (local) | Flight | From/To | Airline | Aircraft | Reg | Status |")
                lines.append("|---|---|---|---|---|---|---|")
                for f in flights:
                    lines.append(flight_row(f, "arr" if direction == "arrivals" else "dep"))
                lines.append("")
        lines.append("")

    if total == 0:
        lines.append("_No 747 traffic in any window this run. This is normal — 747 movements at AKL/SYD are rare and mostly freight._")

    return "\n".join(lines)


# ---------- Slack ----------

def post_to_slack(text: str) -> None:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        os.environ["SLACK_WEBHOOK_URL"],
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Slack webhook returned {resp.status}")


# ---------- main ----------

def main() -> int:
    for key in ("RAPIDAPI_KEY", "SLACK_WEBHOOK_URL"):
        if not os.environ.get(key):
            print(f"ERROR: env var {key} is not set", file=sys.stderr)
            return 1

    results: dict[str, dict] = {}

    for airport in AIRPORTS:
        local_now = datetime.now(timezone(timedelta(hours=airport["tz_offset_hours"]))).replace(tzinfo=None)
        arrivals: list[dict] = []
        departures: list[dict] = []

        for h in range(0, LOOK_AHEAD_HOURS, CHUNK_HOURS):
            t0 = local_now + timedelta(hours=h)
            t1 = local_now + timedelta(hours=h + CHUNK_HOURS)
            try:
                payload = fetch_window(airport["icao"], t0, t1)
            except urllib.error.HTTPError as e:
                print(f"WARN: {airport['icao']} {t0}-{t1} fetch failed: HTTP {e.code}", file=sys.stderr)
                continue
            except Exception as e:
                print(f"WARN: {airport['icao']} {t0}-{t1} fetch failed: {e}", file=sys.stderr)
                continue

            for f in payload.get("arrivals", []):
                if is_747(f):
                    arrivals.append(f)
            for f in payload.get("departures", []):
                if is_747(f):
                    departures.append(f)

        window_start = local_now.strftime("%H:%M %d %b")
        window_end = (local_now + timedelta(hours=LOOK_AHEAD_HOURS)).strftime("%H:%M %d %b")
        results[airport["name"]] = {
            "flag": airport["flag"],
            "window": f"{window_start} → {window_end} local",
            "arrivals": arrivals,
            "departures": departures,
        }

    message = format_message(results)
    print(message)  # also visible in the GitHub Actions log
    post_to_slack(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
