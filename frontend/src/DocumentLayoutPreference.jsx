import React, { useEffect, useRef, useState } from 'react';

const layouts = ['modern', 'vintage', 'mrp_discount', 'elegant', 'evergreen', 'classic', 'compact', 'bold', 'minimal'];
const session = () => localStorage.getItem('token');

export default function DocumentLayoutPreference({ companyId, role, api }) {
  const [result, setResult] = useState(null);
  const activeCompany = useRef(companyId);
  activeCompany.current = companyId;
  const sequence = useRef(0);
  const saving = useRef(false);
  const current = result?.companyId === companyId && result.token === session() ? result : null;
  const ready = current?.status === 'ready';
  const sessionChanged = current?.status === 'session-changed' || (result?.companyId === companyId && result.token !== session());
  const loading = !result || result.companyId !== companyId || current?.status === 'loading';

  async function load() {
    const id = companyId, token = session(), request = ++sequence.current;
    const isCurrent = () => activeCompany.current === id && sequence.current === request && session() === token;
    saving.current = false;
    setResult({ companyId: id, token, status: 'loading' });
    try {
      const data = await api(`/companies/${id}/preferences`);
      if (!layouts.includes(data?.document_template)) throw Error('The document layout response is invalid. Retry loading the setting.');
      if (isCurrent()) setResult({ companyId: id, token, status: 'ready', value: data.document_template });
    } catch (error) {
      if (isCurrent()) setResult({ companyId: id, token, status: 'error', error: error.message });
      else if (activeCompany.current === id && sequence.current === request) setResult({ companyId: activeCompany.current, token: session(), status: 'session-changed' });
    }
  }
  useEffect(() => { load(); return () => { sequence.current++; }; }, [companyId]);
  useEffect(() => {
    const changed = event => {
      if (event.key === 'token' || event.key === null) {
        sequence.current++; saving.current = false; setResult({ companyId: activeCompany.current, token: session(), status: 'session-changed' });
      }
    };
    window.addEventListener('storage', changed);
    return () => window.removeEventListener('storage', changed);
  }, []);

  async function save(value) {
    // Check at dispatch as well as render: another tab can replace the token
    // without this tab having processed its storage event yet.
    if (saving.current || !ready || result.token !== session() || result.companyId !== activeCompany.current || role !== 'owner' || !layouts.includes(value)) return;
    saving.current = true;
    const previous = result, request = ++sequence.current;
    const isCurrent = () => activeCompany.current === previous.companyId && sequence.current === request && session() === previous.token;
    setResult({ ...previous, status: 'saving', error: '' });
    try {
      await api(`/companies/${previous.companyId}/preferences`, { method: 'PUT', body: JSON.stringify({ document_template: value }) });
      if (isCurrent()) setResult({ ...previous, value, error: '' });
    } catch (error) {
      if (isCurrent()) setResult({ companyId: previous.companyId, token: previous.token, status: 'error', error: `The save could not be confirmed. Reload the setting before editing again. ${error.message}` });
      else if (activeCompany.current === previous.companyId && sequence.current === request) setResult({ companyId: activeCompany.current, token: session(), status: 'session-changed' });
    } finally {
      if (sequence.current === request) saving.current = false;
    }
  }
  return <div className="document-layout-preference">
    <label>Document PDF layout
      <select className="form-select" value={current?.value || ''} disabled={!ready || role !== 'owner'} onChange={event => save(event.target.value)}>
        {!current?.value && <option value="">{loading ? 'Loading document layout…' : 'Document layout unavailable'}</option>}
        {layouts.map(value => <option key={value} value={value}>{value === 'mrp_discount' ? 'MRP + Discount' : value[0].toUpperCase() + value.slice(1)}</option>)}
      </select>
    </label>
    {current?.error && <p role="alert">{current.error}</p>}
    {sessionChanged && <p role="status">The signed-in session changed. Reload this setting before editing it.</p>}
    {(sessionChanged || current?.status === 'error') && <button className="button secondary" onClick={load}>Retry document layout</button>}
  </div>;
}
