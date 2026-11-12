import React, { useEffect, useState } from 'react';
import { ArrowUpRight, Building2, Check, ChevronDown, FileText, Landmark, Package, ShieldCheck, UsersRound, X } from 'lucide-react';
import { setupSteps } from './setupSteps.js';

const icons = { business: Building2, payment: Landmark, party: UsersRound, item: Package, invoice: FileText };

/** Suggestions only: opening a checklist action never posts a transaction. Shown until every step is done or dismissed. */
export default function SetupChecklist({ company, records, onCreate, onNavigate, api }) {
  const canWrite = ['owner', 'editor'].includes(company?.role);
  const dismissKey = `apex-setup-dismissed-${company?.id}`;
  const [branding, setBranding] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(() => { try { return localStorage.getItem(dismissKey) === '1'; } catch { return false; } });
  useEffect(() => {
    let active = true;
    if (!company?.id) return undefined;
    const load = api ? api(`/companies/${company.id}/document-branding`)
      : (() => { let token = ''; try { token = localStorage.token || ''; } catch { /* no storage */ } return fetch(`/api/companies/${company.id}/document-branding`, { headers: { Authorization: `Bearer ${token}` } }).then(r => (r.ok ? r.json() : {})); })();
    Promise.resolve(load).then(value => active && setBranding(value || {})).catch(() => active && setBranding({}));
    return () => { active = false; };
  }, [company?.id]);
  if (dismissed || branding === null) return null;
  const steps = setupSteps({ company, records, branding });
  const done = steps.filter(step => step.complete).length;
  if (done === steps.length) return null;
  const dismiss = () => { try { localStorage.setItem(dismissKey, '1'); } catch { /* per-viewer convenience only */ } setDismissed(true); };
  return <section className="setup-guide" aria-labelledby="setup-guide-title">
    <div className="setup-guide-intro"><div className="setup-guide-mark"><ShieldCheck size={25} /></div><div><span className="workspace-kicker">YOUR WORKSPACE · {done} OF {steps.length} READY</span><h2 id="setup-guide-title">Make this workspace yours.</h2><p>{canWrite ? 'Your details, your people, your way of doing business.' : 'An owner or editor can finish these steps.'}</p></div><div className="setup-progress" role="progressbar" aria-label="Workspace setup" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done}><span style={{width:`${done / steps.length * 100}%`}} /></div><button className="button secondary setup-toggle" aria-expanded={expanded} aria-controls="setup-guide-steps" onClick={() => setExpanded(value => !value)}>{expanded ? 'Close setup' : 'Continue setup'}<ChevronDown size={16} /></button><button className="icon-button" aria-label="Hide setup checklist" title="Hide" onClick={dismiss}><X size={18} /></button></div>
    {expanded && <><div className="setup-guide-steps" id="setup-guide-steps">{steps.map((step, index) => <article key={step.key} className={step.complete ? 'complete' : ''}><span className="setup-step-icon">{step.complete ? <Check size={19} /> : React.createElement(icons[step.key], { size: 19 })}</span><span className="setup-step-index">0{index + 1}</span><h3>{step.title}</h3><p>{step.note}</p>{canWrite || step.complete ? <button className="link" onClick={() => (!step.complete && step.create ? onCreate(step.create) : onNavigate(step.go, step.key === "payment" ? "documents" : ""))}>{step.label}<ArrowUpRight size={14} /></button> : <span className="setup-readonly">Owner or editor action</span>}</article>)}</div>
    <div className="setup-guide-footer"><span>Moving from another app? Review your import before bringing it into your books.</span><button className="link" onClick={() => onNavigate('settings', 'data')}>Explore import & backup<ArrowUpRight size={14} /></button></div></>}
  </section>;
}
