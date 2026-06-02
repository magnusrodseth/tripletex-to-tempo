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

### 3. Get your Atlassian (Jira) API token

This is used to resolve Jira issue keys (e.g. `HEIHU-1`) to numeric IDs.

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**
3. Give it a label and copy the token

### 4. Set up environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
TEMPO_API_TOKEN=your-tempo-api-token
ATLASSIAN_SITE=your-domain.atlassian.net
ATLASSIAN_EMAIL=your-email@example.com
ATLASSIAN_API_TOKEN=your-jira-api-token
ATLASSIAN_ACCOUNT_ID=your-account-id
JIRA_ISSUE_KEY=your-jira-issue-key
```

| Variable | Where to find it |
| --- | --- |
| `TEMPO_API_TOKEN` | Tempo > Settings > API Integration > New Token |
| `ATLASSIAN_SITE` | Your Jira domain, e.g. `acme.atlassian.net` (no `https://`) |
| `ATLASSIAN_EMAIL` | The email you log in to Jira with |
| `ATLASSIAN_API_TOKEN` | https://id.atlassian.com/manage-profile/security/api-tokens |
| `ATLASSIAN_ACCOUNT_ID` | Visit `https://YOUR-DOMAIN.atlassian.net/rest/api/3/myself` and copy the `accountId` field |
| `JIRA_ISSUE_KEY` | The issue to log hours against, e.g. `HEIHU-1` |

The script auto-loads `.env` on startup, so no need to `source` or `export` manually.

## Exporting CSV from Tripletex

1. Log in to [Tripletex](https://tripletex.no)
2. Go to **Timeliste** (Time sheet) in the left menu
3. Click **Rapporter** (Reports)
4. Select **Månedsoversikt** (Monthly overview)
5. Set the period to the month you want to sync
6. Click **Vis rapport** (Show report)
7. Click the **download icon** and choose **CSV**

**Important**: You must use the **Månedsoversikt** report — not "Timeoversikt" or other formats. The script expects one row per activity with day-number columns (1, 2, 3, ... 30/31).

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

### Sync without a CSV (from JSON / the Tripletex MCP)

If you already have the hours as data (for example read from the Tripletex
MCP), skip the CSV export entirely and pipe a JSON array of `{date, hours}`
to `--stdin`. The caller filters to the chargeable activity first; the script
applies the same upsert/skip behavior as the CSV path.

```bash
echo '[{"date":"2026-06-01","hours":7.5},{"date":"2026-06-02","hours":7.5}]' \
  | python3 tripletex_to_tempo.py --stdin --dry-run

# Drop --dry-run to post for real
```

### Options

| Flag           | Required | Default            | Description                                    |
| -------------- | -------- | ------------------ | ---------------------------------------------- |
| `--csv`        | One of¹  |                    | Path to the Tripletex monthly overview CSV     |
| `--stdin`      | One of¹  | `false`            | Read entries as a JSON array of `{date, hours}` from stdin |
| `--issue`      | Yes      |                    | Jira issue key to log hours against            |
| `--account-id` | Yes      |                    | Your Atlassian account ID                      |
| `--activity`   | No       | `Konsulentbistand` | Tripletex activity name to filter on (CSV mode only) |
| `--dry-run`    | No       | `false`            | Preview without posting                        |

¹ Provide exactly one input source: `--csv` **or** `--stdin`.

## Upsert behavior

The script is safe to run multiple times for the same period:

- **Already logged (same hours)**: Skipped with info message
- **Already logged (different hours)**: Skipped with warning. Delete the worklog in Tempo first if you want to re-sync.
- **Not yet logged**: Created normally

The script checks **all** worklogs for the target issue on each date, regardless of how they were created (manually or via sync). This prevents duplicates even if you've already logged hours manually in Tempo.
