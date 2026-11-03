# Bounded encrypted-backup v1 compatibility tests

Reusable .NET library and console tests, now referenced by the Windows app’s capability-gated complete-backup export/restore dialogs. The local API integration and bounded streaming checks are documented in `../WindowsClient/COMPLETE_TRANSFERS.md`; real native UI execution remains a separate verification gate. No production data or passwords are used in tests.

The existing format is unchanged: `apex-encrypted-backup`, integer version 1, 16-byte salt, 12-byte IV, PBKDF2-HMAC-SHA256 (250,000 iterations, 32-byte UTF-8-password key), AES-256-GCM with the 16-byte authentication tag appended to ciphertext, JSON/base64 fields. No new encryption protocol or unauthenticated plaintext delivery.

## Dependency decision

Pinned `BouncyCastle.Cryptography` **2.7.0**, the official current stable C# package, for incremental GCM. Built-in .NET `AesGcm` requires complete input/output buffers; it remains the independent compatibility oracle in tests. This is the ordinary maintained library, not a claim of FIPS validation.

- [Official C# download and NuGet link](https://www.bouncycastle.org/download/bouncy-castle-c/)
- [Official package](https://www.nuget.org/packages/BouncyCastle.Cryptography/2.7.0)
- NuGet `dotnet list package --vulnerable --include-transitive` on 2026-11-02: no vulnerable packages reported from nuget.org. This is advisory-feed evidence, not proof of absence of defects. Project lock files, including the shared library’s explicit Windows RID variants, pin the dependency hash.

## Security and bounded-memory contract

- Encryption uses fresh cryptographic salt/IV, bounded blocks and incremental base64. Caller owns the output; cancellation may leave a partial encrypted export which integration must delete rather than publish as successful.
- Decryption accepts nonseekable input. A narrow bounded tokenizer parses only the existing five fields, handles JSON escapes and arbitrary property order, rejects duplicate/unknown fields, invalid lengths/base64/version, trailing content, and configured size overflow. No complete ciphertext JSON string is allocated.
- Ciphertext is first staged because its field can precede salt/IV. Plaintext goes to a separate exclusive `DeleteOnClose` file. Neither file handle/path is returned before the complete GCM tag authenticates. The authenticated stream is then returned at position zero; disposing it removes staging.
- Callers must supply an **app-private directory**, run synchronous crypto off the UI thread, dispose returned streams, and propagate cancellation. On Unix files are created user-read/write only; Windows relies on the app-private directory ACL plus exclusive handles. This utility makes no OS ACL/security changes.
- Key and plaintext work arrays are zeroed on exit. Managed cryptographic implementation internals and OS page cache are not claimed to be securely erased. A configured default 320MiB byte limit is a safety bound, not a promise that the application accepts that backup size. Compression/ZIP/restore validation is separate and must occur after authentication.

## Run

```sh
dotnet run --project native/tests/WindowsBackupStreaming
DOTNET_GCHeapHardLimit=0x4000000 dotnet native/tests/WindowsBackupStreaming/bin/Debug/net10.0/WindowsBackupStreaming.Tests.dll --large
dotnet list native/shared/WindowsBackupStreaming package --vulnerable --include-transitive
```

`--large` round-trips and SHA256-compares 128MiB under a **64MiB managed heap cap** and prints process peak working set separately (not a total-process 64MiB limit). It also cancels after plaintext staging starts and verifies cleanup. Use `--max` instead of `--large` for the 320MiB utility limit; upload routes may impose a lower quota.

Small tests cover the existing C# writer (its method copied verbatim from `ApexFiles.EncryptBackup` to isolate WinUI dependencies), the platform AesGcm decryptor, ciphertext-first/reordered fields, Unicode/slash base64 escapes, wrong password, ciphertext/tag tampering, truncation, duplicate/malformed fields, cancellation, limits and delete-on-close ownership. Cross-platform fixture commands:

```sh
dotnet run --project native/tests/WindowsBackupStreaming -- --fixtures /private/synthetic-fixtures
dotnet run --project native/tests/WindowsBackupStreaming -- --cross-read /private/android-compatible-v1.json SHA256_HEX [PASSWORD]
```

The default test run always verifies the checked-in synthetic fixtures in `native/tests/backup-fixtures`; MSBuild copies them alongside the executable so this does not depend on the current directory. Additional fixtures produced with `--fixtures` are not committed. Their test-only passwords are `cross-platform-test-only` and (for `csharp-legacy-unicode-password-v1.json`) `cross-platform-₹-test-🔒`. The Unicode fixture shares the `csharp-legacy-v1.bin` plaintext. Interoperability evidence is a JVM/C# algorithm-compatible test, not Android device or Windows WinUI execution.

## Local verification (2026-11-02, Linux .NET10)

- Locked restore/build succeeded; 30 small checks passed (including six checked-in crosswriter fixtures and fully Unicode-escaped ciphertext at an exact plaintext limit).
- Existing Android-compatible JCE writer, Android streaming writer, and Unicode-password fixture all decrypted to the exact expected SHA256 in C#. Reverse C# fixtures are supplied to the Android utility tests separately.
- 128MiB: roundtrip plus cancellation cleanup passed under 64MiB managed heap cap, process peak 102,236,160 bytes (~97.5MiB), 16.8 seconds including a second parse for cancellation.
- 320MiB: same checks passed under the same managed cap, process peak 102,236,160 bytes, 44.9 seconds including cancellation test. These are local synthetic throughput/memory observations, not an app/UI or device performance guarantee.

## Restore isolation

The WinUI build propagates `RuntimeIdentifier=win-x64`, while the standalone codec test is portable. The shared library now uses `packages.<RuntimeIdentifier>.lock.json` only for an explicit runtime and keeps `packages.lock.json` portable. Windows x64/x86/ARM64 variants are checked in. This prevents an app build from rewriting the portable lock graph and causing NU1004 on the subsequent `dotnet restore native/tests/WindowsBackupStreaming --locked-mode`. Locked mode remains enforced; no package versions or hashes were relaxed. Local cached/offline checks cover app-then-codec and codec-then-app restore ordering.
