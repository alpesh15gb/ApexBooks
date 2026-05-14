# Frontend Build Guide — GST API Engine

## Prerequisites (Build Machine)

Install once on your build machine (macOS recommended for iOS, Linux/Windows for Android & Web):

```bash
# 1. Install Flutter SDK 3.19+ (with mobile support)
# https://flutter.dev/docs/get-started/install
flutter doctor

# 2. Install Android SDK (for Android builds)
# Android Studio → SDK Manager → Android SDK + NDK + CMake
# Or via CLI:
sdkmanager "platforms;android-34" "build-tools;34.0.0" "ndk;25.2.9519653"

# 3. Install Xcode (macOS only, for iOS builds)
# App Store → Xcode, then:
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer

# 4. Desktop dependencies (Linux)
sudo apt update
sudo apt install -y cmake ninja-build pkg-config libgtk-3-dev liblzma-dev

# 5. Desktop dependencies (macOS)
brew install cmake ninja
```

## Build Commands

### Option A: Build on the VPS directly (Linux only — web + desktop)

```bash
cd /opt/gst-api-engine/gst_frontend

# Install deps
flutter pub get

# Generate code
flutter pub run build_runner build --delete-conflicting-outputs

# --- Build Web (for apexbooks.in) ---
API_BASE_URL=https://api.apexbooks.in/api/v1 bash /opt/gst-api-engine/scripts/build_frontend.sh web
# Copy to nginx:
sudo cp -r build/web/* /opt/gst-api-engine/frontend/

# --- Build Linux Desktop (for distribution) ---
API_BASE_URL=https://api.apexbooks.in/api/v1 bash /opt/gst-api-engine/scripts/build_frontend.sh linux
# Output: build/linux/x64/release/bundle/

# --- Build AppImage (for easy distribution) ---
API_BASE_URL=https://api.apexbooks.in/api/v1 bash /opt/gst-api-engine/scripts/build_frontend.sh appimage
```

### Option B: Build mobile apps (macOS required for iOS)

```bash
cd gst_frontend

# Install deps & generate
flutter pub get
flutter pub run build_runner build --delete-conflicting-outputs

# --- Android APK ---
API_BASE_URL=https://api.apexbooks.in/api/v1 flutter build apk --release --split-per-abi
# Output: build/app/outputs/flutter-apk/
# Upload to Google Play or distribute directly

# --- Android App Bundle (Play Store) ---
API_BASE_URL=https://api.apexbooks.in/api/v1 flutter build appbundle --release
# Output: build/app/outputs/bundle/release/

# --- iOS (requires Xcode + Apple Developer account) ---
API_BASE_URL=https://api.apexbooks.in/api/v1 flutter build ios --release --no-codesign
# Then open in Xcode for signing & distribution
open ios/Runner.xcworkspace
```

### Option C: Build locally, deploy to VPS via Docker

```bash
# Build web locally
cd gst_frontend
flutter pub get
flutter pub run build_runner build --delete-conflicting-outputs
flutter build web --release --dart-define=API_BASE_URL=https://api.apexbooks.in/api/v1

# Copy to VPS
scp -r build/web/* user@your-vps:/opt/gst-api-engine/frontend/
ssh user@your-vps "docker compose restart nginx"
```

## Docker Integration (CI/CD)

To build the frontend inside Docker automatically:

```bash
# Build Flutter web inside Docker
docker run --rm \
  -v "$PWD/gst_frontend:/app" \
  -v "$PWD/frontend:/output" \
  ghcr.io/cirruslabs/flutter:stable-release \
  /bin/bash -c "
    cd /app && \
    flutter pub get && \
    flutter pub run build_runner build --delete-conflicting-outputs && \
    flutter build web --release --dart-define=API_BASE_URL=https://api.apexbooks.in/api/v1 && \
    cp -r build/web/* /output/"
```

## Post-Build Verification

```bash
# Verify web build structure
ls build/web/
# Expected: assets/  favicon.png  icons/  index.html  main.dart.js  manifest.json

# Verify API connection
curl https://api.apexbooks.in/api/v1/health
# Expected: {"status":"ok","service":"GST API Engine",...}

# Verify frontend loads
curl https://apexbooks.in/index.html
# Expected: HTML with Flutter app shell

# Verify Android APK
adb install build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
# Expected: App installs and connects to API
```

## Mobile-Specific Notes

### Android
- Package name: `com.apexbooks.gst` (configure in `android/app/build.gradle`)
- Minimum SDK: 23 (Android 6.0)
- Target SDK: 34 (Android 14)
- `flutter_secure_storage` uses Android Keystore automatically
- Add `INTERNET` permission (already in `AndroidManifest.xml`)

### iOS
- Bundle ID: `com.apexbooks.gst` (configure in `ios/Runner.xcconfig`)
- Minimum iOS: 13.0
- `flutter_secure_storage` uses Keychain automatically
- Requires Apple Developer account for App Store / TestFlight distribution
- Add `NSAppTransportSecurity` exception if using HTTP for local dev

### `flutter_secure_storage` Platform Setup
Already included in dependencies. On Android it uses EncryptedSharedPreferences. On iOS it uses Keychain. No extra setup needed beyond standard Flutter plugin installation.