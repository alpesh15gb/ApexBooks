import { supportsFeature, supportedMasterData } from "./capabilities.js";
import {imageInput} from "./imageInput.js";
import React, { useEffect, useRef, useState } from "react";
import { registerPostingRequest } from "./postingRegistry.js";
import { X } from "lucide-react";

export default function MasterForm({ kind, close: onClose, save, record, features = [], readOnly = false }) {
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
    name: record?.name || "",tax_treatment:record?.data?.tax_treatment || (Number(record?.data?.gst_rate||0)>0?"taxable":"nil_rated"),
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const operation = useRef({ busy: false });
  const discardTrigger = useRef(null);
  const keepEditingButton = useRef(null);
  useEffect(() => registerPostingRequest(operation.current), []);
  useEffect(() => {
    if (discard) keepEditingButton.current?.focus();
  }, [discard]);
  useEffect(() => {
    const warn = event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function close() {
    if (operation.current.busy) return;
    if (discard) { keepEditing(); return; }
    if (dirty) {
      discardTrigger.current = document.activeElement;
      setDiscard(true);
    } else onClose();
  }
  function keepEditing() {
    setDiscard(false);
    if (discardTrigger.current?.isConnected) discardTrigger.current.focus();
  }
  const update=event=>{const key=event.target.name,value=event.target.value;setForm(current=>({...current,[key]:value,...(key==='gst_rate'?{tax_treatment:Number(value)>0?'taxable':current.tax_treatment==='taxable'?'nil_rated':current.tax_treatment}:key==='tax_treatment'&&value!=='taxable'?{gst_rate:'0'}:{})}))};
  async function submit(event) {
    event.preventDefault();
    if (readOnly) { setError("You have read-only access. Your draft is preserved; ask the owner for editor access before saving."); return; }
    if (operation.current.busy) return;
    if (!form.name.trim()) { setError(`Enter a ${isParty ? "party" : "item"} name.`); return; }
    if (!isParty && form.track_stock && form.item_type === 'services' && !(record?.data?.track_stock && record?.data?.item_type === 'services')) { setError('Stock tracking is supported for goods only. Turn off stock tracking for a new service, or keep this tracked item as goods.'); return; }
    operation.current.busy = true;
    setBusy(true);
    setError("");
    try {
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
      await save({ kind, name: form.name.trim(), data: supportedMasterData(data, features) });
    } catch (err) {
      setError(err.message);
    } finally {
      operation.current.busy = false;
      setBusy(false);
    }
  }
  return (
    <div
      className="overlay"
      onMouseDown={(event) => event.target === event.currentTarget && close()}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${record ? "Edit" : "New"} ${isParty ? "party" : "item"}`}
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
          <button className="icon-button" aria-label="Close" disabled={busy} onClick={close}>
            <X size={18} />
          </button>
        </div>
        {readOnly && <p className="info-box">Read-only access: your draft is preserved, but saving requires editor access.</p>}
        <form className="form-grid" onSubmit={submit} onChangeCapture={() => setDirty(true)} aria-busy={busy}>
          {discard && <div className="info-box full" role="alert"><strong>Discard unsaved changes?</strong><p>Your {isParty ? "party" : "item"} details have not been saved.</p><div className="modal-actions"><button ref={keepEditingButton} type="button" className="button secondary" onClick={keepEditing}>Keep editing</button><button type="button" className="button danger-outline" onClick={onClose}>Discard changes</button></div></div>}
          <fieldset className="form-grid full submission-fields" disabled={busy || readOnly}>
          {!supported("master_lifecycle") && <p className="info-box full">Advanced master settings need an updated connected API. Core details can still be saved; unsupported settings will not be submitted.</p>}
          <label className="full">
            {isParty ? "Party name" : "Item name"}
            <input
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
              <div className="full"><label>Item image<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy || readOnly} onChange={async e=>{const file=e.target.files?.[0];if(!file || operation.current.busy)return;operation.current.busy=true;setBusy(true);setError('');try{const [image,thumbnail]=await Promise.all([imageInput(file,600,64000),imageInput(file,160,15000)]);setForm(current=>({...current,image_data_url:image,image_thumbnail:thumbnail}))}catch(err){setError(err.message)}finally{operation.current.busy=false;setBusy(false);e.target.value=''}}}/></label>{(form.image_data_url||form.image_thumbnail)&&<><img src={form.image_data_url||form.image_thumbnail} alt="Item preview" style={{maxWidth:150,maxHeight:120}}/><button className="link" type="button" onClick={()=>{setDirty(true);setForm({...form,image_data_url:'',image_thumbnail:''});}}>Remove item image</button></>}</div>
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
                  disabled={!!record || (form.item_type === "services" && !form.track_stock)}
                  onChange={(event) =>
                    setForm({ ...form, track_stock: event.target.checked })
                  }
                />{" "}
                Track stock quantities for this item
                {record && " (fixed after creation)"}
                {form.item_type === "services" && <small>Inventory tracking is supported for goods only. Existing service stock history requires review; it is not changed here.</small>}
              </label>
              {supported("low_stock_reorder") && ((form.track_stock && form.item_type !== "services") || (form.low_stock_threshold !== "" && form.low_stock_threshold != null)) && <label className="full">Low-stock threshold<input name="low_stock_threshold" type="number" min="0" step="0.001" value={form.low_stock_threshold ?? ""} onChange={update} placeholder="Disabled" /><small>Alerts when on-hand stock is at or below this quantity. Blank explicitly disables alerts. Clear this value before changing to a service or untracked item. Changing this never posts stock or accounting entries.</small></label>}

            </>
          )}
          </fieldset>
          {error && <div className="error full" role="alert">{error}</div>}
          <div className="modal-actions full">
            <button type="button" className="button secondary" onClick={close} disabled={busy}>
              Cancel
            </button>
            <button className="button primary" disabled={busy || readOnly}>
              {busy ? "Saving…" : `Save ${isParty ? "party" : "item"}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
