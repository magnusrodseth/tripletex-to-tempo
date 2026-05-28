---
name: tripletex-mcp
description: Drive Tripletex (Norwegian accounting/time-tracking) via its MCP server. Covers time tracking (log hours, clock in/out, week/month approval), projects, customers, contacts, suppliers, products, orders, outgoing invoices, supplier invoices, reminders, payslips, wage compilation, ledger postings, and reference data. Use when the user mentions tripletex, says "log hours", "clock in", "approve week/month", "search projects/customers/invoices", "send invoice", "create order", "credit invoice", "my payslip", "wage compilation", or any Norwegian accounting term (timer, prosjekt, kunde, leverandør, faktura, lønnsslipp, månedsoversikt). Also use when running the monthly sync to Tempo since hours can now be read directly from the MCP instead of CSV.
---

# Tripletex MCP

Tripletex internal MCP for accounting and time tracking. All tools are prefixed `mcp__tripletex__`.

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
    projectName: "Gjensidige", activityName: "Konsulentbistand" }
]}
```

For a general activity (Ferie, Sykdom, Administrasjon): omit project entirely, pass only activity.

Batch up to 200 entries in one call. Upsert semantics: one entry per `(employee, date, project, activity)`. Re-registering replaces hours.

## Workflows

### Log a full work week
1. `get_current_datetime` for the week's dates.
2. Build a 5-entry batch (Mon to Fri) with project + activity + 7.5h each.
3. Call `execute_hour_registration` once. Read `dayStates` to confirm.

### Audit / fix already-logged hours
1. `search_hour_entries { dateFrom, dateTo }` to see what's there.
2. `execute_hour_registration` to overwrite (same key = upsert) or `delete_hours` to remove.
3. Entries in COMPLETED or APPROVED months are locked, run `reopen_month` first.

### Complete and approve a timesheet period
- Employee: `complete_week` / `complete_month` once done logging.
- Manager: `get_week_status` (or month) to find COMPLETED employees, then `approve_week` / `approve_month` with `employeeIds`. Without `employeeIds`, it acts on your own period.
- Reverse via `unapprove_*` / `reopen_*`.

### Monthly Tempo sync (this repo's purpose)
Two options now exist:
- **CSV path** (existing): `python3 tripletex_to_tempo.py --csv ~/Desktop/...csv --dry-run` per the project's documented workflow. See [feedback memory](../../../../../.claude/projects/-Users-magnus-rodseth-dev-capra-tripletex-to-tempo/memory/feedback_sync_workflow.md).
- **MCP path** (new): `search_hour_entries { dateFrom, dateTo }` for the month, filter by activity `Konsulentbistand`, then push to Tempo. Skips needing the CSV export.

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

Magnus is a Capra consultant logging to Gjensidige. Defaults: activity `Konsulentbistand`, 7.5 hours/day, single Jira issue in Tempo. See [user_consultant memory](../../../../../.claude/projects/-Users-magnus-rodseth-dev-capra-tripletex-to-tempo/memory/user_consultant.md) and [feedback_sync_workflow memory](../../../../../.claude/projects/-Users-magnus-rodseth-dev-capra-tripletex-to-tempo/memory/feedback_sync_workflow.md).
