import React from "react";
const money = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(value || 0),
  );
export default function GstReturnView({ data }) {
  const info = data.export_info;
  const tables = data.return_tables || [
    {
      name: "Register",
      title: data.title,
      headers: data.columns.map((c) => c.label),
      rows: data.rows.map((row) => data.columns.map((c) => row[c.key])),
      money_columns: data.columns.flatMap((c, i) =>
        [
          "taxable",
          "cgst",
          "sgst",
          "igst",
          "total",
          "proposed_itc",
          "ineligible",
        ].includes(c.key)
          ? [i]
          : [],
      ),
    },
  ];
  return (
    <>
      <div className="summary-grid">
        <div className="summary-card">
          <small>OUTPUT GST</small>
          <strong>
            {money(
              Object.values(data.output).reduce((s, v) => s + Number(v), 0),
            )}
          </strong>
        </div>
        <div className="summary-card">
          <small>INPUT FROM ENTERED BILLS</small>
          <strong>
            {money(
              Object.values(data.book_itc).reduce((s, v) => s + Number(v), 0),
            )}
          </strong>
        </div>
        <div className="summary-card">
          <small>ESTIMATED CASH PAYABLE</small>
          <strong>{money(data.cash_total)}</strong>
        </div>
      </div>
      {info && (
        <section className="panel settings-panel">
          <h2>Export format & preparation checks</h2>
          <p>
            {data.standard === "GSTR-1"
              ? `Section worksheets follow GSTN ${info.template}. Review the XLSX or draft JSON in the current offline tool before upload.`
              : data.standard === "GSTR-2A"
                ? "Purchase-book workbook: supplier bills, buyer-issued purchase returns and unregistered suppliers. Supplier filing details need the portal GSTR-2A."
                : "Numbered 3B schedules with a separate book estimate. Blank fields require external records; they do not mean zero."}
          </p>
          {!!info.issues.length && (
            <details>
              <summary>
                {info.issues.length} preparation{" "}
                {info.issues.length === 1 ? "check" : "checks"}
                {data.standard === "GSTR-1"
                  ? " · JSON unavailable until resolved"
                  : " · review before use"}
              </summary>
              <ul>
                {info.issues.map((item, i) => (
                  <li key={i}>
                    <strong>{item.document}:</strong> {item.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details>
            <summary>Included schedules & review notes</summary>
            <p>
              {info.schedules.map((s) => `${s.name} (${s.rows})`).join(" · ")}
            </p>
            <ul>
              {info.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </details>
        </section>
      )}
      {tables.map((table) => (
        <section className="panel register" key={table.name}>
          <div className="panel-header">
            <h2>{table.title}</h2>
          </div>
          <div className="table-wrap" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  {table.headers.map((h, i) => (
                    <th key={i}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((value, j) => (
                      <td key={j}>
                        {value == null
                          ? "Needs review"
                          : table.money_columns.includes(j)
                            ? money(value)
                            : value}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {!table.rows.length && <p>No applicable entries in this period.</p>}
          </div>
        </section>
      ))}
      <p className="info-box">{data.note}</p>
      {!!data.hsn.length && (
        <section className="panel settings-panel">
          <h2>HSN / SAC summary</h2>
          <div className="table-wrap" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>HSN/SAC</th>
                  <th>Rate</th>
                  <th>Qty</th>
                  <th>Base</th>
                  <th>GST</th>
                </tr>
              </thead>
              <tbody>
                {data.hsn.map((r, i) => (
                  <tr key={i}>
                    <td>{r.hsn || "Not entered"}</td>
                    <td>{r.rate}%</td>
                    <td>{r.quantity}</td>
                    <td>{money(r.taxable)}</td>
                    <td>{money(r.tax)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
