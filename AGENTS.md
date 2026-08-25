# tripletex-to-tempo

Simple Python script that syncs hours from a Tripletex monthly CSV export to Tempo (Atlassian).

## Architecture

Single-file Python 3 script (`tripletex_to_tempo.py`) with zero external dependencies. Uses only the standard library (`csv`, `json`, `urllib`, `argparse`).

## Key design decisions

- **Upsert behavior**: Before posting, the script fetches existing worklogs from Tempo for the user/date range. It skips days that already have a synced worklog (matched by description "Synced from Tripletex") and logs info. It never crashes on duplicates.
- **CSV format**: Tripletex exports monthly overviews as semicolon-delimited, ISO-8859-1-encoded CSV files. The script auto-detects encoding.
- **No API key for Tripletex**: We use CSV export instead of the Tripletex API to avoid the complexity of obtaining API credentials.

## Tripletex MCP

Hours can be read straight from the Tripletex MCP instead of a CSV export. The server is
declared per-project in `~/.claude.json` as `https://mcp.tripletex.no` (transport `http`).

Its OAuth login fails in Claude Code with an RFC 9207 issuer mismatch, because Tripletex
advertises `iss` support and then omits the parameter. That is an upstream bug
([Tripletex/tripletex-mcp#3](https://github.com/Tripletex/tripletex-mcp/issues/3)), not a
config problem. The manual re-auth procedure is in
[`.claude/skills/tripletex-mcp/SKILL.md`](.claude/skills/tripletex-mcp/SKILL.md) under
"Connecting the MCP", and in
[our comment on the issue](https://github.com/Tripletex/tripletex-mcp/issues/3#issuecomment-5411074661).

## Running

```bash
python3 tripletex_to_tempo.py --csv "file.csv" --dry-run
```

## Secrets

All secrets and config live in `.env` (auto-loaded by the script). Never hardcode tokens. The `.env` file is gitignored.
