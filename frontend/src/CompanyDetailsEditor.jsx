import React, {useEffect, useState} from 'react';
import {X} from 'lucide-react';

export default function CompanyDetailsEditor({company, onSaved}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {setOpen(false); setError('');}, [company?.id]);
  if (!company || company.role !== 'owner') return null;
  const update = event => setForm({...form, [event.target.name]: event.target.value});
  function show() {setForm({name: company.name, gstin: company.gstin || '', state_code: company.state_code || '', address: company.address || ''}); setError(''); setOpen(true);}
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${company.id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}`}, body: JSON.stringify(form)});
      const result = await response.json();
      if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : 'Company update failed');
      onSaved(result); setOpen(false);
    } catch (err) {setError(err.message);} finally {setBusy(false);}
  }
  return <><button className="button secondary" onClick={show}>Edit company details</button>{open && <div className="overlay" onMouseDown={event => event.target === event.currentTarget && setOpen(false)}><div className="modal" role="dialog" aria-modal="true" aria-label="Edit company details"><div className="modal-heading"><div><h2>Edit company details</h2><p>Changes apply to future documents. Existing document snapshots are preserved.</p></div><button className="icon-button" aria-label="Close" onClick={() => setOpen(false)}><X size={18}/></button></div><form className="form-grid" onSubmit={submit}><label className="full">Company name<input required maxLength="120" name="name" value={form.name} onChange={update}/></label>{company.tax_mode === 'regular' && <label>GSTIN<input maxLength="15" name="gstin" value={form.gstin} onChange={update}/></label>}<label>State code<input name="state_code" required={company.tax_mode === 'regular'} pattern="[0-9]{2}" maxLength="2" value={form.state_code} onChange={update}/></label><label className="full">Address<input name="address" maxLength="500" value={form.address} onChange={update}/></label>{error && <div className="error full">{error}</div>}<div className="modal-actions full"><button className="button secondary" type="button" onClick={() => setOpen(false)}>Cancel</button><button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save details'}</button></div></form></div></div>}</>;
}
