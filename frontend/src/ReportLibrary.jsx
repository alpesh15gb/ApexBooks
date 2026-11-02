import React, { useState } from "react";
import { ArrowUpRight, BarChart3, Search } from "lucide-react";

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
        "financial",
        "Profit & balance sheet",
        "Income, expenses, assets and liabilities",
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
  const matches = reportGroups
    .map((g) => ({
      ...g,
      reports: g.reports.filter((r) =>
        `${g.title} ${r.join(" ")}`
          .toLowerCase()
          .includes(search.trim().toLowerCase()),
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
            Choose a report, set the period and export the figures you need.
          </p>
        </div>
        <span className="library-count">15 reports · PDF & XLSX</span>
      </div>
      <label className="library-search">
        <Search size={19} />
        <input
          aria-label="Find a report"
          placeholder="Find a report, e.g. sales, GST or stock"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
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
          <button className="link" onClick={() => setSearch("")}>
            Clear search
          </button>
        </div>
      )}
    </div>
  );
}
