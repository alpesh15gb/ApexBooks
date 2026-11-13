# Windows UI backup completion race

Base: 1a739efbab0a40ded5090fcd91c0060301850ebf (tree b591633b1ff1612f1fb65ae46f1727aea5e22b24), fetched from alpesh15gb/ApexBooks. Investigation on 13 November 2026; no production access or deployment.

## Evidence and cause

Windows UI run 43342729083 failed at Program.cs:317 parsing the local backupPath, not an HTTP response. Its wait accepted File.Exists plus an absent UIA save button. A native Save picker may create an empty destination before the asynchronous stream writer completes; transient UIA disappearance is not a completion signal.

Downloaded artifact 14000586914 verified against SHA256 8184b7ef8c777cf6a254778559ee433c54ea55421578d4bc1391fd5df9e9ad14. The final artifact contains a 4,108-byte valid encrypted v1 envelope. In-memory PBKDF2/AES-GCM authentication with the fixture's synthetic passphrase succeeded, yielding a valid 2,975-byte ZIP with two entries and SHA256 59ea0a994871fa34256050fadd1f9550a8134efcdde0f21486916fa85148b491. API logs show successful export/create/metadata/chunk and cleanup responses. This supports an early-read race rather than evidence of a failed final save.

## Repair

The application emits “Complete backup saved to the selected file.” only after ScopedFileExport returns true, which follows SaveStream completion, flush and ownership checks. Cancellation, disk errors and stale contexts do not produce this notice. The smoke test requires the positive notice and dialog closure, then asserts nonempty persisted bytes and parses once. It does not catch/retry malformed JSON or weaken envelope/restore assertions.

## Checks

WindowsExportContext compiles and passes 43 actual-callback cases with PYTHONWARNDEFAULTENCODING=1 and -W error::EncodingWarning. Three added deterministic cases create an empty destination while saving is held, then resolve success, disk error or stale access. Before completion the callback remains pending and no success notice exists; only successful completion yields a notice and readable persisted JSON. Existing 40 fetch/encryption cases remain intact.

WindowsSaveOwnership passes actual byte/stream picker ownership, cancellation and delayed-open preservation. git diff --check passes. Logs: /workspace/shared/apex-save-completion-regression.log and /workspace/shared/apex-save-completion-picker.log.

These compiled tests use synthetic UI/crypto/storage boundaries. The existing downloaded artifact was separately authenticated using real cryptography. Full Windows UI automation cannot run on this Linux environment and has NOT been rerun here; exact-commit Windows UI CI remains required. No blind rerun, upload retry, license-blob action, merge or deployment was performed.
