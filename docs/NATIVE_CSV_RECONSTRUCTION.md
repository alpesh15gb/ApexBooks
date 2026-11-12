# Native CSV reconstruction — compiled verification pending

Windows and Android now reject malformed quotes (including text after a closing quote), invalid UTF-8, duplicate normalized master headers, populated unnamed/unsupported/extra master columns and invalid stock Boolean values. Valid quoted commas, newlines, doubled quotes, UTF-8 BOM and leading-zero text remain supported by design and regression cases. Strict decoding is wired to both master and bank-statement CSV entry. Android clears old input/preview before file parsing so a rejected replacement cannot leave the preceding table active.

C# regressions are wired into both existing WindowsClient and PortableClient test projects; Android CsvIntegrityTest uses the actual Csv helper. No .NET or Kotlin/JVM compiler is available in this execution environment: these new compiled tests and full native builds have NOT run locally. Source diff checks passed. CI and device import preview/commit checks are required before release.

Backend follow-up rejects all animated PNG images, including a corrupt second APNG frame with valid chunk CRC. Eight targeted import/payment tests pass; static PNG/JPEG success and atomic import/create rejection are covered. This closes a first-frame-only decode gap; it does not claim broader media support.
