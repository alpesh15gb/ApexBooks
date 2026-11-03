import React from "react";

const rupees = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value || 0));

function Row({ label, value, tone = "", detail }) {
  return (
    <tr className={`statement-row ${tone}`}>
      <td>
        {label}
        {detail ? <small>{detail}</small> : null}
      </td>
      <td className="right">{value === undefined || value === null ? "" : rupees(value)}</td>
    </tr>
  );
}

function Lines({ items }) {
  return items.map((item) => (
    <Row key={item.code + item.name} label={item.name} value={item.amount} tone="indent" />
  ));
}

export default function StatementsView({ data }) {
  const pl = data.profit_loss;
  const bs = data.balance_sheet;
  const balanced = Number(bs.difference) === 0;
  return (
    <div className="statements">
      <div className="statement-grid">
        <section className="panel statement" aria-labelledby="pl-title">
          <h2 id="pl-title">Profit and loss</h2>
          <p className="statement-period">{data.from_date} to {data.to_date}</p>
          <table>
            <tbody>
              <Row label="Revenue" tone="section" />
              {pl.revenue.lines.length ? <Lines items={pl.revenue.lines} /> : <Row label="No sales in this period" tone="indent muted" />}
              <Row label="Total revenue" value={pl.revenue.total} tone="subtotal" />
              <Row label="Cost of sales" tone="section" />
              {pl.cost_of_sales.lines.length ? <Lines items={pl.cost_of_sales.lines} /> : <Row label="No cost of sales" tone="indent muted" />}
              <Row label="Total cost of sales" value={pl.cost_of_sales.total} tone="subtotal" />
              <Row label="Gross profit" value={pl.gross_profit} tone="total" detail={pl.gross_margin_percent !== null ? `${pl.gross_margin_percent}% of revenue` : undefined} />
              {pl.other_income.lines.length > 0 && (
                <>
                  <Row label="Other income" tone="section" />
                  <Lines items={pl.other_income.lines} />
                  <Row label="Total other income" value={pl.other_income.total} tone="subtotal" />
                </>
              )}
              <Row label="Operating expenses" tone="section" />
              {pl.operating_expenses.lines.length ? <Lines items={pl.operating_expenses.lines} /> : <Row label="No expenses recorded" tone="indent muted" />}
              <Row label="Total operating expenses" value={pl.operating_expenses.total} tone="subtotal" />
              <Row label={Number(pl.net_profit) < 0 ? "Net loss" : "Net profit"} value={pl.net_profit} tone="grand" />
            </tbody>
          </table>
        </section>
        <section className="panel statement" aria-labelledby="bs-title">
          <h2 id="bs-title">Balance sheet</h2>
          <p className="statement-period">As of {bs.as_of}</p>
          <table>
            <tbody>
              <Row label="Assets" tone="section" />
              {bs.assets.sections.length ? bs.assets.sections.map((section) => (
                <React.Fragment key={section.key}>
                  <Row label={section.label} value={section.total} tone="group" />
                  {section.lines.length > 1 ? <Lines items={section.lines} /> : null}
                </React.Fragment>
              )) : <Row label="No assets" tone="indent muted" />}
              <Row label="Total assets" value={bs.assets.total} tone="total" />
              <Row label="Liabilities" tone="section" />
              {bs.liabilities.sections.length ? bs.liabilities.sections.map((section) => (
                <React.Fragment key={section.key}>
                  <Row label={section.label} value={section.total} tone="group" />
                  {section.lines.length > 1 ? <Lines items={section.lines} /> : null}
                </React.Fragment>
              )) : <Row label="No liabilities" tone="indent muted" />}
              <Row label="Total liabilities" value={bs.liabilities.total} tone="total" />
              <Row label="Equity" tone="section" />
              <Lines items={bs.equity.lines} />
              <Row label="Total equity" value={bs.equity.total} tone="total" />
              <Row label="Total liabilities and equity" value={bs.total_liabilities_and_equity} tone="grand" />
            </tbody>
          </table>
          <p className={`statement-check ${balanced ? "ok" : "bad"}`} role="status">
            {balanced ? "Balance sheet balances: assets equal liabilities plus equity." : `Out of balance by ${rupees(bs.difference)}. Contact support before relying on these figures.`}
          </p>
        </section>
      </div>
      <div className="info-box">
        {data.basis} Depreciation, net realisable value write-downs and accruals are not calculated; review with your accountant before using these statements for filing or lending.
      </div>
    </div>
  );
}
