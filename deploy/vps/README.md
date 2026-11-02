# Dedicated Apex Books VPS deployment

Target: Ubuntu 24.04 x86-64, system Nginx, existing Docker apps. DNS already points to 82.112.236.81. Reuses the valid apexbooks.in-0001 and api.apexbooks.in certificates. Bagisto hosting is deferred.

Only the `apexbooks-vps` Compose project is started. Web/API publish on 127.0.0.1:18090/18091, with 192 MB/1 GB memory limits. Prebuilt images avoid compiling on the VPS. There is no new PostgreSQL container or published database port; the existing accounting Neon database and commerce encryption key are retained. No migrations execute during container startup. Readiness refuses an incompatible schema.

Private `server.env` is transferred separately and kept at `/opt/apexbooks-vps/shared/server.env` with mode 600. It contains a new VPS JWT session key, so users sign in on the new domains. Existing accounts/data are shared; Vercel stays available with its own sessions. Add the existing OmniRoute key privately before deployment; preflight refuses a missing OCR key. Do not regenerate the commerce encryption key or replace the database URL with an empty database.

## Transfer from Windows PowerShell

```powershell
ssh root@82.112.236.81 "install -d -m 0700 /root/apexbooks-vps-incoming"
scp "D:\Apex Books\deliverables\Apex-Books-VPS-1.3.0.tar.gz" "D:\Apex Books\deliverables\Apex-Books-VPS-1.3.0-images.tar.gz" "D:\Apex Books\deliverables\release.sha256" "D:\Apex Books\deliverables\images.sha256" "D:\Apex Books\deliverables\Apex-Books-VPS-bootstrap.sh" root@82.112.236.81:/root/apexbooks-vps-incoming/
scp "$env:LOCALAPPDATA\ApexBooks\Deployments\apexbooks-vps\server.env" root@82.112.236.81:/root/apexbooks-vps-incoming/server.env
```

Use the normal SSH host-key verification and authentication process. No credential values are command arguments.

## Prepare on the VPS

```bash
bash /root/apexbooks-vps-incoming/Apex-Books-VPS-bootstrap.sh
nano /opt/apexbooks-vps/shared/server.env
```

Set `OMNIROUTE_API_KEY='your-existing-key'`, save and exit. Keep the database, encryption and other prepared settings intact. Do not paste the environment file in chat.

## Deploy after saving the key

```bash
cd /opt/apexbooks-vps/releases/1.3.0
bash deploy/vps/install.sh
```

The installer checks private settings, free ports, source/image checksums and current Nginx validity. It loads only the two Apex images, starts the separate project, checks local readiness, then backs up and replaces only the API domain site plus a new Apex web site/snippet. It checks TLS names/expiry, validates Nginx and performs a graceful reload. A failed validation/HTTPS check restores those files automatically. No global restart, pruning, certificate renewal or firewall changes are performed.

Only after both HTTPS domains report 1.3.0 does it disable automatic restart and stop `atria-server-api-1` and `atria-server-db-1`. Unexpected Atria service names refuse retirement. Atria's containers, volumes, images and `/opt/atria-server` configuration remain available. Other apps' running-container baseline is compared afterward; unrelated services are never restarted automatically.

The API address is `https://api.apexbooks.in` and routes retain `/api/...`; the web app uses same-origin `/api/` proxying. Test Windows/Android with that API origin after public readiness passes. Existing native defaults still point to the Vercel preview until their next distribution/configuration update.

## Checks and rollback

```bash
python3 deploy/vps/manage.py verify-public
docker compose -p apexbooks-vps -f deploy/vps/compose.yml ps
```

Paste these outputs or the installer's error, not full environments or Docker inspection dumps.

```bash
python3 deploy/vps/manage.py rollback
```

Rollback restores Atria's original restart policies, starts its retained containers and restores only the saved Apex-domain Nginx files. Apex containers remain available on loopback; accounting data is not reverted or deleted. Source/config backups and activation state live under `/opt/apexbooks-vps/backups` and `/opt/apexbooks-vps/shared`.

Local verification: existing PostgreSQL schema read-only check, actual non-root API/web container startup, both readiness routes, existing synthetic-account sign-in/company lookup, and seven cutover/rollback/scope regressions. Both site templates also pass actual Nginx 1.24 syntax validation in an isolated sandbox. Host activation still requires the operator to run the transfer/install commands and return the resulting output.
