# tripletex-to-tempo

Sync hours from Tripletex to Tempo (Atlassian). Reads a monthly CSV export from Tripletex and posts worklogs to Tempo via their REST API.

**Zero dependencies** -- uses only Python 3 standard library.

## How it works

1. You export a monthly overview CSV from Tripletex
2. The script parses it and filters for the activity you want (default: "Konsulentbistand")
3. It checks Tempo for existing worklogs to avoid duplicates
4. It creates worklogs in Tempo for each day that hasn't been logged yet

## Setup

### 1. Get your Tempo API token

1. Go to **Tempo** > **Settings** (gear icon) > **API Integration**
2. Click **New Token**
3. Give it a name, select the scopes you need (at minimum: **Manage Worklogs**)
4. Copy the token

### 2. Find your Atlassian account ID

While logged into Jira, visit:

```
https://YOUR-DOMAIN.atlassian.net/rest/api/3/myself
```

Look for the `accountId` field in the JSON response.

### 3. Set up environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
TEMPO_API_TOKEN=your-tempo-api-token
ATLASSIAN_ACCOUNT_ID=your-account-id
JIRA_ISSUE_KEY=your-jira-issue-key
```

The script auto-loads `.env` on startup, so no need to `source` or `export` manually.

## Exporting CSV from Tripletex

1. Log in to [Tripletex](https://tripletex.no)
2. Go to **Timeliste** (Time sheet) in the left menu
3. Click **Rapporter** (Reports)
4. Select **Timeliste - Oversikt** (Time sheet - Overview)
5. Set the period to the month you want to sync
6. Set **Vis per** (Show per) to **Dag** (Day)
7. Click **Vis rapport** (Show report)
8. Click the **download icon** and choose **CSV**

The downloaded file will be named something like `Månedsoversikt - (Mars 2026).csv`.

## Usage

With `.env` configured, you only need to pass the CSV file:

```bash
# Preview first (always recommended)
python3 tripletex_to_tempo.py \
  --csv "Månedsoversikt - (Mars 2026).csv" \
  --dry-run

# Run for real
python3 tripletex_to_tempo.py \
  --csv "Månedsoversikt - (Mars 2026).csv"
```

You can still override any `.env` value via CLI flags:

```bash
python3 tripletex_to_tempo.py \
  --csv "file.csv" \
  --issue "OTHER-99" \
  --account-id "different-id"
```

### Options

| Flag           | Required | Default            | Description                                    |
| -------------- | -------- | ------------------ | ---------------------------------------------- |
| `--csv`        | Yes      |                    | Path to the Tripletex monthly overview CSV     |
| `--issue`      | Yes      |                    | Jira issue key to log hours against            |
| `--account-id` | Yes      |                    | Your Atlassian account ID                      |
| `--activity`   | No       | `Konsulentbistand` | Tripletex activity name to filter on           |
| `--dry-run`    | No       | `false`            | Preview without posting                        |

## Upsert behavior

The script is safe to run multiple times for the same period:

- **Already logged (same hours)**: Skipped with info message
- **Already logged (different hours)**: Skipped with warning. Delete the worklog in Tempo first if you want to re-sync.
- **Not yet logged**: Created normally

The script checks **all** worklogs for the target issue on each date, regardless of how they were created (manually or via sync). This prevents duplicates even if you've already logged hours manually in Tempo.
