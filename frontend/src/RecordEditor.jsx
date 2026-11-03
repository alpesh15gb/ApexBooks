import { sourceInputTaxSummary } from "./purchaseReturnGuidance.js";
import { captureConversionSource, conversionBlockReason, isDefiniteConversionConflict } from "./conversionRevision.js";
import InlineItemForm from "./InlineItemForm.jsx";
import InlinePartyForm from "./InlinePartyForm.jsx";
import { changeLineDiscount, serializeLineDiscount, lineDiscountMode } from "./lineDiscount.js";
import { supportsFeature } from "./capabilities.js";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
import { purchaseDraftForm } from "./purchaseDraft.js";
import { linkCatalogueItem, OCR_LINE } from "./itemLink.js";
import {
  DocumentIdentity,
  DocumentItems,
  DocumentTotals,
  useDocumentPreview,
} from "./DocumentWorkbench.jsx";
import { prepareInvoiceImage } from "./prepareInvoiceImage.js";
import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from "react";
import { availableMasters, partyShippingAddress, shippingForPartySelection } from "./masterLifecycle.js";
import CreditStatus from "./CreditStatus.jsx";
import PriceHistory from "./PriceHistory.jsx";
import PaymentAllocations from "./PaymentAllocations.jsx";
export default function RecordEditor({
  kind,
  features = [],
  capabilities,
  onRetryCapabilities,
  company,
  companyId,
  records,
  source,
  relatedSource,
  draftSeed,
  close,
  save,
  createParty,
  createItem,
  api,
  Modal,
  labels,
  documentKinds,
  money,
  today,
  edit = false,
}) {
  const conversion = useRef(captureConversionSource(source, edit)).current;
  const [conversionRejected, setConversionRejected] = useState("");
  const conversionBlocked = conversionRejected || conversionBlockReason(conversion, capabilities, features);
  const supported = feature => supportsFeature(features, feature);
  const termsSupported = supported("party_payment_terms");
  const doc = documentKinds.includes(kind),
    party = kind === "party",
    item = kind === "item",
    purchase = [
      "purchase_bill",
      "purchase_order",
      "debit_note",
      "expense",
    ].includes(kind),
    showTax = company.tax_mode === "regular" || purchase;
  const initial = source || relatedSource || draftSeed;
  const [priceLine, setPriceLine] = useState(null), [termsSuggestion, setTermsSuggestion] = useState(null), [termsError, setTermsError] = useState("");
  const lastShippingDefault = useRef("");
  const [inlineParty, setInlineParty] = useState(false);
  const [partyLocked, setPartyLocked] = useState(false);
  const [createdParties, setCreatedParties] = useState([]);
  const partyButton = useRef(null);
  const partyLockRef = useRef(false);
  const updatePartyLock = useCallback(value => { partyLockRef.current = value; setPartyLocked(value); }, []);
  const dismissParty = () => {
    if (partyLockRef.current) return;
    setInlineParty(false);
    setTimeout(() => partyButton.current?.focus(), 0);
  };
  const [inlineItem, setInlineItem] = useState(false);
  const [itemLocked, setItemLocked] = useState(false);
  const [createdItems, setCreatedItems] = useState([]);
  const [itemAdded, setItemAdded] = useState("");
  const itemButton = useRef(null);
  const itemFocusTarget = useRef(null);
  useLayoutEffect(() => {
    if (inlineItem || !itemFocusTarget.current) return;
    // The invoice is visible and its new line is committed before focus moves.
    // A timer can run before React commits, focusing a hidden or obsolete field.
    const target = itemFocusTarget.current;
    itemFocusTarget.current = null;
    if (target === "quantity") {
      const quantities = itemButton.current?.form?.querySelectorAll('.document-item-row [name="quantity"]');
      quantities?.[quantities.length - 1]?.focus();
    } else {
      itemButton.current?.focus();
    }
  }, [inlineItem]);
  const itemLockRef = useRef(false);
  const updateItemLock = useCallback(value => { itemLockRef.current = value; setItemLocked(value); }, []);
  const dismissItem = () => {
    if (itemLockRef.current) return;
    itemFocusTarget.current = "trigger";
    setInlineItem(false);
  };
  const retainedParties = edit || relatedSource ? [initial?.data?.party_id].filter(Boolean) : [];
  const retainedItems = edit || relatedSource ? (initial?.data?.lines || []).map(line => line.item_id).filter(Boolean) : [];
  const partyChoices = availableMasters([...records, ...createdParties.filter(row => !records.some(record => record.id === row.id))], "party", ["payment_in", "payment_out"].includes(kind) ? records.filter(record => record.kind === "party").map(record => record.id) : retainedParties);
  const itemChoices = availableMasters([...records, ...createdItems.filter(row => !records.some(record => record.id === row.id))], "item", retainedItems);
  const canWrite = ["owner", "editor"].includes(company.role);
  const isPayment = ["payment_in", "payment_out"].includes(kind);
  const [dirty, setDirty] = useState(false),
    [confirmClose, setConfirmClose] = useState(false);
  const requestClose = () => {
    if (inlineParty) { dismissParty(); return; }
    if (inlineItem) { dismissItem(); return; }
    if (saving || scanning || pending) return;
    if (dirty) setConfirmClose(true);
    else close();
  };
  const [advance, setAdvance] = useState(!!(edit && source?.data?.is_advance));
  const [paymentRows, setPaymentRows] = useState([
    ...(edit && !source?.data?.is_advance
      ? source?.allocations ||
        source?.data?.allocations ||
        (source?.data?.applied_to
          ? [
              {
                document_id: source.data.applied_to,
                amount: String(source.amount),
              },
            ]
          : [{ document_id: "", amount: "" }])
      : relatedSource && isPayment
        ? [{ document_id: relatedSource.id, amount: String(relatedSource.outstanding || "") }]
        : [{ document_id: "", amount: "" }]),
  ]);
  const appliesTo = {
    payment_in: "sales_invoice",
    credit_note: "sales_invoice",
    payment_out: "purchase_bill",
    debit_note: "purchase_bill",
  }[kind];
  const targets = records
    .filter(
      (r) =>
        (r.kind === appliesTo ||
          (kind === "credit_note" && r.kind === "pos") ||
          (isPayment &&
            r.kind ===
              (kind === "payment_in"
                ? "opening_receivable"
                : "opening_payable"))) &&
        r.posted &&
        (!isPayment ||
          Number(r.outstanding) > 0 ||
          (edit && paymentRows.some((row) => row.document_id === r.id))),
    )
    .map((r) =>
      isPayment && edit
        ? {
            ...r,
            outstanding:
              Number(r.outstanding || 0) +
              (source?.allocations || source?.data?.allocations || [])
                .filter((row) => row.document_id === r.id)
                .reduce((a, row) => a + Number(row.amount || 0), 0),
          }
        : r,
    );
  const emptyLine = () => ({
    description: "",
    item_id: "",
    hsn: "",
    quantity: "1",
    rate: "",
    discount_percent: "0",
    gst_rate: company.tax_mode === "regular" ? "18" : "0",
    tax_treatment: "taxable",
    itc_treatment: "pending_review",
  });
  const [form, setForm] = useState({
      name: initial?.name || "",
      number: edit ? initial?.number || "" : "",
      date: edit ? initial?.date || today() : today(),
      due_date: initial?.data?.due_date || "",
      notes: initial?.data?.notes || "",
      terms: initial?.data?.terms || "",
      document_discount_percent: initial?.data?.document_discount_percent || "0",
      round_total: initial?.data?.round_total || false,
      return_stock: true,
      category: initial?.data?.category || "General",
      supplier_state:
        initial?.data?.supplier_state ||
        initial?.data?.party_gstin?.slice(0, 2) ||
        company.state_code,
      advance_supply: "",
      advance_gst_rate: "18",
      amount: edit ? String(initial?.amount || "") : isPayment && relatedSource ? String(relatedSource.outstanding || "") : "",
      tender_amount: initial?.data?.tender_amount || "",
      place_of_supply: initial?.data?.place_of_supply || company.state_code,
      applied_to: edit ? initial?.data?.applied_to || "" : !isPayment && relatedSource ? relatedSource.id : "",
      payment_account: edit ? initial?.data?.payment_account || "cash" : "cash",
      bank_account_id: edit
        ? initial?.data?.bank_account_id || "default"
        : "default",
      party_id: initial?.data?.party_id || "",
      party_address: initial?.data?.party_address || "",
      party_phone: initial?.data?.party_phone || "",
      shipping_address: initial?.data?.shipping_address || "",
      party_gstin: initial?.data?.party_gstin || "",
    }),
    [lines, setLines] = useState(
      initial?.data?.lines?.map((line) => ({
        ...line,
        description: line.description || "",
        item_id: line.item_id || "",
        hsn: line.hsn || "",
        quantity: String(line.quantity || "1"),
        rate: String(line.rate || ""),
        discount_percent: String(line.discount_percent || "0"),
        gst_rate: String(line.gst_rate || "0"),
        tax_treatment: line.tax_treatment || "taxable",
        itc_treatment: line.itc_treatment || "pending_review",
      })) || [emptyLine()],
    ),
    [error, setError] = useState(""),
    [scanning, setScanning] = useState(false);
  const [reviewedReturnDiscounts, setReviewedReturnDiscounts] = useState("");
  const [sourceInputTax, setSourceInputTax] = useState(() => !edit && kind === "debit_note" ? sourceInputTaxSummary(initial?.data?.lines) : "");
  const requiresDiscountReview = !edit && ["credit_note", "debit_note"].includes(kind) && !!form.applied_to && lines.some(line => lineDiscountMode(line) === "amount" && Number(line.discount_amount) > 0);
  const returnDiscountReviewKey = JSON.stringify([form.applied_to, lines.map(line => [line.item_id, line.description, line.quantity, line.rate, line.discount_amount, line.discount_percent])]);
  const [bankAccounts, setBankAccounts] = useState([
    { id: "default", name: "Bank clearing (legacy)" },
  ]);
  useEffect(() => {
    let active = true;
    api(`/companies/${companyId}/bank-accounts`)
      .then((rows) => {
        if (active) setBankAccounts(rows);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [companyId]);
  const [ocrStatus, setOcrStatus] = useState(null);
  const [ocrTotal, setOcrTotal] = useState("");
  const [sourcePreview, setSourcePreview] = useState("");
  useEffect(
    () => () => {
      if (sourcePreview) URL.revokeObjectURL(sourcePreview);
    },
    [sourcePreview],
  );
  useEffect(() => {
    if (kind !== "purchase_bill") return;
    let active = true;
    api("/ocr/status")
      .then((status) => {
        if (active) setOcrStatus(status);
      })
      .catch(() => {
        if (active)
          setOcrStatus({
            ready: false,
            message: "OCR status could not be checked",
          });
      });
    return () => {
      active = false;
    };
  }, [kind]);
  const saveAction = useRef("close");
  const [submissionKey] = useState(() => crypto.randomUUID());
  const posting = usePostingRequest({ isDefinitiveRetryError: error => !!conversion && isDefiniteConversionConflict(error) });
  const { busy: saving, pending } = posting;
  useEffect(() => {
    const unload = event => {
      if (dirty || saving || pending || partyLocked || itemLocked) { event.preventDefault(); event.returnValue = ""; }
    };
    const back = () => requestClose();
    window.addEventListener("beforeunload", unload);
    window.addEventListener("apex-close-editor", back);
    return () => { window.removeEventListener("beforeunload", unload); window.removeEventListener("apex-close-editor", back); };
  }, [dirty, saving, pending, scanning, inlineParty, partyLocked, inlineItem, itemLocked]);

  async function scan(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setScanning(true);
    setDirty(true);
    try {
      const image = await prepareInvoiceImage(file);
      setSourcePreview(URL.createObjectURL(file));
      const result = await api(`/companies/${companyId}/ocr/purchase-draft`, {
        method: "POST",
        body: JSON.stringify({ image_data_url: image }),
      });
      const d = result.draft;
      setOcrTotal(d.total || "");
      setForm((current) =>
        purchaseDraftForm(current, d, company.state_code, today()),
      );
      if (d.items?.length)
        setLines(
          d.items.map((item) => ({
            [OCR_LINE]: true,
            description: item.description || "",
            item_id: "",
            hsn: item.hsn || "",
            quantity: item.quantity || "1",
            rate: item.rate ?? "",
            discount_percent: "0",
            gst_rate: item.gst_rate || "0",
            tax_treatment: "taxable",
            itc_treatment: "pending_review",
          })),
        );
    } catch (err) {
      setError(err.message);
    } finally {
      setScanning(false);
      e.target.value = "";
    }
  }
  useEffect(() => {
    let active = true; setTermsSuggestion(null); setTermsError("");
    if (termsSupported && form.party_id && form.date && ["sales_invoice", "purchase_bill"].includes(kind)) {
      api(`/companies/${companyId}/parties/${form.party_id}/due-date?document_date=${form.date}`)
        .then(result => { if (active) setTermsSuggestion(result); }).catch(reason => { if (active) setTermsError(reason.message); });
    }
    return () => { active = false; };
  }, [companyId, form.party_id, form.date, kind, termsSupported]);
  const change = (e) => {
    const value = e.target.value;
    const matched =
      e.target.name === "name" && (doc || isPayment)
        ? partyChoices.find(
            (r) =>
              r.kind === "party" &&
              r.name.trim().toLowerCase() === value.trim().toLowerCase(),
          )
        : null;
    const nextShippingDefault = matched ? partyShippingAddress(matched) : "";
    const shipping = shippingForPartySelection(form.shipping_address, lastShippingDefault.current, nextShippingDefault);
    if (e.target.name === "name") lastShippingDefault.current = nextShippingDefault;
    setForm({
      ...form,
      [e.target.name]: value,
      ...(matched
        ? {
            party_id: matched.id,
            party_address: matched.data?.address || "",
            party_gstin: matched.data?.gstin || "",
            party_phone: matched.data?.phone || "",
            shipping_address: shipping,
            ...(purchase
              ? {
                  supplier_state:
                    matched.data?.gstin?.slice(0, 2) || company.state_code,
                }
              : {
                  place_of_supply:
                    matched.data?.gstin?.slice(0, 2) || company.state_code,
                }),
          }
        : e.target.name === "name" &&
            value.trim().toLowerCase() !== form.name.trim().toLowerCase()
          ? {
              party_id: "",
              party_address: "",
              party_gstin: "",
              party_phone: "",
              shipping_address: shipping,
              supplier_state: company.state_code,
              place_of_supply: company.state_code,
            }
          : {}),
    });
  };
  const changeLine = (index, e) =>
    setLines(
      lines.map((line, i) => {
        if (i !== index) return line;
        let next = ["discount_mode", "discount_amount", "discount_percent"].includes(e.target.name)
          ? changeLineDiscount(line, e.target.name, e.target.value)
          : { ...line, [e.target.name]: e.target.value };
        if (e.target.name === "tax_treatment")
          next.gst_rate =
            e.target.value === "taxable"
              ? Number(line.gst_rate) > 0
                ? line.gst_rate
                : "18"
              : "0";
        if (e.target.name === "description") {
          const found = itemChoices.find(
            (r) =>
              r.kind === "item" &&
              r.name.trim().toLowerCase() ===
                e.target.value.trim().toLowerCase(),
          );
          next = { ...next, item_id: found?.id || "" };
          if (found) next = linkCatalogueItem(next, found, purchase, company.tax_mode);
        }
        return next;
      }),
    );
  const sourceRequest = useRef(0);
  const [loadingSource, setLoadingSource] = useState(false);
  useEffect(
    () => () => {
      sourceRequest.current++;
    },
    [],
  );
  async function selectSource(id) {
    const request = ++sourceRequest.current;
    setError("");
    setForm((current) => ({ ...current, applied_to: id, name: "" }));
    setLines([emptyLine()]);
    setSourceInputTax("");
    if (!id) {
      setLoadingSource(false);
      return;
    }
    setLoadingSource(true);
    try {
      const target = await api(`/companies/${companyId}/records/${id}`);
      if (request !== sourceRequest.current) return;
      setSourceInputTax(sourceInputTaxSummary(target.data?.lines));
      setForm((current) => ({
        ...current,
        applied_to: id,
        name: target.name,
        document_discount_percent: target.data?.document_discount_percent || "0",
        party_id: target.data?.party_id || "",
        party_phone: target.data?.party_phone || "",
        shipping_address: target.data?.shipping_address || "",
        place_of_supply: target.data?.place_of_supply || company.state_code,
        supplier_state:
          target.data?.supplier_state ||
          target.data?.party_gstin?.slice(0, 2) ||
          company.state_code,
        party_address: target.data?.party_address || "",
        party_gstin: target.data?.party_gstin || "",
      }));
      setLines(
        (target.data?.lines || []).map((line) => ({
          ...emptyLine(),
          ...line,
          quantity: String(line.quantity),
          rate: String(line.rate),
        })),
      );
    } catch (e) {
      if (request === sourceRequest.current) setError(e.message);
    } finally {
      if (request === sourceRequest.current) setLoadingSource(false);
    }
  }
  async function submit(e) {
    e.preventDefault();
    if (!canWrite || saving || scanning || loadingSource || inlineParty || inlineItem) return;
    setError("");
    try {
      if (conversionBlocked) throw Error(conversionBlocked);
      if (requiresDiscountReview && reviewedReturnDiscounts !== returnDiscountReviewKey) throw Error("Review the fixed discounts for the returned quantities before saving.");
      const payload = {
          kind,
          name: form.name,
          number: form.number,
          date: form.date,
          amount: doc ? 0 : Number(form.amount || 0),
          data: doc
            ? {
                place_of_supply: form.place_of_supply,
                due_date: form.due_date,
                lines: lines.map(serializeLineDiscount),
                applied_to: form.applied_to,
                party_id: form.party_id || undefined,
                party_address: form.party_address,
                party_gstin: form.party_gstin,
                supplier_state: purchase ? form.supplier_state : undefined,
                party_phone: form.party_phone,
                shipping_address: form.shipping_address,
                payment_account: form.payment_account,
                bank_account_id:
                  form.payment_account === "bank"
                    ? form.bank_account_id
                    : undefined,
                source_document_id: conversion?.id,
                source_document_version: conversion?.version,
                version: edit ? source?.data?.version || 0 : undefined,
                notes: form.notes,
                terms: form.terms,
                category: form.category,
                document_discount_percent: form.document_discount_percent,
                tender_amount: form.tender_amount || undefined,
                round_total: form.round_total,
                return_stock: form.return_stock,
              }
            : {
                version: edit ? source?.data?.version || 0 : undefined,
                applied_to: form.applied_to,
                advance_supply: form.advance_supply,
                advance_gst_rate: form.advance_gst_rate,
                place_of_supply: form.place_of_supply,
                party_address: form.party_address || undefined,
                party_gstin: form.party_gstin || undefined,
                party_phone: form.party_phone || undefined,
                ...(isPayment
                  ? {
                      is_advance: advance,
                      allocations: advance ? [] : paymentRows,
                    }
                  : {}),
                payment_account: form.payment_account,
                bank_account_id:
                  form.payment_account === "bank"
                    ? form.bank_account_id
                    : undefined,
              },
        };
      const options = { keepOpen: saveAction.current === "new" };
      await posting.run(() => save(payload, submissionKey, options));
    } catch (err) {
      if (conversion && isDefiniteConversionConflict(err)) setConversionRejected(err.message + ". Close this form, reopen the source and review its current contents before converting. Your entered details remain visible here.");
      setError(err.message);
    }
  }
  const preview = useDocumentPreview({
    api,
    companyId,
    kind,
    form,
    lines: lines.map(serializeLineDiscount),
    enabled: doc,
    recordId: edit?.id,
  });
  const saveLabel =
    {
      sales_invoice: "invoice",
      purchase_bill: "bill",
      estimate: "estimate",
      sales_order: "sales order",
      proforma: "proforma",
      purchase_order: "purchase order",
      credit_note: "credit note",
      debit_note: "debit note",
      expense: "expense",
      payment_in: "receipt",
      payment_out: "payment",
    }[kind] || "record";
  return (
    <>
      <Modal
        title={
          company.tax_mode === "composition" && kind === "sales_invoice"
            ? `${edit ? "Edit" : "New"} bill of supply`
            : `${edit ? "Edit" : "New"} ${labels[kind]?.replace(/s$/, "").toLowerCase() || "record"}`
        }
        subtitle={`${company.name} · ${company.tax_mode === "regular" ? "GST registered" : company.tax_mode === "composition" ? "Composition" : "Non-GST business"}`}
        variant={doc ? "document" : undefined}
        close={requestClose}
      >
        {inlineParty && <InlinePartyForm today={today} features={features} initialName={form.name} createParty={createParty}
          onLockChange={updatePartyLock} close={dismissParty} onCreated={created => {
            if (!created) return;
            const nextDefault = partyShippingAddress(created);
            const previousDefault = lastShippingDefault.current;
            setCreatedParties(current => [...current.filter(row => row.id !== created.id), created]);
            setForm(current => ({ ...current, name: created.name, party_id: created.id,
              party_address: created.data?.address || "", party_gstin: created.data?.gstin || "",
              party_phone: created.data?.phone || "",
              shipping_address: shippingForPartySelection(current.shipping_address, previousDefault, nextDefault),
              place_of_supply: created.data?.gstin?.slice(0, 2) || company.state_code }));
            lastShippingDefault.current = nextDefault;
            setDirty(true); updatePartyLock(false); setInlineParty(false);
            setTimeout(() => partyButton.current?.focus(), 0);
          }} />}
        {inlineItem && <InlineItemForm today={today} features={features} createItem={createItem}
          onLockChange={updateItemLock} close={dismissItem} onCreated={created => {
            if (!created) return;
            setCreatedItems(current => [...current.filter(row => row.id !== created.id), created]);
            // Reuse only the single pristine placeholder, never an edited draft line.
            setLines(current => {
              const blank = emptyLine();
              const pristine = current.length === 1 && Reflect.ownKeys(current[0]).length === Reflect.ownKeys(blank).length &&
                Reflect.ownKeys(blank).every(key => current[0][key] === blank[key]);
              const added = { ...linkCatalogueItem({ ...blank, description: created.name }, created, false, company.tax_mode),
                rate: String(created.data?.sale_rate ?? "") };
              return pristine ? [added] : [...current, added];
            });
            setItemAdded(`${created.name} added as a new line. Review quantity, rate, discount and tax before saving.`);
            itemFocusTarget.current = "quantity";
            setDirty(true); updateItemLock(false); setInlineItem(false);
          }} />}
        <div hidden={inlineParty || inlineItem}>
        <form
          onSubmit={submit}
          onChangeCapture={() => setDirty(true)}
          onInputCapture={() => setDirty(true)}
          className={`form-grid ${doc ? "document-form" : ""}`}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              e.currentTarget.requestSubmit();
            }
          }}
        >
          <fieldset className="form-grid full submission-fields" disabled={!canWrite || saving || scanning || pending}>
          {!canWrite && <p className="info-box full">You have read-only access to this company.</p>}
          {relatedSource && (
            <p className="info-box full">Linked to {relatedSource.number || relatedSource.name}. {isPayment ? "Review the amount and allocation before posting; this does not mark the bank statement as matched." : "Review the quantities and tax before posting a linked return. The original document stays in history."}</p>
          )}
          {source && (
            <div className="info-box full">
              {edit ? "Editing" : "Converting"} {source.number || source.name}.
              Review the invoice or bill before saving.
            </div>
          )}
          {kind === "purchase_bill" && (
            <div className="full ocr-box">
              <strong>Scan purchase bill</strong>
              <p>
                {ocrStatus?.ready
                  ? "Upload a PNG, JPEG or WebP image to prefill a draft. Review every field before saving."
                  : ocrStatus?.message || "Checking OCR availability…"}
              </p>
              {true && (
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={scan}
                  disabled={scanning || !ocrStatus?.ready}
                />
              )}
              {scanning && <small>Extracting draft…</small>}
              {sourcePreview && (
                <a
                  href={sourcePreview}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    className="ocr-source-preview"
                    src={sourcePreview}
                    alt="Selected purchase bill for draft review"
                  />
                  View original bill
                </a>
              )}
              {ocrTotal && (
                <small>
                  Amount shown on bill: ₹{ocrTotal}. Check line totals before
                  saving.
                </small>
              )}
            </div>
          )}
          {!doc && (
            <>
              <label className="full">
                {party
                  ? "Party name"
                  : item
                    ? "Item name"
                    : kind === "bank_account"
                      ? "Account name"
                      : "Party / description"}
                <input
                  name="name"
                  list={doc ? "apex-party-options" : undefined}
                  required
                  value={form.name}
                  onChange={change}
                  placeholder="Enter name"
                />
              </label>
              {appliesTo && !isPayment && (
                <label className="full">
                  Apply to{" "}
                  {appliesTo === "sales_invoice"
                    ? "sales invoice"
                    : "purchase bill"}
                  <select
                    className="form-select"
                    required
                    value={form.applied_to}
                    onChange={(e) => selectSource(e.target.value)}
                  >
                    <option value="">Choose a posted document</option>
                    {targets.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.number || r.id} · {r.name} · {money(r.outstanding)}{" "}
                        due
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {!party && !item && (
                <>
                  <label>
                    Reference number
                    <input
                      name="number"
                      maxLength={16}
                      value={form.number}
                      onChange={change}
                      placeholder="Enter reference"
                    />
                  </label>
                  <label>
                    Date
                    <input
                      type="date"
                      name="date"
                      required
                      value={form.date}
                      onInput={change}
                      onChange={change}
                    />
                  </label>
                </>
              )}
              {isPayment && (
                <PaymentAllocations
                  advance={advance}
                  onAdvance={setAdvance}
                  allowAdvance={true}
                  rows={paymentRows}
                  setRows={setPaymentRows}
                  targets={targets}
                  party={form.name}
                  paymentAmount={form.amount}
                  onPaymentAmount={(amount) =>
                    setForm((current) => ({ ...current, amount }))
                  }
                  onParty={(name) =>
                    setForm((current) => ({ ...current, name }))
                  }
                />
              )}
              {isPayment &&
                advance &&
                company.tax_mode === "regular" &&
                kind === "payment_in" && (
                  <>
                    <label>
                      Advance is for
                      <select
                        className="form-select"
                        aria-label="Advance supply type"
                        required
                        value={form.advance_supply}
                        onChange={(e) =>
                          setForm({ ...form, advance_supply: e.target.value })
                        }
                      >
                        <option value="">Choose goods or services</option>
                        <option value="goods">
                          Goods · GST deferred until invoice
                        </option>
                        <option value="services">
                          Services · GST on advance
                        </option>
                      </select>
                    </label>
                    {form.advance_supply === "services" && (
                      <>
                        <label>
                          Advance GST rate (%)
                          <input
                            required
                            type="number"
                            min="0"
                            max="100"
                            step="0.01"
                            value={form.advance_gst_rate}
                            onChange={(e) =>
                              setForm({
                                ...form,
                                advance_gst_rate: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          Advance place of supply (state code)
                          <input
                            required
                            pattern="[0-9]{2}"
                            value={form.place_of_supply}
                            onChange={(e) =>
                              setForm({
                                ...form,
                                place_of_supply: e.target.value,
                              })
                            }
                          />
                        </label>
                        <p className="info-box full">
                          The amount received includes GST. GST is adjusted when
                          the advance is applied or refunded.
                        </p>
                      </>
                    )}
                    <label>
                      Party address
                      <input
                        maxLength={500}
                        value={form.party_address}
                        onChange={(e) =>
                          setForm({ ...form, party_address: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Party GSTIN
                      <input
                        maxLength={15}
                        value={form.party_gstin}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            party_gstin: e.target.value.toUpperCase(),
                          })
                        }
                      />
                    </label>
                  </>
                )}
              {["sales_invoice", "purchase_bill"].includes(kind) && (
                <label>
                  Due date
                  <input
                    type="date"
                    name="due_date"
                    min={form.date}
                    value={form.due_date}
                    onChange={change}
                  />
                </label>
              )}
            </>
          )}
          {doc ? (
            <>
              {draftSeed && <p className="info-box full">Reorder draft only. Choose a supplier and review quantities, prices and tax. Saving this purchase order does not move stock or money.</p>}
              {termsError && <p className="error full">Payment-term suggestion unavailable: {termsError}. You can still set a due date manually.</p>}
              {termsSuggestion?.suggested_due_date && <div className="info-box full">Party terms: Net {termsSuggestion.payment_terms_days} days · suggested due date {termsSuggestion.suggested_due_date}. <button type="button" className="button secondary" onClick={() => { setDirty(true); setForm(current => ({ ...current, due_date: termsSuggestion.suggested_due_date })); }}>Apply payment terms</button></div>}
              <DocumentIdentity
                form={form}
                setForm={setForm}
                change={change}
                kind={kind}
                purchase={purchase}
                showTax={showTax}
                company={company}
                targets={targets}
                onSelectSource={selectSource}
              />
              {kind === "sales_invoice" && !edit && !source && !relatedSource && createParty && <div className="full"><button ref={partyButton} type="button" className="button secondary" onClick={() => setInlineParty(true)}>Create new party</button></div>}
              <datalist id="apex-party-options">
                {partyChoices
                  .map((r) => (
                    <option key={r.id} value={r.name} />
                  ))}
              </datalist>
              <datalist id="apex-item-options">
                {itemChoices
                  .map((r) => (
                    <option key={r.id} value={r.name} />
                  ))}
              </datalist>
              {!edit && kind === "debit_note" && company.tax_mode === "regular" && form.applied_to && <section className="info-box full" aria-label="Purchase return input-tax guidance"><strong>Keep the original bill’s input-tax classification</strong>{sourceInputTax && <p>Source bill: {sourceInputTax}.</p>}<p>Review each line’s tax options: input GST pending review or GST included in cost (ineligible). Earlier returns reduce the amount available in each classification. Pending review does not mean credit has been claimed.</p></section>}
              {!edit && (source || relatedSource || form.applied_to) && lines.some(line => lineDiscountMode(line) === "amount") && <p className="info-box full">Fixed rupee discounts were copied unchanged from the source. They are not automatically prorated when you change quantities. Review each discount against the quantities being converted or returned before saving.</p>}
              {requiresDiscountReview && <label className="checkbox full"><input type="checkbox" required checked={reviewedReturnDiscounts === returnDiscountReviewKey} onChange={event => setReviewedReturnDiscounts(event.target.checked ? returnDiscountReviewKey : "")} />I reviewed the copied fixed discounts for these returned quantities.</label>}
              {kind === "sales_invoice" && !edit && !source && !relatedSource && createItem && <div className="full">
                <button ref={itemButton} type="button" className="button secondary" disabled={lines.length >= 100} onClick={() => { if (lines.length < 100) setInlineItem(true); }}>Create item/service and add line</button>
                <small>{lines.length >= 100 ? "Maximum 100 lines. Remove a line before creating another item." : "Creates a new catalogue entry and adds a new line. Existing lines stay unchanged."}</small>
              </div>}
              {itemAdded && <p className="info-box full" role="status">{itemAdded}</p>}
              <DocumentItems
                lines={lines}
                setLines={(next) => {
                  setDirty(true);
                  setLines(next);
                }}
                changeLine={changeLine}
                onPriceHistory={supported("party_price_history") && form.party_id && !source && !relatedSource ? index => setPriceLine({ index, item: { ...lines[index] }, party: { id: form.party_id, name: form.name } }) : null}
                emptyLine={emptyLine}
                showTax={showTax}
                purchase={purchase}
                company={company}
                preview={preview}
                money={money}
              />
            </>
          ) : (
            !party &&
            !item && (
              <label className="full">
                {isPayment ? "Payment amount (₹)" : "Amount (₹)"}
                <input
                  name="amount"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={form.amount}
                  onChange={change}
                />
              </label>
            )
          )}
          {["payment_in", "payment_out", "expense", "pos"].includes(kind) && (
            <label className="full">
              Paid through
              <select
                className="form-select"
                value={form.payment_account}
                onChange={(e) =>
                  setForm({ ...form, payment_account: e.target.value })
                }
              >
                <option value="cash">Cash</option>
                <option value="bank">Bank</option>
              </select>
            </label>
          )}
          {["payment_in", "payment_out", "expense", "pos"].includes(kind) &&
            form.payment_account === "bank" && (
              <label className="full">
                Bank account
                <select
                  className="form-select"
                  value={form.bank_account_id}
                  onChange={(e) =>
                    setForm({ ...form, bank_account_id: e.target.value })
                  }
                >
                  {bankAccounts.map((bank) => (
                    <option key={bank.id} value={bank.id}>
                      {bank.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          {doc && (
            <section className="document-bottom full">
              <div className="document-extras">
                <div className="editor-section-heading">
                  <span>03</span>
                  <div>
                    <h3>Adjustments & notes</h3>
                    <p>Review the final amounts before saving.</p>
                  </div>
                </div>
                <div className="form-grid">
                  <label>
                    Document discount (%)
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={form.document_discount_percent}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          document_discount_percent: e.target.value,
                        })
                      }
                    />
                  </label>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={form.round_total}
                      onChange={(e) =>
                        setForm({ ...form, round_total: e.target.checked })
                      }
                    />
                    Round total to nearest rupee
                  </label>
                  {["credit_note", "debit_note"].includes(kind) && (
                    <label className="checkbox-label full">
                      <input
                        type="checkbox"
                        checked={form.return_stock}
                        onChange={(e) =>
                          setForm({ ...form, return_stock: e.target.checked })
                        }
                      />
                      Return stock with this note
                    </label>
                  )}
                  {kind === "expense" && (
                    <label className="full">
                      Expense category
                      <input
                        required
                        maxLength={80}
                        value={form.category}
                        onChange={(e) =>
                          setForm({ ...form, category: e.target.value })
                        }
                        placeholder="Travel, rent, office supplies"
                      />
                    </label>
                  )}
                </div>
                <details className="document-notes">
                  <summary>
                    Notes & terms{form.notes || form.terms ? " · added" : ""}
                  </summary>
                  <div className="form-grid">
                    <label>
                      Notes
                      <textarea
                        maxLength={1500}
                        value={form.notes}
                        onChange={(e) =>
                          setForm({ ...form, notes: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Terms and conditions
                      <textarea
                        maxLength={3000}
                        value={form.terms}
                        onChange={(e) =>
                          setForm({ ...form, terms: e.target.value })
                        }
                      />
                    </label>
                  </div>
                </details>
              </div>
              <DocumentTotals preview={preview} money={money} />
              {supported("party_credit_limits") && !edit && ["sales_invoice", "estimate", "proforma", "sales_order"].includes(kind) && form.party_id && preview && !preview.error && <CreditStatus api={api} companyId={companyId} partyId={form.party_id} asOf={form.date} proposedAmount={preview.amount} compact />}
            </section>
          )}
          {kind === "pos" && form.payment_account === "cash" && (
            <label className="full">
              Cash tendered
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.tender_amount || ""}
                onChange={(e) =>
                  setForm({ ...form, tender_amount: e.target.value })
                }
              />
            </label>
          )}
          </fieldset>
          {pending && !saving && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
          {conversionBlocked && <div className="info-box full" role="status">{conversionBlocked}{onRetryCapabilities && !conversionRejected && <button type="button" className="button secondary" disabled={saving} onClick={onRetryCapabilities}>Check API support again</button>}</div>}
          {error && <div className="error full">{error}</div>}
          <div className="modal-actions full document-actions">
            {doc && (
              <div className="editor-footer-total">
                <small>DOCUMENT TOTAL</small>
                <strong>
                  {preview && !preview.error ? money(preview.amount) : "—"}
                </strong>
                <span>Ctrl + Enter to save</span>
              </div>
            )}
            <button
              type="button"
              className="button secondary"
              disabled={saving || scanning || pending}
              onClick={requestClose}
            >
              Cancel
            </button>
            {doc && !edit && !source && !relatedSource && !draftSeed && (
              <button
                className="button secondary save-new"
                type="button"
                onClick={(e) => {
                  saveAction.current = "new";
                  e.currentTarget.form.requestSubmit();
                  saveAction.current = "close";
                }}
                disabled={!canWrite || saving || scanning || loadingSource || pending}
              >
                Save & new
              </button>
            )}
            <button
              className="button primary"
              disabled={!canWrite || saving || scanning || loadingSource || !!conversionBlocked}
            >
              {loadingSource
                ? "Loading document…"
                : saving
                  ? "Saving…"
                  : `Save ${saveLabel}`}
            </button>
          </div>
        </form>
        </div>
      </Modal>
      {priceLine && <PriceHistory api={api} companyId={companyId} party={priceLine.party} item={priceLine.item} side={purchase ? "purchase" : "sales"} Modal={Modal} close={() => setPriceLine(null)} apply={price => {
        setLines(current => current.map((line, index) => index === priceLine.index && line.item_id === priceLine.item.item_id ? { ...line, ...price } : line));
        setDirty(true); setPriceLine(null);
      }} />}
      {confirmClose && (
        <Modal
          title="Discard unsaved changes?"
          subtitle="This document has not been saved."
          close={() => setConfirmClose(false)}
        >
          <p>
            Keep editing to finish your document, or discard this unsaved draft.
          </p>
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setConfirmClose(false)}
            >
              Keep editing
            </button>
            <button className="button danger" onClick={close}>
              Discard draft
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
