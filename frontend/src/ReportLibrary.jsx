import React, { useState } from "react";
import { ArrowUpRight, BarChart3, Search, TrendingUp, Wallet, Package } from "lucide-react";

export const reportGroups = [
  {
    title: "Business & transactions",
    description: "Understand performance and review the books.",
    reports: [
      [
        "summary",
        "Transaction summary",
        "Sales, purchases, cash activity and balances",
      ],
      ["sales", "Sales register", "Invoices, POS sales and credit notes"],
      ["purchases", "Purchase register", "Supplier bills and debit notes"],
      ["expenses", "Expense register", "Business spending and supplier tax"],
      [
        "statements",
        "Profit & loss and balance sheet",
        "Formatted statements with gross profit and classified balances",
      ],
      [
        "financial",
        "Account balances",
        "Every ledger account for the period and closing balance",
      ],
    ],
  },
  {
    title: "Parties & balances",
    description: "Follow collections, dues and unapplied balances.",
    reports: [
      [
        "parties",
        "Party statement",
        "A party's transactions and running balance",
      ],
      ["ageing", "Receivables & payables ageing", "Outstanding amounts by age"],
      ["credits", "Credit balances", "Available customer and supplier credits"],
      [
        "advances",
        "Advance balances",
        "Unapplied receipts and supplier advances",
      ],
    ],
  },
  {
    title: "GST preparation",
    description: "Review book figures before filing or claiming credit.",
    reports: [
      ["gst", "GST analysis", "Output tax and supplier tax pending review"],
      ["gstr1", "GSTR-1", "Outward supplies working paper"],
      [
        "gstr2a",
        "GSTR-2A · purchase books",
        "Calculated from entered bills, not the GST portal",
      ],
      ["gstr3b", "GSTR-3B", "Liability and input tax working paper"],
    ],
  },
  {
    title: "Items & inventory",
    description: "Check item movement, quantities and stock value.",
    reports: [
      ["items", "Item activity", "Sales and purchase quantities by item / HSN"],
      [
        "stock",
        "Tracked stock",
        "Opening, movements, closing quantity and cost",
      ],
    ],
  },
];
export const reportInfo = Object.fromEntries(
  reportGroups.flatMap((g) =>
    g.reports.map((r) => [
      r[0],
      { title: r[1], description: r[2], group: g.title },
    ]),
  ),
);
export default function ReportLibrary({ onSelect }) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const shortcuts = [
    ["statements", "How is my business doing?", "Profit & loss and balance sheet", TrendingUp],
    ["ageing", "Who owes money?", "Unpaid customer invoices and supplier bills", Wallet],
    ["stock", "What is in stock?", "Quantities on hand and inventory value", Package],
  ];
  const searchWords = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const keywords = {
    statements: "profit loss profitability income expenses assets liabilities equity financial performance",
    ageing: "who owes money overdue unpaid customer invoices supplier bills collect pay due receivable payable aging",
    stock: "inventory quantity on hand value cost available",
    parties: "customer supplier vendor ledger balance statement",
    credits: "refund credit return remaining",
    advances: "deposit prepayment advance unapplied",
  };
  const matches = reportGroups
    .filter((g) => category === "all" || category === g.title)
    .map((g) => ({
      ...g,
      reports: g.reports.filter((r) =>
        searchWords.every(word => `${g.title} ${r.join(" ")} ${keywords[r[0]] || ""}`.toLowerCase().includes(word)),
      ),
    }))
    .filter((g) => g.reports.length);
  return (
    <div className="report-library">
      <div className="page-heading">
        <div>
          <div className="workspace-kicker">
            <span /> YOUR BUSINESS, IN VIEW
          </div>
          <h1>Reports</h1>
          <p>
            Start with a business question, or find a report below.
          </p>
        </div>
        <span className="library-count">{reportGroups.reduce((total, group) => total + group.reports.length, 0)} reports · PDF & XLSX</span>
      </div>
      {!search && category === "all" && <section className="report-shortcuts" aria-label="Common business questions">
        {shortcuts.map(([key, title, description, Icon]) => <button type="button" className="report-shortcut" key={key} onClick={() => onSelect(key)}>
          <Icon size={22} aria-hidden="true" /><span><strong>{title}</strong><small>{description}</small></span><ArrowUpRight size={18} aria-hidden="true" />
        </button>)}
      </section>}
      <label className="library-search">
        <Search size={19} />
        <input
          aria-label="Find a report"
          placeholder="Find a report, e.g. sales, GST or stock"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <div className="library-category-filter" role="group" aria-label="Report category">
        {["all", ...reportGroups.map(group => group.title)].map(key => <button type="button" key={key} aria-pressed={category === key} onClick={() => setCategory(key)}>{key === "all" ? "All reports" : key}</button>)}
      </div>
      {(search || category !== "all") && <p className="detail-caption" role="status">{matches.reduce((count, group) => count + group.reports.length, 0)} matching reports</p>}
      <div className="report-library-grid">
        {matches.map((group) => (
          <section className="report-category" key={group.title}>
            <div className="report-category-heading">
              <BarChart3 size={20} />
              <div>
                <h2>{group.title}</h2>
                <p>{group.description}</p>
              </div>
            </div>
            <div>
              {group.reports.map(([key, title, description]) => (
                <button
                  className="report-choice"
                  key={key}
                  onClick={() => onSelect(key)}
                >
                  <span>
                    <strong>{title}</strong>
                    <small>{description}</small>
                  </span>
                  <ArrowUpRight size={17} />
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>
      {!matches.length && (
        <div className="empty">
          <strong>No matching reports</strong>
          <p>Try sales, party, GST or inventory.</p>
          <button className="link" onClick={() => { setSearch(""); setCategory("all"); }}>
            Show all reports
          </button>
        </div>
      )}
    </div>
  );
}
