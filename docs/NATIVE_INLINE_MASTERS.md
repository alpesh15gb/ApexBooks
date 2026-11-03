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

**At the initial local checkpoint, native compilation and all new native tests/runtime journeys were pending hosted CI.** Local Android SDK/Gradle and .NET toolchains are unavailable. Only project XML parsing, source review and diff checks passed for the native changes locally. No new device permission or production action was taken. An authored test is not a passing test; CI compilation is not real Android device or Windows UI acceptance. Missing local SDKs/licenses must not be bypassed or fabricated.

The retained retry state is in memory. Activity/navigation retention is distinct from process-death recovery. This flow does not introduce an offline posting queue or claim crash-proof exactly-once behavior.

## First hosted verification and narrow corrections

PR5 source `f04f777` passed API/web checks and PostgreSQL. The Windows application compiled and unsigned Release passed. Actual Windows UI confirmed inline customer cancellation/creation retained the invoice reference, then stopped before inline item creation because its button was below the viewport.

The first hosted build found a Kotlin recursive inferred getter and a shadowed local variable in the Windows portable test program. The corrections explicitly type the getter as Boolean and rename the test variable. The Windows harness now reveals the actual item button through its own bounded scroll ancestor, then still requires a visible, enabled control before invoking it. No invoice, stock, receipt or backup assertion was removed. These corrections require a new hosted build/runtime run; local diff checks passed but native compilers remain unavailable.

## Hosted parity proof

PR5 source `6fa4da7` passed all main checks (run `41593152195`), unsigned Android/Windows Release (run `41593152293`), and actual Windows UI (run `41593152254`). Android reported 63 unit tests: 62 passed, zero failed and one pre-existing loopback-HTTP test skipped; all seven new inline-master tests passed. Windows passed all 20 new portable assertions. The actual Windows journey created and selected customer/item masters while retaining the invoice reference and original line, then verified invoice 250, collection 100, outstanding 150, retained receipt evidence and the full encrypted backup restore.

At that checkpoint, the new Android inline screens had **not** run on a device/emulator; that workflow remained intentionally skipped. The later authorized runtime result is recorded below. A subsequent static review found Windows child inputs were locked only after the POST returned. A narrow follow-up locks them before awaiting, preserving the original submitted values and restoring service-specific stock controls only after a definitive outcome. Its additional regression and hosted results must be recorded separately.

The in-flight input-lock correction adds three portable assertions using a controlled delayed validation response: inputs remain locked while the request is suspended, a definitive 422 restores editable fields but not service stock tracking, and an unknown outcome keeps all inputs locked. Local source/diff review passed; executing these new assertions and recompiling the Windows UI remain pending hosted CI.

## Final isolated Android inline acceptance

The Windows in-flight lock correction at source `4820641c9cad35d072f595664f3201fbbe475057` subsequently passed main CI (`41593934852`), actual Windows UI (`41593934978`) and both unsigned Release checks (`41593934817`), including its three added input-lock assertions.

The Android emulator journey passed on 2026-11-03 in run [41609295979](https://github.com/alpesh15gb/ApexBooks/actions/runs/41609295979), job `125826863702`, artifact `13218283047`. It checked out application/test source `2c7f56aed2bebb8944dd35be8aad98171dbc9078`, whose tree matches local `d7876b2d93707ab112ee6854f89dfaeae62e4848`; gate commit `385eaee8ee70548ed839e810c54df5fa9467f454` supplied only the explicitly scoped run permission. The report contains **four tests, zero failures, zero errors and zero skips**, completed in 256.055 seconds.

Actual visible UI created and selected one customer and one service within a retained new invoice. The original quantity 3, rate 100 and fixed discount 10 remained intact (290), the service added 25, and the reviewed total was 315. The service did not track stock. Canonical checks verified exactly one of each master, no additional invoice or financial change from master creation, and explicit discard. Existing invoice/payment, dirty-draft, reorder and payment-term assertions also passed. The same journey exercised the genuine receipt picker, archived evidence, encrypted backup Save/Open/authentication/preview, explicit restore to a new synthetic company, matching reports and receipt bytes, and unchanged original company.

Earlier attempts exposed harness transition races, a keyboard overlapping a click target and controls below the viewport. The retained test-only corrections wait for actual modal dismissal, selected values and stable visible controls, dismiss only a positively identified keyboard, and scroll to the intended controls. They do not repeat financial submissions or remove financial assertions. No application changes were made during these retries. The runner's original virtualization-device ACL was restored and compared successfully after the passing run.

This cleanup restores the ordinary workflow: device execution requires an explicitly authorized manual dispatch with `allow_temporary_kvm_access=true`; its default is false, and ordinary pull-request/push runs skip it. A skipped future device job is not a new runtime pass. The proof above applies to the pinned PR5 source, not automatically to later stacked feature branches. Main, production and real accounting data were not changed by this verification.
