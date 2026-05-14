#!/bin/bash
# Flutter Build Script for GST Frontend
# Usage: bash scripts/build_frontend.sh [web|linux|windows|macos|android|ios|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../gst_frontend"
cd "$FRONTEND_DIR"

TARGET="${1:-web}"
API_URL="${API_BASE_URL:-https://api.apexbooks.in/api/v1}"

echo "============================================="
echo "  Flutter Build - GST Frontend"
echo "  Target: $TARGET"
echo "  API URL: $API_URL"
echo "============================================="
echo ""

# Clean previous builds
echo "[1/6] Cleaning previous builds..."
rm -rf build/ dist/

# Install dependencies
echo "[2/6] Installing dependencies..."
flutter pub get

# Run code generators (json_serializable, freezed, riverpod, hive)
echo "[3/6] Running code generators..."
flutter pub run build_runner build --delete-conflicting-outputs

echo "[4/6] Running Flutter analyze..."
flutter analyze lib/

# Build based on target
echo "[5/6] Building for $TARGET..."
case "$TARGET" in
  web)
    echo "Building web (release)..."
    flutter build web --release --web-renderer canvaskit --dart-define=API_BASE_URL=$API_URL
    echo ""
    echo "✅ Web build complete!"
    echo "   Output: build/web/"
    echo ""
    echo "   Deploy to Nginx:"
    echo "     cp -r build/web/* /opt/gst-api-engine/frontend/"
    OPTIMIZE=true
    ;;

  linux)
    echo "Building Linux (release)..."
    flutter build linux --release --dart-define=API_BASE_URL=$API_URL
    echo ""
    echo "✅ Linux build complete!"
    echo "   Output: build/linux/x64/release/bundle/"
    OPTIMIZE=true
    ;;

  windows)
    echo "Building Windows (release)..."
    flutter build windows --release --dart-define=API_BASE_URL=$API_URL
    echo ""
    echo "✅ Windows build complete!"
    echo "   Output: build/windows/x64/runner/Release/"
    OPTIMIZE=true
    ;;

  macos)
    echo "Building macOS (release)..."
    flutter build macos --release --dart-define=API_BASE_URL=$API_URL
    echo ""
    echo "✅ macOS build complete!"
    echo "   Output: build/macos/Build/Products/Release/"
    OPTIMIZE=true
    ;;

  android)
    echo "Building Android APK (release)..."
    flutter build apk --release --dart-define=API_BASE_URL=$API_URL --split-per-abi
    echo ""
    echo "✅ Android APK build complete!"
    echo "   Output: build/app/outputs/flutter-apk/"
    echo ""
    echo "   Also builds app bundle (AAB) for Play Store:"
    echo "     flutter build appbundle --release --dart-define=API_BASE_URL=$API_URL"
    echo "   Output: build/app/outputs/bundle/release/"
    OPTIMIZE=true
    ;;

  ios)
    echo "Building iOS (release)..."
    echo "   NOTE: Requires macOS with Xcode installed"
    flutter build ios --release --dart-define=API_BASE_URL=$API_URL --no-codesign
    echo ""
    echo "✅ iOS build complete (unsigned)!"
    echo "   Output: build/ios/iphoneos/"
    echo ""
    echo "   To sign and export for App Store / TestFlight:"
    echo "     1. Open ios/Runner.xcworkspace in Xcode"
    echo "     2. Set team & bundle ID"
    echo "     3. Product → Archive → Distribute App"
    OPTIMIZE=true
    ;;

  appimage)
    echo "Building Linux AppImage..."
    flutter build linux --release --dart-define=API_BASE_URL=$API_URL
    if command -v linuxdeploy &> /dev/null; then
      echo "Creating AppImage..."
      linuxdeploy --appdir AppDir --output appimage
      echo "✅ AppImage created!"
    else
      echo "⚠ linuxdeploy not installed."
      echo "   Install: pip install linuxdeploy"
      echo "   Or download from: https://github.com/linuxdeploy/linuxdeploy/releases"
    fi
    ;;

  all)
    echo "Building all platforms..."
    flutter build web --release --web-renderer canvaskit --dart-define=API_BASE_URL=$API_URL
    flutter build linux --release --dart-define=API_BASE_URL=$API_URL
    flutter build windows --release --dart-define=API_BASE_URL=$API_URL
    flutter build macos --release --dart-define=API_BASE_URL=$API_URL
    flutter build apk --release --dart-define=API_BASE_URL=$API_URL --split-per-abi
    echo ""
    echo "✅ All builds complete!"
    echo "   Web:    build/web/"
    echo "   Linux:  build/linux/x64/release/bundle/"
    echo "   Win:    build/windows/x64/runner/Release/"
    echo "   macOS:  build/macos/Build/Products/Release/"
    echo "   Android: build/app/outputs/flutter-apk/"
    ;;

  *)
    echo "❌ Unknown target: $TARGET"
    echo "Usage: $0 [web|linux|windows|macos|android|ios|appimage|all]"
    exit 1
    ;;
esac

# Optionally optimize web build
if [ "$OPTIMIZE" = true ] && [ "$TARGET" = "web" ]; then
  echo ""
  echo "Optimizing web assets..."
  if command -v npx &> /dev/null; then
    echo "[Optional] Test locally:"
    echo "  npx http-server build/web -p 8080 -c-1"
  fi
fi

echo ""
echo "============================================="
echo "  Build Complete ✓"
echo "============================================="