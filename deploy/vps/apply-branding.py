#!/usr/bin/env python3
"""Scoped web-only branding update. Does not read or print server credentials."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

IMAGE = 'apexbooks-vps-web:1.3.2'
BASE = Path('/opt/apexbooks-vps/releases/1.3.0/deploy/vps/compose.yml')
OVERRIDE = Path('/opt/apexbooks-vps/shared/branding.compose.yml')
ARCHIVE = Path('/root/apexbooks-vps-incoming/Apex-Books-Web-Branding-1.3.2-images.tar.gz')
IMAGE_SHA256 = '__IMAGE_SHA256__'
LOGO_SHA256 = '__LOGO_SHA256__'

def run(*args):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

def baseline():
    ids = run('docker', 'ps', '-q').split()
    if not ids:
        raise RuntimeError('No running containers found; refusing an unexpected host')
    lines = run('docker', 'inspect', '--format', '{{.Id}} {{.State.StartedAt}} {{.Name}}', *ids).splitlines()
    return {line.split()[0]: line.split()[1:] for line in lines}

def web_id():
    ids = run('docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=apexbooks-vps',
              '--filter', 'label=com.docker.compose.service=web').split()
    if len(ids) != 1:
        raise RuntimeError('Expected exactly one running Apex Books web container')
    return ids[0]

def probe():
    logo = subprocess.run(['curl', '--noproxy', '*', '--fail', '--silent', '--show-error',
                          '--connect-timeout', '3', '--max-time', '8', '--resolve', 'apexbooks.in:443:127.0.0.1',
                          'https://apexbooks.in/apexbooks-logo.png'], check=True, capture_output=True).stdout
    if hashlib.sha256(logo).hexdigest() != LOGO_SHA256:
        raise RuntimeError('Public HTTPS logo checksum does not match the supplied artwork')
    ready = json.loads(run('curl', '--noproxy', '*', '--fail', '--silent', '--show-error',
                           '--connect-timeout', '3', '--max-time', '8', '--resolve', 'apexbooks.in:443:127.0.0.1',
                           'https://apexbooks.in/api/ready'))
    if ready.get('status') != 'ready' or ready.get('version') != '1.3.0':
        raise RuntimeError('Accounting API readiness failed')

def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run this installer as root on the Apex Books VPS')
    if not BASE.is_file():
        raise RuntimeError('Apex Books compose file is missing: '+str(BASE))
    if BASE.is_symlink() or OVERRIDE.is_symlink():
        raise RuntimeError('Unexpected deployment file symlink; refusing to overwrite it')
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != IMAGE_SHA256:
        raise RuntimeError('Branding image archive checksum failed')
    before = baseline()
    old_web = web_id()
    old_image = run('docker', 'inspect', '--format', '{{.Config.Image}}', old_web).strip()
    if old_image not in ('apexbooks-vps-web:1.3.0', IMAGE):
        raise RuntimeError('Unexpected current Apex web image; refusing to overwrite it')
    if old_image == IMAGE:
        probe()
        print('The supplied logo is already active; no containers restarted')
        return
    run('docker', 'load', '-i', str(ARCHIVE))
    run('docker', 'image', 'inspect', IMAGE)
    previous = OVERRIDE.read_bytes() if OVERRIDE.exists() else None
    backup = OVERRIDE.with_name('branding-before-1.3.2.json')
    if backup.exists():
        raise RuntimeError('A previous activation snapshot exists; inspect it before retrying')
    backup.write_text(json.dumps({'image':old_image,'override':previous.decode() if previous is not None else None},indent=2))
    command = ['docker', 'compose', '-p', 'apexbooks-vps', '-f', str(BASE), '-f', str(OVERRIDE),
               'up', '-d', '--no-deps', '--pull', 'never', 'web']
    try:
        OVERRIDE.write_text('services:\n  web:\n    image: '+IMAGE+'\n')
        run(*command)
        deadline = time.monotonic()+60
        while True:
            try:
                probe()
                break
            except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Branding readiness timed out')
                time.sleep(2)
        after = baseline()
        if any(after.get(cid) != info for cid,info in before.items() if cid != old_web):
            raise RuntimeError('Another container changed during the operation; no other container will be restarted')
        print('Apex Books logo is active over validated HTTPS. API and other running containers were not restarted.')
    except Exception:
        OVERRIDE.write_text(previous.decode() if previous is not None else 'services:\n  web:\n    image: '+old_image+'\n')
        run(*command)
        if previous is None:
            OVERRIDE.unlink()
        print('Only the Apex Books web image was rolled back. API, Nginx and database configuration were not changed.',file=sys.stderr)
        raise

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Subprocess stderr might contain deployment details. Report its command and exit code only.
        if isinstance(exc,subprocess.CalledProcessError):
            print(f'Command failed: {exc.cmd[0]}, exit {exc.returncode}',file=sys.stderr)
        else:
            print(str(exc),file=sys.stderr)
        sys.exit(1)
