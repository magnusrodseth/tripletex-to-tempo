#!/usr/bin/env python3
"""
Tripletex to Tempo sync script.

Reads a monthly overview CSV exported from Tripletex and posts
worklogs to Tempo (Atlassian) for a given Jira issue.

The script implements upsert behavior: it checks for existing worklogs
before posting and skips days that are already logged.
"""

import csv
import json
import os
import re
import sys
import argparse
import time as time_module
from datetime import date
from urllib.request import Request, urlopen
from urllib.error import HTTPError

TEMPO_API_BASE = "https://api.tempo.io/4"
SYNC_DESCRIPTION = "Synced from Tripletex"

MONTH_NAMES = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}


def detect_encoding(filepath: str) -> str:
    """Detect file encoding by trying common encodings."""
    for encoding in ("utf-8", "iso-8859-1", "cp1252"):
        try:
            with open(filepath, "r", encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def parse_month_year_from_filename(filepath: str) -> tuple[int | None, int | None]:
    """Extract year and month from the CSV filename."""
    basename = os.path.basename(filepath).lower()

    month = None
    for name, num in MONTH_NAMES.items():
        if name in basename:
            month = num
            break

    year = None
    year_match = re.search(r"20\d{2}", basename)
    if year_match:
        year = int(year_match.group())

    return year, month


def parse_tripletex_csv(filepath: str, activity_filter: str) -> list[dict]:
    """
    Parse Tripletex monthly overview CSV.

    Returns list of {"date": "YYYY-MM-DD", "hours": float, "seconds": int}.
    """
    encoding = detect_encoding(filepath)

    with open(filepath, "r", encoding=encoding) as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)

    # Find where day columns start (first column named "1")
    day_start_idx = None
    for i, col in enumerate(header):
        if col.strip() == "1":
            day_start_idx = i
            break

    if day_start_idx is None:
        print("ERROR: Could not find day columns in CSV header.")
        print(f"Header: {header}")
        sys.exit(1)

    year, month = parse_month_year_from_filename(filepath)

    if not year or not month:
        print(f"Could not detect month/year from filename: {os.path.basename(filepath)}")
        year_input = input("Enter year (e.g. 2026): ").strip()
        month_input = input("Enter month number (1-12): ").strip()
        year, month = int(year_input), int(month_input)

    print(f"Detected period: {year}-{month:02d}")

    entries = []
    with open(filepath, "r", encoding=encoding) as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # skip header

        for row in reader:
            if len(row) < day_start_idx + 1:
                continue

            activity_name = row[5].strip().strip('"') if len(row) > 5 else ""

            if activity_name != activity_filter:
                continue

            employee = row[3].strip().strip('"') if len(row) > 3 else "Unknown"
            print(f"Found matching row: {employee}, {activity_name}")

            for day_num in range(1, 32):
                col_idx = day_start_idx + day_num - 1
                if col_idx >= len(row):
                    break

                raw = row[col_idx].strip().strip('"').replace(",", ".")
                if not raw or raw == "0.00" or raw == "0":
                    continue

                try:
                    hours = float(raw)
                except ValueError:
                    continue

                if hours <= 0:
                    continue

                try:
                    d = date(year, month, day_num)
                except ValueError:
                    continue

                entries.append({
                    "date": d.isoformat(),
                    "hours": hours,
                    "seconds": int(hours * 3600),
                })

    return entries


def format_hours(hours: float) -> str:
    """Format hours as 'Xh Ym'."""
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}h {m}m" if m else f"{h}h"


def tempo_request(method: str, path: str, token: str,
                  data: dict | None = None) -> dict | list | None:
    """Make an authenticated request to the Tempo API."""
    url = f"{TEMPO_API_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data else None

    req = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )

    resp = urlopen(req)
    raw = resp.read()
    if not raw:
        return None
    return json.loads(raw)


def fetch_existing_worklogs(account_id: str, from_date: str, to_date: str,
                            token: str) -> list[dict]:
    """
    Fetch all existing worklogs for the user in the given date range.

    Handles pagination automatically.
    """
    all_worklogs = []
    offset = 0
    limit = 1000

    while True:
        path = (
            f"/worklogs/user/{account_id}"
            f"?from={from_date}&to={to_date}"
            f"&offset={offset}&limit={limit}"
        )
        result = tempo_request("GET", path, token)
        worklogs = result.get("results", [])
        all_worklogs.extend(worklogs)

        metadata = result.get("metadata", {})
        total = metadata.get("count", 0)

        if offset + len(worklogs) >= total or not worklogs:
            break
        offset += len(worklogs)

    return all_worklogs


def build_existing_lookup(worklogs: list[dict]) -> dict[str, list[dict]]:
    """
    Build a lookup of existing worklogs by date.

    Returns {date_str: [worklog, ...]} for worklogs synced by this script.
    """
    lookup: dict[str, list[dict]] = {}
    for wl in worklogs:
        desc = wl.get("description") or ""
        if SYNC_DESCRIPTION not in desc:
            continue
        d = wl.get("startDate", "")
        if d not in lookup:
            lookup[d] = []
        lookup[d].append(wl)
    return lookup


def post_to_tempo(entries: list[dict], issue_key: str, account_id: str,
                  token: str, dry_run: bool = False) -> None:
    """Post worklogs to Tempo API v4 with upsert behavior."""
    if not entries:
        print("No entries to post.")
        return

    # Fetch existing worklogs to implement upsert
    existing_lookup: dict[str, list[dict]] = {}
    if not dry_run and token and account_id:
        dates = [e["date"] for e in entries]
        from_date = min(dates)
        to_date = max(dates)

        print(f"Checking existing worklogs ({from_date} to {to_date})...")
        try:
            existing = fetch_existing_worklogs(account_id, from_date, to_date, token)
            existing_lookup = build_existing_lookup(existing)
            synced_count = sum(len(v) for v in existing_lookup.values())
            print(f"Found {synced_count} previously synced worklog(s)\n")
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"WARNING: Could not fetch existing worklogs ({e.code}): {body[:200]}")
            print("Proceeding without duplicate check\n")

    label = "DRY RUN" if dry_run else "Posting"
    print(f"{label}: {len(entries)} worklogs to {issue_key}\n")

    created = 0
    skipped = 0
    failed = 0

    for entry in entries:
        time_str = format_hours(entry["hours"])
        d = entry["date"]

        # Check for existing worklog on this date
        if d in existing_lookup:
            existing_seconds = sum(
                wl.get("timeSpentSeconds", 0) for wl in existing_lookup[d]
            )
            if existing_seconds == entry["seconds"]:
                print(f"  SKIP {d}  {time_str:>6s}  already logged ({existing_seconds}s)")
                skipped += 1
                continue
            else:
                existing_h = format_hours(existing_seconds / 3600)
                print(
                    f"  SKIP {d}  {time_str:>6s}  "
                    f"already has {existing_h} synced (different from CSV). "
                    f"Delete in Tempo first to re-sync."
                )
                skipped += 1
                continue

        if dry_run:
            print(f"  POST {d}  {time_str:>6s}  -> {issue_key}")
            created += 1
            continue

        payload = {
            "issueKey": issue_key,
            "timeSpentSeconds": entry["seconds"],
            "startDate": entry["date"],
            "startTime": "09:00:00",
            "description": SYNC_DESCRIPTION,
            "authorAccountId": account_id,
        }

        try:
            result = tempo_request("POST", "/worklogs", token, payload)
            wl_id = result.get("tempoWorklogId", "?")
            print(f"    OK {d}  {time_str:>6s}  -> {issue_key}  (worklog #{wl_id})")
            created += 1
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  FAIL {d}  {time_str:>6s}  -> {e.code}: {body[:200]}")
            failed += 1

        # Respect Tempo rate limit (5 req/s)
        time_module.sleep(0.25)

    print(f"\nDone: {created} created, {skipped} skipped, {failed} failed")


def main():
    parser = argparse.ArgumentParser(
        description="Sync Tripletex hours to Tempo (Atlassian)"
    )
    parser.add_argument(
        "--csv", required=True,
        help="Path to the Tripletex monthly overview CSV file"
    )
    parser.add_argument(
        "--issue", required=True,
        help="Jira issue key to log against (e.g. TPRIBO-123)"
    )
    parser.add_argument(
        "--activity", default="Konsulentbistand",
        help="Tripletex activity to filter on (default: Konsulentbistand)"
    )
    parser.add_argument(
        "--account-id", required=True,
        help="Your Atlassian account ID"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be posted without actually posting"
    )
    args = parser.parse_args()

    token = os.environ.get("TEMPO_API_TOKEN", "")
    if not token and not args.dry_run:
        print("ERROR: Set TEMPO_API_TOKEN environment variable.")
        print("  export TEMPO_API_TOKEN='your-tempo-api-token'")
        sys.exit(1)

    # Parse CSV
    print(f"Reading: {args.csv}")
    print(f"Activity filter: {args.activity}\n")

    entries = parse_tripletex_csv(args.csv, args.activity)

    if not entries:
        print("No matching entries found. Check your --activity filter.")
        print("Available activities in the file:")
        enc = detect_encoding(args.csv)
        with open(args.csv, "r", encoding=enc) as f:
            reader = csv.reader(f, delimiter=";")
            next(reader)
            activities = set()
            for row in reader:
                if len(row) > 5:
                    a = row[5].strip().strip('"')
                    if a:
                        activities.add(a)
            for a in sorted(activities):
                print(f"  - {a}")
        sys.exit(1)

    total_hours = sum(e["hours"] for e in entries)
    print(f"\nFound {len(entries)} days, total: {total_hours} hours\n")

    post_to_tempo(entries, args.issue, args.account_id, token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
