import {decodeMasterCsv, parseMasterCsv} from './masterCsv.js';
import {masterImportStore, masterImportHash, masterImportActor} from './masterImportRecovery.js';
import {sessionFetch as fetch} from './sessionScope.js';
import React, {useEffect, useRef, useState} from 'react';
import {downloadBlob} from './downloadBlob.js';
import {registerPostingRequest} from './postingRegistry.js';
import {createRequestScope} from './requestScope.js';

export default function MasterImport({companyId, onImported, role, receiptSupport = false}) {
  const [kind, setKind] = useState('party');
  const [rows, setRows] = useState([]);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(null);
  const frozen = useRef(null);
  const [recoveryFault, setRecoveryFault] = useState('');
  const store = () => masterImportStore(companyId, localStorage.token);
  const [busy, setBusy] = useState(false);
  const [refreshError, setRefreshError] = useState('');
  const [refreshBusy, setRefreshBusy] = useState(false);
  const refreshing = useRef(false);
  const operation = useRef({busy:false});
  const scope = useRef(createRequestScope(`${companyId}:${kind}`));
  scope.current.setContext(`${companyId}:${kind}`);
  useEffect(() => registerPostingRequest(operation.current), []);
  useEffect(() => () => scope.current.setContext(Symbol('unmounted')), []);
  useEffect(() => {
    setRows([]); setPreview(null); setError(''); setRefreshError(''); frozen.current = null;
    try { if (!receiptSupport && !masterImportActor(localStorage.token)) { setPending(null); setRecoveryFault(''); return; } const saved = store().read(); setPending(saved); if (saved) setKind(saved.kind); setRecoveryFault(''); }
    catch (failure) { setPending(null); setRecoveryFault(failure.message); }
  }, [companyId, receiptSupport]);
  operation.current.pending = !!pending;
  const writable = role === 'owner' || role === 'editor';
  async function request(dryRun, values = rows, key, importKind = kind) {
    const response = await fetch(`/api/companies/${companyId}/masters/import`, {
      method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token}`, ...(key ? {'Idempotency-Key':key} : {})},
      body: JSON.stringify({kind:importKind, dry_run: dryRun, rows: values})
    });
    const result = await response.json();
    if (!response.ok) { const failure = Error(typeof result.detail === 'string' ? result.detail : result.detail?.message || `Import failed (${response.status})`); failure.status = response.status; throw failure; }
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
      const importKind = pending?.kind || kind;
      const values = parseMasterCsv(decodeMasterCsv(await file.arrayBuffer()), importKind);
      if (!values.length || values.length > 500) throw Error('CSV must contain 1 to 500 data rows');
      if (!current()) return;
      if (pending) {
        if (!receiptSupport) throw Error('Reconnect to a server supporting import receipts before recovering this operation.');
        const body = {kind:pending.kind, dry_run:false, rows:values};
        if (await masterImportHash(body) !== pending.hash) throw Error('This file does not match the original import. Select the original CSV without changes.');
        if (!current()) return;
        frozen.current = body; setRows(values); setError('Original file verified. Check the receipt or retry the original import.'); return;
      }
      if (recoveryFault) throw Error(recoveryFault);
      const result = await request(true, values);
      if (current()) { setRows(values); setPreview(result); }
    } catch (err) {if(current()){setRows([]); setError(err.message);}} finally {operation.current.busy=false;setBusy(false); event.target.value = '';}
  }
  async function refreshImported() {
    if (refreshing.current) return;
    const current = scope.current.capture();
    refreshing.current = true; setRefreshBusy(true); setRefreshError('');
    try { await onImported(); }
    catch (failure) { if (current()) setRefreshError(failure.message); }
    finally { refreshing.current = false; setRefreshBusy(false); }
  }
  async function commit() {
    if (operation.current.busy || !writable || recoveryFault) return;
    if (pending && (!receiptSupport || !frozen.current)) return;
    if (!pending && (!preview?.dry_run || !rows.length)) return;
    operation.current.busy = true;
    const current = scope.current.capture();
    const retrying = !!pending;
    let marker = pending, recoveryStore;
    setBusy(true); setError('');
    try {
      let body = frozen.current || {kind, dry_run:false, rows};
      if (receiptSupport) {
        recoveryStore = store();
        if (!marker) {
          marker = {key:crypto.randomUUID(), kind, hash:await masterImportHash(body)};
          if (!current()) return;
          recoveryStore.save(marker); frozen.current = body; setPending(marker);
        }
      }
      const result = await request(false, body.rows, marker?.key, body.kind);
      if (!current()) return;
      if (marker && result.operation_key !== marker.key) throw Error('The server did not return the original import receipt. Keep the recovery reference and verify the result.');
      if (marker) recoveryStore.clear(marker.key);
      setPending(null); frozen.current = null;
      setPreview({...result, dry_run:false}); setRows([]); await refreshImported();
    } catch (failure) {
      if (current()) {
        if (marker && !retrying && failure.status >= 400 && failure.status < 500 && ![408,409].includes(failure.status)) {
          try { recoveryStore?.clear(marker.key); setPending(null); frozen.current = null; } catch { /* Keep the marker on storage failure. */ }
        }
        setError(failure.message);
      }
    } finally {operation.current.busy=false;setBusy(false);}
  }
  async function checkReceipt() {
    if (operation.current.busy || !pending || !writable || !receiptSupport) return;
    const current = scope.current.capture(), marker = pending;
    operation.current.busy = true; setBusy(true); setError('');
    try {
      const response = await fetch(`/api/companies/${companyId}/masters/import-receipts/${encodeURIComponent(marker.key)}`, {headers:{Authorization:`Bearer ${localStorage.token}`}});
      const result = await response.json();
      if (!current()) return;
      if (!response.ok) throw Error('The original import is not confirmed. A missing receipt does not prove failure. Keep this reference; reselect the original file to retry the same operation.');
      if (result.operation_key !== marker.key) throw Error('Unexpected import receipt; the original operation remains unresolved.');
      store().clear(marker.key); setPending(null); frozen.current=null; setRows([]); setPreview({...result,dry_run:false}); await refreshImported();
    } catch (failure) {if(current())setError(failure.message);}
    finally {operation.current.busy=false;setBusy(false);}
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
    <div className="master-import-controls"><label>Record type<select className="form-select" disabled={busy || !!pending || !!recoveryFault} value={kind} onChange={event => {if(operation.current.busy || pending || recoveryFault)return;setKind(event.target.value); setRows([]); setPreview(null);}}><option value="party">Parties</option><option value="item">Items</option></select></label>{writable && <label>CSV file<input type="file" accept=".csv,text/csv" onChange={chooseFile} disabled={busy}/></label>}</div>
    <p className="import-hint">Party columns: name, party_type, gstin, address, phone, email. Item columns: name, hsn, unit, sale_rate, purchase_rate, gst_rate, track_stock (true/false).</p>
    <div className="master-export-actions"><button type="button" className="button secondary" disabled={busy} onClick={downloadTemplate}>CSV template</button><button type="button" className="button secondary" disabled={busy} onClick={() => exportList('xlsx')}>Export XLSX</button><button type="button" className="button secondary" disabled={busy} onClick={() => exportList('pdf')}>Export PDF</button></div>
    {!receiptSupport && <p>The connected server does not advertise exact import recovery. Duplicate names are skipped, but an interrupted import has no replay receipt.</p>}
    {recoveryFault && <p role="alert">{recoveryFault}</p>}
    {pending && <div className="info-box" role="status">The original import is unconfirmed. Recovery reference: <code>{pending.key}</code>. This tab retains only the reference and a file fingerprint, not CSV contents. Reloading this tab can recover the receipt; closing the tab may lose the reference. Keep it until confirmed. Do not start another import.
      <button type="button" disabled={busy || !writable || !receiptSupport} onClick={checkReceipt}>Check original import</button>
      <button type="button" disabled={busy || !writable || !receiptSupport || !frozen.current} onClick={commit}>Retry original import</button>
      {!frozen.current && <p>Select the original CSV above to verify its fingerprint before retrying.</p>}
    </div>}
    {busy && <p role="status">Processing {kind === 'party' ? 'parties' : 'items'}…</p>}
    {refreshError && <div className="info-box" role="alert">The import was confirmed, but the record list could not refresh: {refreshError}. Do not import the file again.<button type="button" disabled={refreshBusy || busy} onClick={refreshImported}>Refresh imported records</button></div>}
    {error && <div className="error banner" role="alert">{error}</div>}
    {preview && <><p>{preview.dry_run ? 'Preview' : 'Imported'}: {preview.ready} ready · {preview.duplicates} duplicates · {preview.errors.length} errors</p>{preview.errors.map(issue => <p className="error" key={issue.row}>Row {issue.row}: {issue.message}</p>)}{preview.dry_run && !pending && <button className="button primary" disabled={busy || !writable || !!recoveryFault || preview.ready === 0 || preview.errors.length > 0} onClick={commit}>Import {preview.ready} records</button>}</>}
  </section>;
}
