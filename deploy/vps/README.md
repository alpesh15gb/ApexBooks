# Dedicated Apex Books VPS deployment

Target: Ubuntu 24.04 x86-64, system Nginx, existing Docker apps. DNS already points to 82.112.236.81. Reuses the valid apexbooks.in-0001 and api.apexbooks.in certificates. Bagisto hosting is deferred.

Only the `apexbooks-vps` Compose project is started. Web/API publish on 127.0.0.1:18090/18091, with 192 MB/1 GB memory limits. Prebuilt images avoid compiling on the VPS. There is no new PostgreSQL container or published database port; the existing accounting Neon database and commerce encryption key are retained. No migrations execute during container startup. Readiness refuses an incompatible schema.

Private `server.env` is transferred separately and kept at `/opt/apexbooks-vps/shared/server.env` with mode 600. It contains a new VPS JWT session key, so users sign in on the new domains. Existing accounts/data are shared; Vercel stays available with its own sessions. Add the existing OmniRoute key privately before deployment; preflight refuses a missing OCR key. Do not regenerate the commerce encryption key or replace the database URL with an empty database.

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

After separate operational approval, bootstrap prepares `/opt/apexbooks-vps/releases/<version>-<source_sha>/`, verifies the packaged and incoming identities match, and refuses malformed/unknown targets. Then the operator edits private settings and runs `bash deploy/vps/install.sh` from that release directory.

The installer checks explicit release identity, private settings, free ports, source/image checksums and current Nginx validity before loading images. It verifies immutable image IDs and OCI revision/version labels before starting only the separate Apex project. Local/public checks require the configured API version, exact served `build_revision` source SHA **and running container image identity**. Certificates remain verified; no insecure or force bypass is added. No migrations run automatically. An incompatible schema must be resolved through a separately approved, backup-verified migration procedure before readiness can pass.

The cutover backs up/replaces only the Apex API domain site and web site/snippet. Failed Nginx/HTTPS validation restores those files. Activation state records the complete release identity. Missing/legacy or different activation identity refuses automatic resume/upgrade/retirement/rollback and requires operator review; never delete or rewrite an old marker merely to bypass this gate. Only after verified public readiness may the existing narrowly scoped Atria retirement step run. Unrelated services are not restarted and database volumes are retained.

The API address is `https://api.apexbooks.in` and routes retain `/api/...`; the web app uses same-origin `/api/` proxying. Test Windows/Android with that API origin after public readiness passes. The 1.5.0 native Release builds target this API origin; historical installed clients may still use a preview origin. Verify the actual installed client and connected API build revisions before rollout.

## Checks and rollback

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
