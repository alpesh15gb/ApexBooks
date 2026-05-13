# GST Frontend (Flutter)

Cross-platform mobile, web, and desktop app for the GST API Engine.

## Platforms
- **Web** — `flutter build web`
- **Desktop (Linux/Windows/macOS)** — `flutter build linux`, `flutter build windows`, `flutter build macos`
- **Mobile (iOS/Android)** — `flutter build apk`, `flutter build ios`

## Getting Started

1. Install Flutter SDK (3.22+)
2. Run `flutter pub get` in this directory
3. Run `flutter run` for your target platform

## Architecture
- **State Management**: Riverpod 2.x
- **Networking**: Dio with interceptors
- **Auth**: RS256 JWT tokens stored in `flutter_secure_storage`
- **Theme**: Light/dark with Material 3
- **Charts**: Syncfusion Flutter Charts
- **PDF**: `printing` + `pdf` packages
- **API**: Auto-generated types from `/api/v1/openapi.json`

## Project Structure
```
lib/
├── main.dart                    # App entry point
├── core/
│   ├── constants/               # App-wide constants
│   ├── theme/                   # Light/dark theme definitions
│   ├── utils/                   # Utility functions
│   ├── services/                # API & Auth services
│   └── models/                  # Data models (JSON-serializable)
├── providers/                   # Riverpod state notifiers
├── screens/
│   ├── auth/                    # Login / registration
│   ├── dashboard/               # Home dashboard with stats
│   ├── invoices/                # Invoice CRUD list + form
│   ├── parties/                 # Party CRUD with ledger
│   ├── payments/                # Payment list + reconciliation
│   ├── gst/                     # GST compliance dashboard
│   ├── settings/                # Settings categories
│   └── admin/                   # Admin panel (logs, jobs, webhooks)
└── widgets/                     # Shared widgets (AppScaffold, etc.)
```

## API Connection
Default API base URL: `http://localhost:8000/api/v1`
Override via `--dart-define=API_BASE_URL=<url>` at build time.