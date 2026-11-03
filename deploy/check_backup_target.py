#!/usr/bin/env python3
"""Fail closed: these fixed-name scripts support only the root local Compose DB.

Never prints resolved Compose configuration (which can contain credentials).
This is a target guard, not proof that a backup is restorable or complete.
"""
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit


def local_database(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme in {"postgresql", "postgresql+psycopg"}
                and parsed.hostname == "db" and parsed.port in (None, 5432)
                and parsed.username == "apex" and parsed.path == "/apex"
                and not parsed.query and not parsed.fragment)
    except (TypeError, ValueError):
        return False


def valid_config(config):
    services = config.get("services", {})
    db, api = services.get("db", {}), services.get("api", {})
    db_env, api_env = db.get("environment", {}), api.get("environment", {})
    image = db.get("image", "")
    return (isinstance(db_env, dict) and isinstance(api_env, dict)
            and (image.startswith("postgres:") or image.startswith("postgres@sha256:"))
            and db_env.get("POSTGRES_DB") == "apex"
            and db_env.get("POSTGRES_USER") == "apex"
            and local_database(api_env.get("DATABASE_URL"))
            and not api.get("extra_hosts") and not api.get("network_mode")
            and not db.get("network_mode")
            and not any(n.get("external") for n in config.get("networks", {}).values()))


# Validate inside the running API too: a changed Compose file must not disguise
# a running API which still uses an external database. No URL leaves the process.
RUNTIME_CHECK = '''import os,sys
from urllib.parse import urlsplit
try:
 p=urlsplit(os.environ.get("DATABASE_URL", ""))
 ok=p.scheme in ("postgresql", "postgresql+psycopg") and p.hostname=="db" and p.port in (None,5432) and p.username=="apex" and p.path=="/apex" and not p.query and not p.fragment
except (TypeError,ValueError):
 ok=False
sys.exit(0 if ok else 1)
'''


def main():
    if os.environ.get("APEX_BACKUP_SCOPE") != "compose-local":
        print("Set APEX_BACKUP_SCOPE=compose-local only after reviewing the local Compose target. Hosted/external PostgreSQL requires its own recovery procedure.", file=sys.stderr)
        return 1
    try:
        result = subprocess.run(["docker", "compose", "config", "--format", "json"],
                                check=True, capture_output=True, timeout=30)
        if not valid_config(json.loads(result.stdout)):
            raise ValueError("unsupported target")
        subprocess.run(["docker", "compose", "exec", "-T", "api", "python", "-c", RUNTIME_CHECK],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        print("Backup target preflight failed. These scripts require the reviewed local Compose db/apex database and a running API using it. No backup/restore was started. Use a separately reviewed provider recovery procedure for external PostgreSQL.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
