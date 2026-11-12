import {usePostingRequest, pendingPostingMessage} from './usePostingRequest.js';
import {captureCompanyAccess} from './companyAccess.js';
import {createRequestScope} from './requestScope.js';
import {sessionFetch as fetch, captureSession} from './sessionScope.js';
import React, {useEffect, useRef, useState} from 'react';
import {downloadBlob} from './downloadBlob.js';
const money=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(Number(value||0));

export default function VyaparImport({companyId, role, onImported}) {
  const [encoded,setEncoded]=useState(''),[storedReport,setReport]=useState(null),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[accepted,setAccepted]=useState(false),[mode,setMode]=useState('posting');
  const exports = useRef(createRequestScope(`${companyId}:${role}:${mode}`));
  exports.current.setContext(`${companyId}:${role}:${mode}`);
  const exporting = useRef(false), processing = useRef(false), previewOwner = useRef(null), pendingOwner = useRef(null);
  const submission = usePostingRequest();
  const matches = owner => owner && owner.companyId === companyId && owner.mode === mode && owner.token === localStorage.token && role === 'owner';
  const report = matches(previewOwner.current) && (submission.pending || previewOwner.current.current()) ? storedReport : null;
  const locked = busy || submission.busy || submission.pending;
  useEffect(() => { setError(''); }, [companyId, role, mode]);
  const [exportBusy, setExportBusy] = useState(false);
  useEffect(() => { setExportBusy(false); if(!processing.current)setBusy(false); }, [companyId, role, mode]);
  useEffect(() => () => exports.current.setContext(Symbol('unmounted')), []);
  async function request(action, content, digest, origin) {
    const endpoint=origin.mode==='posting'?'vyapar-posting':'vyapar';
    const response=await fetch(`/api/companies/${origin.companyId}/imports/${endpoint}/${action}`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${origin.token}`},body:JSON.stringify({backup_base64:content,digest})});
    const result=await response.json();
    if(!response.ok){const error=Error(typeof result.detail==='string'?result.detail:result.detail?.message||'Backup migration failed');error.status=response.status;throw error;}
    return result;
  }
  async function run() {
    if (processing.current || role !== 'owner' || (submission.pending ? !matches(pendingOwner.current) : !report || !accepted || !previewOwner.current.current())) return;
    const retrying=submission.pending;
    const current=exports.current.capture(), origin=pendingOwner.current || {companyId,mode,token:localStorage.token};
    processing.current=true;setBusy(true);setError('');
    try {
      const verifySession=captureSession(), access=captureCompanyAccess(`/api/companies/${companyId}`);
      const content=encoded, digest=report?.digest || '';
      pendingOwner.current=origin;
      const outcome=await submission.run(()=>request('commit',content,digest,origin));
      if(!outcome)return;
      pendingOwner.current=null;
      if(!current())return;verifySession();access?.verify();
      previewOwner.current={...origin,current};setReport(outcome.value);
      if(outcome.value.imported)await onImported();
    } catch(reason){if(!retrying&&reason.status>=400&&reason.status<500&&reason.status!==408)pendingOwner.current=null;if(current())setError(reason.message);}
    finally{processing.current=false;setBusy(false);}
  }
  async function choose(event) {
    if(processing.current || submission.pending || role !== 'owner')return;
    const file=event.target.files?.[0];setReport(null);previewOwner.current=null;setAccepted(false);setEncoded('');setError('');
    if(!file)return;
    if(!file.name.toLowerCase().endsWith('.vyb')||file.size>3_000_000){setError('Choose a .vyb backup under 3 MB');return;}
    const current=exports.current.capture(), origin={companyId,mode,token:localStorage.token};
    processing.current=true;setBusy(true);
    try {
      const verifySession=captureSession(), access=captureCompanyAccess(`/api/companies/${companyId}`);
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Backup could not be read'));reader.readAsDataURL(file);});
      if(!current())return;verifySession();access?.verify();
      const result=await request('preview',content,'',origin);
      if(!current())return;verifySession();access?.verify();
      setEncoded(content);previewOwner.current={...origin,current};setReport(result);
    }catch(reason){if(current())setError(reason.message);}
    finally{processing.current=false;setBusy(false);}
  }
  async function saved(reconciliation=false) {
    if (role !== 'owner' || exporting.current) return;
    const current = exports.current.capture();
    let verify = () => {};
    exporting.current = true; setExportBusy(true); setError('');
    try {
      const session = captureSession(), access = captureCompanyAccess(`/api/companies/${companyId}`);
      verify = () => { session(); access?.verify(); };
      const response=await fetch(`/api/companies/${companyId}/imports/${reconciliation?'vyapar-posting/reconciliation':'vyapar/archive.json'}`,{headers:{Authorization:`Bearer ${localStorage.token}`}});
      if(!response.ok)throw Error(reconciliation?'No posted migration reconciliation is available':'No imported archive is available');
      const blob = await response.blob();
      if (!current()) return;
      verify();
      downloadBlob(blob,reconciliation?'vyapar-posting-reconciliation.json':'vyapar-source-archive.json');
    }catch(reason){if(current()){try{verify();setError(reason.message);}catch{/* An obsolete operation cannot publish an error. */}}}
    finally { exporting.current = false; if(current())setExportBusy(false); }
  }
  if(role!=='owner')return null;
  const posting=mode==='posting',errors=report?.errors||[],checks=report?.reconciliation||[];
  const ready=posting?report?.ready:!errors.length;
  return <section className="panel settings-panel"><h2>Import Vyapar backup</h2>
    <p>Migrate into a new company. The posting adapter supports sales, purchase bills, receipts, estimates and purchase orders. Unsupported source data blocks posting without changing your books.</p>
    <div className="form-grid"><label className="full">Import scope<select className="form-select" value={mode} disabled={locked} onChange={event=>{if(processing.current||submission.pending)return;setMode(event.target.value);setReport(null);setEncoded('');setAccepted(false);setError('');}}><option value="posting">Full transaction posting</option><option value="archive">Masters and source archive only</option></select></label>
    <label className="full">Vyapar .vyb file<input key={mode} type="file" accept=".vyb" disabled={locked} onChange={choose}/></label></div>
    {busy&&<p role="status">Processing and reconciling backup…</p>}{error&&<p className="error" role="alert">{error}</p>}
    {submission.pending&&<div className="info-box" role="status"><p>{pendingPostingMessage}</p><p>Return to the original company and import scope to retry the exact backup.</p><button type="button" className="button secondary" disabled={busy||!matches(pendingOwner.current)} onClick={()=>run()}>Retry original migration</button></div>}
    {report&&<div><h3>{report.company_name||'Backup summary'}</h3>
      {posting?<><p>{report.source_transaction_count} source transactions mapped</p><p>{Object.entries(report.document_counts||{}).map(([kind,count])=>`${count} ${kind.replaceAll('_',' ')}`).join(' · ')}</p><p>{report.payment_count} payment entries · {report.stock_items} stock items · {report.negative_stock_items} source items with negative stock</p>
        <div className="migration-control-grid">{[["Source sales",report.totals?.sales],["Purchase bills",report.totals?.purchases],["Receivable",report.totals?.receivable]].map(([label,value])=><div key={label}><span>{label}</span><strong>{money(value)}</strong></div>)}</div>
        <p>Invoice payments are imported and allocated. {report.supplier_advance_count} purchase-order payments enter supplier advances and cash/bank, without posting purchases, stock or input GST. Converted estimates remain closed.</p></>:<p>{report.ready?.parties} parties · {report.ready?.items} items ready. Historical transactions and stock remain unposted in the source archive.</p>}
      {report.warnings?.map(message=><p key={message}>{message}</p>)}
      {!!report.tax_rounding_by_party?.length&&<details><summary>GST source precision and posting rounding · {report.tax_rounding_by_party.length} differences</summary><p>Vyapar groups unrounded line tax by party. Journals post rounded document components in paise. Original tax precision is preserved; these differences are shown explicitly.</p><div className="table-wrap" tabIndex={0}><table><thead><tr><th>PARTY</th><th>SOURCE REPORT TAX</th><th>POSTED TAX</th><th>DIFFERENCE</th></tr></thead><tbody>{report.tax_rounding_by_party.map(row=><tr key={row.kind+row.party}><td>{row.party}</td><td>{row.source_report_tax}</td><td>{row.posted_tax}</td><td>{row.difference}</td></tr>)}</tbody></table></div></details>}
      {!!errors.length&&<div role="alert"><strong>Posting blocked · {errors.length} source checks failed</strong>{errors.map((issue,index)=><p className="error" key={index}>{typeof issue==='string'?issue:issue.name+': '+issue.error}</p>)}</div>}
      {report.imported||report.already_imported?<p className={"migration-result"+(checks.some(c=>!c.passed)?" has-differences":"")} role="status">{posting?`Migration posted: ${report.journals_posted} balanced journals, ${report.allocations_created} payment allocations. ${checks.filter(c=>c.passed).length} of ${checks.length} reconciliation checks passed.`:'Masters and source archive saved. Historical transactions remain unposted.'}{report.already_imported?' This exact backup was already imported; no duplicate entries were created.':''}</p>:<><label><input type="checkbox" checked={accepted} disabled={locked} onChange={event=>setAccepted(event.target.checked)}/>{posting?' I have reviewed this preview. Post this backup atomically into this company.':' Import masters and source archive without posting transactions or stock.'}</label><button className="button primary" disabled={locked||!accepted||!ready} onClick={()=>run()}>{posting?'Post and reconcile migration':'Import masters and source archive'}</button></>}
      {!!checks.length&&<details><summary>Posting reconciliation · {checks.length} checks</summary><div className="table-wrap" tabIndex={0}><table><thead><tr><th>CHECK</th><th>SOURCE</th><th>POSTED</th><th>RESULT</th></tr></thead><tbody>{checks.map(row=><tr key={row.check}><td>{row.check}</td><td>{row.expected}</td><td>{row.actual}</td><td>{row.passed?'Matched':'Difference'}</td></tr>)}</tbody></table></div></details>}
    </div>}
    <div className="actions"><button className="button secondary" disabled={busy||exportBusy} onClick={()=>saved(false)}>Download source archive</button><button className="button secondary" disabled={busy||exportBusy} onClick={()=>saved(true)}>Download posting reconciliation</button></div>
  </section>;
}
