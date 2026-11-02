// A scanned bill replaces supplier-specific draft fields; missing OCR values
// must never inherit the previous supplier's identity or tax origin.
export function purchaseDraftForm(previous, draft, companyState, currentDate) {
  const gstin = String(draft.supplier_gstin || "")
    .trim()
    .toUpperCase();
  return {
    ...previous,
    name: draft.supplier_name || "",
    party_id: "",
    party_gstin: gstin,
    party_address: draft.supplier_address || "",
    party_phone: "",
    shipping_address: "",
    supplier_state: /^\d{2}/.test(gstin) ? gstin.slice(0, 2) : companyState,
    place_of_supply: /^\d{2}$/.test(draft.place_of_supply || "")
      ? draft.place_of_supply
      : companyState,
    number: draft.invoice_number || "",
    date: /^\d{4}-\d{2}-\d{2}$/.test(draft.invoice_date || "")
      ? draft.invoice_date
      : currentDate,
    due_date: "",
    document_discount_percent: "0",
    round_total: false,
  };
}
