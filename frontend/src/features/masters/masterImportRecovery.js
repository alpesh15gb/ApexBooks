// Only opaque references and a one-way payload fingerprint survive tab reload.
// Session storage is not a cross-device or closed-tab recovery journal.
export function masterImportActor(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const {sub} = JSON.parse(atob(part));
    if (typeof sub === 'string' && /^[a-zA-Z0-9-]{1,128}$/.test(sub)) return sub;
  } catch { /* The server still owns authentication; this is only a namespace. */ }
  return '';
}
export function masterImportStore(companyId, token, storage = globalThis.sessionStorage) {
  const actor = masterImportActor(token);
  if (!actor || !companyId) throw Error('Sign in again before starting a recoverable import.');
  const slot = `apex-master-import:${actor}:${companyId}`;
  return {
    read() {
      const raw = storage.getItem(slot);
      if (!raw) return null;
      let value; try { value = JSON.parse(raw); } catch { throw Error('The import recovery reference is damaged. Verify the original import before starting another.'); }
      if (!/^[a-f0-9-]{36}$/.test(value.key || '') || !/^[a-f0-9]{64}$/.test(value.hash || '') || !['party','item'].includes(value.kind)) throw Error('The import recovery reference is damaged. Verify the original import before starting another.');
      return {key:value.key, hash:value.hash, kind:value.kind};
    },
    save(value) {
      const previous = this.read();
      if (previous && previous.key !== value.key) throw Error('Recover the previous import before starting another.');
      storage.setItem(slot, JSON.stringify({key:value.key, hash:value.hash, kind:value.kind}));
      if (this.read()?.key !== value.key) throw Error('Could not retain the import recovery reference. No import was sent.');
    },
    clear(key) { if (this.read()?.key === key) storage.removeItem(slot); },
  };
}
export async function masterImportHash(body) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(body)));
  return Array.from(new Uint8Array(hash), value => value.toString(16).padStart(2,'0')).join('');
}
