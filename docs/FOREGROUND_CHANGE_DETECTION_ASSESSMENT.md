# Foreground company-change detection assessment

This is a design and isolated synthetic proof, not an enabled application feature. No client timer, server endpoint, deployed schema change, or realtime guarantee is introduced.

## Existing signals are insufficient

The company model has no company-wide revision. Synthetic checks showed that archiving a lower-revision master and changing document preferences can leave record count, maximum business date and maximum record revision unchanged. A mocked commerce verification changed visible connection configuration without changing either that tuple or the audit count/time. A backup download can append an audit event without changing books. Audit count is neither complete nor constant-time.

An explicit token must cover committed mutations in a defined domain, including imports, restores, background commerce workers, settings, membership and retained evidence. Authentication, company-directory discovery, transfer staging and time-dependent calculations require separate treatment. Reservation expiry and the business-date boundary can change displayed values without any database write.

## Synthetic read cost

The existing isolated SQLite performance fixture was loaded with 100 and 1,000 posted records, including large line/source metadata, journals and allocations. Actual TestClient compact-record scans plus the bank request used respectively 2/4 HTTP requests, 11/22 SQL statements and 31,687/316,990 response-body bytes. Record-scan medians were 15.76/194.89 ms; the separate bank request took 4.42/5.72 ms. These are separate local component timings, not measured parallel loading or production latency.

An authenticated in-process audit count/time experiment used 4 SQL statements and a hypothetical 65–66-byte response at approximately 1.36–1.38 ms. It was not an HTTP endpoint and was proven incomplete. It is not a deployable optimization. Reports, PostgreSQL, native devices and network latency were not measured here.

## Native coordination prerequisites

Android currently has no foreground refresh lifecycle owner. Its manual-refresh guard does not fully represent dirty POS drafts and local workspace sheets. Windows has no activation-owned refresh coordinator; current guards do not cover every held cart/operation, and rebuilding navigation can reset register filters. An automatic timer must not simply call the existing manual refresh method.

A later bounded design should:

- Own a single check in the foreground lifecycle; cancel on background, logout or company replacement.
- Bind all results to the original account/session, company, workspace and request epoch. Authenticate and recheck membership on every server probe, even for an unchanged token.
- Keep only one pending invalidation while an editor, sheet, POS draft or unresolved command blocks refresh. Never resend financial writes.
- Initially restrict automatic rebuilding to an idle Dashboard. Other pages can show “Changes available” and offer a guarded explicit refresh, without resetting filters or input.
- Recheck UI safety and scope both before fetching and before publishing. A newly opened editor must prevent a late refresh from replacing its context.
- Acknowledge a loaded token only after a successful matching-scope reload. A token-before/read/token-after handshake can detect intervening mutations, but does not turn separately fetched endpoints into an atomic snapshot.
- Keep failures and last-good snapshot provenance visible. Network failure must not look like an unchanged company.
- Use a bounded, single-flight interval with jitter and capped error backoff, resetting promptly on genuine foreground entry. No interval has been performance-approved. For scale context, a proposed 30-second interval would mean up to 120 checks per active workspace-hour before backoff; backend and battery costs require measurement.

No continuous polling has been added. Foreground lifecycle, editor interlocks and the new failure states still need actual native runtime acceptance if implemented.

## Transactional proof boundary

The separate test-only generation prototype evaluates a dedicated, preseeded per-company counter and explicit table/trigger coverage. Updating the Company row itself would introduce a concrete lock-order cycle between commerce worker claim and retry operations. A dedicated counter avoids that particular cycle, but PostgreSQL concurrent-writer and lock-order safety remain unverified locally. Arbitrary multi-company SQL, unsupported replacement operations, counter lifecycle, trigger integrity and backup/recovery semantics must be resolved before any production migration or endpoint.

The prototype is not imported by application startup. Its passing SQLite tests must not be described as PostgreSQL, native-device or deployed verification. No existing OCR transport policy or live configuration is changed.
