import { imageInput } from './imageInput.js';
import React, { useEffect, useRef, useState } from 'react';
import { registerPostingRequest } from './postingRegistry.js';

const fields = { phone: 'Phone', email: 'Email', bank_name: 'Bank name', account_number: 'Bank account number', ifsc: 'IFSC', branch: 'Branch', upi_id: 'UPI ID', notes: 'Notes', terms: 'Terms and conditions' };
export default function DocumentBranding({ companyId, role }) {
  const [form, setForm] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const generation = useRef(0);
  const operation = useRef({ busy: false });
  useEffect(() => registerPostingRequest(operation.current), []);
  useEffect(() => {
    const current = ++generation.current;
    setForm(null); setBusy(false); setMessage(''); setError(''); operation.current.busy = false;
    fetch(`/api/companies/${companyId}/document-branding`, { headers: { Authorization: `Bearer ${localStorage.token}` } })
      .then(async response => { if (!response.ok) throw Error('Could not load branding'); return response.json(); })
      .then(data => { if (current === generation.current) setForm(data); })
      .catch(reason => { if (current === generation.current) setError(reason.message); });
    return () => { generation.current++; };
  }, [companyId]);

  async function write(method, body, current) {
    const response = await fetch(`/api/companies/${companyId}/document-branding`, { method, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}` }, body: JSON.stringify(body) });
    const result = await response.json();
    if (current !== generation.current) return null;
    if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Document branding could not be saved');
    return result;
  }
  async function perform(action) {
    if (operation.current.busy || role !== 'owner') return;
    const current = generation.current;
    operation.current.busy = true; setBusy(true); setError(''); setMessage('');
    try { await action(current); }
    catch (reason) { if (current === generation.current) setError(reason.message); }
    finally { if (current === generation.current) { operation.current.busy = false; setBusy(false); } }
  }
  async function saveLogo(value, current) {
    const result = await write('PATCH', { logo: value }, current);
    if (!result) return;
    setForm(previous => ({ ...previous, logo: result.logo }));
    setMessage(value ? 'Company logo saved. It will appear on newly downloaded documents, including older invoices.' : 'Company logo removed from document output.');
  }
  async function upload(event, key) {
    const input = event.target, file = input.files?.[0];
    if (!file) return;
    await perform(async current => {
      const value = await imageInput(file, 700, 240000);
      if (current !== generation.current) return;
      if (key === 'logo') await saveLogo(value, current);
      else { setForm(previous => ({ ...previous, [key]: value })); setMessage('Signature selected. Save document details to apply it to new documents.'); }
    });
    input.value = '';
  }
  async function remove(key) {
    if (operation.current.busy) return;
    if (key !== 'logo') { setForm(previous => ({ ...previous, [key]: '' })); setMessage('Signature removed from this draft. Save document details to apply the change.'); return; }
    await perform(current => saveLogo('', current));
  }
  async function submit(event) {
    event.preventDefault();
    if (!form) return;
    await perform(async current => {
      const result = await write('PUT', Object.fromEntries(Object.entries(form).filter(([key]) => key !== 'logo')), current);
      if (!result) return;
      setForm(result); setMessage('Saved. Your company logo appears on all documents; other details are saved with new document snapshots.');
    });
  }
  if (role !== 'owner') return null;
  return <section className="panel settings-panel">
    <h2>Company logo and document branding</h2>
    <p>Your logo saves immediately after upload and appears on all newly downloaded documents, including existing invoices. Configure the signature, bank details, UPI QR code, notes and terms saved with new documents.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!form && !error && <p role="status">Loading document details…</p>}
    {form && <form onSubmit={submit} className="form-grid" aria-busy={busy}>
      <fieldset className="form-grid full submission-fields" disabled={busy}>
        {['logo', 'signature'].map(key => <div key={key}>
          <label>{key === 'logo' ? 'Company logo · upload saves immediately' : 'Authorized signature image'}<input type="file" accept="image/png,image/jpeg" onChange={event => upload(event, key)} /></label>
          {form[key] && <><img src={form[key]} alt={key} style={{ maxWidth: 140, maxHeight: 90 }} /><button type="button" className="link" onClick={() => remove(key)}>Remove {key}</button></>}
        </div>)}
        {Object.entries(fields).map(([key, label]) => <label key={key}>{label}{['notes', 'terms'].includes(key)
          ? <textarea maxLength={key === 'terms' ? 3000 : 1500} value={form[key] || ''} onChange={event => setForm({ ...form, [key]: event.target.value })} />
          : <input maxLength={key === 'email' ? 254 : 120} value={form[key] || ''} onChange={event => setForm({ ...form, [key]: event.target.value })} />}</label>)}
      </fieldset>
      <button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save document details'}</button>
    </form>}
  </section>;
}
