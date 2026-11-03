#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /root/apexbooks-vps-incoming
sha256sum --check release.sha256
# Nonsecret approved identity accompanies the checksummed release archive.
identity_text="$(python3 - <<'PYCONFIG'
import json,re
c=json.load(open("release.json"))
if c.get("target")!="apexbooks-vps":raise SystemExit("Unknown deployment target")
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+",str(c.get("version",""))):raise SystemExit("Invalid version")
if not re.fullmatch(r"[0-9a-f]{40}",str(c.get("source_sha",""))) or c["source_sha"]=="0"*40:raise SystemExit("Full approved source SHA required")
print(c["version"]);print(c["source_sha"])
PYCONFIG
)"
readarray -t identity <<< "$identity_text"
[ "${#identity[@]}" -eq 2 ] || { echo "Invalid release identity" >&2; exit 1; }
release="${identity[0]}-${identity[1]}"
archive="Apex-Books-VPS-${release}.tar.gz"
install -d -m 0755 /opt/apexbooks-vps/releases
install -d -m 0700 /opt/apexbooks-vps/shared /opt/apexbooks-vps/backups
if [ ! -d "/opt/apexbooks-vps/releases/${release}" ]; then
    install -d -m 0755 "/opt/apexbooks-vps/releases/${release}"
    tar --extract --gzip --file "${archive}" --directory "/opt/apexbooks-vps/releases/${release}" --no-same-owner
else
    echo 'Release directory already exists; checking its source manifest.'
    (cd "/opt/apexbooks-vps/releases/${release}" && sha256sum --check VPS_FILES.sha256)
fi
cmp -- release.json "/opt/apexbooks-vps/releases/${release}/release.json"
(cd "/opt/apexbooks-vps/releases/${release}" && python3 deploy/vps/manage.py release-env >/dev/null)
if [ ! -f /opt/apexbooks-vps/shared/server.env ]; then
    install -m 0600 server.env /opt/apexbooks-vps/shared/server.env
fi
chmod 0600 /opt/apexbooks-vps/shared/server.env
if [ -f /opt/apexbooks-vps/shared/activated.json ]; then
    echo 'Prepared existing installation. Retain its activation marker and follow the README prepare-upgrade / finish-upgrade procedure; ordinary install.sh deliberately refuses a different release.'
else
    echo 'Prepared first installation. Configure the OCR endpoint/key privately in shared/server.env, then run install.sh.'
fi
