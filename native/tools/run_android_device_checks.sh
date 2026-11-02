#!/usr/bin/env bash
# Dedicated emulator + isolated host API at 127.0.0.1:8012 only. Never use hosted data.
set -uo pipefail
cd "$(dirname "$0")/../android"
serial="${ANDROID_SERIAL:-emulator-${EMULATOR_PORT:-5554}}"
if [[ ! "$serial" =~ ^emulator-[0-9]+$ ]]; then echo 'Use a dedicated synthetic emulator.' >&2; exit 2; fi
classes='com.apexbooks.accounting.LocalUiAcceptanceTest,com.apexbooks.accounting.LoginTransportAcceptanceTest,com.apexbooks.accounting.NativeHostedAcceptanceTest'
bash gradlew :app:connectedDebugAndroidTest --no-daemon --max-workers=2 \
  -Pkotlin.compiler.execution.strategy=in-process '-Dorg.gradle.jvmargs=-Xmx2048m' \
  -PapexApiOrigin=http://10.0.2.2:8012 \
  -Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true \
  "-Pandroid.testInstrumentationRunnerArguments.class=$classes"
status=$?
mkdir -p app/build/device-evidence
adb -s "$serial" pull /sdcard/Android/data/com.apexbooks.accounting.debug/files app/build/device-evidence/ 2>/dev/null || true
adb -s "$serial" logcat -d > app/build/device-evidence/logcat.txt 2>&1 || true
exit "$status"
