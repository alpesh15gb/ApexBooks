import React, {useEffect, useState} from 'react';

export default function AuditLog({companyId, role}) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() {
    if (!companyId || role !== 'owner') return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/audit-events?limit=50`, {headers: {Authorization: `Bearer ${localStorage.token}`}});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || 'Could not load activity');
      setEvents(data);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  useEffect(() => { setEvents([]); refresh(); }, [companyId, role]);
  if (role !== 'owner') return null;
  return <div className="settings-section audit-log">
    <div className="settings-section-heading"><div><h3>Activity log</h3><p>Recent changes in this company, including who made them.</p></div><button type="button" className="button secondary" onClick={refresh} disabled={busy}>{busy ? 'Loading…' : 'Refresh'}</button></div>
    {error && <div className="error">{error}</div>}
    <div className="table-wrap"><table><thead><tr><th>WHEN</th><th>ACTION</th><th>BY</th><th>DETAIL</th></tr></thead><tbody>{events.map(event => <tr key={event.id}><td>{new Date(event.occurred_at).toLocaleString('en-IN')}</td><td>{event.action.replaceAll('.', ' · ').replaceAll('_', ' ')}</td><td>{event.actor}</td><td>{event.details?.number || event.details?.reference || event.details?.code || event.details?.kind || event.entity_type}</td></tr>)}</tbody></table>{!events.length && !busy && <p className="muted">No activity yet.</p>}</div>
  </div>;
}
