# Native complete-backup verification

## Compatibility and privacy

Android and Windows use the existing encrypted-v1 envelope, not a new encryption
protocol. Encryption format version 1 is independent of complete archive schema 8.
Both clients authenticate the full GCM tag into private staging before upload,
verify every transfer chunk and the whole archive SHA256, preview an import, and
require explicit creation of a new company. Unknown commit outcomes reuse the
same stage and digest; completed recovery opens the existing restored company.
Receipt downloads are explicit saves, never automatic rendering or OCR.

Legacy JSON/gzip backups and old encrypted writers remain supported. Tests use
only synthetic data and documented test-only passwords. No signing keys,
production accounts or production API calls are needed.

## New dependency audit (2026-11-02)

- Java: `org.bouncycastle:bcprov-jdk18on:1.86` and maintained Jackson LTS
  `com.fasterxml.jackson.core:jackson-core:2.21.8`. Exact-version OSV querybatch
  returned no known advisories. Gradle dependency locks and SHA256 verification
  metadata are checked in.
- .NET: `BouncyCastle.Cryptography:2.7.0`. NuGet transitive vulnerability audit
  reported no known vulnerable packages; project lock files pin content hashes.

These are advisory-feed results, not guarantees. Reaudit dependencies before
release. Platform whole-buffer GCM APIs were not treated as streaming merely
because they can be wrapped in streams.

## Reproducible codec checks

From the repository root:

```sh
cd native/shared/AndroidBackupStreaming
bash ../../android/gradlew -p . verifyBackupStreaming -PlargeMiB=320
cd ../../..
dotnet restore native/tests/WindowsBackupStreaming --locked-mode
dotnet build native/tests/WindowsBackupStreaming --no-restore
DOTNET_GCHeapHardLimit=0x4000000 dotnet native/tests/WindowsBackupStreaming/bin/Debug/net10.0/WindowsBackupStreaming.Tests.dll --max
```

The Java test process uses a 64 MiB heap limit. Both suites cover old and new
crosswriter fixtures, Unicode passwords, JSON property order and escaping,
wrong passwords, tampering, truncation, bounds, cancellation, and staging cleanup.
CI runs the 320 MiB checks separately from app compilation.

Measured Linux results, **not device memory or UI performance promises**:

| Pipeline | Plaintext | Heap cap | Peak process memory | Time |
|---|---:|---:|---:|---:|
| Java full JSON/base64/GCM | 320 MiB | 64 MiB | 112,744 KiB RSS | 16.845 s |
| .NET full JSON/base64/GCM plus cancellation parse | 320 MiB | 64 MiB | 102,236,160 bytes | 44.9 s |

The Java encrypted JSON output was 447,392,568 bytes. A heap limit is not a total
process-memory limit. Private disk capacity is also required for staging.

## Application integration checks

`CompleteBackupHttpTest.kt` and `CompleteTransferSmoke.cs` exercise an isolated
loopback API with a synthetic retained receipt larger than one chunk: upload,
archive, immutable export, per-chunk and whole-file checks, staged import,
preview, atomic commit replay, completed-result recovery, and byte-exact restored
receipt verification. Android requires `APEX_SYNTHETIC_API_ORIGIN`; without it the
live-HTTP test is explicitly skipped, not reported as a live integration pass.
See `tests/WindowsClient/COMPLETE_TRANSFERS.md` for the Windows command.

The native UI fixtures additionally exercise real receipt file pickers. Compilation
and portable integration are not substitutes for those hosted Windows/device
runtime gates. Unsigned Release R8/build checks are separate from Debug UI tests;
unsigned verification artifacts are not signed distribution releases.

## Candidate identity

Candidate versions are Android `1.5.0` / code `10` and Windows `1.5.0` /
manifest `1.5.0.0`. Build revision is optional explicit `APEX_BUILD_SHA`, validated
as a full 40- or 64-character hexadecimal identifier; absent or invalid values
show `unknown`. CI derives it from the checked-out source, including fixed-ref
checkouts. Local builds never infer a clean revision from a possibly dirty tree.
Settings displays client and connected API identity from the existing capability
response, without another company-startup request. Artifact compilation does not
constitute signing, deployment, or verification of a production rollout.
