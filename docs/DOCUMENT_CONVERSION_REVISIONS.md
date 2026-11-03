# Reviewed source revisions for document conversion

## Reproduced gap

A client opened an estimate for 100 at source version 0. Another client changed that estimate to 200 at version 1. The first client's conversion still posted an invoice for 100 and marked the current 200 estimate converted, without warning that the reviewed source had changed. The ledger itself balanced; the defect was silently consuming a source revision the user had not reviewed.

A separate synthetic baseline found no duplicate posting under simultaneous same-key or different-key conversions across estimate→invoice, proforma→sales order, sales order→invoice and purchase order→bill. Same-key requests returned one identity; different-key contenders produced one success and one conflict. Stock and journals changed once.

## Deliberately bounded behavior

Conversion remains a reviewed **one-shot** operation. Editing the target quantity or price is permitted, but consumes the source once; this is not partial fulfillment or a remaining-quantity order system. For example, converting three of ten units does not leave an automatically convertible balance of seven. No new fulfillment accounting is introduced here.

The correction requires the original source revision alongside its identity, checked under the company write lock. The client captures it when opening the conversion and must not fetch or substitute a newer token immediately before saving. Rejected stale conversions retain the entered target draft for comparison; they must be reopened from a freshly reviewed source rather than silently rebased.

## Compatibility and rollout

This is a **breaking conversion API change** for older clients that submit only `source_document_id`. Deploy the matching API and web/Windows/Android clients together. Updated clients must verify the `document_conversion_revisions` capability before allowing conversion; a verified unsupported backend requires an update, while an unavailable capability check offers retry. Neither condition silently enables an unprotected conversion.

Normal document creation and unrelated edits do not require this conversion token. Existing successful idempotent commands replay before source revision or already-converted checks, so an original-key retry can recover its committed result. Unrelated financial conflicts remain subject to the existing cautious uncertain-outcome rules. In-memory retry state is not a process-death recovery journal.

This work is isolated development, not a production rollout or an instruction to merge the stack. No database migration, new device permission, browser automation or real accounting data is required.

## API contract

For a fresh conversion, `data.source_document_id` identifies the source and `data.source_document_version` is a strict nonnegative JSON integer equal to the source record's `data.version` (historical missing version means zero). Boolean, string, fractional and negative values are invalid. Do not derive this token from the target invoice's revision.

Missing revision returns 409 with `Conversion source revision required; update the app and reopen the source document before converting`. A stale revision returns 409 with `Conversion source changed; reopen it and review the conversion again`. These two exact messages identify definitive rejection of the current attempt. Clients retain entered values but permit leaving/reopening for explicit comparison. Other 409 outcomes are not reclassified. An earlier interrupted attempt might already have succeeded; reconcile against the source and original request before starting a new conversion.

## Verification checkpoint (2026-11-03)

Local checks passed: 230 backend tests, 10 focused conversion/sales-order tests, 152 web tests with lint/build, five HTTP journeys, a 6.4 MB complete-backup HTTP round trip, 232 native API route checks with zero unmatched routes, and 9 + 21 deployment/backup mocks. Independent functional review found no concrete bypass or accounting regression within the tested scope.

The API tests cover all six allowed conversion paths, strict version types, stale review, simultaneous source editing/conversion, same/different-key contenders, stock effects, failed-post rollback, tenant/party/date guards and successful historical versionless-command replay. Two additional PostgreSQL concurrency methods were authored and syntax-checked; their execution awaits the isolated hosted database job.

Android has four new focused tests and Windows has 26 new assertions for immutable tokens, strict versions, capability gates and narrowly classified conflicts. Local native SDK/.NET toolchains are unavailable: these new tests and native compilation have **not** run locally. Existing device evidence does not establish this new conversion flow. Hosted compilation/tests are required before accepting the candidate; no new device permission is implied.
