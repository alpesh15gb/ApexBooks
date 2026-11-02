#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /root/apexbooks-vps-incoming
sha256sum --check release.sha256
install -d -m 0755 /opt/apexbooks-vps/releases
install -d -m 0700 /opt/apexbooks-vps/shared /opt/apexbooks-vps/backups
if [ ! -d /opt/apexbooks-vps/releases/1.3.0 ]; then
    install -d -m 0755 /opt/apexbooks-vps/releases/1.3.0
    tar --extract --gzip --file Apex-Books-VPS-1.3.0.tar.gz --directory /opt/apexbooks-vps/releases/1.3.0 --no-same-owner
else
    echo 'Release directory already exists; checking its source manifest.'
    (cd /opt/apexbooks-vps/releases/1.3.0 && sha256sum --check VPS_FILES.sha256)
fi
if [ ! -f /opt/apexbooks-vps/shared/server.env ]; then
    install -m 0600 server.env /opt/apexbooks-vps/shared/server.env
fi
chmod 0600 /opt/apexbooks-vps/shared/server.env
echo 'Prepared. Add OMNIROUTE_API_KEY privately in /opt/apexbooks-vps/shared/server.env, then run install.sh.'
