"""Scoped VPS lifecycle. No schema changes, global Docker stops or volume deletion."""
import argparse, base64, datetime, hashlib, json, os, re, shlex, shutil, socket, subprocess, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/opt/apexbooks-vps')
STATE = BASE / 'shared'
ENV = STATE / 'server.env'
API = Path('/etc/nginx/sites-enabled/apexbooks-api')
NGINX_ROOT = Path('/etc/nginx')
WEB = Path('/etc/nginx/sites-available/apexbooks-vps-web.conf')
LINK = Path('/etc/nginx/sites-enabled/apexbooks-vps-web.conf')
PROXY = Path('/etc/nginx/snippets/apexbooks-vps-proxy.conf')
PROJECT = 'apexbooks-vps'

def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kwargs)

def compose(*args):
    release=release_config()
    env={**os.environ,'APEX_API_IMAGE':release['api_image'],'APEX_WEB_IMAGE':release['web_image'],'APEX_SOURCE_SHA':release['source_sha']}
    return run(['docker', 'compose', '-p', PROJECT, '-f', ROOT / 'deploy/vps/compose.yml', *args], capture_output=True,env=env)

def settings():
    values = {}
    for line in ENV.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        key, raw = line.split('=', 1)
        parsed = shlex.split(raw, comments=True)
        values[key.strip()] = parsed[0] if parsed else ''
    return values

def release_config():
    """Nonsecret, packaged release identity; never infer a target from a running host."""
    try: value=json.loads((ROOT/'release.json').read_text())
    except (OSError,ValueError): raise RuntimeError('Missing or invalid release.json; explicit approved release identity required') from None
    if not isinstance(value,dict) or set(value)!={'target','version','source_sha','api_image','web_image'}:
        raise RuntimeError('Invalid release configuration fields')
    if value['target']!=PROJECT or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',str(value['version'])):
        raise RuntimeError('Unknown deployment target or invalid release version')
    if not re.fullmatch(r'[0-9a-f]{40}',str(value['source_sha'])) or value['source_sha']=='0'*40:
        raise RuntimeError('A full approved source commit SHA is required')
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}',str(value[key])) for key in ('api_image','web_image')):
        raise RuntimeError('Immutable API and web image IDs are required')
    return value

def verify_image_identity(running=False):
    release=release_config()
    for service in ('api','web'):
        image=release[service+'_image']
        if running:
            cid=compose('ps','-q',service).stdout.strip()
            if not cid:raise RuntimeError('Missing release container: '+service)
            actual=run(['docker','inspect','--format','{{.Image}}',cid],capture_output=True).stdout.strip()
            if actual!=image:raise RuntimeError('Deployed image identity mismatch: '+service)
        data=json.loads(run(['docker','image','inspect','--format','{{json .}}',image],capture_output=True).stdout)
        labels=(data.get('Config') or {}).get('Labels') or {}
        if data.get('Id')!=image or labels.get('org.opencontainers.image.revision')!=release['source_sha'] or labels.get('org.opencontainers.image.version')!=release['version']:
            raise RuntimeError('Packaged image release identity mismatch: '+service)

def activation_state():
    release=release_config()
    value=json.loads((STATE/'activated.json').read_text())
    if value.get('release_identity')!=release:raise RuntimeError('Activation state belongs to another or unidentified release; operator review required')
    return value


def ready(url, domain=None):
    release=release_config()
    args = ['curl', '--fail', '--silent', '--show-error', '--noproxy', '*', '--connect-timeout', '3', '--max-time', '8']
    if domain: args += ['--resolve', domain + ':443:127.0.0.1']
    try:
        result = run([*args, url], capture_output=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or '').strip()[:500]
        raise RuntimeError(f'HTTPS/HTTP probe {url}: curl exit {error.returncode}: {detail}') from None
    try: body = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('Expected readiness JSON at ' + url + '; response body withheld') from None
    if body.get('status') not in ('ready', 'ok') or body.get('version') != release['version'] or body.get('build_revision') != release['source_sha']:
        raise RuntimeError('Unexpected application/version/source revision at ' + url)

def other_containers():
    result = run(['docker', 'ps', '-q'], capture_output=True)
    data = {}
    for cid in result.stdout.split():
        value = run(['docker', 'inspect', '--format', '{{.Name}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.State.Status}}|{{.State.StartedAt}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', cid], capture_output=True).stdout.strip()
        parts = value.split('|')
        if len(parts) == 5 and parts[1] != PROJECT: data[cid] = parts
    return data

def preflight():
    release_config()
    if (STATE/'activated.json').exists():activation_state()
    if not ENV.is_file(): raise RuntimeError('Missing private server.env')
    if ENV.stat().st_mode & 0o077: raise RuntimeError('Run chmod 600 on private server.env')
    values = settings()
    if not values.get('DATABASE_URL', '').startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        raise RuntimeError('Existing PostgreSQL DATABASE_URL required; refusing empty/local database')
    if len(values.get('JWT_SECRET', '')) < 32: raise RuntimeError('Valid VPS JWT_SECRET required')
    try: assert len(base64.urlsafe_b64decode(values['COMMERCE_ENCRYPTION_KEY'])) == 32
    except Exception: raise RuntimeError('Original commerce encryption key required') from None
    external_ocr = values.get('OCR_BASE_URL', 'https://api.openai.com/v1').rstrip('/') != 'https://api.openai.com/v1'
    ocr_key = (values.get('OMNIROUTE_API_KEY') or values.get('OMNIROUTE')) if external_ocr else values.get('OPENAI_API_KEY')
    if not ocr_key:
        raise RuntimeError('Add your existing OmniRoute API key privately to server.env before deployment')
    if shutil.disk_usage(BASE).free < 5 * 1024**3: raise RuntimeError('At least 5 GB free disk is required')
    for port in (18090, 18091):
        with socket.socket() as listener:
            try: listener.bind(('127.0.0.1', port))
            except OSError:
                service = 'api' if port == 18091 else 'web'
                cid = compose('ps', '-q', service).stdout.strip()
                if not cid: raise RuntimeError(f'Port {port} belongs to another process; stopping') from None
                mapping = run(['docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', cid], capture_output=True)
                bindings = [x for group in json.loads(mapping.stdout).values() if group for x in group]
                if not any(x['HostIp'] == '127.0.0.1' and x['HostPort'] == str(port) for x in bindings):
                    raise RuntimeError(f'Unexpected port mapping for {service}')
    run(['nginx', '-t'])
    run(['systemctl', 'is-active', '--quiet', 'nginx'])
    STATE.mkdir(parents=True, exist_ok=True)
    baseline = STATE / 'other-containers-before.json'
    if not baseline.exists(): baseline.write_text(json.dumps(other_containers(), indent=2))
    print('Preflight passed: original database configuration, private keys, ports and Nginx checked')

def verify_local():
    verify_image_identity(running=True)
    last = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            ready('http://127.0.0.1:18091/api/ready')
            ready('http://127.0.0.1:18090/api/health')
            html = run(['curl', '-fsS', '--max-time', '10', 'http://127.0.0.1:18090/'], capture_output=True).stdout
            if 'id="root"' not in html: raise RuntimeError('React entry page not found')
            print('Local API, shared web/API routing and React entry page passed')
            return
        except Exception as error:
            last = type(error).__name__
            time.sleep(2)
    raise RuntimeError('Local health checks failed (' + str(last) + '); Nginx has not been changed')

def atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(content)
    temporary.chmod(mode)
    os.replace(temporary, path)

def restore(backup):
    state = json.loads((backup / 'files.json').read_text())
    for row in state:
        target = Path(row['path'])
        if row['existed']:
            atomic(target, (backup / row['name']).read_bytes(), row['mode'])
        elif target.exists(): target.unlink()
    if not json.loads((backup / 'meta.json').read_text())['web_link_existed'] and LINK.is_symlink(): LINK.unlink()
    run(['nginx', '-t'])
    run(['systemctl', 'reload', 'nginx'])
    print('Only Apex Books Nginx files restored; existing containers were left intact')

def activate():
    verify_local()
    marker = STATE / 'activated.json'
    if marker.exists():
        activation_state()
        verify_public()
        print('This release is already active')
        return
    dump = run(['nginx', '-T'], capture_output=True).stdout
    current = ''
    expected = API.resolve()
    if not API.is_file() or not expected.is_relative_to(NGINX_ROOT):
        raise RuntimeError('Expected API site path is missing or outside /etc/nginx')
    api_names = re.findall(r'^\s*server_name\s+([^;]+);', API.read_text(), re.M)
    if not api_names or any(set(names.split()) != {'api.apexbooks.in'} for names in api_names):
        raise RuntimeError('Existing API file contains unexpected domains; refusing replacement')
    for line in dump.splitlines():
        if line.startswith('# configuration file '): current = line[len('# configuration file '):].rstrip(':')
        match = re.match(r'\s*server_name\s+([^;]+);', line)
        if match and 'apexbooks.in' in match.group(1).split():
            raise RuntimeError('Root domain already has a site in ' + current + '; review it before cutover')
        if match and 'api.apexbooks.in' in match.group(1).split() and Path(current).resolve() != expected:
            raise RuntimeError('API domain appears in another site; refusing duplicate server blocks')
    if WEB.exists() or LINK.exists() or LINK.is_symlink() or PROXY.exists():
        raise RuntimeError('Apex VPS site/snippet already exists without activation state; review before replacing')
    for domain, certificate in [('apexbooks.in', 'apexbooks.in-0001'), ('api.apexbooks.in', 'api.apexbooks.in')]:
        cert = Path('/etc/letsencrypt/live') / certificate / 'fullchain.pem'
        run(['openssl', 'x509', '-in', cert, '-noout', '-checkhost', domain], capture_output=True)
        run(['openssl', 'x509', '-in', cert, '-noout', '-checkend', '86400'], capture_output=True)
    backup = BASE / 'backups' / ('nginx-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(parents=True, mode=0o700)
    files = []
    for index, target in enumerate((expected, WEB, PROXY)):
        row = {'path': str(target), 'existed': target.exists(), 'mode': target.stat().st_mode & 0o777 if target.exists() else 0o644, 'name': str(index) + '.conf'}
        if row['existed']: (backup / row['name']).write_bytes(target.read_bytes())
        files.append(row)
    (backup / 'files.json').write_text(json.dumps(files, indent=2))
    (backup / 'meta.json').write_text(json.dumps({'web_link_existed': False}))
    try:
        atomic(expected, (ROOT / 'deploy/vps/api.conf').read_bytes(), files[0]['mode'])
        atomic(WEB, (ROOT / 'deploy/vps/web.conf').read_bytes())
        atomic(PROXY, (ROOT / 'deploy/vps/proxy.conf').read_bytes())
        LINK.symlink_to(WEB)
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
        verify_public()
    except Exception:
        restore(backup)
        raise
    marker.write_text(json.dumps({'release_identity': release_config(), 'backup': str(backup), 'verified_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}, indent=2))
    print('Apex Books HTTPS sites active; rollback snapshot: ' + str(backup))

def public_probe_once():
    for domain in ('api.apexbooks.in', 'apexbooks.in'):
        ready('https://' + domain + '/api/ready', domain)
    try:
        html = run(['curl', '-fsS', '--noproxy', '*', '--resolve', 'apexbooks.in:443:127.0.0.1', '--connect-timeout', '3', '--max-time', '8', 'https://apexbooks.in/'], capture_output=True).stdout
    except subprocess.CalledProcessError as error:
        raise RuntimeError('HTTPS web probe https://apexbooks.in/: curl exit ' + str(error.returncode) + ': ' + (error.stderr or '').strip()[:500]) from None
    if 'id="root"' not in html: raise RuntimeError('Public React entry page not found')

def verify_public():
    verify_image_identity(running=True)
    # systemctl reload can finish before the new Nginx workers accept requests.
    # Retry the actual TLS/version checks; never bypass certificate validation.
    deadline = time.monotonic() + 45
    attempt = 0
    while True:
        attempt += 1
        try:
            public_probe_once()
            break
        except RuntimeError as error:
            if time.monotonic() >= deadline:
                raise RuntimeError('HTTPS checks did not become ready; ' + str(error)) from None
            if attempt == 1 or attempt % 5 == 0:
                print('Waiting for HTTPS readiness: ' + str(error), flush=True)
            time.sleep(1)
    print('Both HTTPS domains serve verified Apex Books '+release_config()['version']+' source '+release_config()['source_sha']+' with certificate validation')

def retire_atria():
    if not (STATE / 'activated.json').exists(): raise RuntimeError('Activate and verify Apex Books first')
    activation_state()
    verify_public()
    found = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=atria-server'], capture_output=True).stdout.split()
    if not found:
        print('No Atria containers found; no Atria services or data were changed')
        return
    policies = {}
    for cid in found:
        name = run(['docker', 'inspect', '--format', '{{.Name}}', cid], capture_output=True).stdout.strip().lstrip('/')
        if name not in ('atria-server-api-1', 'atria-server-db-1'):
            raise RuntimeError('Unexpected Atria service; refusing broader stop')
        policies[cid] = json.loads(run(['docker', 'inspect', '--format', '{{json .HostConfig.RestartPolicy}}', cid], capture_output=True).stdout)
    policy_file = STATE / 'atria-restart-policies.json'
    if not policy_file.exists(): policy_file.write_text(json.dumps(policies, indent=2))
    if found:
        run(['docker', 'update', '--restart=no', *found], capture_output=True)
        run(['docker', 'stop', '--time', '45', *found])
    print('Atria services stopped. Database volumes, images and /opt/atria-server are retained.')

def verify_other_apps():
    previous = json.loads((STATE / 'other-containers-before.json').read_text())
    current = other_containers()
    changed = [row[0] for cid, row in previous.items() if row[1] != 'atria-server' and current.get(cid) != row]
    if changed:
        print('Other-app baseline changed during deployment; no corrective actions taken: ' + ', '.join(changed))
    else: print('Other-app running-container baseline is unchanged')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'verify-local', 'activate', 'verify-public', 'retire-atria', 'verify-other-apps', 'rollback', 'resume', 'release-env', 'verify-images'])
    args = parser.parse_args()
    if args.action=='release-env':
        release=release_config()
        for key,value in {'APEX_RELEASE_VERSION':release['version'],'APEX_SOURCE_SHA':release['source_sha'],'APEX_API_IMAGE':release['api_image'],'APEX_WEB_IMAGE':release['web_image']}.items():print('export '+key+'='+shlex.quote(value))
        return
    if os.geteuid() != 0: raise RuntimeError('Run this VPS script as root')
    if not ROOT.is_relative_to(BASE / 'releases'): raise RuntimeError('Use the staged /opt/apexbooks-vps/releases directory')
    if args.action == 'resume':
        preflight()
        run(['sha256sum', '--check', ROOT / 'VPS_FILES.sha256'], cwd=ROOT, capture_output=True)
        activate()
        retire_atria()
        verify_other_apps()
    elif args.action == 'rollback':
        state = activation_state()
        # Restart the retired legacy services before restoring their proxy.
        found = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=atria-server'], capture_output=True).stdout.split()
        policies = json.loads((STATE / 'atria-restart-policies.json').read_text()) if (STATE / 'atria-restart-policies.json').exists() else {}
        for cid in found:
            if cid in policies:
                policy = policies[cid]
                flag = policy['Name']
                if flag == 'on-failure' and policy.get('MaximumRetryCount'): flag += ':' + str(policy['MaximumRetryCount'])
                run(['docker', 'update', '--restart=' + flag, cid], capture_output=True)
        if found: run(['docker', 'start', *found])
        restore(Path(state['backup']))
        (STATE / 'activated.json').unlink()
    else: {'verify-images':verify_image_identity, 'preflight': preflight, 'verify-local': verify_local, 'activate': activate, 'verify-public': verify_public, 'retire-atria': retire_atria, 'verify-other-apps': verify_other_apps}[args.action]()

if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Never render database connection strings or Docker environment values.
        if isinstance(error, subprocess.CalledProcessError):
            print('Command failed: ' + str(error.cmd[0]) + '. Existing apps were not globally restarted.')
            if str(error.cmd[0]) == 'curl': print((error.stderr or '').strip()[:500])
        else: print(str(error))
        raise SystemExit(1)
