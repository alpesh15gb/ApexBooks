# ApexBooks: myBillBook / Vyapar / Swipe workflow research

Research date: 2026-11-02. Scope: official public product documentation, help articles, tutorial transcripts and support-community instructions. No signup, trial, purchase, account access, source extraction or protected-asset copying was performed.

## Highest-impact conclusions

1. **Payment received, invoice settled and bank matched are three separate events.** Show all three explicitly. A party can have cash received and still have an unpaid invoice until an allocation is made. Keep advance balance separate from invoice balance; never imply bank reconciliation creates a second receipt.
2. **One document detail page should complete the lifecycle:** view/print/share, collect/pay, inspect allocations, convert source document, issue linked return, view stock/journal effects and reverse where permitted. Lists need useful status filters and direct actions, not just creation forms.
3. **POS is a distinct speed-oriented interaction, not a second accounting engine.** Search/scan, quantity shortcuts, held drafts, payment and print are the primary path. A failed print must not repeat posting.
4. **Central API correctness outranks copying competitor controls.** Company boundaries, journal/stock atomicity, retry deduplication, allocation caps and same-party checks must hold regardless of web/desktop/Android UI or old client version.
5. **Do not promise universal competitor parity.** Product documentation proves workflows, not internal posting algorithms, concurrent-write correctness, offline conflict resolution or full statutory compliance. Apex's documented conservative stock/GST restrictions must remain visible rather than silently relaxed.

## Evidence and limits

“Documented” below means an official page describes the behavior; it is not a logged-in product test. Tutorial transcripts were readable. Help pages reference screenshots and their captions; a myBillBook POS image URL resolved, but no pixel-level screenshot inspection or video playback was completed. Thus layout recommendations are derived from documented navigation/control names, not a claim to have independently tested today's logged-in UI. Some help articles date to 2023–2025; newer product updates can supersede them. Financial/tax behavior here is product research, not legal advice.

The repository `README.md` was reviewed. `IMPLEMENTATION_PLAN.md` was referenced by README but was not present at that path when read. README reports existing regular/composition/unregistered setup, posting, allocations, advances, linked notes, moving-average stock, reconciliation, period locks, roles, exports, portable backup and native clients. These are **repo claims to verify**, not fresh acceptance evidence. It also says native final posting requires network and no durable offline posting queue exists.

## Cross-product workflow comparison

### Company setup and onboarding

- **myBillBook documented:** business name/logo/contact/address/GST setup; dashboard orientation; numbering, payment terms, taxes and roles; import items/customers/suppliers; validate imported data; create a test invoice and verify print/report output. Supports non-GST businesses. [Quick setup guide](https://knowledge.mybillbook.in/articles/8812717-quick-setup-guide).
- **Vyapar documented:** primary device enables Sync and Share, authenticates, adds a user, and invited device chooses **Join a company shared with you** rather than creates another company. Initial sync requires internet; admin controls access. [Multi-device guide](https://vyaparapp.in/guides/how-to-use-vyapar-app-on-multiple-devices).
- **Swipe:** inspected public material proves multi-business/roles capabilities, not an independently verified first-run wizard. Do not invent its exact onboarding sequence.
- **Apex recommendation:** after sign-in present existing companies before Create Company; distinguish Create / Join / Restore. A resumable readiness checklist should cover tax profile/state, financial year/numbering, bank details, items/opening stock, parties/openings and first draft preview. Preview must not manufacture a real accounting transaction. Company name and server origin should remain visible, especially on native apps.

### Parties and items

- **myBillBook documented:** Parties → Create Party, contact/GST/address/opening balance; party click opens related invoices/payments/outstanding. Bulk Excel upload exists; parties can be made inactive rather than deleted. [Party guide](https://knowledge.mybillbook.in/en/help/articles/2318637-how-to-add-parties-in-mybillbook).
- **Vyapar documented:** quotation entry selects existing customers or creates one in place; line entry covers quantity, price, discount and tax. [Official quotation transcript](https://vyaparapp.in/videos/how-to-create-quotation-in-vyapar).
- **Swipe documented:** mobile credit-note flow allows choosing/creating customer and product in context, rather than abandoning the document. [Mobile credit-note guide](https://intercom.help/swipebilling/en/articles/8166073-how-to-create-sales-return-credit-notes-on-mobile).
- **Apex recommendation:** searchable selectors with stable IDs, inline creation without losing draft, separate item/service and stock-tracked flags, visible tax/HSN defaults and quantity/unit precision. Historical documents retain snapshots. Apex currently links some parties by name and fixes names after creation; do not expose rename until a reviewed ID migration exists. Import needs preview, row errors, duplicates and an atomic/idempotent commit.

### Sales, POS and conversion

- **myBillBook documented:** POS searches name/barcode/category, changes quantity, holds current bill while opening another, and offers Save or Save & Print. Zero/negative stock is warned in red. [POS guide](https://knowledge.mybillbook.in/articles/8679710-how-to-use-pos-billing-in-mybillbook-web-app). Estimates/proformas support conversion to sales invoices. [Invoicing page](https://mybillbook.in/invoicing-software).
- **Vyapar documented:** quotation can be enabled in settings, opened with Alt+M, saved, shared, printed and converted from Sales. Its delivery-challan guide explicitly documents review before conversion, then Closed status and destination invoice number. [Quotation transcript](https://vyaparapp.in/videos/how-to-create-quotation-in-vyapar), [challan guide](https://vyaparapp.in/guides/how-to-create-delivery-challan-in-vyapar-app).
- **Swipe documented:** normal invoices prioritize customer credit/outstanding, product/service details and richer document content; POS prioritizes quick walk-in checkout and payment at sale. [Sales versus POS](https://community.getswipe.in/t/what-is-the-difference-between-sales-invoice-and-pos-invoice/4847).
- **Apex recommendation:** separate Draft / Posted / Reversed lifecycle from Unpaid / Part-paid / Paid payment state and Open / Converted source state. Conversion must preserve source linkage, show destination and safely return the existing destination on an identical retry. Estimate/proforma/PO saves must not move revenue, cash, stock or tax. Hold drafts should retain input across navigation; any local persistence must be scoped to account/company and protected against logout/account-switch leakage.

### Purchase and expense

- **myBillBook documented:** Purchases → Purchase Invoices → Create; select/create vendor; enter items, prices and taxes; optionally attach bills/add PO/notes. Saved purchases update stock. Linked payments/returns constrain editing; supplier changes affect future transactions, not historical records. [Purchase guide](https://knowledge.mybillbook.in/articles/8884620-how-to-create-a-purchase-voucher-in-mybillbook).
- **Swipe documented:** expenses separate amount/date/category/notes from payment type/date/bank. Tax-enabled expenses add vendor, supplier date and item/category/tax details; web and Android use the same conceptual sections despite different layouts. [Expense web steps](https://community.getswipe.in/t/how-to-create-expense-in-web/1731), [tax expense web/Android](https://getswipe.in/blog/product-demo/how-to-create-an-expense-with-gst).
- **Vyapar documented:** Sale, Purchase, Expense, Cash & Bank and Reports are first-class navigation areas; purchases and purchase returns are distinct registers. [Feature/navigation guide](https://vyaparapp.in/blog/vyapar-app-features/).
- **Apex recommendation:** clearly label purchase inventory versus operating expense and unpaid bill versus immediate cash/bank expense. Keep OCR as a reviewable draft; display missing supplier/date/tax/line values and source-total differences before posting. Purchase-order conversion must not duplicate supplier advances or inventory.

### Receipts, payouts, advances and allocations

- **myBillBook documented:** Sales → Payment In and Purchases → Payment Out select party, amount, optional pending-invoice checkboxes, date/mode/notes. Unlinked receipts become advances; linked payments constrain editing/deletion. [Payments guide](https://knowledge.mybillbook.in/en/help/articles/5969819-how-to-record-payments-on-mybillbook-payment-in-and-payment). Its FAQ explicitly illustrates one payment allocated across three invoices with a partial final invoice. [FAQ](https://mybillbook.in/s/faqs/).
- **Swipe documented:** a party payment may leave an invoice pending; invoice Record Payment → settle from Advance Payments → Update Payment explicitly applies the balance. [Support example](https://community.getswipe.in/t/payment-has-been-recorded-for-customer-but-invoice-is-showing-as-pending-how-to-make-it-as-paid/1019).
- **Apex recommendation:** amount received/paid, allocation total and unapplied balance should remain visible together. Show dated payment history, original receipt, applications and refunds. Disable Apply for wrong party/company/date or insufficient balance. Never use a paid checkbox as an independent source of truth. Preserve transaction date separately from request/created timestamps. Tax-bearing service advances require their own validated path, not generic non-GST advance reuse.

### Returns and cancellation

- **Swipe documented:** an invoice can be converted into a sales return, reduce selected quantities/remove unreturned lines, then saved. Its guide explicitly says the return does **not** automatically settle the invoice; credits are subsequently applied through advance settlement. [Invoice-to-return guide](https://community.getswipe.in/t/how-to-convert-sales-invoice-to-sales-return-on-web/1250).
- **myBillBook documented:** cancellation is irreversible, preserves numbering, reverses sale stock, marks PDFs cancelled, blocks edits and requires recorded Payment-In removal first; client support differs. [Cancellation guide](https://mybillbook.featurebase.app/help/articles/5125143-how-to-cancel-an-invoice-in-mybillbook).
- **Apex recommendation:** do not copy Swipe's settlement behavior into Apex's existing linked-note implementation. State clearly whether a linked note automatically reduces outstanding. Returnable quantity/value must be capped cumulatively; preserve original price/tax/cost provenance. Return, credit allocation and cash refund are distinct. Prefer audited reversal/correction to destructive delete; explain blocked actions and link to dependencies.

### Stock and costing

- **Swipe documented:** a configurable Allow Negative Quantity permits overselling; later purchase or manual stock-in restores quantity. This source does not establish valuation correctness. [Negative-stock support](https://community.getswipe.in/t/if-i-create-a-bill-with-negative-stock-will-the-stock-automatically-adjust-after-creating-the-purchase-bill/4267).
- **myBillBook documented:** POS provides stockout warnings; its knowledgebase separately exposes stock history, batch/serial, alternative units and valuation-related guides. These feature titles are not proof of every underlying accounting rule. [Knowledgebase](https://knowledge.mybillbook.in/).
- **Apex recommendation:** retain its server-enforced conservative stock policy and date-order restrictions; surface actionable available quantity/date-conflict information before Save. Imported legacy negative stock is a special migration case, not permission for all new transactions. Inventory report should distinguish quantity, moving-average cost, inventory value and sales price. Quantity-only adjustments must not silently overwrite valuation.

### Reports and bank reconciliation

- **myBillBook documented:** statement import selects a bank and supports file/date constraints; displays New/Completed/Partial/Error/No Data, match-confidence categories, manual confirmation and skip/restore. [Reconciliation guide](https://knowledge.mybillbook.in/articles/7155416-how-to-use-smart-bank-statement-reconciliation-in-mybillbook).
- **Swipe documented:** import → choose date range/bank → confirm → side-by-side bank rows and existing payments → Link → Linked/Skipped tabs; unmatched lines can create a payment. Reconciled payments cannot be edited until handled appropriately. [Help walkthrough](https://intercom.help/swipebilling/en/articles/9620152-how-to-match-your-swipe-payments-with-your-bank-statements-bank-reconciliation). Unlink is documented separately. [Unlink instructions](https://community.getswipe.in/t/what-is-bank-reconcillation-under-payment-section/1468).
- **Apex recommendation:** distinguish matching existing ledger cash from creating missing cash entries. Require confirmation, show matched/unmatched amounts on both sides, allow traceable unmatch, reject duplicate statement rows and cap split allocations. Report filters must survive drilldown/export; report screen/PDF/XLSX must use identical dates/company/accounting basis. Include empty and failed states distinct from zero totals. GST preparation reports must not claim filed status.

### Permissions, shared API, recovery and export

- **Swipe documented:** Invite Users → All Users/Roles → Roles & Permissions → Add Role; start with existing role or custom permissions by section. [Role setup](https://community.getswipe.in/t/how-to-add-role-in-web/2507).
- **Vyapar documented:** multi-device sharing assigns roles to limit sensitive information; backup restore selects a local .vyb and preserves the previously open company in the company list. [Sync](https://vyaparapp.in/guides/how-to-use-vyapar-app-on-multiple-devices), [restore transcript](https://vyaparapp.in/videos/how-to-restore-backup).
- **Apex recommendation:** owner/editor/viewer restrictions belong in the API, including PDF/export/import/OCR/backup/restore, not only hidden buttons. Central server is authoritative; native apps should not have divergent tax/allocation algorithms. Expose server/API compatibility, connection state and last successful refresh. Do not claim offline posting until a durable outbox, per-command idempotency and conflict handling exist. Portable restore should produce a separate company, retain lineage, validate totals and never inherit source user credentials/team access. CSV/PDF exports are not restorable backups.

## Prioritized acceptance checklist

### P0: release blockers (fresh evidence required)

- [ ] New account/company plus regular/composition/non-GST setup works; cross-company access denied for reads, writes, exports and ID references.
- [ ] Purchase → stocked sale → partial receipt → second receipt → partial linked return → reconciliation produces balanced journals and the same stock/outstanding totals in every client/report.
- [ ] One receipt allocated across two invoices; insufficient/excess/wrong-party/date-invalid requests rejected; retry does not duplicate money or allocations.
- [ ] Advance receipt → partial application → remaining balance → refund path reconciles cash/liability/tax; no invisible double settlement.
- [ ] Estimate/proforma/PO → review → conversion once; double click, concurrent request and timeout retry yield one posted destination with source link.
- [ ] Interrupted posting preserves form and distinguishes definite rejection from unknown outcome; same retry key survives retry. Server-created ID is retrieved before offering another post.
- [ ] Concurrent clients selling last stock or consuming last invoice balance cannot both overconsume it. Unique numbering is server-scoped by company/document/year.
- [ ] Printing/download/share failure leaves saved transaction intact; reprint is read-only and shows original snapshot and cancellation status.
- [ ] Cancellation/reversal preserves history, stock/cash/tax consistency and dependent-payment protections; locked-period changes are rejected.
- [ ] Web-posted transaction appears in native refresh and vice versa using the same company; revoked sessions and role changes apply immediately server-side.
- [ ] Backup/restore rehearsal into separate company reproduces report totals and lineage; failed restore changes nothing. Deployed offsite backup is separately verified, not inferred from UI export.

### P1: complete everyday usability

- [ ] Company setup checklist, context-preserving inline party/item creation, labeled required fields and field-specific API validation.
- [ ] Search/filter lists by party/document/date/status; detail actions route to prefilled workflows; loading/empty/error states are distinct.
- [ ] POS keyboard/scan flow, hold/resume without ledger effects, cash/bank selection, and Save vs Save & Print; native touch targets and responsive line editing.
- [ ] Document preview shows tax basis, discounts, payment balance and print size before sharing; no outgoing message is sent merely by previewing.
- [ ] Reconciliation upload preview, duplicates/error rows, bank selection, matched/unmatched/skip/unmatch flow and report closing-balance explanation.
- [ ] Master import gives downloadable row errors and duplicate counts; OCR draft review never posts automatically.
- [ ] Reports have shared filter semantics, drilldown to source and matching PDF/XLSX totals with numeric spreadsheet cells.

### P2: explicit future scope, not reasons to weaken P0

Batch/serial/expiry, multiple warehouses, complex alternate units, partial order/challan fulfillment, custom permission granularity, offline final posting, payment gateways, e-invoice/e-way integrations, GST filing, credit limits and automated reminders need their own data models and tests. Expose unsupported features honestly rather than dummy success controls.

## Error/retry contract recommended for Apex (design inference, not competitor internals)

- Validation: 422 plus stable field paths and actionable message; retain all entered lines.
- Authentication: 401, preserve safe draft, reauthenticate; no background automatic mutation after session expiry.
- Authorization: 403 with explanation; do not retry repeatedly.
- Version/state conflict: 409 with current resource/state and Refresh / Review options; never overwrite silently.
- Network timeout after POST: outcome unknown, retain command ID, query/retry idempotently; do not tell user it failed if server may have committed.
- Server failure: request ID and safe retry; transaction rollback must encompass journal, stock, allocation, number and activity record.
- Import/restore: preview first, owner permission, bounded file parsing, commit atomicity, exact-file deduplication and verification totals.

These invariants should be tested at the API and then through real UI journeys. A successful build or endpoint unit test alone cannot establish end-to-end client, PDF, print or production operational acceptance.

## Exact delivery scope: API, web, Windows and Android

The requested scope is **API, web, Windows and Android**. iOS/macOS are not required delivery scope. The API is the authoritative contract; the three user interfaces each require independent journey evidence.
For the API, collect contract/invariant tests. For **each user interface**, collect a separate result (Pass / Fail / Not implemented / Not runnable in environment) and evidence for:

1. Login, select existing company, visibly confirm company/server, refresh, logout/revocation.
2. Create party/item without losing document; create purchase then invoice; verify server-assigned number and totals.
3. Search and reopen detail; collect partial payment; apply advance; linked return; inspect balance/history.
4. Create and convert estimate/PO; source/destination navigation and duplicate-conversion protection.
5. Cash/bank selection and report filters; bank reconciliation UI or a clearly identified unavailable capability, not a dead control.
6. PDF preview, platform save/share/print and retry after print failure with original transaction unchanged.
7. Viewer permissions, forbidden edit explanation, expired login and offline/timeout recovery without duplicate posting.
8. Cross-client round trip: create on client A, read/act on B, refresh A and verify identical canonical amounts/status/stock. Include web↔native and native↔native.
9. Native keyboard/back behavior: confirm dirty-draft exit; focus/validation scroll; accessible labels; no clipped totals or untappable footer controls.
10. Install/launch/update package on real target OS; preserve API endpoint settings safely and never embed production credentials.

Use consistent business labels and lifecycle semantics, but platform-native navigation: desktop may use persistent sidebar/list-detail and keyboard shortcuts; phones need a focused Create action, short forms/section sheets, sticky total and a single clear save action. Do not force phone forms into desktop tables or reproduce every desktop menu on a bottom bar. Hide or explain unsupported operations; do not create false success placeholders. API support can be shared; execution evidence cannot be shared across platforms.
