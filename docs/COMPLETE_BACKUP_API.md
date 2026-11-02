# Retained receipts and complete portable backups (v8)

All paths below have `/api` prefix. All operations except `/capabilities` require bearer authentication. Gate UI on `document_attachments` and `chunked_backups` capabilities. Passphrases and encryption keys **never** go to these APIs: clients encrypt/decrypt the portable file locally using the existing encrypted portable-backup envelope. API transport carries authenticated plaintext ZIP chunks, never silently downgrading the user's encrypted-backup choice.

## Receipts

Company path prefix `/companies/{company_id}`. Members can read; owner/editor can upload/archive; target records must be `purchase_bill` or `expense`. Evidence changes do not change journals, stock or historic document values, including locked periods.

- `GET /records/{record_id}/attachments` → `{attachments:[metadata],storage}` (includes archived).
- `POST /records/{record_id}/attachments?filename=...`: raw PDF/JPEG/PNG bytes, matching `Content-Type`, required `Idempotency-Key` (1–80 characters). → `{attachment:metadata,storage,replayed}`.
- `PUT /attachments/{attachment_id}`: `{version:integer,is_archived:boolean}`, required retry key. → same shape. No hard deletion; archiving retains bytes/quota/backup lineage.
- `GET /attachments/{attachment_id}/download`: raw verified bytes, attachment disposition, nosniff, no-store, `X-Content-SHA256`. Do not automatically render the evidence.

Metadata: `{id,record_id,filename,media_type,size_bytes,sha256,is_archived,version,created_at}`. Filenames are server-normalized to a safe basename and verified type extension; use returned filename.
Storage: `{used_bytes,quota_bytes,remaining_bytes,file_count,max_file_bytes,max_files_per_record,max_files_per_company}`.

Defaults: 2 MiB/file, 5 retained files/record, 500/company, 64 MiB/company (deployment configurable 1–256 MiB). Archived files count. Identical bytes for the same record deduplicate even across different retry keys; changed body with an existing key conflicts. Preserve exact unresolved payload/key across network failures.

## Complete export

Owner only, transfer belongs to creator and every request rechecks current owner access.

1. `POST /companies/{company_id}/backup-exports` JSON `{}`, required retry key → transfer metadata. Creates an immutable company+evidence snapshot in one transaction.
2. `GET /companies/{company_id}/backup-exports/{export_id}` → metadata.
3. `GET /companies/{company_id}/backup-exports/{export_id}/chunks/{index}` → binary part, at most 524288 bytes; `X-Chunk-SHA256`, `X-Archive-SHA256`, no-store/nosniff. Verify size/hash against metadata; concatenate in index order, verify entire archive hash, then encrypt locally/save.
4. `DELETE /companies/{company_id}/backup-exports/{export_id}` → `{export_id,state,cancelled}`; cancels staging only, never source books/evidence.

## Lost-response / restart recovery

`GET /backups/transfers` → `{transfers:[transfer_metadata + {direction,source_company_id}]}`. Lists only current user's unexpired active transfers and restored import results with current company membership (exports additionally require current company ownership). Use for explicit resume/cancel after losing a begin response or restarting, without storing financial payloads locally. Restored results include `company_id` and allow an explicit “Open restored company” after a lost commit response plus restart; never create another company to recover that result. Never automatically restore.

## Complete import into a new company

Decrypt locally first. Never send encrypted wrapper or passphrase to API.

1. `POST /backups/uploads` `{company_name,byte_count,sha256}` with required retry key → transfer metadata. Hash/length describe decrypted whole ZIP (or supported bounded legacy v6/v7 JSON/gzip).
2. `PUT /backups/uploads/{upload_id}/chunks/{index}` raw bytes → `{index,size_bytes,sha256,received:true,replayed:boolean}`. Every nonfinal chunk must have exactly `chunk_size` bytes; final exact remainder. Same index+bytes replay safely without key; different bytes conflict.
3. `GET /backups/uploads/{upload_id}` → metadata/resume received indices.
4. `POST /backups/uploads/{upload_id}/preview` (no body) → existing company-restore validation report plus `{digest,attachment_count,attachment_bytes,format,schema_version}`. The digest is whole-upload SHA256; validation seals immutable chunks. Show preview before confirmation.
5. `POST /backups/uploads/{upload_id}/commit` `{digest}` → restore report including `{company_id,digest,already_restored}`. Atomic financial+evidence restore; same transfer/digest replay returns the same company, never duplicates. An unknown response must retry this same transfer/digest.
6. `DELETE /backups/uploads/{upload_id}` → `{upload_id,state,cancelled}`. Cancels staging only; a restored company is never deleted.

Transfer metadata: `{upload_id|export_id,state,target_company_name,format,schema_version,byte_count,sha256,chunk_size,chunk_count,expires_at,received_indices,chunks:[{index,size_bytes,sha256}],...preview_report}`; restored status also has `company_id`. States uploading/sealed/restored for imports; ready for exports; expired/cancelled terminal. TTL 24 hours. One active import and export per user, one export/company; atomically bounded global staging. Cleanup removes staging only.

Success responses are HTTP 200. Standard role/tenant errors 403/404; invalid chunks/archive 422; quota/size 413; conflicting key/bytes/state 409; expired/cancelled 410. Do not assume all 409s imply an unknown prior write did not commit: inspect status or retry exact original operation.

Limits are public capability `limits` values in bytes: `attachment_max_file_bytes`, `attachment_company_quota_bytes`, `attachment_max_files_per_record`, `attachment_max_files_per_company`, `backup_chunk_bytes`, `backup_archive_max_bytes`, `backup_company_json_max_bytes`, `backup_stage_ttl_seconds`. Default archive cap128 MiB, financial JSON50,000,000 bytes, chunk524288. Request AND response sizes remain below hosting payload cap; do not concatenate an entire archive into one HTTP request.

## Portable ZIP and compatibility

ZIP has `company.json` (schema_version8, complete financial snapshot, metadata-only attachments manifest) and `attachments/{canonical-uuid}.bin` for every retained file including archived. Never omit evidence. Parser verifies bounded central directory before ZipFile, rejects ZIP64/extra entries/path traversal/duplicates/encryption/unsupported compression, strict JSON duplicate keys, full entry hashes/types/size/tenant references, count and expanded-byte limits. No filesystem extraction.

Legacy v6/v7 JSON/gzip imports remain supported within their historical limits. Legacy company JSON export/backup routes return409 `COMPLETE_BACKUP_REQUIRED` (also `X-Apex-Error`) whenever retained evidence exists, directing clients to complete export rather than silently losing files. No production migration is performed by these source changes.

## Local verification evidence

Synthetic SQLite tests cover attachment signatures/quotas/deduplication, concurrent writes, immutable snapshots, archived-file roundtrip, chunk tamper and partial upload, atomic rollback/retry, cross-user denial, restart recovery, expiry-budget reclamation, and central-directory/duplicate-JSON rejection. The >4.5MB HTTP test uses 5.1MB of retained binary evidence, exports/imports in <=512KiB verified parts and restores identical hashes. An isolated run took 0.758s and process peak RSS 159.2MiB (includes Python/FastAPI/SQLite/TestClient and the test's assembled source/destination buffers; not a server-only or full-quota memory benchmark). This verifies transport correctness, not production capacity/latency. PostgreSQL-specific concurrent attachment/upload/restore cases are added to the dedicated loopback CI suite; local PostgreSQL execution is not claimed.

## Client memory bounds

The web client supports complete plaintext transfers up to **16 MiB**. Encrypted web transfers retain the existing v1 envelope with an **8 MiB plaintext / 12 MiB envelope** limit. It refuses oversized files before reading and oversized exports before transfer, directs users to the native file-backed path, and never omits evidence or silently falls back to plaintext. Complete-backup tools are lazy-loaded so ordinary company startup does not pay their bundle cost.

Synthetic Node analog measurements were 124 MiB peak RSS for 16 MiB plaintext and 180.5 MiB for 8 MiB encrypted. These are not mobile-browser memory guarantees. Native file-backed incremental encrypted transport is the larger-archive path; its device/build acceptance remains a separate gate. Server capability limits do not override a client's stricter safe memory limits.
