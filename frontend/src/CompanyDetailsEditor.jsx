import { supportsFeature, companyUpdatePayload } from "./capabilities.js";
import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { registerPostingRequest } from './postingRegistry.js';

export default function CompanyDetailsEditor({ company, onSaved, features = [] }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const operation = useRef({ busy: false });
  const generation = useRef(0);
  const keepEditing = useRef(null);
  useEffect(() => registerPostingRequest(operation.current), []);
  useEffect(() => {
    generation.current++;
    setOpen(false); setError(''); setDirty(false); setDiscard(false);
    setBusy(false); operation.current.busy = false;
    return () => { generation.current++; };
  }, [company?.id]);
  useEffect(() => { if (discard) keepEditing.current?.focus(); }, [discard]);
  useEffect(() => {
    const warn = event => { if (dirty || operation.current.busy) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  if (!company || company.role !== 'owner') return null;
  const update = event => { setDirty(true); setForm({ ...form, [event.target.name]: event.target.value }); };
  function show() {
    setForm({ name: company.name, book_label: company.book_label || '', gstin: company.gstin || '', state_code: company.state_code || '', address: company.address || '' });
    setError(''); setDirty(false); setDiscard(false); setOpen(true);
  }
  function close() {
    if (operation.current.busy) return;
    if (discard) { setDiscard(false); return; }
    if (dirty) setDiscard(true);
    else setOpen(false);
  }
  async function submit(event) {
    event.preventDefault();
    if (operation.current.busy) return;
    if (!form.name.trim()) { setError('Enter a company name.'); return; }
    operation.current.busy = true;
    const requestGeneration = generation.current;
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${company.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}` }, body: JSON.stringify(companyUpdatePayload({ ...form, name: form.name.trim() }, features)) });
      const result = await response.json();
      if (requestGeneration !== generation.current) return;
      if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Company update failed');
      onSaved(result); setDirty(false); setOpen(false);
    } catch (err) { if (requestGeneration === generation.current) setError(err.message); }
    finally { if (requestGeneration === generation.current) { operation.current.busy = false; setBusy(false); } }
  }
  return <>
    <button className="button secondary" onClick={show}>Edit company details</button>
    {open && <div className="overlay" onMouseDown={event => event.target === event.currentTarget && close()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Edit company details">
        <div className="modal-heading"><div><h2>Edit company details</h2><p>Changes apply to future documents. Existing document snapshots are preserved.</p></div><button className="icon-button" aria-label="Close" disabled={busy} onClick={close}><X size={18} /></button></div>
        <form className="form-grid" onSubmit={submit} aria-busy={busy}>
          {discard && <div className="info-box full" role="alert"><strong>Discard unsaved changes?</strong><p>Your company details have not been saved.</p><div className="modal-actions"><button ref={keepEditing} type="button" className="button secondary" onClick={() => setDiscard(false)}>Keep editing</button><button type="button" className="button danger-outline" onClick={() => { setDirty(false); setOpen(false); }}>Discard changes</button></div></div>}
          <fieldset className="form-grid full submission-fields" disabled={busy}>
            <label className="full">Company name<input required maxLength="120" name="name" value={form.name} onChange={update} /></label>
            {supportsFeature(features, 'company_book_labels') && <label className="full">Book label (optional)<input name="book_label" maxLength="80" value={form.book_label || ''} onChange={update} /><small>A synced label for distinguishing separate books. It never replaces the legal company name on invoices.</small></label>}
            {['regular', 'composition'].includes(company.tax_mode) && <label>GSTIN<input required maxLength="15" name="gstin" value={form.gstin} onChange={update} /></label>}
            <label>State code<input name="state_code" required={['regular', 'composition'].includes(company.tax_mode)} pattern="[0-9]{2}" maxLength="2" value={form.state_code} onChange={update} /></label>
            <label className="full">Address<input name="address" maxLength="500" value={form.address} onChange={update} /></label>
          </fieldset>
          {error && <div className="error full" role="alert">{error}</div>}
          <div className="modal-actions full"><button className="button secondary" type="button" disabled={busy} onClick={close}>Cancel</button><button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save details'}</button></div>
        </form>
      </div>
    </div>}
  </>;
}
