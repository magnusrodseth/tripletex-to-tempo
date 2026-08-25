---
name: tripletex-mcp
description: Drive Tripletex (Norwegian accounting/time-tracking) via its MCP server. Covers time tracking (log hours, clock in/out, week/month approval), projects, customers, contacts, suppliers, products, orders, outgoing invoices, supplier invoices, reminders, payslips, wage compilation, ledger postings, and reference data. Use when the user mentions tripletex, says "log hours", "clock in", "approve week/month", "search projects/customers/invoices", "send invoice", "create order", "credit invoice", "my payslip", "wage compilation", or any Norwegian accounting term (timer, prosjekt, kunde, leverandør, faktura, lønnsslipp, månedsoversikt). Also use when running the monthly sync to Tempo since hours can now be read directly from the MCP instead of CSV.
---

# Tripletex MCP

Tripletex internal MCP for accounting and time tracking. All tools are prefixed `mcp__tripletex__`.

## Connecting the MCP (OAuth workaround)

Server URL `https://mcp.tripletex.no`, transport `http`, exactly as the
[beta docs](https://developer.tripletex.no/tripletex-mcp-beta/) specify. The config is correct
and needs no change, but the normal `/mcp` login **fails in Claude Code**:

```
Issuer mismatch in authorization response (RFC 9207): expected "https://mcp.tripletex.no/", received undefined
```

Tripletex advertises `"authorization_response_iss_parameter_supported": true` in
`/.well-known/oauth-authorization-server` but never sends `iss` on the redirect back. RFC 9207
§2.4 makes the check mandatory once that flag is true, so Claude Code rejects a login the
browser has already reported as successful. Claude Desktop and the claude.ai connector work
because their OAuth client does not enforce the check yet.

Tracked upstream as [Tripletex/tripletex-mcp#3](https://github.com/Tripletex/tripletex-mcp/issues/3).
The workaround below is written up in
[our comment on that thread](https://github.com/Tripletex/tripletex-mcp/issues/3#issuecomment-5411074661),
verified 25.08.2026 on Claude Code 2.1.245.

### Re-authenticating by hand

Do this when the server drops back to "needs authentication". The browser must never reach the
localhost callback: Claude Code's own callback listener receives it, fails the `iss` check, and
cancels the flow, spending the authorization code before you can reuse it. So drive the last
hop with `curl` instead of the browser.

1. `mcp__tripletex__authenticate` returns an authorize URL. Note its `redirect_uri` port, it
   changes on every attempt.
2. Open that URL in Chrome. The `playwriter` skill does this without leaving the terminal. It
   lands on `/oauth/select-company?id=<selectionId>`. **Do not click Connect.**
3. Read that page's cookies. `tlx_cs_nonce` is scoped to `Path=/oauth`, so query cookies
   against the full page URL rather than the origin, or step 4 answers 400:
   ```bash
   playwriter -s <id> -e 'const cdp = await getCDPSession({ page: state.page }); const { cookies } = await cdp.send("Network.getCookies", { urls: [state.page.url()] }); console.log(cookies.map(c => c.name + "=" + c.value).join("; "))'
   ```
4. Submit the company selection outside the browser, so nothing follows the 302:
   ```bash
   curl -sS -i -X POST https://mcp.tripletex.no/oauth/select-company \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -H 'Origin: https://mcp.tripletex.no' \
     -H 'Referer: https://mcp.tripletex.no/oauth/select-company?id=<selectionId>' \
     -b '<cookies from step 3>' \
     --data-urlencode 'selectionId=<selectionId>' \
     --data-urlencode 'companyId=228265'
   ```
   curl does not follow redirects, so the `location:` header hands over the callback URL with
   the `code`.
5. Pass that URL to `mcp__tripletex__complete_authentication` with
   `&iss=https%3A%2F%2Fmcp.tripletex.no%2F` appended by hand. That satisfies the check and the
   server connects with the full tool set.

`companyId` 228265 is Capra Consulting AS. Any failed attempt invalidates both the
authorization code and the selection nonce, so restart from step 1 instead of retrying a step.

Two blind alleys, both already tried and both useless here: Playwright's `page.route()` and CDP
`Network.setBlockedURLs` fail to stop the callback navigation under playwriter's extension mode,
so the request still reaches Claude Code and kills the flow.

## Core conventions

1. **No raw IDs in user-facing text.** IDs are for tool plumbing only. Show names, dates, hours, amounts to the user.
2. **Names work on write tools.** `execute_hour_registration`, `delete_hours`, and similar accept `projectName` / `activityName`. Pass the user's words directly; the server resolves them.
3. **Europe/Oslo for every date.** Call `get_current_datetime` when the user says "today", "now", "this week", or "this month". Never compute dates locally.
4. **Inspect predictive context before issuing another call.** Write tools return `dayStates`, `calendarFlags`, post-write state. The next answer is usually already in the response.
5. **`dateTo` is EXCLUSIVE** in `search_hour_entries`. For a single day, pass `dateFrom=<day>`, `dateTo=<day+1>`.
6. **Write tools require `confirm: true`** as a guard (executeproject, customer, supplier, product, order, invoice, credit, send, delete_hours).

## Quick start: log hours

The most common task. For a project + activity:

```
get_recent_projects_and_activities   # confirm name resolves
execute_hour_registration { entries: [
  { date: "2026-05-28", hours: 7.5,
    projectName: "Innovasjon i privat", activityName: "Konsulentbistand" },
  { date: "2026-05-28", hours: 0.5,
    projectName: "Innovasjon i privat", activityName: "Lunsj - ikke kundebetalt" }
]}
```

Magnus's standard day is **8h = 7.5 Konsulentbistand (chargeable) + 0.5 Lunsj - ikke kundebetalt (not chargeable)**, both on project *Innovasjon i privat*. "7.5 + 0.5" means exactly this pair.

For a general activity (Ferie, Sykdom, Administrasjon): omit project entirely, pass only activity.

**Ferie is 8h, not 7.5h.** A vacation day is a single 8h `Ferie` line: no project, and no
0.5h lunch line alongside it. Never reuse the 7.5 + 0.5 workday split for absence. Confirmed
by Tuva Brynildsen (Capra) on 2026-07-27: "ferie føres som 8 timer og ikke 7,5 time".

Batch up to 200 entries in one call. Upsert semantics: one entry per `(employee, date, project, activity)`. Re-registering replaces hours.

## Workflows

### Log a full work week
1. `get_current_datetime` for the week's dates.
2. Build a batch for Mon–Fri. For Magnus that's **two lines per day** (7.5 Konsulentbistand + 0.5 Lunsj - ikke kundebetalt) on *Innovasjon i privat* = 10 entries; check `list_company_holidays` and skip holidays/weekends.
3. Call `execute_hour_registration` once. Read `dayStates` (each day should total 8h) to confirm.

### Audit / fix already-logged hours
1. `search_hour_entries { dateFrom, dateTo }` to see what's there.
2. `execute_hour_registration` to overwrite (same key = upsert) or `delete_hours` to remove.
3. Entries in COMPLETED or APPROVED months are locked, run `reopen_month` first.

### Complete and approve a timesheet period
- Employee: `complete_week` / `complete_month` once done logging.
- Manager: `get_week_status` (or month) to find COMPLETED employees, then `approve_week` / `approve_month` with `employeeIds`. Without `employeeIds`, it acts on your own period.
- Reverse via `unapprove_*` / `reopen_*`.

### Monthly Tempo sync (this repo's purpose)
Two options exist. See [feedback memory](../../../../../.claude/projects/-Users-magnus-rodseth-dev-capra-tripletex-to-tempo/memory/feedback_sync_workflow.md) for defaults. Always `--dry-run` first, then post. Only the chargeable **Konsulentbistand** hours (7.5/day) sync — the 0.5h lunch line stays in Tripletex. Target issue: `HEIHU-1`.

- **MCP path** (preferred when hours were logged via the MCP this session): `search_hour_entries { dateFrom, dateTo }` for the month, keep only `Konsulentbistand` lines, build a JSON array of `{date, hours}`, and pipe it to the script's stdin mode — no CSV needed:
  ```bash
  echo '[{"date":"2026-06-01","hours":7.5}, ...]' \
    | python3 tripletex_to_tempo.py --stdin --dry-run   # drop --dry-run to post
  ```
- **CSV path** (when working from an exported report): `python3 tripletex_to_tempo.py --csv ~/Desktop/...csv --dry-run`. The script filters by `--activity Konsulentbistand` automatically.

Both paths share the same upsert/skip logic, so re-running never duplicates worklogs.

**`--dry-run` does not check Tempo.** It returns before resolving the Jira issue and fetching
existing worklogs, so it reports every day as "created" even when Tempo already holds a
different number of hours for that date. Treat it as a parser check only. The real run is what
surfaces conflicts, and it *skips* them rather than reconciling: a date whose hours changed in
Tripletex after an earlier sync stays stale in Tempo until you update that worklog yourself
(`PUT /worklogs/<id>` on the Tempo v4 API) or delete it and re-sync.

### Outgoing invoice (3-step atomic flow)
1. `execute_order` to create order + lines (link products via `productId`, free-text lines need `vatTypeId` + `unitPriceExclVat`).
2. `invoice_order` to convert order to invoice. **Ask user before calling.** Permanent ledger entry.
3. `send_invoice` to dispatch. **Ask user which sendType** (EMAIL/EHF/EFAKTURA/AVTALEGIRO/PAPER). Use `get_customer_invoice_send_types` first to check availability. Cannot be unsent.

### Credit (cancel) an invoice
`credit_invoice { invoiceId }`. Reverses the full invoice with a credit note. **Ask user first**, permanent. Then ask whether to send the credit note.

### Approve an incoming supplier invoice
1. `get_supplier_invoices_for_approval` to list yours (or `showAll=true` for the company queue).
2. `get_supplier_invoice` for line items + posting accounts.
3. `get_supplier_invoice_pdf` for the document.

## All tool categories

See [REFERENCE.md](REFERENCE.md) for the full per-tool breakdown. Categories:

- **Time / hours**: `execute_hour_registration`, `search_hour_entries`, `delete_hours`, `get_recent_projects_and_activities`, `get_activities_for_project`
- **Clock**: `clock_in`, `clock_out`, `get_current_clock_status`
- **Timesheet approval**: `complete_week/month`, `approve_week/month`, `unapprove_week/month`, `reopen_week/month`, `get_week_status`, `get_month_status`
- **Projects**: `search_projects`, `search_project_categories`, `execute_project_operation`
- **Customers / contacts**: `search_customers`, `execute_customer`, `delete_customer`, `search_contacts`, `get_contact`, `execute_contact`, `get_customer_invoice_send_types`
- **Suppliers**: `search_suppliers`, `list_suppliers`, `get_supplier`, `execute_supplier`, `delete_supplier`
- **Products**: `search_products`, `execute_product`
- **Orders**: `search_orders`, `get_order`, `execute_order`, `delete_order`, `invoice_order`
- **Outgoing invoices**: `search_invoices`, `get_invoice`, `get_invoice_pdf`, `send_invoice`, `credit_invoice`
- **Reminders / dunning**: `search_reminders`, `get_reminder`, `get_reminder_pdf`, `send_invoice_reminder`
- **Supplier invoices**: `search_supplier_invoices`, `get_supplier_invoice`, `get_supplier_invoice_pdf`, `get_supplier_invoices_for_approval`, `get_voucher_inbox_count`
- **Payslips / wage**: `search_my_payslips`, `get_my_payslip`, `get_payslip_pdf`, `get_my_wage_compilation`, `get_my_wage_compilation_pdf`
- **Activities catalog**: `search_activities`
- **Reference data**: `search_employees`, `search_departments`, `search_countries`, `search_vat_types`, `search_voucher_types`, `search_ledger_postings`, `list_company_holidays`, `list_active_companies`, `logged_in_user_info`, `get_current_datetime`, `submit_feedback`

## Project-specific context

Magnus is a Capra consultant logging to Gjensidige. Defaults:
- **Project**: `Innovasjon i privat` (customer *Gjensidige Business Services AB*). Note: "Gjensidige" alone is not the project name.
- **Daily pattern**: 7.5h `Konsulentbistand` (chargeable) + 0.5h `Lunsj - ikke kundebetalt` (not chargeable) = 8h.
- **Vacation pattern**: `Ferie` is a single 8h line, no project, no lunch line. The 7.5 + 0.5 split applies to workdays only.
- **Tempo target**: single Jira issue `HEIHU-1`; only the 7.5h Konsulentbistand syncs.

See [user_consultant memory](../../../../../.claude/projects/-Users-magnus-rodseth-dev-capra-tripletex-to-tempo/memory/user_consultant.md) and [feedback_sync_workflow memory](../../../../../.claude/projects/-Users-magnus-rodseth-dev-capra-tripletex-to-tempo/memory/feedback_sync_workflow.md).
