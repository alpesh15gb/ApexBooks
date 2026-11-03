# Native inline master creation

## Scope and invariants

This follow-up targets Android and Windows **new sales invoices** only. It is separate from the already-tested web inline party/item flow and is not a production rollout.

- Keep the original document editor and all entered quantities, rates, percentage/fixed discounts, dates, due dates, notes and manual delivery address alive while creating a master.
- A created party is selected using the returned identity and reviewed contact defaults. Do not automatically apply payment terms or post the invoice.
- A created item/service adds a reviewed line. Only a sole exactly pristine placeholder may be reused; no edited line may be overwritten. Enforce the document's 100-line limit before creation.
- New masters use the existing company-scoped POST endpoint with a stable idempotency key, immutable submitted body and explicit business date. No journal, stock opening or invoice is posted by creation.
- A new tracked item has no stock merely because a purchase rate was entered. Existing API stock validation remains authoritative. Services do not track inventory.
- Unknown outcomes lock child inputs and every path that could discard the retained request: parent close, Back, company navigation and sign-out. Recovery retries the original command, not current edited fields. Definitive errors remain visible and permit correction without auto-selecting a duplicate.
- Late responses may not populate another session/company, including switching away and back. Viewers and existing/converting documents cannot initiate this flow.
- Real accessible labels, keyboard/back behavior and return focus are required. Windows must not attempt unsupported nested ContentDialogs. Optional image upload is outside this flow.

## Verification gates

Existing synthetic HTTP regressions `backend/test_inline_party.py` and `backend/test_inline_item.py` cover non-posting creation/replay, duplicates, tenant and viewer enforcement, manual invoice values, service discounts and insufficient stock. These APIs are unchanged.

Local verification on 2026-11-03 passed the unchanged API/web release suite: 200 backend tests, 143 frontend tests, lint/build, five HTTP workflows, one complete-backup HTTP round trip, native API route audit and deployment/backup mock checks. The four focused inline-master HTTP regressions also passed. Real-age infrastructure backup checks were not run locally because `age`/`age-keygen` are unavailable.

Seven Android unit methods and 20 Windows portable assertions were authored for the new flow, together with actual Android/Windows UI acceptance extensions. These extensions create customer and service masters inside an existing invoice, retain edited quantities/discounts, verify no invoice is posted by master creation, then explicitly discard the invoice. Existing financial and encrypted-backup acceptance assertions remain.

**Native compilation and all new native tests/runtime journeys are pending hosted CI.** Local Android SDK/Gradle and .NET toolchains are unavailable. Only project XML parsing, source review and diff checks passed for the native changes locally. No new device permission or production action was taken. An authored test is not a passing test; CI compilation is not real Android device or Windows UI acceptance. Missing local SDKs/licenses must not be bypassed or fabricated.

The retained retry state is in memory. Activity/navigation retention is distinct from process-death recovery. This flow does not introduce an offline posting queue or claim crash-proof exactly-once behavior.

## First hosted verification and narrow corrections

PR5 source `f04f777` passed API/web checks and PostgreSQL. The Windows application compiled and unsigned Release passed. Actual Windows UI confirmed inline customer cancellation/creation retained the invoice reference, then stopped before inline item creation because its button was below the viewport.

The first hosted build found a Kotlin recursive inferred getter and a shadowed local variable in the Windows portable test program. The corrections explicitly type the getter as Boolean and rename the test variable. The Windows harness now reveals the actual item button through its own bounded scroll ancestor, then still requires a visible, enabled control before invoking it. No invoice, stock, receipt or backup assertion was removed. These corrections require a new hosted build/runtime run; local diff checks passed but native compilers remain unavailable.

## Hosted parity proof

PR5 source `6fa4da7` passed all main checks (run `41593152195`), unsigned Android/Windows Release (run `41593152293`), and actual Windows UI (run `41593152254`). Android reported 63 unit tests: 62 passed, zero failed and one pre-existing loopback-HTTP test skipped; all seven new inline-master tests passed. Windows passed all 20 new portable assertions. The actual Windows journey created and selected customer/item masters while retaining the invoice reference and original line, then verified invoice 250, collection 100, outstanding 150, retained receipt evidence and the full encrypted backup restore.

The new Android inline screens have **not** run on a device/emulator; that workflow remained intentionally skipped. A subsequent static review found Windows child inputs were locked only after the POST returned. A narrow follow-up locks them before awaiting, preserving the original submitted values and restoring service-specific stock controls only after a definitive outcome. Its additional regression and hosted results must be recorded separately.

The in-flight input-lock correction adds three portable assertions using a controlled delayed validation response: inputs remain locked while the request is suspended, a definitive 422 restores editable fields but not service stock tracking, and an unknown outcome keeps all inputs locked. Local source/diff review passed; executing these new assertions and recompiling the Windows UI remain pending hosted CI.
