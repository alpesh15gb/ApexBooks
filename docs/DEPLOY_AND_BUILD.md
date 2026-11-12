# Deploy and build the UI/workflow fixes

These commands describe the existing Apex Books VPS and native release tools. They have not been executed against production. Use the full pushed commit SHA printed in the handoff as `APEX_SOURCE_SHA` / `APEX_BUILD_SHA`; build from a clean checkout of that commit.

The current workspace changes and local acceptance evidence are described in [the web release review](WEB_RELEASE_REVIEW.md) and [native review](../native/NATIVE_REVAMP_REVIEW.md). This revision adds no database schema migration, but the deployment procedure still explicitly checks/applies the repository's existing migrations for the installed server version.

## Existing VPS: stage the candidate

Run as root on the existing Ubuntu x86-64 VPS, with Docker Compose v2 and Python 3.12 available. This procedure expects `/opt/apexbooks-vps/shared/activated.json` and the existing private `server.env`. For a new VPS, use [first-install packaging/bootstrap](../deploy/vps/README.md) instead.

```bash
set -euo pipefail
test -f /opt/apexbooks-vps/shared/activated.json
test -f /opt/apexbooks-vps/shared/server.env

# Only needed if the separate Git checkout does not exist yet:
if [ ! -d /opt/apexbooks-vps/source ]; then
  git clone https://github.com/alpesh15gb/ApexBooks.git /opt/apexbooks-vps/source
fi
cd /opt/apexbooks-vps/source
git switch main
git pull --ff-only origin main
export APEX_SOURCE_SHA='<full pushed commit SHA>'
test "$(git rev-parse HEAD)" = "$APEX_SOURCE_SHA"
python3 deploy/vps/update_from_git.py stage --source-sha "$APEX_SOURCE_SHA"
```

Staging builds the two images sequentially and leaves the running services in place. It needs at least 5 GB of free space. It creates `/opt/apexbooks-vps/releases/1.5.0-$APEX_SOURCE_SHA` with immutable image IDs, source checksums and release metadata.

## Existing VPS: reviewed cutover

Before cutover, verify a real full-database recovery point and isolated restore, review schema/recovery compatibility, and pause **all** writers to that database, including other deployments/workers/native clients. Company ZIP backups are not full-database schema recovery. Keep the existing database URL, encryption keys and private settings.

Prepare `/opt/apexbooks-vps/shared/upgrade-plan.json` using the exact JSON template in [Upgrade an existing activation](../deploy/vps/README.md#upgrade-an-existing-apex-books-activation-including-13). Set `target_release_identity` to the staged `release.json`; record the real recovery reference, old activation checksum, and current API/web image IDs. Its boolean fields attest completed operator work. Keep the file private (`chmod 600`). Do not replace these with invented backup evidence.

From the same shell after completing that review:

```bash
set -euo pipefail
cd "/opt/apexbooks-vps/releases/1.5.0-$APEX_SOURCE_SHA"
export APEXBOOKS_ENV_FILE=/opt/apexbooks-vps/shared/server.env
release_exports="$(python3 deploy/vps/manage.py release-env)"
eval "$release_exports"
python3 deploy/vps/manage.py prepare-upgrade

docker compose -p apexbooks-vps -f deploy/vps/compose.yml stop api web
docker compose -p apexbooks-vps -f deploy/vps/compose.yml run --rm --no-deps api python migrate.py
docker compose -p apexbooks-vps -f deploy/vps/compose.yml up -d --no-build --pull never api web

python3 deploy/vps/manage.py finish-upgrade
python3 deploy/vps/manage.py verify-public
python3 deploy/vps/manage.py verify-other-apps
docker compose -p apexbooks-vps -f deploy/vps/compose.yml ps
```

Only resume writers after successful verification and report reconciliation. If migration/readiness fails, keep writers paused and use the reviewed recovery/forward-fix plan. Do not automatically start old code against a changed schema. The `update_from_git.py apply --without-backup` route is an explicit backup waiver and is not this procedure. Do not use the root development `docker-compose.yml` to update the dedicated production deployment.

Review `verify-other-apps` output yourself: it compares with a persisted earlier baseline and prints differences without failing the command. It is a diagnostic, not proof that unrelated applications stayed unchanged during this upgrade.

## Windows installer ZIP

On Windows 10 build 19041 or later / Windows 11, install the .NET 10 SDK and appropriate Windows SDK/WinUI build tools, plus Python 3. These are the same prerequisites as the repository's Windows CI. Run in PowerShell from the repository root:

```powershell
$ErrorActionPreference = 'Stop'
git switch main
if ($LASTEXITCODE -ne 0) { throw 'Cannot select main' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Pull failed' }
$env:APEX_BUILD_SHA = (git rev-parse HEAD).Trim()

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native\tools\Build-Native.ps1 -Target Windows -Configuration Release
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
```

Output: `deliverables\Apex-Books-Windows-1.5.0-Release-win-x64.zip`.

Extract the entire ZIP and run **Install Apex Books.cmd** from the extracted folder. This per-user installer adds desktop/Start-menu shortcuts and an uninstall entry; it is not an MSI or a signed Setup.exe. Complete the Windows UI/printing acceptance before distribution.

## Signed Android APK on Windows

Use an installed JDK 17 or 21 and Android SDK with platform 36/build tools 36.0.0. Set `JAVA_HOME` and `ANDROID_HOME` to their actual local installations. The wrapper accepts an explicit JDK path and requires `bin\java.exe`.

For an update, use the **same keystore and alias as the installed release**. `Build-Native.ps1` automatically loads an existing signing identity from `%LOCALAPPDATA%\ApexBooksNative\Signing\signing.dpapi`, or uses `APEX_ANDROID_KEYSTORE`, `APEX_ANDROID_KEY_ALIAS`, `APEX_ANDROID_STORE_PASSWORD` and `APEX_ANDROID_KEY_PASSWORD` supplied privately in the build process. Do not put keys/passwords in Git or command-line literals. For a new application signing identity only, use `Initialize-AndroidSigning.ps1`; do not generate a replacement key to update an existing installation.

With that identity available, from the same clean checkout and PowerShell session:

```powershell
$env:APEX_BUILD_SHA = (git rev-parse HEAD).Trim()
if (-not $env:JAVA_HOME -or -not $env:ANDROID_HOME) { throw 'Set JAVA_HOME and ANDROID_HOME first' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native\tools\Build-Native.ps1 -Target Android -Configuration Release -JdkPath $env:JAVA_HOME
if ($LASTEXITCODE -ne 0) { throw 'Android build failed' }
```

Output: `deliverables\Apex-Books-Android-1.5.0-Release.apk`. Both native Release clients connect to `https://api.apexbooks.in`; deploy/verify the matching API before rolling out the clients. The project currently uses Android versionCode 12. Increase it above the last distributed code when publishing a subsequent release, while retaining package/signing identity.

For a developer APK without release signing, run the same command with `-Configuration Debug`. Its separate debug package connects to the local emulator API, not production.

## Signed Android APK on Linux

With JDK 17, the Android SDK, and the existing release key available outside the repository:

```bash
set -euo pipefail
export APEX_BUILD_SHA="$(git rev-parse HEAD)"
: "${JAVA_HOME:?Point JAVA_HOME at the installed JDK}"
: "${ANDROID_HOME:?Point ANDROID_HOME at the installed Android SDK}"
: "${APEX_ANDROID_KEYSTORE:?Set the existing private release keystore path}"
: "${APEX_ANDROID_KEY_ALIAS:?Set the existing release alias}"
read -rsp 'Keystore password: ' APEX_ANDROID_STORE_PASSWORD; echo
export APEX_ANDROID_STORE_PASSWORD
read -rsp 'Signing-key password: ' APEX_ANDROID_KEY_PASSWORD; echo
export APEX_ANDROID_KEY_PASSWORD
trap 'unset APEX_ANDROID_STORE_PASSWORD APEX_ANDROID_KEY_PASSWORD' EXIT

(cd native/android && bash gradlew :app:lintRelease :app:assembleRelease --no-daemon --max-workers=2)
test -s native/android/app/build/outputs/apk/release/app-release.apk
mkdir -p .native-build/releases
cp native/android/app/build/outputs/apk/release/app-release.apk .native-build/releases/Apex-Books-Android-1.5.0-Release.apk
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose .native-build/releases/Apex-Books-Android-1.5.0-Release.apk
sha256sum .native-build/releases/Apex-Books-Android-1.5.0-Release.apk
```

Use a subshell or dedicated build shell for the Linux block; its exit trap clears the temporary signing-password environment variables. No release key is supplied by this source checkout. Unsigned CI verification APKs are not installable signed releases. Do not add generated release packages to Git history; distribute them as release artifacts.
