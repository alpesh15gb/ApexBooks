import React, { useEffect, useMemo, useRef, useState } from "react";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
const aliases = {
  date: ["date", "transactiondate", "txndate", "valuedate", "postingdate"],
  description: [
    "description",
    "narration",
    "particulars",
    "remarks",
    "details",
  ],
  reference: [
    "reference",
    "referenceno",
    "refno",
    "chequeno",
    "utr",
    "transactionid",
  ],
  amount: ["amount", "transactionamount", "netamount"],
  debit: ["debit", "withdrawal", "withdrawals", "debitamount", "withdrawalamt"],
  credit: ["credit", "deposit", "deposits", "creditamount", "depositamt"],
};
const normalize = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
function parse(text) {
  const candidates = ["\t", ";", ","],
    sample = text.split(/\r?\n/).slice(0, 20),
    score = (sep) =>
      Math.max(
        ...sample.map((line) => {
          const values = line.split(sep);
          return values.some((v) => aliases.date.includes(normalize(v)))
            ? values.length * 10
            : values.length;
        }),
      ),
    sep = candidates.sort((a, b) => score(b) - score(a))[0];
  let field = "",
    row = [],
    quoted = false;
  const rows = [];
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (quoted && text[i + 1] === '"') {
        field += '"';
        i++;
      } else quoted = !quoted;
    } else if (ch === sep && !quoted) {
      row.push(field);
      field = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      if (row.some((s) => s.trim())) rows.push(row);
      row = [];
      field = "";
    } else field += ch;
  }
  if (quoted) throw Error("CSV contains an unclosed quote");
  row.push(field);
  if (row.some((s) => s.trim())) rows.push(row);
  return rows.map((r) => r.map((s) => s.replace(/^\uFEFF/, "").trim()));
}
function amount(raw) {
  let value = (raw || "").replace(/[₹,\s]/g, "");
  if (!value) return "";
  if (/^\(.*\)$/.test(value)) value = "-" + value.slice(1, -1);
  const suffix = value.match(/(Cr|Dr)$/i);
  if (suffix) {
    value = value.slice(0, -2);
    if (suffix[1].toLowerCase() === "dr" && !value.startsWith("-"))
      value = "-" + value;
  }
  if (!/^[+-]?\d+(\.\d{1,2})?$/.test(value)) throw Error("invalid amount");
  return value;
}
function date(raw, format) {
  let y, m, d, parts;
  if ((parts = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/))) [, y, m, d] = parts;
  else if ((parts = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/))) {
    y = parts[3];
    d = parts[format === "dmy" ? 1 : 2];
    m = parts[format === "dmy" ? 2 : 1];
  } else if (
    (parts = raw.match(/^(\d{1,2})[- /]+([A-Za-z]{3,9})[- /,]+(\d{4})$/))
  ) {
    d = parts[1];
    y = parts[3];
    const names = [
      "january",
      "february",
      "march",
      "april",
      "may",
      "june",
      "july",
      "august",
      "september",
      "october",
      "november",
      "december",
    ];
    m =
      names.findIndex(
        (n) =>
          n === parts[2].toLowerCase() ||
          n.slice(0, 3) === parts[2].toLowerCase(),
      ) + 1;
  } else throw Error("invalid date");
  const value = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  if (
    value.getUTCFullYear() !== Number(y) ||
    value.getUTCMonth() + 1 !== Number(m) ||
    value.getUTCDate() !== Number(d)
  )
    throw Error("invalid date");
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
export default function StatementImportPreview({
  file,
  companyId,
  bankId,
  bankName,
  api,
  onClose,
  onImported,
}) {
  const [table, setTable] = useState([]),
    [header, setHeader] = useState(0),
    [mapping, setMapping] = useState({}),
    [format, setFormat] = useState("dmy"),
    [error, setError] = useState(""),
    [report, setReport] = useState(null),
    [busy, setBusy] = useState(false),
    [payload, setPayload] = useState(null);
  const processing = useRef(false);
  const posting = usePostingRequest();
  const locked = busy || posting.busy || posting.pending;
  const requestClose = () => { if (!processing.current && !posting.pending) onClose(); };
  useEffect(() => {
    let live = true;
    if (file.size > 5_000_000) { setError("CSV exceeds 5 MB"); return; }
    file
      .text()
      .then((text) => {
        if (!live) return;
        const rows = parse(text);
        if (rows.length > 5021)
          throw Error("Import up to 5,000 transactions per CSV");
        const firstHeader = rows.findIndex((row) =>
          row.some((v) => aliases.date.includes(normalize(v))),
        );
        setTable(rows);
        setHeader(Math.max(0, firstHeader));
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [file]);
  const headers = table[header] || [];
  useEffect(() => {
    const next = {};
    for (const [key, names] of Object.entries(aliases)) {
      const index = headers.findIndex((h) => names.includes(normalize(h)));
      next[key] = index < 0 ? "" : String(index);
    }
    setMapping(next);
    setReport(null);
  }, [header, table]);
  const parsed = useMemo(() => {
    try {
      if (
        mapping.date === "" ||
        mapping.description === "" ||
        (mapping.amount === "" &&
          (mapping.debit === "" || mapping.credit === ""))
      )
        return {
          error:
            "Map date, description and either amount or both debit and credit columns.",
        };
      const rows = table.slice(header + 1).map((cells, index) => {
        const get = (key) => cells[Number(mapping[key])]?.trim() || "";
        try {
          let value;
          if (mapping.amount !== "") value = amount(get("amount"));
          else {
            const debit = amount(get("debit")) || "0",
              credit = amount(get("credit")) || "0";
            if (
              Number(debit) < 0 ||
              Number(credit) < 0 ||
              (Number(debit) > 0 && Number(credit) > 0)
            )
              throw Error("use one positive debit or credit");
            value = Number(debit) > 0 ? "-" + debit : credit;
          }
          if (!value || Number(value) === 0)
            throw Error("amount is zero or empty");
          if (!get("description")) throw Error("description is empty");
          return {
            date: date(get("date"), format),
            description: get("description"),
            reference: mapping.reference === "" ? "" : get("reference"),
            amount: value,
          };
        } catch (e) {
          throw Error(`CSV row ${header + index + 2}: ${e.message}`);
        }
      });
      if (!rows.length || rows.length > 5000)
        throw Error("Choose a CSV containing 1–5,000 transactions");
      return { rows };
    } catch (e) {
      return { error: e.message };
    }
  }, [table, header, mapping, format]);
  async function validate() {
    if (processing.current || posting.pending) return;
    processing.current = true;
    setBusy(true);
    setError("");
    try {
      if (parsed.error) throw Error(parsed.error);
      const body = { bank_account_id: bankId, lines: parsed.rows };
      const value = await api(`/companies/${companyId}/bank-statement/import`, {
        method: "POST",
        body: JSON.stringify({ ...body, dry_run: true }),
      });
      setPayload(body);
      setReport(value);
    } catch (e) {
      setError(e.message);
    } finally {
      processing.current = false;
      setBusy(false);
    }
  }
  async function commit() {
    if (processing.current || !payload || !report) return;
    processing.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await posting.run(() => api(`/companies/${companyId}/bank-statement/import`, {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      if (!result) return;
      await onImported(result.value);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      processing.current = false;
      setBusy(false);
    }
  }
  return (
    <div className="overlay">
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Import bank statement"
      >
        <div className="modal-heading">
          <div>
            <h2>Import bank statement</h2>
            <p>
              {file.name} → {bankName}
            </p>
          </div>
          <button className="icon-button" aria-label="Close" onClick={requestClose} disabled={locked}>
            ×
          </button>
        </div>
        <div className="form-grid">
          <label>
            Header row
            <select
              className="form-select"
              aria-label="Header row"
              disabled={locked}
              value={header}
              onChange={(e) => setHeader(Number(e.target.value))}
            >
              {table.slice(0, 20).map((row, i) => (
                <option value={i} key={i}>
                  {i + 1}: {row.join(" · ").slice(0, 75)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Date format
            <select
              className="form-select"
              aria-label="Date format"
              disabled={locked}
              value={format}
              onChange={(e) => {
                setFormat(e.target.value);
                setReport(null);
              }}
            >
              <option value="dmy">DD/MM/YYYY (India)</option>
              <option value="mdy">MM/DD/YYYY</option>
            </select>
          </label>
          {Object.keys(aliases).map((key) => (
            <label key={key}>
              {key[0].toUpperCase() + key.slice(1)} column
              <select
                className="form-select"
                aria-label={`${key} column`}
                disabled={locked}
                value={mapping[key] ?? ""}
                onChange={(e) => {
                  setMapping({ ...mapping, [key]: e.target.value });
                  setReport(null);
                }}
              >
                <option value="">Not mapped</option>
                {headers.map((h, i) => (
                  <option value={i} key={i}>
                    {i + 1} · {h}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <p className="full">
            Amount uses positive values for receipts and negative values for
            payments. With separate debit/credit columns, debit is paid and
            credit is received. ISO and dates such as 31-Oct-2026 are also
            supported.
          </p>
          {parsed.rows && (
            <div className="table-wrap full">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Description</th>
                    <th>Reference</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.rows.slice(0, 20).map((r, i) => (
                    <tr key={i}>
                      <td>{r.date}</td>
                      <td>{r.description}</td>
                      <td>{r.reference}</td>
                      <td>{r.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <small>
                Showing {Math.min(parsed.rows.length, 20)} of{" "}
                {parsed.rows.length} rows.
              </small>
            </div>
          )}
          {parsed.error && <p className="error full">{parsed.error}</p>}
          {report && (
            <div className="info-box full">
              {report.added} new transactions · {report.duplicates} duplicates
              will be skipped.
            </div>
          )}
          {error && (
            <div className="error full" role="alert">
              {error}
            </div>
          )}
          {posting.pending && !busy && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
          <div className="modal-actions full">
            <button
              className="button secondary"
              onClick={requestClose}
              disabled={locked}
            >
              Cancel
            </button>
            {report ? (
              <button
                className="button primary"
                onClick={commit}
                disabled={busy || posting.busy || !report.added}
              >
                {busy ? "Importing…" : posting.pending ? "Retry same import" : `Import ${report.added} transactions`}
              </button>
            ) : (
              <button
                className="button primary"
                onClick={validate}
                disabled={busy || !!parsed.error}
              >
                {busy ? "Validating…" : "Validate mapped rows"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
