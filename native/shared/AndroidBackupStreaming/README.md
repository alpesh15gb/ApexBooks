# Bounded Android-compatible encrypted-v1 backup utility

Java 8 bytecode; Android minimum API26. The Android complete-backup workflow
uses this library for authenticated private-file staging before chunk upload.
JVM verification is not device verification. Legacy readers remain compatible.

## Format and lifecycle

The exact existing envelope is retained: `apex-encrypted-backup`, version1,
16-byte random salt, PBKDF2-HMAC-SHA256/250,000 iterations/256-bit key, 12-byte
random nonce, AES-GCM with 128-bit tag appended to ciphertext, and JSON/base64.
There is no new encryption protocol or provider registration.

Jackson's streaming binary reader/writer avoids creating a giant base64 string.
Reordered fields, escaped slash and Unicode-escaped base64 are accepted. Duplicate,
unknown or missing fields, trailing content, wrong types/version, malformed salt/
nonce/base64, oversize metadata and decoded-byte overruns are rejected. Encoded
input has a separate finite budget allowing JSON's six-character Unicode escapes;
decoded ciphertext/plaintext never exceeds the requested budget (maximum320MiB).

The caller MUST provide app-private cache storage and run operations off the UI
thread. Decryption first stages bounded ciphertext, then writes private plaintext;
no plaintext handle is returned until the entire GCM tag is authenticated.
Failure/cancellation removes staging. Close the returned `PrivateFile` to delete
it. Callers retain ownership of input streams and password character arrays.
The app removes expired private staging files when creating its staging directory. No upload/viewer/preview occurs here. Do not upload a
partial file or silently fall back to plaintext when encryption fails.

Transport integration must verify the whole-archive checksum, identify supported
legacy gzip/JSON versus complete ZIP schema8, and run server preflight before
commit. Encryption formatversion1 and backup contents schema8 are independent.
No API routes are guessed or called by this library.

## Run

From this directory, with JDK17 and the repo's Gradle wrapper:

```sh
bash ../../android/gradlew -p . verifyBackupStreaming
bash ../../android/gradlew -p . verifyBackupStreaming -PlargeMiB=320
```

The test process is capped at64MiB Java heap. Tests consume only checked-in
synthetic fixtures with documented test passwords. They cover old C#/Android-
compatible writers, new streaming output, Unicode passwords, arbitrary property
order/escaped base64, wrong password, tampered tag, truncation, size bounds,
metadata validation, cancellation and staging cleanup. The large test covers
full JSON/base64/GCM, not merely raw cipher bytes.

## Dependencies and evidence

Pinned `bcprov-jdk18on:1.86` and maintained Jackson LTS `jackson-core:2.21.8`
were verified against Maven Central metadata. Gradle lock state and SHA256
verification metadata are checked in. OSV querybatch on2026-11-02 returned no
known advisories for those exact runtime artifacts; this is not a guarantee of
absence of vulnerabilities. Reaudit before release and updates.

Official implementation references:
- [Conscrypt AEAD buffering](https://github.com/google/conscrypt/blob/master/common/src/main/java/org/conscrypt/OpenSSLAeadCipher.java): merely wrapping platform `Cipher` in streams does not establish bounded memory.
- [Bouncy Castle GCM API](https://downloads.bouncycastle.org/java/docs/bcprov-jdk18on-javadoc/org/bouncycastle/crypto/modes/GCMBlockCipher.html): incremental processing and final authentication.
- [Jackson streaming parser](https://github.com/FasterXML/jackson-core/blob/2.21/src/main/java/com/fasterxml/jackson/core/JsonParser.java): `readBinaryValue(OutputStream)`.

Local Linux JVM measurements (not Android device memory): the full320MiB
plaintext roundtrip creates a447,392,568-byte encrypted JSON envelope and passes
with a64MiB Java heap. A measured Linux run took16.845s with112,744KiB peak RSS (including JVM/native
allocations); the heap limit is not a total-process memory limit. Standard JDK17 buffered GCM decryption of128MiB
failed under the same heap cap; Android Conscrypt source also buffers updates.
