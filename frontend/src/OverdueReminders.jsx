import React, { useEffect, useMemo, useState } from "react";
import { BellRing, CheckCircle2, X } from "lucide-react";
import { overdueByParty, partyReminderMessage, whatsappPhone, whatsappUrl } from "./whatsappShare.js";
import { businessDate } from "./businessDate.js";

const rupees = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value || 0));

export function overdueCount(records) {
  return overdueByParty(records, businessDate()).length;
}

// "Remind all overdue": WhatsApp opens one customer at a time; nothing is sent until you press send there.
export default function OverdueReminders({ records, company, onClose }) {
  const groups = useMemo(() => overdueByParty(records, businessDate()), [records]);
  const [upi, setUpi] = useState("");
  const [sent, setSent] = useState(() => new Set());
  useEffect(() => {
    let active = true;
    fetch(`/api/companies/${company.id}/document-branding`, { headers: { Authorization: `Bearer ${localStorage.token}` } })
      .then((r) => (r.ok ? r.json() : {})).then((b) => active && setUpi(b.upi_id || "")).catch(() => {});
    return () => { active = false; };
  }, [company.id]);
  const remind = (group, key) => {
    window.open(whatsappUrl(group.phone, partyReminderMessage(group, company.name || "", upi)), "_blank");
    setSent((current) => new Set(current).add(key));
  };
  const total = groups.reduce((sum, g) => sum + g.total, 0);
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="modal overdue-reminders" role="dialog" aria-modal="true" aria-labelledby="overdue-title">
        <header className="modal-header">
          <div><h2 id="overdue-title">Remind overdue customers</h2><p>{groups.length} {groups.length === 1 ? "customer" : "customers"} · {rupees(total)} overdue · one WhatsApp message each</p></div>
          <button className="icon-button" aria-label="Close" onClick={onClose}><X size={20} /></button>
        </header>
        {!groups.length && <div className="empty"><strong>No overdue invoices</strong><span>Invoices past their due date with a balance appear here.</span></div>}
        <ul className="overdue-list">
          {groups.map((group) => {
            const key = group.name.trim().toLowerCase();
            return (
              <li key={key}>
                <div><strong>{group.name}</strong><small>{group.invoices.map((i) => i.number).join(", ")}{whatsappPhone(group.phone) ? "" : " · no phone saved"}</small></div>
                <span className="amount">{rupees(group.total)}</span>
                <button type="button" className={`button ${sent.has(key) ? "secondary" : "primary"} whatsapp`} onClick={() => remind(group, key)}>
                  {sent.has(key) ? <><CheckCircle2 size={15} />Opened</> : <><BellRing size={15} />Remind</>}
                </button>
              </li>
            );
          })}
        </ul>
        <p className="info-box">WhatsApp opens with the message filled in. Customers without a saved phone open WhatsApp so you can pick the chat.</p>
      </section>
    </div>
  );
}
