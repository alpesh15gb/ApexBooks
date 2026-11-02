import React, {useEffect, useState} from 'react';

export default function PeriodLock({companyId, role}) {
  const [lockedThrough, setLockedThrough] = useState('');
  const [nextDate, setNextDate] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let active = true;
    setLockedThrough(''); setNextDate(''); setError('');
    fetch(`/api/companies/${companyId}/period-lock`, {headers: {Authorization: `Bearer ${localStorage.token}`}})
      .then(async response => {const data = await response.json(); if (!response.ok) throw Error(data.detail || 'Could not load period lock'); return data;})
      .then(data => {if (active) {setLockedThrough(data.locked_through || ''); setNextDate(data.locked_through || '');}})
      .catch(err => {if (active) setError(err.message);});
    return () => {active = false;};
  }, [companyId]);

  async function save(event) {
    event.preventDefault();
    if (!nextDate || (lockedThrough && nextDate <= lockedThrough)) return;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/period-lock`, {method: 'PUT', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}`}, body: JSON.stringify({locked_through: nextDate})});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || 'Could not lock period');
      setLockedThrough(data.locked_through);
    } catch (err) {setError(err.message);}
    finally {setBusy(false);}
  }

  return <div className="settings-section period-lock"><h3>Accounting period lock</h3><p>Posted entries dated on or before the lock date cannot be added. The date can only move forward.</p><p><strong>Locked through:</strong> {lockedThrough || 'No date set'}</p>{role === 'owner' && <form onSubmit={save} className="period-lock-form"><label>New lock date<input type="date" min={lockedThrough || undefined} required value={nextDate} onChange={event => setNextDate(event.target.value)}/></label><button className="button secondary" disabled={busy || !nextDate || !!lockedThrough && nextDate <= lockedThrough}>{busy ? 'Saving…' : 'Lock through date'}</button></form>}{error && <div className="error">{error}</div>}</div>;
}
