# Windows import receipt recovery checks

Run with an installed official .NET 10 SDK:

    python native/tests/WindowsImportReceipt/check.py --dotnet /path/to/dotnet
    python native/tests/WindowsImportReceipt/workflow.py --dotnet /path/to/dotnet

The first compiles production storage logic and the extracted save callback. The
second compiles the complete production MasterCsvImport method against fake UI,
API and file-picker boundaries. No external service or production database is used.
Tests cover opaque references, concurrent creation, changed input, legacy servers,
unknown/rejected retries, GET-only restart recovery, missing receipts and stale
picker ownership. Full WinUI controls and device restart require separate acceptance.
