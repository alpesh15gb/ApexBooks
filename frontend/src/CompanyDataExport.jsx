import React, {useEffect, useRef, useState} from 'react';
import {Download} from 'lucide-react';

export default function CompanyDataExport({companyId, role}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false), active = useRef(null), scope = useRef({companyId, role});
  scope.current = {companyId, role};
  useEffect(() => {
    mounted.current = true;
    const invalidate = () => {
      active.current?.controller.abort(); active.current = null;
      if (mounted.current) { setBusy(false); setError(''); }
    };
    const changedSession = event => { if (event.key === 'token' || event.key === null) invalidate(); };
    window.addEventListener('storage', changedSession);
    invalidate();
    return () => {
      mounted.current = false; active.current?.controller.abort(); active.current = null;
      window.removeEventListener('storage', changedSession);
    };
  }, [companyId, role]);
  if (role !== 'owner') return null;
  async function download() {
    if (active.current || !mounted.current || scope.current.role !== 'owner') return;
    const operation = {companyId, role, token: localStorage.getItem('token'), controller: new AbortController()};
    active.current = operation;
    const current = () => mounted.current && active.current === operation && !operation.controller.signal.aborted
      && scope.current.companyId === operation.companyId && scope.current.role === operation.role
      && operation.role === 'owner' && localStorage.getItem('token') === operation.token;
    setBusy(true); setError('');
    try {
      if (!current()) return;
      const response = await fetch(`/api/companies/${operation.companyId}/data-export.json`, {headers: {Authorization: `Bearer ${operation.token}`}, signal: operation.controller.signal});
      if (!current()) return;
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        if (!current()) return;
        const detail = payload.detail;
        throw Error(typeof detail === 'string' && detail.includes('COMPLETE_BACKUP_REQUIRED') ? 'This company contains retained receipts. Use Complete backup and restore below so no evidence is omitted.' : typeof detail === 'string' ? detail : detail?.message || 'Company data export failed. Use Complete backup and restore when this company contains retained receipts.');
      }
      const blob = await response.blob();
      if (!current()) return;
      let url;
      try {
        url = URL.createObjectURL(blob);
        if (!current()) return;
        const link = document.createElement('a');
        link.href = url; link.download = `apex-company-${operation.companyId.slice(0, 8)}.json`;
        if (current()) link.click();
      } finally { if (url) setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (err) { if (current()) setError(err.message); }
    finally { if (active.current === operation) { active.current = null; if (mounted.current && scope.current.companyId === operation.companyId && scope.current.role === operation.role) setBusy(false); } }
  }
  return <section className="member-settings"><h2>Company data export</h2><p>Download this company's records, journal entries, bank statement lines and settings as JSON. Keep the file private. Use Backup and restore below to restore an export as a separate company.</p><button className="button secondary" onClick={download} disabled={busy}><Download size={16}/>{busy ? 'Preparing…' : 'Download company data'}</button>{error && <div className="error banner">{error}</div>}</section>;
}
