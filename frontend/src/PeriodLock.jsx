import {sessionFetch as fetch} from './sessionScope.js';
import React, { useEffect, useRef, useState } from 'react';
import { registerPostingRequest, memoryPostingRecoveryMessage } from './postingRegistry.js';
import { ledgerDate } from './ledgerFormat.js';

export default function PeriodLock({ companyId, role }) {
  const [lockedThrough, setLockedThrough] = useState('');
  const [nextDate, setNextDate] = useState('');
  const [reviewDate, setReviewDate] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);
  const operation = useRef({ busy: false, pending: false });
  const generation = useRef(0);
  const confirmButton = useRef(null);
  const dateInput = useRef(null);
  const wasReviewing = useRef(false);
  useEffect(() => registerPostingRequest(operation.current), []);
  useEffect(() => {
    if (reviewDate) confirmButton.current?.focus();
    else if (wasReviewing.current) dateInput.current?.focus();
    wasReviewing.current = !!reviewDate;
  }, [reviewDate]);
  useEffect(() => {
    const current = ++generation.current;
    setLockedThrough(''); setNextDate(''); setReviewDate(''); setError(''); setLoaded(false); setBusy(false); setSaved(false);
    operation.current.busy = false; operation.current.pending = false; setPending(false);
    if (!companyId) return;
    fetch(`/api/companies/${companyId}/period-lock`, { headers: { Authorization: `Bearer ${localStorage.token}` } })
      .then(async response => { const data = await response.json(); if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Could not load period lock'); return data; })
      .then(data => { if (current === generation.current) { setLockedThrough(data.locked_through || ''); setNextDate(data.locked_through || ''); setLoaded(true); } })
      .catch(err => { if (current === generation.current) setError(err.message); });
    return () => { generation.current++; };
  }, [companyId, loadAttempt]);

  function review(event) {
    event.preventDefault();
    if (role !== 'owner' || pending || !loaded || operation.current.busy || !nextDate || (lockedThrough && nextDate <= lockedThrough)) return;
    setSaved(false); setError(''); setReviewDate(nextDate);
  }
  async function save() {
    if (!loaded || operation.current.busy || !reviewDate || role !== 'owner') return;
    const current = generation.current;
    operation.current.busy = true;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/period-lock`, { method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}` }, body: JSON.stringify({ locked_through: reviewDate }) });
      const data = await response.json();
      if (current !== generation.current) return;
      if (!response.ok) throw Object.assign(Error(typeof data.detail === 'string' ? data.detail : 'Could not lock period'), {status: response.status});
      operation.current.pending = false; setPending(false);
      setLockedThrough(data.locked_through); setNextDate(data.locked_through); setReviewDate(''); setSaved(true);
      dateInput.current?.focus();
    } catch (err) { if (current === generation.current) {
      if (operation.current.pending || !err.status || err.status === 408 || err.status === 409 || err.status >= 500) { operation.current.pending = true; setPending(true); }
      setError(err.message);
    } }
    finally { if (current === generation.current) { operation.current.busy = false; setBusy(false); } }
  }

  async function checkCurrentLock() {
    if (!operation.current.pending || operation.current.busy) return;
    const current = generation.current;
    operation.current.busy = true; setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/period-lock`, {headers: {Authorization: `Bearer ${localStorage.token}`}});
      const data = await response.json();
      if (current !== generation.current) return;
      if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Could not verify current period lock');
      if (!data.locked_through || data.locked_through < reviewDate) { setError('The requested lock is not visible yet. This does not prove the save failed; check again or retry the original date.'); return; }
      operation.current.pending = false; setPending(false); setLoaded(true);
      setLockedThrough(data.locked_through); setNextDate(data.locked_through); setReviewDate(''); setSaved(true);
    } catch (err) { if (current === generation.current) setError(err.message); }
    finally { if (current === generation.current) { operation.current.busy = false; setBusy(false); } }
  }

  return <div className="settings-section period-lock">
    <h3>Accounting period lock</h3>
    <p>Posted entries dated on or before the lock date cannot be added. The date can only move forward.</p>
    <p><strong>Locked through:</strong> {pending ? 'Not verified after save' : loaded ? lockedThrough ? ledgerDate(lockedThrough) : 'No date set' : error ? 'Not available' : 'Loading…'}</p>
    {pending && <div className="info-box" role="alert"><strong>Period-lock result not confirmed.</strong><p>The original date {ledgerDate(reviewDate)} is frozen until the current lock is verified. {memoryPostingRecoveryMessage}</p><button type="button" disabled={busy} onClick={checkCurrentLock}>Check current lock</button></div>}
    {role === 'owner' && <form onSubmit={review} className="period-lock-form" aria-busy={busy}>
      <label>New lock date<input ref={dateInput} type="date" min={lockedThrough || undefined} required disabled={!loaded || busy || !!reviewDate} value={nextDate} onChange={event => { setNextDate(event.target.value); setSaved(false); }} /></label>
      <button className="button secondary" disabled={!loaded || busy || !!reviewDate || !nextDate || !!lockedThrough && nextDate <= lockedThrough}>Lock through date</button>
    </form>}
    {reviewDate && role === 'owner' && <div className="info-box" role="alert">
      <strong>Lock all entries through {ledgerDate(reviewDate)}?</strong>
      <p>This includes {ledgerDate(reviewDate)}. You cannot move this lock backwards. Complete and review all entries for this period before confirming.</p>
      <div className="modal-actions"><button type="button" className="button secondary" disabled={busy || pending} onClick={() => { setReviewDate(''); dateInput.current?.focus(); }}>Cancel</button><button ref={confirmButton} type="button" className="button primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : pending ? 'Retry original lock' : 'Confirm period lock'}</button></div>
    </div>}
    {saved && <p role="status">Period locked through {ledgerDate(lockedThrough)}.</p>}
    {error && <div className="error" role="alert">{error}{!loaded && <button type="button" className="button secondary" onClick={() => setLoadAttempt(value => value + 1)}>Retry loading</button>}</div>}
  </div>;
}
