#!/usr/bin/env python3
"""
Global Entry appointment monitor for Charlotte-Douglas Airport (location 14321).
Polls the TTP CBP scheduler API and alerts when slots open up.

When run with no args (e.g. by a cron job): checks once and writes result to JSONL.
Interactive use: pass --loop to poll continuously.
"""

import time
import datetime
import argparse
import subprocess
import platform
import json
import httpx

LOCATION_ID = 14321
LOCATION_NAME = "Charlotte-Douglas Airport"
API_URL = (
    "https://ttp.cbp.dhs.gov/schedulerapi/slots"
    f"?orderBy=soonest&limit=10&locationId={LOCATION_ID}&minimum=1"
)
DATA_FILE = "/home/lawrence/tracking-everything/tracked_data/appt-mon.jsonl"
DEFAULT_INTERVAL_SECONDS = 60


def fetch_slots() -> list[dict]:
    resp = httpx.get(API_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()


def format_slot(slot: dict) -> str:
    ts = slot.get("startTimestamp", "")
    try:
        dt = datetime.datetime.fromisoformat(ts)
        return dt.strftime("%A, %B %d %Y at %I:%M %p")
    except (ValueError, TypeError):
        return ts


def desktop_notify(title: str, message: str) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                check=True,
            )
        elif system == "Linux":
            subprocess.run(["notify-send", title, message], check=True)
        elif system == "Windows":
            from win10toast import ToastNotifier  # type: ignore
            ToastNotifier().show_toast(title, message, duration=10)
    except Exception:
        pass  # notification is best-effort


def check_once(verbose: bool = True) -> list[dict]:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        slots = fetch_slots()
    except httpx.RequestError as e:
        print(f"[{now_str}] Request error: {e}")
        return []

    if slots:
        print(f"\n[{now_str}] *** {len(slots)} SLOT(S) AVAILABLE at {LOCATION_NAME} ***")
        for slot in slots:
            print(f"  -> {format_slot(slot)}")
        desktop_notify(
            "Global Entry Slot Available!",
            f"{len(slots)} slot(s) at {LOCATION_NAME}\nFirst: {format_slot(slots[0])}",
        )
    elif verbose:
        print(f"[{now_str}] No slots available at {LOCATION_NAME}")

    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "url": API_URL,
        "location": LOCATION_NAME,
        "slots_available": len(slots),
        "slots": [{"time": format_slot(s), "raw": s.get("startTimestamp", "")} for s in slots],
    }
    try:
        with open(DATA_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"Warning: could not write to data file: {e}")

    return slots


def run_loop(interval: int, quiet: bool) -> None:
    print(f"Monitoring {LOCATION_NAME} every {interval}s. Press Ctrl+C to stop.\n")
    while True:
        check_once(verbose=not quiet)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor Global Entry appointment availability at Charlotte-Douglas Airport"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Poll continuously (interactive use); default is check-once for cron jobs",
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Check interval in seconds when --loop is set (default: {DEFAULT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help='Suppress "no slots" messages; only print when slots are found',
    )
    args = parser.parse_args()

    if args.loop:
        try:
            run_loop(args.interval, args.quiet)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        check_once(verbose=True)


if __name__ == "__main__":
    main()
