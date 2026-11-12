import {captureCompanyAccess} from './companyAccess.js';
import {captureSession} from './sessionScope.js';
import React, { useEffect, useRef, useState } from 'react';
import { Download, Upload, ShieldCheck } from 'lucide-react';
import { usePostingRequest, pendingPostingMessage } from './usePostingRequest.js';
import { downloadBackupChunks, uploadBackupChunks, sha256Bytes, MAX_WEB_ARCHIVE_BYTES, validateBackupManifest, readBackupChunkResponse } from './backupChunks.js';
import { encryptPortableBackup, readPortableBackup, MAX_BACKUP_PLAINTEXT_BYTES } from './portableBackup.js';
import { businessDate } from './businessDate.js';
const normalize = value => ({ ...value, chunks: (value.chunks || []).map(row => ({ ...row, byte_count: row.size_bytes })) });
const checkAbort = signal => { if (signal.aborted) throw new DOMException('Transfer cancelled', 'AbortError'); };
const mib = value => `${(Number(value || 0) / 1048576).toFixed(1)} MiB`;
function saveFile(blob, filename) {
  const url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function CompleteBackup({ companyId, api, onRestored }) {
  const [password, setPassword] = useState(''), [plainAccepted, setPlainAccepted] = useState(false);
  const [name, setName] = useState(''), [file, setFile] = useState(null), [exportJob, setExportJob] = useState(null), [upload, setUpload] = useState(null);
  const [preview, setPreview] = useState(null), [resumeId, setResumeId] = useState(''), [resumeDirection, setResumeDirection] = useState('import'), [error, setError] = useState(''), [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false), [progress, setProgress] = useState(null), [pendingKind, setPendingKind] = useState(''), [transfers, setTransfers] = useState(null), [restoredCompany, setRestoredCompany] = useState('');
  const posting = usePostingRequest(), abort = useRef(null), alive = useRef(true), running = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; abort.current?.abort(); }; }, []);
  const locked = busy || posting.busy || posting.pending;
  async function perform(operation) {
    if (running.current) return;
    running.current = true;
    setError(''); setSuccess(''); setBusy(true);
    const controller = new AbortController(); abort.current = controller;
    try { await operation(controller.signal); }
    catch (failure) { if (alive.current) setError(failure.name === 'AbortError' ? 'Transfer stopped. Retained server chunks can be resumed; nothing was restored automatically.' : failure.message); }
    finally { running.current = false; if (alive.current) { setBusy(false); setProgress(null); } }
  }
  function prepareExport() {
    if (posting.pending && pendingKind !== 'export') return;
    setPendingKind('export');
    const key = crypto.randomUUID();
    perform(async () => {
      const result = await posting.run(() => api(`/companies/${companyId}/backup-exports`, { method: 'POST', body: '{}', headers: { 'Idempotency-Key': key } }));
      if (result && alive.current) setExportJob(normalize(result.value));
    });
  }
  function download() {
    const selected = exportJob, secret = password;
    perform(async signal => {
      const verifySession = captureSession();
      const access = captureCompanyAccess(`/api/companies/${companyId}`);
      if (!secret && !plainAccepted) throw Error('Acknowledge that the unencrypted file contains private financial information.');
      if (secret && secret.length < 12) throw Error('Use a backup password of at least 12 characters.');
      validateBackupManifest(selected, secret ? MAX_BACKUP_PLAINTEXT_BYTES : MAX_WEB_ARCHIVE_BYTES);
      const blob = await downloadBackupChunks(selected, async (index, options) => {
        const response = await api(`/companies/${companyId}/backup-exports/${selected.export_id}/chunks/${index}`, { ...options, rawResponse: true });
        return readBackupChunkResponse(response, options);
      }, { signal, maximumBytes: secret ? MAX_BACKUP_PLAINTEXT_BYTES : MAX_WEB_ARCHIVE_BYTES, onProgress: setProgress });
      const output = secret ? new Blob([await encryptPortableBackup(await blob.arrayBuffer(), secret, { signal })], { type: 'application/json' }) : blob;
      if (signal.aborted || !alive.current) return;
      verifySession(); access?.verify();
      saveFile(output, `apex-complete-${companyId.slice(0, 8)}-${businessDate()}.${secret ? 'apexbackup' : 'zip'}`);
      setSuccess(`Complete backup downloaded with ${selected.attachment_count || 0} retained receipts. Keep the file${secret ? ' and password' : ''} securely. The snapshot remains available until expiry or cancellation.`);
    });
  }
  function validate() {
    if (posting.pending && pendingKind !== 'upload') return;
    setPendingKind('upload');
    const selected = file, targetName = name.trim(), key = crypto.randomUUID();
    perform(async signal => {
      if (!selected || !targetName) throw Error('Choose a backup and enter the name for the new company.');
      if (selected.size > MAX_WEB_ARCHIVE_BYTES) throw Error('This backup exceeds the browser limit. Use a native client for the complete archive.');
      const signature = new Uint8Array(await selected.slice(0, 2).arrayBuffer());
      checkAbort(signal);
      const binary = signature[0] === 0x50 && signature[1] === 0x4b ? 'zip' : signature[0] === 0x1f && signature[1] === 0x8b ? 'gzip' : null;
      const decoded = binary ? { content: new Uint8Array(await selected.arrayBuffer()), kind: binary } : await readPortableBackup(selected, password, { signal });
      checkAbort(signal);
      let content = decoded.content;
      if (decoded.kind === 'json') {
        if (!('CompressionStream' in globalThis)) throw Error('Use a gzip backup or a native client to restore this JSON file.');
        content = new Uint8Array(await new Response(new Blob([content]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
      }
      if (decoded.kind !== 'zip' && content.length > 3000000) throw Error('Legacy JSON/gzip imports are limited to 3 MB compressed. Use a complete ZIP backup for larger books.');
      checkAbort(signal);
      const blob = new Blob([content]), digest = await sha256Bytes(content);
      checkAbort(signal);
      let job = upload;
      if (job && (job.sha256 !== digest || job.byte_count !== blob.size)) throw Error('This file differs from the retained upload. Cancel that transfer before choosing another.');
      if (!job) {
        const result = await posting.run(() => api('/backups/uploads', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ company_name: targetName, byte_count: blob.size, sha256: digest }) }));
        if (!result) return;
        job = normalize(result.value); if (alive.current) setUpload(job);
      } else job = normalize(await api(`/backups/uploads/${job.upload_id}`, { signal }));
      await uploadBackupChunks(blob, job, async (index, bytes, hash, options) => {
        const receipt = await api(`/backups/uploads/${job.upload_id}/chunks/${index}`, { ...options, method: 'PUT', body: bytes, headers: { 'Content-Type': 'application/octet-stream' } });
        return { sha256: receipt.sha256, byte_count: receipt.size_bytes };
      }, { signal, received: job.chunks, onProgress: setProgress });
      const report = await api(`/backups/uploads/${job.upload_id}/preview`, { method: 'POST', signal });
      if (alive.current && !signal.aborted) { setPreview(report); setUpload(job); }
    });
  }
  function restore() {
    if (posting.pending && pendingKind !== 'commit') return;
    setPendingKind('commit');
    const id = upload.upload_id, digest = preview.digest;
    perform(async () => {
      const result = await posting.run(() => api(`/backups/uploads/${id}/commit`, { method: 'POST', body: JSON.stringify({ digest }) }));
      if (result && alive.current) { setPreview(null); setUpload(null); setSuccess('Complete backup restored into a separate company, including retained receipts.'); await onRestored?.(result.value.company_id); }
    });
  }
  function chooseTransfer(value) {
    const job = normalize(value);
    if (job.state === 'restored') { setRestoredCompany(job.company_id); setTransfers(null); setSuccess('This transfer already restored a company. Open the existing result; no new restore is needed.'); return; }
    if (job.direction === 'export') {
      if (job.source_company_id !== companyId) { setError('Switch to the original company to recover that export.'); return; }
      setExportJob(job);
    } else { setUpload(job); setName(job.target_company_name || ''); setPreview(job.state === 'sealed' ? job : null); }
    setTransfers(null); setSuccess('Temporary transfer recovered. Review it before resuming; no restore was performed.');
  }
  function findTransfers() {
    perform(async signal => {
      const result = await api('/backups/transfers', { signal });
      if (!signal.aborted && alive.current) setTransfers(result.transfers || []);
    });
  }
  function resume() {
    perform(async signal => {
      const id = resumeId.trim();
      if (!/^[a-f0-9-]{36}$/i.test(id)) throw Error('Enter the transfer ID shown when the upload was prepared.');
      const job = normalize(await api(resumeDirection === 'export' ? `/companies/${companyId}/backup-exports/${id}` : `/backups/uploads/${id}`, { signal }));
      if (resumeDirection === 'export') { setExportJob(job); setSuccess('Immutable snapshot recovered. Review its size and download or discard it.'); return; }
      if (job.state === 'restored') { setRestoredCompany(job.company_id); setSuccess('This transfer already restored a company. Open the existing result; do not upload it again.'); return; }
      setUpload(job); setName(job.target_company_name || 'Recovered company'); setPreview(job.state === 'sealed' ? job : null);
      setSuccess('Transfer recovered. Select the original file to resume missing chunks, or review the validated preview.');
    });
  }
  function cancelJob(direction) {
    const job = direction === 'export' ? exportJob : upload;
    perform(async () => {
      await api(direction === 'export' ? `/companies/${companyId}/backup-exports/${job.export_id}` : `/backups/uploads/${job.upload_id}`, { method: 'DELETE' });
      if (direction === 'export') setExportJob(null); else { setUpload(null); setPreview(null); }
      setSuccess('Temporary transfer cancelled. Existing companies and retained receipts were not changed.');
    });
  }
  return <section className="member-settings complete-backup">
    <h2><ShieldCheck size={20} /> Complete backup and restore</h2>
    <p>One consistent ZIP snapshot contains the books, settings and every retained receipt, including archived evidence. Restore creates a separate company; it never replaces the current books.</p>
    <p className="info-box">Browser limits: {mib(MAX_WEB_ARCHIVE_BYTES)} plain ZIP; {mib(MAX_BACKUP_PLAINTEXT_BYTES)} before password encryption. Use a native client for larger archives or a memory-constrained device. Nothing is omitted to fit.</p>
    <label>Backup password<input type="password" autoComplete="new-password" value={password} disabled={locked} onChange={event => setPassword(event.target.value)} placeholder="At least 12 characters to encrypt; also used to open an encrypted backup" /></label>
    {!password && <label className="checkbox"><input type="checkbox" checked={plainAccepted} disabled={locked} onChange={event => setPlainAccepted(event.target.checked)} />I understand an unencrypted ZIP contains private financial information.</label>}
    <button className="button secondary" disabled={busy || !!exportJob || (posting.pending && pendingKind !== 'export')} onClick={prepareExport}>{posting.pending && !exportJob && !upload ? 'Retry original preparation' : 'Prepare complete snapshot'}</button>
    {exportJob && <div className="info-box"><strong>{mib(exportJob.byte_count)} · {exportJob.attachment_count || 0} retained receipts</strong><p>Transfer ID: {exportJob.export_id}</p><p>Immutable snapshot expires {exportJob.expires_at}. Later transactions are not added to this file.</p><button className="button secondary" disabled={locked || (!password && !plainAccepted)} onClick={download}><Download size={16} />Download complete backup</button> <button className="button secondary" disabled={locked} onClick={() => cancelJob('export')}>Discard temporary snapshot</button></div>}
    <h3>Recover temporary transfers</h3>
    <p>If the app closed or a preparation response was lost, retrieve active transfers and recently completed restores without uploading the books again. Recovery never automatically restores a company.</p>
    <button className="button secondary" disabled={locked} onClick={findTransfers}>Find my active transfers and recent restores</button>
    {transfers && <div className="info-box">{transfers.length ? transfers.map(job => <div key={job.export_id || job.upload_id}><p>{job.direction === 'export' ? 'Export snapshot' : 'Restore upload'} · {job.target_company_name || 'Company backup'} · {mib(job.byte_count)} · {job.state}</p><button className="button secondary" disabled={locked || (job.direction === 'export' ? !!exportJob || job.source_company_id !== companyId : !!upload)} onClick={() => chooseTransfer(job)}>{job.state === 'restored' ? 'Recover completed result' : 'Recover this transfer'}</button>{job.direction === 'export' && job.source_company_id !== companyId && <small>Switch to the original company to recover this export.</small>}</div>) : <p>No retained unexpired transfers. Existing books are unchanged.</p>}</div>}
    {restoredCompany && <button className="button primary" disabled={locked} onClick={() => perform(() => onRestored?.(restoredCompany))}>Open restored company</button>}
    <h3>Restore into a new company</h3>
    <label>New company name<input maxLength={120} value={name} disabled={locked || !!upload} onChange={event => { setName(event.target.value); setPreview(null); }} /></label>
    <label>Backup file<input type="file" accept=".zip,.json,.gz,.apexbackup" disabled={locked} onChange={event => { setFile(event.target.files?.[0] || null); setPreview(null); }} /></label>
    <p>Old JSON/gzip and encrypted-v1 backups remain readable within browser limits. Passwords are used only on this device and never sent to the API. Login credentials and team invitations are not restored.</p>
    <button className="button secondary" disabled={busy || (!file && !posting.pending) || (posting.pending && pendingKind !== 'upload')} onClick={validate}><Upload size={16} />{posting.pending ? 'Retry original request' : upload ? 'Resume and validate original file' : 'Upload and validate'}</button>
    {upload && <div className="info-box"><strong>Transfer ID: {upload.upload_id}</strong><p>Retain this ID to recover the staged upload after reopening this page. Chunks expire {upload.expires_at}; sign in to the same account to resume. No company exists until you confirm restore.</p><button className="button secondary" disabled={locked} onClick={() => cancelJob('import')}>Cancel staged upload</button></div>}
    {!upload && <details><summary>Recover a previous transfer</summary><label>Transfer type<select disabled={locked} value={resumeDirection} onChange={event => setResumeDirection(event.target.value)}><option value="import">Restore upload</option><option value="export">This company's export snapshot</option></select></label><label>Transfer ID<input value={resumeId} disabled={locked} onChange={event => setResumeId(event.target.value)} /></label><button className="button secondary" disabled={locked || !resumeId} onClick={resume}>Recover transfer</button></details>}
    {preview && <div className="info-box"><strong>Validated: {preview.company_name}</strong><p>{preview.counts?.records || 0} records · {preview.counts?.journals || 0} journals · {preview.attachment_count || 0} retained receipts ({mib(preview.attachment_bytes)})</p><button className="button primary" disabled={busy || (posting.pending && pendingKind !== 'commit')} onClick={restore}>{posting.pending ? 'Retry original restore' : 'Restore as separate company'}</button></div>}
    {progress && <p role="status">{progress.phase}: {mib(progress.completedBytes)} / {mib(progress.totalBytes)}</p>}
    {busy && !posting.busy && <button className="button secondary" onClick={() => abort.current?.abort()}>Stop transfer</button>}
    {posting.pending && <p className="error banner" role="alert">{pendingPostingMessage}</p>}
    {error && <p className="error banner" role="alert">{error}</p>}{success && <p role="status">{success}</p>}
  </section>;
}
