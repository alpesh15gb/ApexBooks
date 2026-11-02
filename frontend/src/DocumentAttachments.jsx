import React, { useEffect, useRef, useState } from 'react';
import { usePostingRequest } from './usePostingRequest.js';
import { validateReceiptFile, validateReceiptSignature, verifiedReceiptDownload, safeReceiptFilename } from './attachmentFiles.js';
import './documentAttachments.css';
const bytesLabel = value => `${(Number(value || 0) / 1024 / 1024).toFixed(2)} MiB`;
export default function DocumentAttachments({ companyId, recordId, role, api, onLockChange = () => {} }) {
  const [data,setData] = useState(null), [error,setError] = useState(''), [loading,setLoading] = useState(true), [file,setFile] = useState(null), [revision,setRevision] = useState(0), [downloading,setDownloading] = useState('');
  const posting = usePostingRequest(), scope = useRef(0), input = useRef(null), download = useRef(null);
  const writable = ['owner','editor'].includes(role), locked = posting.busy || posting.pending;
  const base = `/companies/${companyId}/records/${recordId}/attachments`;
  useEffect(() => { onLockChange(locked); }, [locked,onLockChange]);
  useEffect(() => {
    const current = ++scope.current; let active = true;
    setLoading(true); setData(null); setError(''); setFile(null);
    api(base).then(value => { if (active && scope.current === current) setData(value); }).catch(e => { if (active && scope.current === current) setError(e.message); }).finally(() => { if (active && scope.current === current) setLoading(false); });
    return () => { active = false; scope.current++; download.current?.abort(); };
  }, [api,base,revision]);
  async function perform(operation) {
    const current = scope.current; setError('');
    try {
      const result = await posting.run(operation);
      if (result && scope.current === current) { setFile(null); if (input.current) input.current.value = ''; setRevision(value => value + 1); }
    } catch (e) { if (scope.current === current) setError(e.message || 'Receipt operation failed.'); }
  }
  function upload() {
    if (locked) { if (!posting.busy) perform(); return; }
    let metadata;
    try { metadata = validateReceiptFile(file); } catch (e) { setError(e.message); return; }
    const selected = file, key = crypto.randomUUID(), path = `${base}?filename=${encodeURIComponent(metadata.filename)}`;
    let content;
    perform(async () => {
      if (!content) {
        try { content = new Uint8Array(await selected.arrayBuffer()); validateReceiptSignature(content,metadata.mediaType); }
        catch (e) { e.status = 422; throw e; }
      }
      return api(path,{method:'POST',headers:{'Content-Type':metadata.mediaType,'Idempotency-Key':key},body:content});
    });
  }
  function archive(row) {
    const body = JSON.stringify({version:row.version,is_archived:!row.is_archived}), key = crypto.randomUUID();
    perform(() => api(`/companies/${companyId}/attachments/${row.id}`,{method:'PUT',headers:{'Content-Type':'application/json','Idempotency-Key':key},body}));
  }
  async function saveFile(row) {
    const current = scope.current; const controller = new AbortController(); download.current?.abort(); download.current = controller;
    setDownloading(row.id); setError('');
    try {
      const response = await api(`/companies/${companyId}/attachments/${row.id}/download`,{rawResponse:true,signal:controller.signal});
      const blob = await verifiedReceiptDownload(response,row);
      if (scope.current !== current || controller.signal.aborted) return;
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url; link.download = safeReceiptFilename(row.filename); link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch (e) { if (scope.current === current && !controller.signal.aborted) setError(e.message); }
    finally { if (scope.current === current) setDownloading(''); }
  }
  const storage = data?.storage;
  const full = storage && (Number(storage.remaining_bytes) < (file?.size || 1) || data.attachments.length >= storage.max_files_per_record || storage.file_count >= storage.max_files_per_company);
  return <section className="detail-section document-attachments" aria-label="Document receipts">
    <div className="detail-section-heading"><h3>Receipts & evidence</h3><span>{data?.attachments?.length || 0} retained files</span></div>
    <p className="detail-caption">PDF, PNG or JPEG · up to 2 MiB each. Files download only; Apex Books does not preview or certify their safety.</p>
    {storage && <p className="attachment-storage">Company storage: {bytesLabel(storage.used_bytes)} / {bytesLabel(storage.quota_bytes)} · {storage.file_count}/{storage.max_files_per_company} files. This document allows {storage.max_files_per_record} retained files.</p>}
    <p className="detail-caption">Archiving hides a receipt from active use; it does not delete evidence or release storage. Complete backups retain archived files.</p>
    {loading && <p role="status">Loading receipts…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {locked && <p className="info-box" role="status">{posting.busy ? 'Saving receipt change… Keep this document open.' : 'Receipt response was not confirmed. Keep this document open and retry the original request; its bytes and retry key are preserved.'}</p>}
    {posting.pending && !posting.busy && <button className="button primary" onClick={() => perform()}>Retry original receipt request</button>}
    {!locked && <button className="button secondary" disabled={loading} onClick={() => setRevision(value => value + 1)}>Refresh receipts</button>}
    <ul className="attachment-list">{(data?.attachments || []).map(row => <li key={row.id}><div><strong>{row.filename}</strong><small>{bytesLabel(row.size_bytes)} · {row.is_archived ? 'Archived · retained' : 'Active'}</small></div><div className="attachment-actions"><button className="button secondary" disabled={!!downloading || locked} onClick={() => saveFile(row)}>{downloading === row.id ? 'Verifying…' : 'Download'}</button>{writable && <button className="button secondary" disabled={locked || loading} onClick={() => archive(row)}>{row.is_archived ? 'Reactivate' : 'Archive'}</button>}</div></li>)}</ul>
    {data && !data.attachments.length && <p className="detail-caption">No receipt attached yet. Your accounting entry is unchanged.</p>}
    {writable ? <div className="attachment-upload"><label>Receipt file<input ref={input} type="file" accept="application/pdf,image/png,image/jpeg" disabled={locked || loading || !data} onChange={event => { const value = event.target.files?.[0]; try { validateReceiptFile(value); setFile(value); setError(''); } catch (e) { setFile(null); event.target.value = ''; setError(e.message); } }} /></label><button className="button primary" disabled={!file || locked || loading || !data || full} onClick={upload}>Attach receipt</button>{full && <p className="info-box">Retained receipt storage or count limit reached. Archiving will not free this space.</p>}</div> : <p className="detail-caption">Read-only access: you can download receipts, but cannot upload, archive or reactivate them.</p>}
  </section>;
}
