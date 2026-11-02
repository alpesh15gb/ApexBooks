import { businessDate } from "./businessDate.js";
import React from "react";
import { CheckCheck, Clock3, FileText, Wallet } from "lucide-react";
const money = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    value || 0,
  );
export default function RegisterOverview({ page, records, filter, onFilter }) {
  const rows = records.filter((r) => r.kind === page),
    invoice = ["sales_invoice", "purchase_bill"].includes(page),
    draft = ["estimate", "proforma", "sales_order", "purchase_order"].includes(page);
  const transaction = [
    "payment_in",
    "payment_out",
    "expense",
    "credit_note",
    "debit_note",
  ].includes(page);
  if (!invoice && !draft && !transaction) return null;
  const posted = rows.filter((r) => r.posted),
    open = posted.filter((r) => Number(r.outstanding) > 0),
    closed = posted.filter((r) => Number(r.outstanding) === 0),
    active = rows.filter((r) => !r.converted_to),
    converted = rows.filter((r) => r.converted_to);
  const stats = invoice
    ? [
        [
          "Posted value",
          posted.reduce((s, r) => s + Number(r.amount || 0), 0),
          FileText,
          false,
        ],
        [
          "Outstanding",
          open.reduce((s, r) => s + Number(r.outstanding || 0), 0),
          Wallet,
          false,
        ],
        ["Unpaid documents", open.length, Clock3, true],
        ["Settled documents", closed.length, CheckCheck, true],
      ]
    : transaction
      ? [
          [
            "Posted value",
            posted.reduce((s, r) => s + Number(r.amount || 0), 0),
            Wallet,
            false,
          ],
          ["Posted transactions", posted.length, CheckCheck, true],
          ["Unposted records", rows.length - posted.length, Clock3, true],
        ]
      : [
          ["Active drafts", active.length, FileText, true],
          [
            "Draft value",
            active.reduce((s, r) => s + Number(r.amount || 0), 0),
            Wallet,
            false,
          ],
          ["Converted", converted.length, CheckCheck, true],
        ];
  const today = businessDate(),
    overdue = open.filter((r) => r.data?.due_date && r.data.due_date < today);
  const options = invoice
    ? [
        ["all", "All", rows.length],
        ["unpaid", "Unpaid", open.length],
        ["paid", "Settled", closed.length],
        ["overdue", "Overdue", overdue.length],
      ]
    : transaction
      ? [
          ["all", "All", rows.length],
          ["posted", "Posted", posted.length],
          ["unposted", "Unposted", rows.length - posted.length],
        ]
      : [
          ["all", "All", rows.length],
          ["draft", "Draft", active.length],
          ["converted", "Converted", converted.length],
        ];
  return (
    <>
      <div className="register-overview">
        {stats.map(([label, value, Icon, count]) => (
          <div key={label}>
            <span className="register-stat-icon">
              <Icon size={18} />
            </span>
            <div>
              <small>{label}</small>
              <strong>{count ? value : money(value)}</strong>
            </div>
          </div>
        ))}
      </div>
      <div
        className="register-filter-tabs"
        role="tablist"
        aria-label="Transaction status"
      >
        {options.map(([key, label, count]) => (
          <button
            key={key}
            role="tab"
            aria-selected={filter === key}
            onClick={() => onFilter(key)}
          >
            {label}
            <span>{count}</span>
          </button>
        ))}
      </div>
    </>
  );
}
