# ApexBooks dependency metadata audit — 2 November 2026

Scope: standard package-manager advisory lookups for the checked-out application and isolated local test environment. No production inventory, credential access, exploit tests, or broad security assessment. Remediations below were performed only in local source/tooling; no production configuration or secrets were changed.

## Results

| Inventory | Result |
|---|---|
| Frontend lockfile, npm audit --omit=dev | 0 reported advisories |
| Frontend complete lockfile | Before: 1 distinct moderate advisory across 4 dev-tool entries. After scoped override: 0 reported advisories |
| Backend requirements.txt, pip-audit resolved requirements | 0 reported advisories across 43 resolved distributions |
| Existing isolated backend test venv | Before: pip 25.0.1 had 6 distinct installer advisories. After pip 26.2.2: 0 reported advisories |

These checks cover known advisory metadata, not proof of exploitability or absence of vulnerabilities. Backend requirements pin top-level packages but not the full transitive graph; the resolved runtime audit is not a production-installed inventory.

## Frontend development tool finding

- Installed minimatch **10.2.6**, through ESLint **10.14.0** and @eslint/config-array **0.23.5**.
- **GHSA-g3hv-75wg-m249 / CVE-2026-118764**, moderate, patched **11.0.1**.
- Advisory concerns excessive work from specially supplied glob patterns when optimizationLevel >= 2. Here the package is in the development lint toolchain, not the browser runtime. No application-facing path or current ESLint optimizationLevel >= 2 setting was established; do not infer deployed exposure solely from package presence.
- Latest registry ESLint remains 10.14.0 and declares minimatch ^10.2.6. Applied a **scoped ESLint-subtree override** to minimatch 11.0.1, not a blanket audit-force upgrade. v11 removes APIs such as makeRe/AST, but current ESLint and config-array call only the retained Minimatch constructor, .pattern and .match(path, partial). Dual ESM/CommonJS exports and Node 18/20/22+ engine support are unchanged. Installation used --ignore-scripts. Directory lint, explicit glob lint, all 59 web tests and production build pass. Full npm audit now reports zero advisories. Remove the override after upstream ESLint adopts the fixed major version and compatibility tests pass.

Sources: [reviewed advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249), [maintainer release](https://github.com/isaacs/minimatch/releases/tag/v11.0.1).

## Python installer finding (not an application dependency)

Updated the isolated /tmp/apex-venv installer from pip 25.0.1 to **26.2.2**, then repeated installed-inventory pip-audit: zero known vulnerabilities. Backend application requirements were unchanged. CI/deployment bootstrap installer versions still require their own inventory; this local result is not a claim about production tooling.

| Advisory aliases | First patched pip version reported |
|---|---|
| CVE-2025-8869 / GHSA-4xh5-x5gv-qwph | 25.3 |
| CVE-2026-1703 / GHSA-6vgw-5pg2-w6jp | 26.0 |
| CVE-2026-3219 / GHSA-58qw-9mgm-455v | 26.1 |
| CVE-2026-6357 / GHSA-jp4c-xjxw-mgf9 | 26.1 |
| CVE-2026-8643 / GHSA-wf93-45jw-7689 | 26.1.2 |
| CVE-2026-13346 / GHSA-qwm4-qh6w-59xr | 26.2 |

These are installation/archive/index-handling concerns, not HTTP API library findings. Reachability depends on installer inputs and environment; it was not tested. Python 3.12 is in use locally, which meets the PEP 706 mitigation described for the older tar-extraction advisory. Other installer advisories should still be addressed by updating the tool.

Source: [official pip changelog](https://pip.pypa.io/en/stable/news/).

## Concrete safe-default observation (source only)

backend/main.py rejects the bundled development JWT fallback and short secrets for PostgreSQL URLs, but the check is conditional on database dialect. An accidentally network-exposed SQLite/default configuration would still accept the development fallback. Implemented fail-closed API startup requiring an explicit non-placeholder secret of at least 32 characters for every database, without an insecure bypass. Actual startup subprocess tests reject missing/short/example SQLite secrets and accept an explicit long synthetic key; fixture and local setup documentation are updated. The full standard checks pass after this change. This is a configuration-code observation; actual production settings were not inspected or changed. CORS defaults to localhost, not a wildcard.

## OCR transport remediation

The source no longer honors a public HTTP OCR transport override. Non-loopback endpoints require HTTPS; explicit loopback HTTP remains available for local development only. URL user-info, query strings, fragments and malformed endpoints are rejected with a safe configuration error. OCR status reports unavailable and purchase extraction returns 503 before sending a document or provider credential; ordinary manual purchase entry remains available. Mock-only API regressions prove the old override cannot trigger an outbound call, and HTTPS/loopback cases remain supported. No live OCR configuration was read or changed, and no invoice image or key was sent during verification.

## Final local verification

- 145 backend tests pass, including 7 startup/transport configuration tests.
- 60 web tests, lint and production build pass.
- Four isolated live HTTP accounting workflows pass; 203 native route contracts match.
- Simulated transactional backup/restore checks pass. Encrypted backup checks remain locally skipped because age/age-keygen are unavailable; hosted verification is tracked separately.
- Known advisory metadata: full npm audit and local installed Python audit both report zero findings after remediation. This is not a comprehensive security certification or a production inventory.

## Evidence and reproducibility

Raw advisory outputs contain dependency names/versions only:
- /tmp/apex-npm-audit.json
- /tmp/apex-npm-audit-runtime.json
- /tmp/apex-pip-audit-runtime.json
- /tmp/apex-pip-audit-installed.json
- /tmp/apex-npm-audit-after.json
- /tmp/apex-pip-audit-installed-after.json

pip-audit 2.10.1 installed into a separate /tmp/apex-audit-venv. Cache paths were redirected into /tmp after default home caches were read-only. Commands: npm audit --json; npm audit --omit=dev --json; pip-audit -r backend/requirements.txt --format json; pip-audit --path /tmp/apex-venv/lib/python3.12/site-packages --format json.
