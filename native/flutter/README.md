# Apex Books Flutter client

The Flutter client runs on web, Windows and Android using the existing Apex Books API and database. Version `0.1.0` runs alongside the current clients and uses a separate Android application ID.

## What you can use

| Workspace | Flutter coverage |
| --- | --- |
| Sign-in and company | Register, sign in, recover an account, create a company and switch companies. The API enforces membership and posting permissions. |
| Home | Checkout and stock shortcuts, financial period selection and server-calculated sales, profit, receivables and payables. |
| POS | Find products by name or barcode, including Android camera scanning. Post reviewed cash, bank, UPI, card or split sales, and open posted receipts. Print or save 58 mm and 80 mm receipts. Return receipt lines to stock or record them without restocking, and settle through credit or a confirmed refund. Open and close the shared register, post cash movements and reconcile counted cash. |
| Stock | Search and filter by shelf, open stock movement history, post opening quantities, adjustments and physical counts, review low-stock items and post partial purchase-order deliveries. |
| Parties and items | Create, edit, import or archive masters, open a dated party statement, and assign items to shelves with optional vehicle fitment. |
| Books | Post invoices, purchase bills, receipts, supplier payments, expenses, estimates, sales and purchase orders, pro forma invoices, and source-linked credit and debit notes. Post an invoice or bill together with its payment. Amend eligible payments and non-POS notes, cancel or convert supported documents and allocate credits and advances. Review saved payment terms, posted prices and customer credit warnings. Use recurring drafts, document PDFs and retained receipt attachments. Where the API has OCR configured, extract a supplier bill from a saved image or an Android camera photo and review the draft. |
| Banking and ledger | Review cash and bank balances, post opening balances and transfers, import bank CSVs, match statement lines and save reconciliation reviews. Review accounts and journal sources, post balanced journals and reverse manual entries. |
| Reports | Use day book, trial balance, profit and loss, balance sheet, ageing, party statements, item activity, stock and GST working papers. Export supported reports to PDF or Excel and save the GSTR-1 draft as JSON. |
| Settings and data | Manage company details, document preferences and branding, number series, closing dates, inventory setup, members and security. Record opening party balances, preview and import Vyapar data, and save or restore complete backups in a separate company. |
| Ecommerce | Connect Bagisto and review catalogue mappings, orders, delivery queues and reconciliation. Review and submit store commands through the existing bridge API. |

The client saves an unresolved posting with its original payload and request key before sending it. If the result is uncertain, use the original retry after re-entering the same company. Flutter secure storage namespaces postings by API origin, account and company. Sign-in credentials and bearer tokens stay in memory; the app asks you to sign in again after a restart.

## Run locally

Use Flutter 3.50 stable with Dart 3.14, Python for the existing backend and preview proxy, and the normal [Flutter platform prerequisites](https://docs.flutter.dev/install). Windows needs Visual Studio with Desktop development with C++ and **C++ ATL for latest v143 build tools (x86 & x64)** for the secure storage dependency. The Android project uses API 36 and the Flutter-pinned NDK. The app runs on Android API 24 or newer.

Run the existing FastAPI server at loopback port `8012` with a disposable database and a test account. Start from this directory:

```powershell
flutter pub get
flutter analyze
flutter test

# Web: the preview forwards /api on the same origin.
flutter build web --no-web-resources-cdn
python tool/serve_preview.py --api-port 8012
# Open http://127.0.0.1:5174/

# Windows debug defaults to http://127.0.0.1:8012.
flutter run -d windows

# Android emulator debug defaults to http://10.0.2.2:8012.
flutter devices
flutter run -d <android-device-id>
```

Use `--dart-define=APEX_API_ORIGIN=https://your-api.example` for native release builds. Native release builds have no default API origin. For web hosting, serve the bundle and `/api/*` through the same HTTPS origin so the client can read the API's response headers and securely recover pending postings. The Python preview binds only to loopback and is for development.

With Playwright and the backend requirements installed in the same Python environment, run `python tool/smoke_web.py --artifacts ../../tmp/flutter-port-proof` after building web. The smoke runner starts its own disposable database and servers. It exercises register reconciliation, exact sale recovery across a browser reload, receipt PDFs, a cash return, invoice posting and reporting, an opening party balance, and complete backup export and restore.

## Before replacing the current clients

Release acceptance includes the store’s scanner, printer, drawer, and payment terminal. Printing uses the operating system’s print service and depends on its driver and the printer’s configured roll width. Check supplier scans and Bagisto commands against the integrations the store will use. The client can save complete ZIP backups up to 64 MB and encrypted backups up to 8 MB. Sign the Android and Windows packages before cutover.
