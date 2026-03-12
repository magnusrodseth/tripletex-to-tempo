# tripletex-to-tempo

Simple Python script that syncs hours from a Tripletex monthly CSV export to Tempo (Atlassian).

## Architecture

Single-file Python 3 script (`tripletex_to_tempo.py`) with zero external dependencies. Uses only the standard library (`csv`, `json`, `urllib`, `argparse`).

## Key design decisions

- **Upsert behavior**: Before posting, the script fetches existing worklogs from Tempo for the user/date range. It skips days that already have a synced worklog (matched by description "Synced from Tripletex") and logs info. It never crashes on duplicates.
- **CSV format**: Tripletex exports monthly overviews as semicolon-delimited, ISO-8859-1-encoded CSV files. The script auto-detects encoding.
- **No API key for Tripletex**: We use CSV export instead of the Tripletex API to avoid the complexity of obtaining API credentials.

## Running

```bash
export TEMPO_API_TOKEN="..."
python3 tripletex_to_tempo.py --csv "file.csv" --issue TPRIBO-123 --account-id "abc123" --dry-run
```

## Secrets

The Tempo API token must come from the `TEMPO_API_TOKEN` environment variable. Never hardcode tokens.
