import React, {useEffect, useRef, useState} from 'react';
import {downloadBlob} from './downloadBlob.js';
import {registerPostingRequest} from './postingRegistry.js';
import {createRequestScope} from './requestScope.js';

function parseCsv(source) {
  const rows = []; let row = [], field = '', quoted = false;
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (char === '"') {
      if (quoted && source[i + 1] === '"') {field += '"'; i++;} else quoted = !quoted;
    } else if (char === ',' && !quoted) {row.push(field); field = '';}
    else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && source[i + 1] === '\n') i++;
      row.push(field); if (row.some(value => value.trim())) rows.push(row);
      row = []; field = '';
    } else field += char;
  }
  if (quoted) throw Error('CSV has an unclosed quote');
  row.push(field); if (row.some(value => value.trim())) rows.push(row);
  const headers = (rows.shift() || []).map((value, i) => (i === 0 ? value.replace(/^\uFEFF/, '') : value).trim().toLowerCase()).map(value=>({'type':'party_type','hsn / sac':'hsn','sale rate':'sale_rate','purchase rate':'purchase_rate','gst rate':'gst_rate','stock tracked':'track_stock','item type':'item_type','tax treatment':'tax_treatment'}[value]||value));
  if (!headers.includes('name')) throw Error('CSV needs a name column');
  const duplicate = headers.find((header, index) => header && headers.indexOf(header) !== index);
  if (duplicate) throw Error(`CSV repeats the ${duplicate} column. Keep one column for each field.`);
  return rows.map((values, i) => {
    if (values.length > headers.length && values.slice(headers.length).some(value => value.trim())) throw Error(`CSV row ${i + 2} has data without a column heading`);
    const result = {name: values[headers.indexOf('name')]?.trim() || ''};
    for (const key of ['gstin', 'address', 'phone', 'email', 'party_type', 'hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment']) {
      if (headers.includes(key)) result[key] = values[headers.indexOf(key)]?.trim() || (key === 'party_type' ? 'both' : key==='item_type'?'goods':key==='tax_treatment'?'taxable': key === 'track_stock' ? 'false' : key.endsWith('rate') ? '0' : '');
    }
    if (!result.name) throw Error(`Name is missing on CSV row ${i + 2}`);
    return result;
  });
}

export default function MasterImport({companyId, onImported, role}) {
  const [kind, setKind] = useState('party');
  const [rows, setRows] = useState([]);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const operation = useRef({busy:false});
  const scope = useRef(createRequestScope(`${companyId}:${kind}`));
  scope.current.setContext(`${companyId}:${kind}`);
  useEffect(() => registerPostingRequest(operation.current), []);
  useEffect(() => () => scope.current.setContext(Symbol('unmounted')), []);
  useEffect(() => {setRows([]); setPreview(null); setError('');}, [companyId]);
  const writable = role === 'owner' || role === 'editor';
  async function request(dryRun, values = rows) {
    const response = await fetch(`/api/companies/${companyId}/masters/import`, {
      method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}`},
      body: JSON.stringify({kind, dry_run: dryRun, rows: values})
    });
    const result = await response.json();
    if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : result.detail?.message || `Import failed (${response.status})`);
    return result;
  }
  async function chooseFile(event) {
    const file = event.target.files?.[0]; if (!file) return;
    if (operation.current.busy) return;
    operation.current.busy = true; setBusy(true);
    const current = scope.current.capture();
    setError(''); setPreview(null);
    try {
      if (file.size > 5_000_000) throw Error('CSV exceeds 5 MB. Import up to 500 rows per file.');
      const values = parseCsv(await file.text());
      if (!values.length || values.length > 500) throw Error('CSV must contain 1 to 500 data rows');
      if (!current()) return;
      const result = await request(true, values);
      if (current()) { setRows(values); setPreview(result); }
    } catch (err) {if(current()){setRows([]); setError(err.message);}} finally {operation.current.busy=false;setBusy(false); event.target.value = '';}
  }
  async function commit() {
    if (operation.current.busy || !preview?.dry_run || !rows.length || !writable) return;
    operation.current.busy = true;
    const current = scope.current.capture();
    setBusy(true); setError('');
    try {
      const result = await request(false);
      if (current()) {setPreview({...result, dry_run: false}); setRows([]); await onImported();}
    } catch (err) {if(current())setError(err.message);} finally {operation.current.busy=false;setBusy(false);}
  }
  function downloadTemplate() {
    const header = kind === 'party' ? 'name,party_type,gstin,address,phone,email\r\n' : 'name,hsn,unit,sale_rate,purchase_rate,gst_rate,track_stock,barcode,item_type,tax_treatment\r\n';
    downloadBlob(new Blob(['\ufeff' + header], {type: 'text/csv;charset=utf-8'}), `apex-${kind}-template.csv`);
  }
  async function exportList(format) {
    if (operation.current.busy) return;
    operation.current.busy = true;
    const current = scope.current.capture();
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/masters/export.${format}?kind=${kind}`, {headers: {Authorization: `Bearer ${localStorage.token}`}});
      if (!response.ok) throw Error('Could not export the list');
      const blob = await response.blob();
      if(current())downloadBlob(blob, `apex-${kind}-list.${format}`);
    } catch (err) {if(current())setError(err.message);} finally {operation.current.busy=false;setBusy(false);}
  }
  return <section className="member-settings"><h2>Import parties or items</h2><p>Preview a CSV before adding records. Duplicate names in this company are skipped.</p>
    <div className="master-import-controls"><label>Record type<select className="form-select" disabled={busy} value={kind} onChange={event => {if(operation.current.busy)return;setKind(event.target.value); setRows([]); setPreview(null);}}><option value="party">Parties</option><option value="item">Items</option></select></label>{writable && <label>CSV file<input type="file" accept=".csv,text/csv" onChange={chooseFile} disabled={busy}/></label>}</div>
    <p className="import-hint">Party columns: name, party_type, gstin, address, phone, email. Item columns: name, hsn, unit, sale_rate, purchase_rate, gst_rate, track_stock (true/false).</p>
    <div className="master-export-actions"><button type="button" className="button secondary" disabled={busy} onClick={downloadTemplate}>CSV template</button><button type="button" className="button secondary" disabled={busy} onClick={() => exportList('xlsx')}>Export XLSX</button><button type="button" className="button secondary" disabled={busy} onClick={() => exportList('pdf')}>Export PDF</button></div>
    {busy && <p role="status">Processing {kind === 'party' ? 'parties' : 'items'}…</p>}
    {error && <div className="error banner" role="alert">{error}</div>}
    {preview && <><p>{preview.dry_run ? 'Preview' : 'Imported'}: {preview.ready} ready · {preview.duplicates} duplicates · {preview.errors.length} errors</p>{preview.errors.map(issue => <p className="error" key={issue.row}>Row {issue.row}: {issue.message}</p>)}{preview.dry_run && <button className="button primary" disabled={busy || preview.ready === 0 || preview.errors.length > 0} onClick={commit}>Import {preview.ready} records</button>}</>}
  </section>;
}
