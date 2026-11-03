import { currentPostingSession, assertPostingSession } from "./postingSession.js";
import { supportsFeature, supportedMasterData } from "./capabilities.js";
import {imageInput} from "./imageInput.js";
import React, { useState, useRef, useEffect } from "react";
import { X } from "lucide-react";

export default function MasterForm({ kind, close, save, record, features = [], editBlockReason = "", checkEditSupport, embedded = false, initialName = "", locked = false, notice = "" }) {
  const supported = feature => supportsFeature(features, feature);
  const isParty = kind === "party";
  const [form, setForm] = useState({
    party_type: "both",
    is_active: true,
    shipping_address: "",
    payment_terms_days: "",
    credit_limit: "",
    low_stock_threshold: "",
    gstin: "",
    address: "",
    phone: "",
    email: "",
    hsn: "",
    unit: "",
    sale_rate: "0",
    purchase_rate: "0",
    gst_rate: "0",
    track_stock: false,
    barcode: "",
    item_type: "goods",
    ...record?.data,
    name: record?.name || initialName,tax_treatment:record?.data?.tax_treatment || (Number(record?.data?.gst_rate||0)>0?"taxable":"nil_rated"),
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const originatingSession = useRef(currentPostingSession()).current;
  const nameInput = useRef(null);
  useEffect(() => { if (embedded) nameInput.current?.focus(); }, [embedded]);
  const dismiss = () => { if (!submitting.current && !busy && !locked) close(); };
  const update=event=>{const key=event.target.name,value=event.target.value;setForm(current=>({...current,[key]:value,...(embedded && key==="item_type" && value==="services"?{track_stock:false,low_stock_threshold:""}:{}),...(key==='gst_rate'?{tax_treatment:Number(value)>0?'taxable':current.tax_treatment==='taxable'?'nil_rated':current.tax_treatment}:key==='tax_treatment'&&value!=='taxable'?{gst_rate:'0'}:{})}))};
  async function submit(event) {
    event.preventDefault();
    if (submitting.current) return;
    if (record && editBlockReason) { setError(editBlockReason); return; }
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      // Editing includes archive/reactivate. Keep this mounted intent bound to
      // its original session without changing master compare-and-swap semantics.
      if (record) assertPostingSession(originatingSession);
      const data = isParty
        ? {
            party_type: form.party_type,
            is_active: form.is_active !== false,
            shipping_address: form.shipping_address,
            gstin: form.gstin,
            address: form.address,
            phone: form.phone,
            email: form.email,
            credit_limit: form.credit_limit === "" || form.credit_limit == null ? null : String(form.credit_limit),
            payment_terms_days: form.payment_terms_days === "" || form.payment_terms_days == null ? null : Number(form.payment_terms_days),
          }
        : {
            ...(form.image_data_url!==undefined?{image_data_url:form.image_data_url}:{}),image_thumbnail:form.image_thumbnail||"",
            is_active: form.is_active !== false,
            hsn: form.hsn,
            unit: form.unit,
            sale_rate: form.sale_rate,
            purchase_rate: form.purchase_rate,
            gst_rate: form.gst_rate,
            track_stock: form.track_stock,
            barcode: form.barcode,
            item_type: form.item_type,tax_treatment:form.tax_treatment,
            low_stock_threshold: form.low_stock_threshold !== "" && form.low_stock_threshold != null ? String(form.low_stock_threshold) : null,
          };
      await save({ kind, name: form.name, data: supportedMasterData(data, features) });
    } catch (err) {
      setError(err.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <div
      className={embedded ? "inline-party-form" : "overlay"}
      onMouseDown={(event) => !embedded && event.target === event.currentTarget && dismiss()}
    >
      <div
        className={embedded ? "" : "modal"}
        role={embedded ? "region" : "dialog"}
        aria-modal={embedded ? undefined : "true"}
        aria-label={embedded ? `Create ${isParty ? "party" : "item or service"} without leaving invoice` : "Entry form"}
        onKeyDown={event => {
          if (!embedded || event.key !== "Tab") return;
          const controls = [...event.currentTarget.querySelectorAll('button, input, select, textarea')].filter(control => !control.matches(':disabled'));
          const first = controls[0], last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }}
      >
        <div className="modal-heading">
          <div>
            <h2>
              {record ? "Edit" : "New"} {isParty ? "party" : "item"}
            </h2>
            <p>
              {record
                ? "Update details for this company."
                : "Add a reusable record to this company."}
            </p>
          </div>
          <button className="icon-button" aria-label="Close" onClick={dismiss} disabled={busy || locked}>
            <X size={18} />
          </button>
        </div>
        <form className="form-grid" onSubmit={submit}>
          <fieldset className="form-grid full submission-fields" disabled={busy || locked}>
          {!supported("master_lifecycle") && <p className="info-box full">Advanced master settings need an updated connected API. Core details can still be saved; unsupported settings will not be submitted.</p>}
          <label className="full">
            {isParty ? "Party name" : "Item name"}
            <input
              ref={nameInput}
              name="name"
              required
              maxLength="120"
              value={form.name}
              onChange={update}
              disabled={!!record}
            />
            {record && (
              <small>
                Names are fixed to preserve existing transaction links.
              </small>
            )}
          </label>
          {supported("master_lifecycle") && record && <label className="full"><span><input type="checkbox" checked={form.is_active !== false} onChange={event => setForm(current => ({ ...current, is_active: event.target.checked }))} /> Active for new transactions</span><small>Archive without deleting history. Existing invoices, balances and settlement remain available. Reactivate here any time.</small></label>}
          {isParty ? (
            <>
              <label>
                Party type
                <select
                  className="form-select"
                  name="party_type"
                  value={form.party_type}
                  onChange={update}
                >
                  <option value="both">Customer and supplier</option>
                  <option value="customer">Customer</option>
                  <option value="supplier">Supplier</option>
                </select>
              </label>
              <label>
                GSTIN
                <input
                  name="gstin"
                  maxLength="15"
                  value={form.gstin}
                  onChange={update}
                  placeholder="Optional"
                />
              </label>
              <label>
                Phone
                <input
                  name="phone"
                  type="tel"
                  maxLength="32"
                  value={form.phone}
                  onChange={update}
                />
              </label>
              <label>
                Email
                <input
                  name="email"
                  type="email"
                  maxLength="254"
                  value={form.email}
                  onChange={update}
                />
              </label>
              {supported("party_credit_limits") && <label className="full">Customer credit limit (₹)<input name="credit_limit" type="number" min="0" max="9999999999999.99" step="0.01" value={form.credit_limit ?? ""} onChange={update} placeholder="No limit warning" /><small>Optional advisory only; does not block saving. Zero warns for any positive customer exposure. Unused customer credits and advances reduce exposure, not supplier payables.</small></label>}
              {supported("party_payment_terms") && <label className="full">Default payment terms (days)<input name="payment_terms_days" type="number" min="0" max="3650" step="1" value={form.payment_terms_days ?? ""} onChange={update} placeholder="No default" /><small>Optional. Net 0 means due on the document date. Existing documents keep their saved due dates.</small></label>}
              {supported("party_shipping_address") && <label className="full">Default delivery address<input name="shipping_address" maxLength="500" value={form.shipping_address} onChange={update} placeholder="Same as billing address when blank" /><small>Copied into new documents only; saved document addresses stay unchanged.</small></label>}
              <label className="full">
                Billing address
                <input
                  name="address"
                  maxLength="500"
                  value={form.address}
                  onChange={update}
                />
              </label>
            </>
          ) : (
            <>
              {!embedded && <div className="full"><label>Item image<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setBusy(true);setError('');try{const [image,thumbnail]=await Promise.all([imageInput(file,600,64000),imageInput(file,160,15000)]);setForm(current=>({...current,image_data_url:image,image_thumbnail:thumbnail}))}catch(err){setError(err.message)}finally{setBusy(false);e.target.value=''}}}/></label>{(form.image_data_url||form.image_thumbnail)&&<><img src={form.image_data_url||form.image_thumbnail} alt="Item preview" style={{maxWidth:150,maxHeight:120}}/><button className="link" type="button" onClick={()=>setForm({...form,image_data_url:'',image_thumbnail:''})}>Remove item image</button></>}</div>}
              <label>
                Item type
                <select
                  className="form-select"
                  name="item_type"
                  value={form.item_type}
                  onChange={update}
                >
                  <option value="goods">Goods</option>
                  <option value="services">Services</option>
                </select>
              </label>
              <label>
                Barcode
                <input
                  name="barcode"
                  maxLength={80}
                  value={form.barcode}
                  onChange={update}
                />
              </label>
              <label>
                HSN / SAC
                <input
                  name="hsn"
                  maxLength="16"
                  value={form.hsn}
                  onChange={update}
                />
              </label>
              <label>
                Unit
                <input
                  name="unit"
                  maxLength="24"
                  value={form.unit}
                  onChange={update}
                  placeholder="e.g. pcs"
                />
              </label>
              <label>
                Sale rate (₹)
                <input
                  name="sale_rate"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.sale_rate}
                  onChange={update}
                />
              </label>
              <label>
                Purchase rate (₹)
                <input
                  name="purchase_rate"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.purchase_rate}
                  onChange={update}
                />
              </label>
              <label>GST treatment<select className="form-select" aria-label="Item GST treatment" name="tax_treatment" value={form.tax_treatment} onChange={update}><option value="taxable">Taxable</option><option value="nil_rated">Nil rated</option><option value="exempt">Exempt</option><option value="non_gst">Non-GST supply</option></select></label>
              <label>
                GST rate (%)
                <input
                  name="gst_rate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={form.gst_rate}
                  onChange={update}
                />
              </label>
              <label className="full stock-toggle">
                <input
                  type="checkbox"
                  checked={form.track_stock}
                  disabled={!!record || (embedded && form.item_type === "services")}
                  onChange={(event) =>
                    setForm({ ...form, track_stock: event.target.checked })
                  }
                />{" "}
                Track stock quantities for this item
                {record && " (fixed after creation)"}
                {embedded && form.item_type === "services" && <small>Services do not track stock. Stock tracking and any low-stock threshold are cleared.</small>}
              </label>
              {supported("low_stock_reorder") && ((form.track_stock && form.item_type !== "services") || (form.low_stock_threshold !== "" && form.low_stock_threshold != null)) && <label className="full">Low-stock threshold<input name="low_stock_threshold" type="number" min="0" step="0.001" value={form.low_stock_threshold ?? ""} onChange={update} placeholder="Disabled" /><small>Alerts when on-hand stock is at or below this quantity. Blank explicitly disables alerts. Clear this value before changing to a service or untracked item. Changing this never posts stock or accounting entries.</small></label>}

            </>
          )}
          {record && editBlockReason && <div className="info-box full" role="status"><p>{editBlockReason}</p>{checkEditSupport && <button type="button" className="button secondary" onClick={() => { setError(""); checkEditSupport(); }}>Check API support again</button>}</div>}
          </fieldset>
          {notice && <p className="info-box full" role="status">{notice}</p>}
          {error && <div className="error full" role="alert">{error}</div>}
          <div className="modal-actions full">
            <button type="button" className="button secondary" onClick={dismiss} disabled={busy || locked}>
              Cancel
            </button>
            <button className="button primary" disabled={busy || (!!record && !!editBlockReason)}>
              {busy ? "Saving…" : locked ? `Retry same ${isParty ? "party" : "item"} save` : embedded ? (isParty ? "Create and use party" : "Create item and add line") : `Save ${isParty ? "party" : "item"}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
