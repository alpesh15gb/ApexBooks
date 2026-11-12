import {sessionFetch as fetch} from './sessionScope.js';
import React, {useEffect, useRef, useState} from 'react';

import {createRequestScope} from './requestScope.js';
const friendly = value => String(value || '').replaceAll('_', ' ').replaceAll('.', ' · ').replace(/^./, char => char.toUpperCase());
const entityLabels = {bank_match_allocation:'Bank statement allocation',bank_statement_line:'Bank statement entry',bank_reconciliation_review:'Bank reconciliation review'};

export default function AuditLog({companyId, role}) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const scope = useRef(createRequestScope(`${companyId}:${role}`));
  scope.current.setContext(`${companyId}:${role}`);
  useEffect(() => () => scope.current.setContext(Symbol('unmounted')), []);

  async function refresh() {
    if (!companyId || role !== 'owner') return;
    const current = scope.current.latest();
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/audit-events?limit=50`, {headers: {Authorization: `Bearer ${localStorage.token}`}});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || 'Could not load activity');
      if (current()) setEvents(data);
    } catch (err) { if (current()) setError(err.message); }
    finally { if (current()) setBusy(false); }
  }

  useEffect(() => { setEvents([]); setError(''); setBusy(false); refresh(); }, [companyId, role]);
  if (role !== 'owner') return null;
  return <div className="settings-section audit-log">
    <div className="settings-section-heading"><div><h3>Activity log</h3><p>Recent changes in this company, including who made them.</p></div><button type="button" className="button secondary" onClick={refresh} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="table-wrap" tabIndex={0}><table><thead><tr><th>WHEN</th><th>ACTION</th><th>BY</th><th>DETAIL</th></tr></thead><tbody>{events.map(event => <tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString('en-IN')}</td><td>{friendly(event.action)}</td><td>{event.actor}</td><td>{event.details?.number || event.details?.reference || event.details?.code || (entityLabels[event.details?.kind || event.entity_type] || friendly(event.details?.kind || event.entity_type))}<details><summary>Technical identifiers</summary><div>Action: <code>{event.action}</code></div><div>Type: <code>{event.entity_type}</code></div>{event.entity_id && <div>ID: <code>{event.entity_id}</code></div>}</details></td></tr>)}</tbody></table>{!events.length && !busy && <p className="muted">No activity yet.</p>}</div>
  </div>;
}
