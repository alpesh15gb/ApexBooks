import React, { useEffect, useMemo, useRef, useState } from "react";
import { decodeMasterCsv } from "./masterCsv.js";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
import {captureCompanyAccess} from "./companyAccess.js";
import {bankImportActor, bankImportStore, bankImportHash} from "./bankImportRecovery.js";
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
  text = text.replace(/^\uFEFF/, "");
  let field = "", row = [], quoted = false, closed = false, line = 1;
  const rows = [];
  const cell = () => { row.push(field); field = ""; closed = false; };
  const finish = () => { cell(); if (row.some(value => value.trim())) rows.push(row); row = []; };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else { quoted = false; closed = true; }
      } else { field += ch; if (ch === "\n" || (ch === "\r" && text[i + 1] !== "\n")) line++; }
      continue;
    }
    if (ch === sep) { cell(); continue; }
    if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      finish(); line++; continue;
    }
    if (closed) { if (ch === " " || ch === "\t") continue; throw Error(`CSV row ${line}: unexpected text after a closing quote.`); }
    if (ch === '"') { if (field.length) throw Error(`CSV row ${line}: quote must begin a field.`); quoted = true; }
    else field += ch;
  }
  if (quoted) throw Error(`CSV row ${line}: unclosed quoted field.`);
  finish();
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
  role,
  receiptSupport = false,
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
  const [marker, setMarker] = useState(null), [recoveryFault, setRecoveryFault] = useState(""),
    [confirmed, setConfirmed] = useState(null);
  const receiptRef = useRef(null), frozen = useRef(null);
  const access = useRef({role, receiptSupport});
  if (access.current.role !== role || access.current.receiptSupport !== receiptSupport) access.current = {role, receiptSupport};
  const store = () => bankImportStore(companyId, localStorage.token);
  useEffect(() => {
    frozen.current = null; setConfirmed(null);
    try {
      const saved = receiptSupport || bankImportActor(localStorage.token) ? store().read() : null;
      receiptRef.current = saved; setMarker(saved); setRecoveryFault("");
    } catch (failure) { setRecoveryFault(failure.message); }
  }, [companyId]);
  const canWrite = ["owner", "editor"].includes(role);
  const writeAccess = useRef(canWrite); writeAccess.current = canWrite;
  const processing = useRef(false);
  const context = useRef({file, companyId, bankId});
  if (context.current.file !== file || context.current.companyId !== companyId || context.current.bankId !== bankId) context.current = {file, companyId, bankId};
  const reviewedContext = useRef(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const posting = usePostingRequest();
  const locked = busy || posting.busy || posting.pending || !!confirmed || (!!marker && !!frozen.current);
  const requestClose = () => { if (!processing.current && !posting.pending && !receiptRef.current) onClose(); };
  useEffect(() => {
    let live = true;
    reviewedContext.current = null; frozen.current=null; setTable([]); setReport(null); setPayload(null); setError("");
    if (file.size > 5_000_000) { setError("CSV exceeds 5 MB"); return; }
    file
      .arrayBuffer()
      .then((bytes) => {
        if (!live) return;
        const rows = parse(decodeMasterCsv(bytes));
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
  }, [file, companyId, bankId]);
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
    if (!writeAccess.current || processing.current || posting.pending || confirmed || recoveryFault) return;
    const owner = context.current, current = capture();
    processing.current = true;
    setBusy(true);
    setError("");
    try {
      if (parsed.error) throw Error(parsed.error);
      if(!current())return;
      const body = { bank_account_id: bankId, lines: parsed.rows };
      if (receiptRef.current) {
        if (!receiptSupport) throw Error("Reconnect to a server supporting bank import receipts before recovering this import.");
        const hash = await bankImportHash(body);
        if (!current()) return;
        if (hash !== receiptRef.current.hash) throw Error("The bank or mapped rows do not match the original import. Select the original CSV, bank and mapping.");
        frozen.current = body; reviewedContext.current = owner; setPayload(body); setReport({added:body.lines.length,duplicates:0});
        return;
      }
      const value = await api(`/companies/${companyId}/bank-statement/import`, {
        method: "POST",
        body: JSON.stringify({ ...body, dry_run: true }),
      });
      if (!current()) return;
      reviewedContext.current = owner;
      setPayload(body);
      setReport(value);
    } catch (e) {
      if (current()) setError(e.message);
    } finally {
      processing.current = false;
      setBusy(false);
    }
  }
  function capture() {
    const owner = context.current, permission = access.current, token = localStorage.token;
    let accessStamp;
    try {accessStamp=captureCompanyAccess(`/api/companies/${companyId}/bank-statement`);} catch {return ()=>false;}
    return () => {
      try {accessStamp?.verify();} catch {return false;}
      return mounted.current && context.current === owner && access.current === permission && localStorage.token === token;
    };
  }
  async function finish(result, current) {
    setConfirmed(result); setReport(null); setPayload(null);
    await onImported(result);
    if (current()) onClose();
  }
  async function refreshConfirmed() {
    if (processing.current || !confirmed) return;
    const current=capture(); processing.current=true; setBusy(true); setError("");
    try { if(!current())return; await onImported(confirmed); if(current()) onClose(); }
    catch(failure) { if(current())setError(failure.message); }
    finally {processing.current=false;setBusy(false);}
  }
  async function checkReceipt() {
    if (!writeAccess.current || processing.current || !receiptRef.current || !receiptSupport) return;
    const current=capture(), original=receiptRef.current, recoveryStore=store();
    processing.current=true;setBusy(true);setError("");
    try {
      if(!current())return;
      const result=await api(`/companies/${companyId}/bank-statement/import-receipts/${encodeURIComponent(original.key)}`);
      if(!current())return;
      if(result.operation_key!==original.key)throw Error("Unexpected receipt. The original import remains unresolved.");
      recoveryStore.clear(original.key);receiptRef.current=null;setMarker(null);frozen.current=null;
      await finish(result,current);
    } catch(failure) {if(current())setError(failure.status===404 ? "No confirmed receipt found. This does not prove failure; keep the reference and verify the original file before retrying." : failure.message);}
    finally{processing.current=false;setBusy(false);}
  }
  async function commit() {
    if (!writeAccess.current || processing.current || confirmed || recoveryFault || !payload || !report || reviewedContext.current !== context.current) return;
    if(receiptRef.current && (!receiptSupport || !frozen.current))return;
    const current=capture(), retrying=!!receiptRef.current;
    let original=receiptRef.current, recoveryStore;
    processing.current = true; setBusy(true); setError("");
    try {
      const body=frozen.current || payload;
      if(receiptSupport) {
        recoveryStore=store();
        if(!original) {
          original={key:crypto.randomUUID(),hash:await bankImportHash(body)};
          if(!current())return;
          recoveryStore.save(original); receiptRef.current=original;setMarker(original);frozen.current=body;
        }
      }
      if(!current())return;
      let value;
      if(original) value=await api(`/companies/${companyId}/bank-statement/import`,{method:"POST",headers:{"Idempotency-Key":original.key},body:JSON.stringify(body)});
      else {const result=await posting.run(()=>api(`/companies/${companyId}/bank-statement/import`,{method:"POST",body:JSON.stringify(body)}));if(!result)return;value=result.value;}
      if(!current())return;
      if(original) {
        if(value.operation_key!==original.key)throw Error("The server did not confirm the original receipt. Keep the reference and check the import.");
        recoveryStore.clear(original.key);receiptRef.current=null;setMarker(null);frozen.current=null;
      }
      await finish(value,current);
    } catch(failure) {
      if(current()) {
        if(original && !retrying && failure.status>=400 && failure.status<500 && ![408,409].includes(failure.status)) {
          try{recoveryStore?.clear(original.key);receiptRef.current=null;setMarker(null);frozen.current=null;}catch{/* Retain uncertainty on storage failure. */}
        }
        setError(failure.message);
      }
    } finally {processing.current=false;setBusy(false);}
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
          <button className="icon-button" aria-label="Close" onClick={requestClose} disabled={locked || !!marker}>
            ×
          </button>
        </div>
        {!canWrite && <p className="info-box" role="status">Read-only access. Your reviewed statement is preserved; an owner or editor is required to import.</p>}
        {!receiptSupport && <p>Exact bank-import receipts are unavailable on this server. Legacy retries deduplicate rows but do not recover the original result.</p>}
        {recoveryFault && <p role="alert">{recoveryFault}</p>}
        {marker && <div role="status" className="info-box">Original import unconfirmed. Recovery reference: <code>{marker.key}</code>. Only the reference and a fingerprint are retained in this tab, not statement contents. Reload can recover the receipt; closing the tab may lose the reference. Do not start another import.
          <button disabled={busy || !canWrite || !receiptSupport} onClick={checkReceipt}>Check original import</button>
          <p>To retry, select the original bank, CSV and mapping, then validate them.</p>
        </div>}
        {confirmed && <div role="status" className="info-box">Import confirmed: {confirmed.added} added, {confirmed.duplicates} duplicates. Do not import again.
          <button disabled={busy} onClick={refreshConfirmed}>Refresh imported transactions</button>
        </div>}
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
                setReport(null); frozen.current=null;
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
                  setReport(null); frozen.current=null;
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
          {parsed.error && <p className="error full" role="alert">{parsed.error}</p>}
          {report && (
            <div className="info-box full">
              {marker ? "Original bank and mapped rows verified. Retry uses the original operation key; counts will come from its receipt." : `${report.added} new transactions · ${report.duplicates} duplicates will be skipped.`}
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
              disabled={locked || !!marker}
            >
              Cancel
            </button>
            {confirmed ? null : report ? (
              <button
                className="button primary"
                onClick={commit}
                disabled={!canWrite || busy || posting.busy || !report.added || !!recoveryFault || (!!marker && !receiptSupport)}
              >
                {busy ? "Importing…" : marker ? "Retry original import" : posting.pending ? "Retry same import" : `Import ${report.added} transactions`}
              </button>
            ) : (
              <button
                className="button primary"
                onClick={validate}
                disabled={!canWrite || busy || !!parsed.error || !!recoveryFault || (!!marker && !receiptSupport)}
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
