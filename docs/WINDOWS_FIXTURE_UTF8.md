# Windows fixture encoding repair

Base: 55999891635439a6b799816ad9bafba022b9afde, fetched from https://github.com/alpesh15gb/ApexBooks.git. Its tree matches the previous local CI repair (520318c). No application source, dependency, workflow or accounting behavior changed.

WindowsExportContext used the system-default text encoding to read UTF-8 Reporting.cs. Windows cp1252 cannot decode one of its bytes. The same hazard existed in related readers and in generated fixture writers, even when Linux tests passed.

All 68 pathlib read_text/write_text calls across 17 Windows Python harnesses now specify UTF-8. Two git-show source decoders also specify UTF-8. Android-only harnesses are outside this Windows CI repair. An AST comparison confirms that removing these encoding keywords produces the same syntax trees as the base; no assertions or production extraction boundaries were weakened.

Verification on 13 November 2026:

- Reproduced cp1252 decoding failure against the actual Reporting.cs bytes; strict UTF-8 decoding succeeds.
- Audited every pathlib text operation in native/tests/Windows*/*.py for explicit UTF-8.
- WindowsExportContext passes 40 compiled export callback cases with PYTHONWARNDEFAULTENCODING=1 and -W error::EncodingWarning.
- All 17 Windows Python harness scripts compile and pass with implicit encodings treated as errors, using .NET SDK 10.0.100. This includes the downstream PDF, retained-read, statement, import, recurring, document, scan, quick-master and upload tests that CI had not reached.
- git diff --check passes. Evidence: /workspace/shared/apex-utf8-export.log and /workspace/shared/apex-utf8-windows-suite.log.

These are compiled synthetic callback tests on Linux, not full WinUI/device execution. Full application builds were not repeated for this encoding-only fixture change. Exact-new-commit Windows CI remains required. No publication retry, merge or deployment was performed; the prior upload restriction remains in force.
