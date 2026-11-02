#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
export APEXBOOKS_ENV_FILE=/opt/apexbooks-vps/shared/server.env
python3 deploy/vps/manage.py preflight
sha256sum --check VPS_FILES.sha256
sha256sum --check /root/apexbooks-vps-incoming/images.sha256
docker load --input /root/apexbooks-vps-incoming/Apex-Books-VPS-1.3.0-images.tar.gz
docker compose -p apexbooks-vps -f deploy/vps/compose.yml config --quiet
docker compose -p apexbooks-vps -f deploy/vps/compose.yml up -d --no-build api web
python3 deploy/vps/manage.py verify-local
python3 deploy/vps/manage.py activate
python3 deploy/vps/manage.py retire-atria
python3 deploy/vps/manage.py verify-other-apps
docker compose -p apexbooks-vps -f deploy/vps/compose.yml ps
