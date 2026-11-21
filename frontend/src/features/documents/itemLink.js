// Symbol metadata survives editor object spreads and is omitted by JSON.stringify.
export const OCR_LINE = Symbol("scanned-purchase-line");

export function linkCatalogueItem(line, item, purchase, taxMode) {
  const data = item.data || {};
  const linked = {
    ...line,
    item_id: item.id,
    hsn: data.hsn || (line[OCR_LINE] ? line.hsn : ""),
    unit: data.unit || (line[OCR_LINE] ? line.unit : ""),
  };
  // Linking stock is an identity change, not permission to reprice an OCR bill.
  if (line[OCR_LINE]) return linked;
  return {
    ...linked,
    rate: String((purchase ? data.purchase_rate : data.sale_rate) || ""),
    gst_rate: taxMode !== "regular" && !purchase ? "0" : String(data.gst_rate || "0"),
    tax_treatment: Number(data.gst_rate || 0) > 0
      ? "taxable"
      : data.tax_treatment && data.tax_treatment !== "taxable"
        ? data.tax_treatment
        : "nil_rated",
  };
}
