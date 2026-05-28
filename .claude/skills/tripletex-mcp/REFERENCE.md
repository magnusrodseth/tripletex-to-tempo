# Tripletex MCP reference

Per-tool details. All tool names prefixed `mcp__tripletex__`.

## Time and hour registration

### `execute_hour_registration`
Register or update hour entries. Up to 200 per call.

Per entry:
- `date` (yyyy-MM-dd, required)
- `hours` (>0, rounded to 2 decimals, required)
- Project: pass `projectId` OR `projectName`. For general activities (Ferie, Sykdom, Administrasjon) omit both, or pass `projectId=0`.
- Activity: pass `activityId` OR `activityName` (required).
- `comment` (optional free text, preserved on updates if omitted).

Upsert key: `(employee, date, project, activity)`. Re-registering replaces hours. Use `delete_hours` to remove.

Name resolution: recents first, then open catalog. Per-entry errors do not block other entries.

Response: `dayStates` lists every entry on each affected date plus `calendarFlags` (isWeekend, isHoliday, holidayPercentage). Inspect this before re-querying.

### `search_hour_entries`
List entries in a date range.

- `dateFrom` (inclusive), `dateTo` (EXCLUSIVE). Single day: `dateFrom=X`, `dateTo=X+1`.
- Defaults to logged-in employee. Pass `employeeId` for others (requires `AUTH_HOURS_COMPANY` or `AUTH_HOURS_DEPARTMENT`).
- Optional `projectId` and `activityId` filters.

Each entry returns `id, date, hours, projectId/projectName, activityId/activityName, comment, locked`. Response also has `totalHours`, `sumAllHours` (full result across pages), and `calendarFlags` per date.

### `delete_hours`
Two modes:
- A: `entryId` (from `search_hour_entries`).
- B: `date` + project + activity (IDs or names).

Requires `confirm: true`. Returns `deletedEntry` (use to undo via `execute_hour_registration`) and `dayState` of the affected day. Locked entries (closed month, invoiced, paid wages) cannot be deleted.

### `get_recent_projects_and_activities`
**Fastest discovery path.** Returns the employee's recent projects with the activities used on each, plus `generalActivities`. Names from this list resolve directly in `execute_hour_registration`. Falls back to full catalog for general activities when recents are empty.

### `get_activities_for_project`
Activities bound to a specific project, filtered to those allowed for the current employee on the target date. Preferred for time registration vs the broader `search_activities`.

### `search_activities`
Browse the general catalog. Use when you need an activity outside any project context. Flags: `isGeneral`, `isProjectActivity`, `isTask` are derived from activity type (read-only).

## Clock (running timer)

### `clock_in`
Start the timer for current user. Requires `activityId`.
- Project-bound activity needs matching `projectId`.
- General activity works without a project.
Optional `comment`. Fails if already clocked in.

### `clock_out`
Stop the running timer. Optional `comment` overwrites prior comment. `timeStop` and `durationMinutes` are computed Oslo wall-clock by the MCP layer.

### `get_current_clock_status`
Whether the user is clocked in or out, with start time, activity, and project if running.

## Timesheet completion and approval

### `complete_week` / `complete_month`
Employee marks the period done. Allows manager review.

### `get_week_status` / `get_month_status`
Fetch state for one or more employees.

- `weekYear` format: `'{year}-{week}'` ISO-8601, e.g. `'2026-17'`. NOT a date. Use `get_current_datetime.weekYear`.
- `monthYear` format: `'2026-04'`.
- `employeeIds`: comma-separated. Defaults to logged-in user.

States: `completed=false,approved=false` (OPEN), `completed=true,approved=false` (COMPLETED), `completed=true,approved=true` (APPROVED, locked).

### `approve_week` / `approve_month`
Lock the period (COMPLETED to APPROVED). Reverse via `unapprove_*`.

`employeeIds` required for admin use. Without it, acts on caller's own period only. Multiple employees loop independently, check `results[]`.

Permissions: `AUTH_HOURS_COMPANY` (all) or `AUTH_HOURS_DEPARTMENT` (own department).

`approve_month` accepts `approvedUntilDate` for partial-month approval.

### `unapprove_week` / `unapprove_month`
Reverse approval.

### `reopen_week` / `reopen_month`
Reopen a COMPLETED period to OPEN. Needed before editing or deleting entries.

## Projects

### `search_projects`
Filter by `name` (substring), `number` (exact), `customerId`, `projectManagerId`, `isClosed`. Defaults hide closed.

Registrability traps:
- `isClosed=false` does NOT guarantee registerable today. Also filter `startDate <= day < endDate` locally. `endDate=null` means open-ended.
- `isReadyForInvoicing` controls invoicing, not time registration.

### `search_project_categories`
Project category lookup for `execute_project_operation`.

### `execute_project_operation`
Batch create/update/delete (up to 100 ops). `confirm: true` required.

- `create`: `name` required. Defaults: `projectManagerId=caller`, `startDate=today`, `isInternal=true`, `endDate=null` (open).
- `update`: `projectId` required, only fields passed are changed.
- `delete`: blocked if any transaction history.

Settable: customerId, departmentId, description, endDate, forParticipantsOnly, invoiceComment, isFixedPrice, mainProjectId, projectCategoryId, vatTypeId.

## Customers, contacts

### `search_customers`
Filters: `name`, `email` (exact), `organizationNumber` (exact), `phoneNumberMobile` (exact), `isInactive`.

### `execute_customer`
Create/update. `confirm: true` required.

- Create: `name` required. Org.nr + email recommended for EHF / B2B / reminders.
- Update: `customerId` required. Pass only fields to change. Address sub-fields preserved if omitted.

Tripletex deduplicates only by id. Always search first.

Addresses: `postalAddress`, `physicalAddress`, `deliveryAddress`. `country` accepts ISO codes or full name in NO/EN. `deliveryAddress.name` is the delivery contact (valid alone).

`invoiceSendMethod`: EMAIL, EHF (PEPPOL B2B), EFAKTURA, AVTALEGIRO, VIPPS, PAPER, MANUAL. Defaults EMAIL on create.

`invoicesDueIn` + `invoicesDueInType` (DAYS, MONTHS, RECURRING_DAY_OF_MONTH) sets customer default payment term.

### `delete_customer`
Blocked if any transaction history. Use `isInactive=true` to archive.

### `get_customer`, `search_contacts`, `get_contact`
Read-only lookups.

### `execute_contact`
Create/update contact (person inside a customer org). `firstName` + `customerId` required on create. Phone numbers normalised on write (leading `+47` may be stripped if it matches tenant country).

### `get_customer_invoice_send_types`
Check which channels a customer is reachable on (EHF/EFAKTURA registration). Call before `send_invoice` with non-EMAIL types.

## Suppliers

### `search_suppliers`
Tokenised wildcard search across name, supplier number, org number. Active suppliers only.

### `list_suppliers`
Exact-match filters (email, org-nr) with pagination and sorting. Use when `search_suppliers` is too fuzzy.

### `get_supplier`
Full supplier detail.

### `execute_supplier`
Create/update. `confirm: true`. Same dedup rule as customers, search first. Same address fields. `bankAccountNumber`: NO 11 digits no spaces.

### `delete_supplier`
Blocked by transaction history. Use `isInactive=true`.

## Products

### `search_products`
Only returns products WITHOUT supplier link (the ones usable on outgoing orders). Filter by `name` (substring), `productNumber` (exact), `ean`, `isInactive`, `isStockItem`.

Names not unique, always resolve to `productId` before writing order/invoice lines.

### `execute_product`
Create/update. `confirm: true`.

- Create: `name` required.
- Pricing: provide EITHER `priceExcludingVat` OR `priceIncludingVat`, not both.
- `isStockItem`: true for physical goods, false for services.
- Cannot delete products with transaction history. Use `isInactive=true`.
- `description` is internal. `orderLineDescription` is what appears on invoices.

## Orders and outgoing invoices

### `execute_order`
Create a sales order. `confirm: true`.

Customer: exactly one of `customerId` or `customerName`. Names resolve case-insensitively; exact match wins. Substring matches return `matchedVia: "substring_name"` with up to 5 near-matches in `substringAlternatives`. Ambiguous = error with candidate list, no write.

Lines: 1 to 500.
- Product-linked: pass `productId` (look up via `search_products` first). Omit `unitPriceExclVat`, VAT, and `description` to inherit from product. VAT override on product-linked line is not supported.
- Free-text: pass `description` + VAT (`vatTypeId` / `vatCode` / `vatPercentage`) + `unitPriceExclVat`.

Optional: `orderDate`, `deliveryDate`, `currency` (must be configured on tenant), `invoicesDueInDays` (default 14), `invoiceComment`, `ourReference`, `projectId` (project must already exist), `isSubscription`.

### `search_orders`, `get_order`, `delete_order`
Standard read/delete. `get_order` includes order lines.

### `invoice_order`
Convert order to invoice. **HUMAN APPROVAL REQUIRED.** Permanent ledger entry; reversed only by credit note.

- `orderId` required, `confirm: true`.
- `invoiceDate` defaults to today (Oslo).
- Prepaid: pass `paymentTypeId` + `paidAmount` together; add `paidAmountAccountCurrency` when currencies differ.
- A-konto: `createOnAccount` (WITH_VAT or WITHOUT_VAT) + `amountOnAccount`.

After success, ask the user whether to send. Do NOT auto-call `send_invoice`.

### `send_invoice`
Dispatch the invoice. **HUMAN APPROVAL REQUIRED.** No deduplication; calling twice sends twice.

`sendType` choices: EMAIL, EHF, EFAKTURA, AVTALEGIRO, PAPER. Ask the user which. For EHF/EFAKTURA call `get_customer_invoice_send_types` first to confirm reachability.

`overrideEmailAddress` only used for EMAIL.

### `credit_invoice`
Create credit note reversing the original. **HUMAN APPROVAL REQUIRED.** Permanent.

- Always full reversal; partial credits not supported.
- Original is marked `isCredited=true`.
- Optional `comment` (audit trail), `creditNoteEmail` (override when later sent by EMAIL, otherwise silent send if customer has no email).

After success, ask whether to send. Credit notes support EMAIL, EHF, PAPER (no eFaktura/AvtaleGiro).

### `search_invoices`
Only CHARGED outgoing invoices (no drafts, no supplier invoices).

`invoiceDateFrom` inclusive, `invoiceDateTo` exclusive. Default last 30 days.

Amounts:
- `amountCurrency`: in invoice's currency, quote to user.
- `amount`: NOK base. Equal to `amountCurrency` for NOK; may be 0 for unconverted foreign.
- `amountOutstanding`: owed excluding dunning fees.
- `amountOutstandingTotal`: owed including dunning and remittances.

`isCredited=true` means cancelled by credit note (not partial payment).

Sort options: `invoiceDate`, `dueDate`, `invoiceNumber`, `amount`.

### `get_invoice`, `get_invoice_pdf`
Detail (flattened `orderLines`) and PDF.

## Reminders (dunning)

### `search_reminders`, `get_reminder`, `get_reminder_pdf`
Overdue payment reminders.

### `send_invoice_reminder`
Send a dunning reminder. Distinct from `send_invoice` (which sends the invoice itself).

## Supplier invoices (incoming)

### `search_supplier_invoices`
Filter incoming invoices.

### `get_supplier_invoice`
Full detail with line items, voucher postings, and approval chain.

Amounts: use `amountCurrency`. `amount` (NOK base) may be 0 while still in voucher reception.

Line items: `orderLines` (empty for invoices not yet posted from voucher reception).

`voucherPostings` states:
- `null`: no voucher yet.
- `[]`: voucher created but not posted.
- `[...]`: posted to ledger. Each row has `accountNumber`, `accountName`, `amount` (NOK), `amountCurrency`, VAT code, `type`.

Posting types: `INVOICE_EXPENSE` (the cost line, target for cost analysis), `null` (AP / periodisation / payment / other system rows). AP row (account 2400 to 2499) always `type=null`.

### `get_supplier_invoice_pdf`
PDF download.

### `get_supplier_invoices_for_approval`
Approval queue. Default: yours only. `showAll=true` shows company queue (needs `AUTH_INCOMING_INVOICE`). `searchText` filters by supplier name, invoice number, or description.

### `get_voucher_inbox_count`
How many vouchers are pending in the inbox.

## Payslips and wage

### `search_my_payslips`
Logged-in employee's own payslips only. COMPLETED only. Optional `year`. Sorted by ID desc (most recent first).

### `get_my_payslip`
Single payslip with specification lines (wage code, description, rate, count, amount, optional project/department allocation).

### `get_payslip_pdf`
PDF.

### `get_my_wage_compilation`
Annual lønnssammenstilling. Four sections: wages, deductions, tax deductions, attachment of earnings (from 2021). Defaults to previous calendar year.

### `get_my_wage_compilation_pdf`
PDF version (also shows count and number of days per wage line).

## Reference data

### `logged_in_user_info`
Current user: name, email, employeeId (company-scoped), departmentId, employeeIsProxy, voucherInboxEmail. Starting point for admin flows.

### `list_active_companies`
Switch context. Each entry has `mcpEnabled` flag.

### `get_current_datetime`
Europe/Oslo. Returns `date`, `time`, `iso`, `timezone` (CET/CEST), `gmtOffset`, `dayOfWeek`, `weekNumber`, `monthYear`, `weekYear`, `isDST`. Use `monthYear` / `weekYear` directly for admin tools.

### `search_employees`
ID lookup for admin flows. Filters: `name` (1 token = last name, 2 tokens = first + last), `departmentId`, `email`, `employeeNumber`. Only employees with `allowInformationRegistration=true`.

### `search_departments`
Department ID lookup. Own department also available via `logged_in_user_info.departmentId`.

### `search_countries`
ISO country lookup for addresses.

### `search_vat_types`
VAT codes. Common NO codes: `0` (no VAT), `3` (25% out), `31` (15% food), `32` (12% transport/hotel), `5` (0% export), `6` (0% EU). Filter `typeOfVat=OUTGOING` for sales invoices, `vatDate` to filter historical/future rates.

Key fields: `code`, `percentage`, `deductionPercentage`.

### `search_voucher_types`
Voucher type catalog.

### `search_ledger_postings`
General ledger search. `dateFrom` required (inclusive), `dateTo` required (exclusive). Always narrow with at least one of `supplierId`, `accountId`, or `accountNumberFrom`/`To`, otherwise can return thousands of rows.

Posting types: `INVOICE_EXPENSE` (cost line, use for cost analysis), `OUTGOING_INVOICE_CUSTOMER_POSTING` (AR), `INCOMING_INVOICE_CUSTOMER_POSTING` (revenue), `INCOMING_PAYMENT` / `INCOMING_PAYMENT_OPPOSITE` (AutoPay), `WAGE`, `null` (AP, periodisation, manual journal, bank).

Amounts: `amount` NOK base, `amountCurrency` posting currency, `amountGross` includes VAT.

Norwegian account number ranges: 4000 to 7999 expense, 3000 to 3999 revenue, 1500 to 1599 AR, 2400 to 2499 AP, 2700 to 2799 VAT.

### `list_company_holidays`
Tenant-configured days off. `{ date, percentage }` (1.0 full day, 0.5 half). Names not exposed. Defaults to current calendar year.

`execute_hour_registration` and `search_hour_entries` already surface `calendarFlags` per date, so only call this for standalone holiday planning.

### `submit_feedback`
Send feedback about the MCP itself.

## Permissions cheat sheet

- `AUTH_HOURS_COMPANY`: hour admin tools for all employees.
- `AUTH_HOURS_DEPARTMENT`: hour admin tools for own department only.
- `AUTH_INCOMING_INVOICE`: supplier invoice queue (showAll).
- `isAuthVoucherInbox`: voucher inbox.

All enforced server-side per employee.

## Tripletex naming glossary (NO to EN)

- timer = hours
- prosjekt = project
- aktivitet = activity
- kunde = customer
- kontaktperson = contact
- leverandør = supplier
- vare / tjeneste = product / service
- ordre = order
- faktura = invoice
- kreditnota = credit note
- purring = reminder / dunning
- bilag / voucher = ledger voucher
- lønnsslipp = payslip
- lønnssammenstilling = wage compilation
- avdeling = department
- MVA = VAT
- avgiftsfritt = tax-exempt
- fastpris = fixed-price project
- løpende = hourly-rate project
- Konsulentbistand = consulting work (this user's default activity)
- Administrasjon, Ferie, Sykdom = general (non-project) activities
- Månedsoversikt = monthly overview (the Tripletex CSV export)
