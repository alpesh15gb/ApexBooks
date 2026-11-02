# Windows retained receipts and complete transfers

The WinUI app references the independently tested streaming-v1 library. New controls require the advertised `document_attachments` / `chunked_backups` capabilities. Legacy APIs remain available when absent, but cannot silently export a company whose evidence requires a complete backup.

- Purchase-bill/expense detail → **Retained receipts**. Explicit upload PDF/JPEG/PNG, verified download/save, archive/reactivate. No automatic viewer, OCR, deletion or ledger changes. Unknown write retains original payload/key and blocks dismissal.
- Settings → **Download backup** uses complete immutable ZIP snapshots with retained evidence. Encryption is checked by default; disabling it is an explicit plaintext choice. Verify every 512KiB chunk and whole SHA256 before encrypting/saving.
- Settings → **Restore company backup** requires explicit encrypted-v1 selection (default for `.apexbackup`), local full authentication before any upload, immutable name/file/hash, upload preview and explicit new-company commit. A failed password/tag never falls back to plaintext.
- Settings → **Recover backup transfers** discovers only the signed-in user's server-side transfers. Resume imports requires the same file/hash/name; received chunks are skipped. Restored transfers offer **Open restored company**, never another automatic restore. Cancel affects staging only. Server TTL is displayed.
- Private staging streams use exclusive delete-on-close handles in the current user's app-data directory. Session changes invalidate further transfer calls. No passphrase/key is sent to the API or persisted.

## Verification

Portable regression suite now covers lost creation response with same-key retry, acknowledged-chunk resume, exact-stage/digest commit replay, export whole/chunk integrity, tampering, wrong-file resume refusal, bounded response reads and replacement-session rejection.

A real isolated local HTTP service smoke is opt-in:

```sh
dotnet run --project native/tests/PortableClient -- --local-complete-backup http://127.0.0.1:18093
```

It refuses non-loopback origins and disables redirects. Start a freshly migrated synthetic SQLite API yourself; do not point it at a real user's books. The test registers unique `@example.invalid` data, creates a synthetic bill and ~600KB PDF, verifies retry/archive, multi-chunk export, upload preview, commit replay, new-company evidence state/SHA256, and cancels only export staging. The caller owns isolated database cleanup.

Local Linux result: **PASS** against the actual API, plus Windows semantic compilation. This is service-contract evidence, not WinUI receipt/file-picker execution. Real Windows hosted UI coverage of those new controls remains a separate gate; existing invoice/partial-collection/dirty-draft UI evidence does not prove them.
