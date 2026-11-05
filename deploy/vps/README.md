# Dedicated Apex Books VPS deployment

Target: Ubuntu 24.04 x86-64, system Nginx, existing Docker apps. DNS already points to 82.112.236.81. Reuses the valid apexbooks.in-0001 and api.apexbooks.in certificates. Bagisto hosting is deferred.

Only the `apexbooks-vps` Compose project is started. Web/API publish on 127.0.0.1:18090/18091, with 192 MB/1 GB memory limits. Prebuilt images avoid compiling on the VPS. There is no new PostgreSQL container or published database port; the existing accounting Neon database and commerce encryption key are retained. No migrations execute during container startup. Readiness refuses an incompatible schema.

Private `server.env` is transferred separately and kept at `/opt/apexbooks-vps/shared/server.env` with mode 600. It contains a new VPS JWT session key, so users sign in on the new domains. Existing accounts/data are shared; Vercel stays available with its own sessions. Add the existing OmniRoute key privately before deployment; preflight refuses a missing OCR key. Do not regenerate the commerce encryption key or replace the database URL with an empty database.

OCR preflight now checks the same endpoint rules as the API. HTTPS is the default outside literal loopback. An existing operator-approved HTTP OmniRoute service can be used by explicitly setting `OCR_ALLOW_INSECURE_HTTP=1` together with its `OCR_BASE_URL`, `OCR_MODEL` and private key in `server.env`. Only the exact value `1` enables this compatibility option. It sends credentials and invoice bytes without transport encryption; prefer HTTPS or a deliberate server-local route. This option never downgrades an HTTPS URL, changes certificate checks, follows a fallback endpoint, or sends keys to a browser. A loopback URL inside Docker refers to the API container itself, not the VPS host.

## Explicit release packaging (no deployment implied)

The candidate application version is **1.5.0**, but its version alone is not sufficient deployment identity. An operator-approved package must include nonsecret `release.json` at the source root and beside the incoming archive:

```json
{
  "target": "apexbooks-vps",
  "version": "1.5.0",
  "source_sha": "<approved full 40-character lowercase Git commit SHA>",
  "api_image": "sha256:<actual 64-character image ID>",
  "web_image": "sha256:<actual 64-character image ID>"
}
```

These placeholders intentionally fail validation. Do not substitute a branch name, short SHA, mutable image tag, or guessed identity. Build both images from that approved source with OCI labels `org.opencontainers.image.revision` equal to its full SHA and `org.opencontainers.image.version` equal to the configured version. Generate image IDs after building; include release.json and source archive in `release.sha256`, all packaged source files in `VPS_FILES.sha256`, and the image archive in `images.sha256`. Keep checksums with the approved build evidence; checksums alone are not a signature or approval.

### Explicit image build identity propagation

Build in a clean checkout of the already approved commit. The SHA is operator/build-system input, **not inferred from whatever checkout happens to be present**. The following is a packaging recipe, not authorization to build or deploy on a host:

```bash
set -euo pipefail
# Set these from the approved immutable release record, never from a branch name.
: "${APEX_SOURCE_SHA:?Set the approved full source SHA first}"
: "${APEX_RELEASE_VERSION:?Set the approved release version (candidate 1.5.0)}"
[ "$(git rev-parse HEAD)" = "$APEX_SOURCE_SHA" ]
[ -z "$(git status --porcelain)" ]
docker build --build-arg APEX_BUILD_SHA="$APEX_SOURCE_SHA" \
  --build-arg APEX_RELEASE_VERSION="$APEX_RELEASE_VERSION" \
  -t "apexbooks-vps-api:$APEX_RELEASE_VERSION-$APEX_SOURCE_SHA" backend
docker build --build-arg VITE_BUILD_SHA="$APEX_SOURCE_SHA" \
  --build-arg APEX_RELEASE_VERSION="$APEX_RELEASE_VERSION" \
  -t "apexbooks-vps-web:$APEX_RELEASE_VERSION-$APEX_SOURCE_SHA" frontend
```

The API image bakes `APEX_BUILD_SHA` into its environment. The frontend exposes `VITE_BUILD_SHA` **before** `npm run build`, so the browser bundle contains the source identity; changing Nginx runtime variables cannot rewrite that bundle. Both final images carry matching OCI revision/version labels. Record their actual immutable image IDs in release.json after building. No argument defaults to a guessed SHA/version: absent inputs remain `unknown` and the VPS release checks refuse them.

Root development Compose passes `APEX_SOURCE_SHA`/`APEX_RELEASE_VERSION` as explicit build arguments (API and commerce worker use `APEX_BUILD_SHA`; web uses `VITE_BUILD_SHA`), defaulting to unknown when omitted. Dedicated VPS Compose does not rebuild: it requires the approved immutable images and validated `APEX_SOURCE_SHA` exported by `manage.py release-env`; `manage.py` also supplies that SHA on its own Compose calls. The API runtime receives the same approved SHA, while image labels/IDs and served readiness revision must independently agree. Inspect the web's displayed build revision as well as the API response during operator acceptance; a runtime API variable is not evidence of the browser bundle's identity.

Artifacts are named `Apex-Books-VPS-<version>-<source_sha>.tar.gz` and `Apex-Books-VPS-<version>-<source_sha>-images.tar.gz`. Transfer those artifacts, the three manifests, release.json and the bootstrap script through the normal operator-authenticated SSH process to `/root/apexbooks-vps-incoming/`. Transfer private server.env separately, never as command arguments or in source archives. This source-only change does not authorize credential access, transfer, migration, or deployment.

After separate operational approval, bootstrap prepares `/opt/apexbooks-vps/releases/<version>-<source_sha>/`, verifies the packaged and incoming identities match, and refuses malformed/unknown targets. For a first installation the operator edits private settings and runs `bash deploy/vps/install.sh` from that release directory. An existing activation instead uses the explicit upgrade procedure below.

The installer checks explicit release identity, private settings, free ports, source/image checksums and current Nginx validity before loading images. It verifies immutable image IDs and OCI revision/version labels before starting only the separate Apex project. Local/public checks require the configured API version, exact served `build_revision` source SHA **and running container image identity**. Certificates remain verified; no insecure or force bypass is added. No migrations run automatically. An incompatible schema must be resolved through a separately approved, backup-verified migration procedure before readiness can pass.

The first cutover backs up/replaces only the Apex API domain site and web site/snippet. Failed Nginx/HTTPS validation restores those files. Activation state records the complete release identity. Missing/legacy or different activation identity still refuses ordinary install/resume/retirement/rollback; use the explicit existing-installation procedure below, never delete an old marker to bypass this gate. Only after verified public readiness may the first-install narrowly scoped Atria retirement step run. Unrelated services are not restarted and database volumes are retained.

The API address is `https://api.apexbooks.in` and routes retain `/api/...`; the web app uses same-origin `/api/` proxying. Test Windows/Android with that API origin after public readiness passes. The 1.5.0 native Release builds target this API origin; historical installed clients may still use a preview origin. Verify the actual installed client and connected API build revisions before rollout.

## Upgrade an existing Apex Books activation, including 1.3

This path reuses the existing Apex proxy configuration and database. It does not retire Atria, replace Nginx files, or automatically migrate/restore data. Complete the actual-database clone rehearsal and verified full-database recovery procedure in [the upgrade checklist](../../docs/UPGRADE_1_3_TO_1_5.md). Identify and pause **every writer**, including any Vercel deployment, native client, worker or other API sharing the database; stopping this Compose project alone does not freeze those writers.

Stage the checksummed candidate, load its checksummed immutable images, and retain the previous images. Record the actual old activation digest (`sha256sum /opt/apexbooks-vps/shared/activated.json`) and only the old containers' `.Image` IDs, without dumping their environment. Save a private `/opt/apexbooks-vps/shared/upgrade-plan.json` with the following exact fields, replacing all placeholders after performing the stated checks:

```json
{
  "target_release_identity": {"target":"apexbooks-vps","version":"1.5.0","source_sha":"<approved full SHA>","api_image":"sha256:<candidate ID>","web_image":"sha256:<candidate ID>"},
  "previous_activation_sha256":"<SHA256 of the unchanged old activated.json bytes>",
  "previous_images":{"api":"sha256:<reviewed current API image ID>","web":"sha256:<reviewed current web image ID>"},
  "database_backup_reference":"<real nonsecret provider recovery point reference>",
  "isolated_restore_verified":true,
  "writers_paused":true,
  "schema_compatibility_reviewed":true,
  "recovery_plan_reviewed":true
}
```

`target_release_identity` must equal the packaged `release.json` exactly. The flags are operator attestations of completed work, not substitutes for a backup or proof generated by this helper. Keep credentials out of this record. The old activation's scoped proxy snapshot must still exist under the Apex backups directory.

Run from the staged candidate release directory during the reviewed maintenance window:

```bash
set -euo pipefail
export APEXBOOKS_ENV_FILE=/opt/apexbooks-vps/shared/server.env
release_exports="$(python3 deploy/vps/manage.py release-env)"
eval "$release_exports"
python3 deploy/vps/manage.py prepare-upgrade
# Only after all external writers are paused and recovery is verified:
docker compose -p apexbooks-vps -f deploy/vps/compose.yml stop api web
# This is the explicit, separately reviewed forward schema migration step:
docker compose -p apexbooks-vps -f deploy/vps/compose.yml run --rm --no-deps api python migrate.py
docker compose -p apexbooks-vps -f deploy/vps/compose.yml up -d --no-build --pull never api web
python3 deploy/vps/manage.py finish-upgrade
python3 deploy/vps/manage.py verify-other-apps
```

Preparation verifies the old running image IDs, exact review record, source checksum, candidate image IDs/labels, original private settings, ports and Nginx validity. It saves a private receipt, including a hash of the unchanged private settings, without replacing the old activation. Completion requires that unchanged receipt, settings and review record, exact candidate local/public readiness (including schema readiness), image IDs, version, source SHA and valid HTTPS. Only then does it archive the previous activation and plan and atomically write the new marker. It makes no Nginx or database changes.

On a migration or readiness failure, keep writers paused and the old activation/recovery evidence intact. Use the reviewed database recovery/forward-fix plan; do not restart old code blindly against a changed schema. The generic `rollback` command deliberately refuses an upgraded activation because the original Atria proxy rollback is not a 1.5 database rollback. Reconcile reports and test sign-in/native clients before re-enabling writers. This procedure and its mocked tests do not assert that a production recovery point, freeze or migration has occurred.

## Checks and rollback

### Updates from a Git checkout

`update_from_git.py` supports an existing deployment whose release directory came
from a source archive and therefore has no `.git` directory. Keep a separate clean
checkout at `/opt/apexbooks-vps/source`, pull with `git pull --ff-only origin main`,
and supply the full tested source SHA explicitly:

```bash
python3 deploy/vps/update_from_git.py stage --source-sha "$APEX_SOURCE_SHA"
# After pausing all Apex writers, when the operator explicitly waived a backup:
python3 deploy/vps/update_from_git.py apply --source-sha "$APEX_SOURCE_SHA" --without-backup --writers-paused
```

Staging exports only tracked public source into a separate versioned directory,
builds API/web sequentially, records actual image IDs and writes the source
manifest. Running services continue during builds. Apply retains the existing
private settings and Nginx routes, changes only `apexbooks-vps` api/web, applies
versioned migrations and verifies exact local/public readiness. The waiver is
stored as `backup_policy=operator_waived`, with a null backup reference and false
restore/rehearsal flags. It never invents backup evidence. The default verified
backup controller workflow remains supported. If a cutover partially completed,
use `resume --source-sha "$APEX_SOURCE_SHA" --writers-paused` after reviewing the
error; this starts the prepared candidate and verifies it without rerunning the
schema migration. Old code is not automatically restarted against a changed schema.

```bash
set -euo pipefail
python3 deploy/vps/manage.py verify-public
release_exports="$(python3 deploy/vps/manage.py release-env)"
eval "$release_exports"
docker compose -p apexbooks-vps -f deploy/vps/compose.yml ps
```

Paste these outputs or the installer's error, not full environments or Docker inspection dumps.

```bash
python3 deploy/vps/manage.py rollback
```

Rollback restores Atria's original restart policies, starts its retained containers and restores only the saved Apex-domain Nginx files. Apex containers remain available on loopback; accounting data is not reverted or deleted. Source/config backups and activation state live under `/opt/apexbooks-vps/backups` and `/opt/apexbooks-vps/shared`.

**Rollback is proxy/container-state recovery, not data or schema recovery.** The helper never reverses database migrations, restores an external PostgreSQL snapshot, or guarantees old code is compatible with a newer schema. Before restoring legacy routing, the operator must independently verify the old application's schema compatibility and external database recovery plan. No automatic downgrade is supported. Existing accounting data is external to these Compose containers; retaining a local container volume is not a backup of the hosted database.

Local verification for this change is limited to mocked command tests and shell syntax checks. No real SSH, Docker, Nginx, PostgreSQL, certificate, or hosted readiness commands were executed. A prior release's operational checks are not evidence that this candidate is deployed or deployment-ready. Actual approved-source packaging, immutable image labels, compatible schema, backup verification, host inspection and deployment acceptance remain operator gates.
