import React from 'react';
import { ArrowUpRight, Check, FileText, Package, ShieldCheck, UsersRound } from 'lucide-react';

/** Suggestions only: opening a checklist action never posts a transaction. */
export default function SetupChecklist({ company, records, onCreate, onNavigate }) {
  const canWrite = ['owner', 'editor'].includes(company?.role);
  const posted = records.some(row => row.posted);
  if (posted) return null;
  const parties = records.filter(row => row.kind === 'party').length;
  const items = records.filter(row => row.kind === 'item').length;
  const drafts = records.filter(row => ['estimate', 'proforma', 'sales_order', 'purchase_order'].includes(row.kind)).length;
  const steps = [
    { title: 'Your customers & suppliers', note: parties ? `${parties} parties ready` : 'Save contacts once, use them on every document.', icon: UsersRound, complete: parties > 0, action: () => onCreate('party'), label: parties ? 'View parties' : 'Add a party', view: () => onNavigate('party') },
    { title: 'Your items & services', note: items ? `${items} items in your catalogue` : 'Set prices, tax and optional stock tracking.', icon: Package, complete: items > 0, action: () => onCreate('item'), label: items ? 'View catalogue' : 'Add an item', view: () => onNavigate('item') },
    { title: 'Try a draft first', note: drafts ? `${drafts} drafts saved without posting` : 'Preview an estimate without affecting your books.', icon: FileText, complete: drafts > 0, action: () => onCreate('estimate'), label: drafts ? 'View drafts' : 'Create an estimate', view: () => onNavigate('estimate') },
  ];
  return <section className="setup-guide" aria-labelledby="setup-guide-title">
    <div className="setup-guide-intro"><div className="setup-guide-mark"><ShieldCheck size={27} /></div><div><span className="workspace-kicker">A CONFIDENT START</span><h2 id="setup-guide-title">Make this workspace yours.</h2><p>{canWrite ? 'A few useful starting points. Add only what your business needs — drafts never change your balances.' : 'Your company is ready. An owner or editor can add the first parties, items and transactions.'}</p></div><button className="button secondary" onClick={() => onNavigate('settings')}>Company setup<ArrowUpRight size={15} /></button></div>
    <div className="setup-guide-steps">{steps.map((step, index) => <article key={step.title} className={step.complete ? 'complete' : ''}><span className="setup-step-icon">{step.complete ? <Check size={19} /> : <step.icon size={19} />}</span><span className="setup-step-index">0{index + 1}</span><h3>{step.title}</h3><p>{step.note}</p>{canWrite || step.complete ? <button className="link" onClick={step.complete ? step.view : step.action}>{step.label}<ArrowUpRight size={14} /></button> : <span className="setup-readonly">Owner or editor action</span>}</article>)}</div>
    <div className="setup-guide-footer"><span>Moving from another app? Import preview is read-only until you confirm.</span><button className="link" onClick={() => onNavigate('settings')}>Explore import & backup<ArrowUpRight size={14} /></button></div>
  </section>;
}
