# Import image integrity and canonical payment replay

Full backend: 340 tests passed; PostgreSQL: 18 concurrency, 79 targeted regression and five HTTP lifecycle tests passed, plus a zero-error eight-client accounting workload. Evidence: /tmp/apex-rebuilt-import-full.log and /tmp/apex-postgres-rebuilt-import. Prior-code regressions fail: /tmp/apex-normalized-import-baseline.log.

Image validation now enforces PNG/JPEG content matching the declared MIME, the existing 67,500-byte and one-megapixel bounds, structural verification and full pixel decoding. Master imports invoke the same validator as regular creation. Tests cover truncated JPEG, JPEG-as-PNG, GIF-as-PNG, oversized pixels, corrupt data, both image fields, atomic batch rejection, supported PNG/JPEG, leading-zero identifiers, formula-like names, duplicate handling and company isolation.

Linked-payment retry uses the saved invoice name consistently for new receipts. Replays verify the complete parent request plus the child hash against saved canonical or legacy raw name. This fixes the independently reproduced spaced/lowercase customer-name replay failure; customer and supplier cases and legacy pair replays pass.

Native CSV quote-state, blank-header data-loss and strict UTF-8 handling remain open for a separate compiled parser batch. No device acceptance, production migration, historical repair or blanket statutory compliance is claimed. No production access or deployment.
