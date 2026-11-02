import React, {useState} from 'react';
import {Download} from 'lucide-react';

export default function CompanyDataExport({companyId, role}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (role !== 'owner') return null;
  async function download() {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/data-export.json`, {headers: {Authorization: `Bearer ${localStorage.token}`}});
      if (!response.ok) throw Error('Company data export failed');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = `apex-company-${companyId.slice(0, 8)}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {setError(err.message);} finally {setBusy(false);}
  }
  return <section className="member-settings"><h2>Company data export</h2><p>Download this company's records, journal entries, bank statement lines and settings as JSON. Keep the file private. Use Backup and restore below to restore an export as a separate company.</p><button className="button secondary" onClick={download} disabled={busy}><Download size={16}/>{busy ? 'Preparing…' : 'Download company data'}</button>{error && <div className="error banner">{error}</div>}</section>;
}
