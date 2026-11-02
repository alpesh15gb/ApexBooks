import test from "node:test";
import assert from "node:assert/strict";
import { linkCatalogueItem, OCR_LINE } from "../src/itemLink.js";

const item = { id: "stock-qa", data: { hsn: "8517", unit: "NOS", purchase_rate: "50", sale_rate: "100", gst_rate: "5" } };

test("linking a scanned bill keeps supplier rate, GST and discounts", () => {
  const line = { [OCR_LINE]: true, description: "Supplier adapter", quantity: "2", rate: "500", gst_rate: "18", discount_percent: "10", price_includes_tax: true, tax_treatment: "taxable" };
  const linked = linkCatalogueItem({ ...line }, item, true, "regular");
  assert.equal(linked.item_id, "stock-qa");
  assert.equal(linked.hsn, "8517");
  assert.equal(linked.unit, "NOS");
  for (const key of ["quantity", "rate", "gst_rate", "discount_percent", "price_includes_tax", "tax_treatment"]) assert.equal(linked[key], line[key]);
  assert.equal(Object.getOwnPropertySymbols(JSON.parse(JSON.stringify(linked))).length, 0);
});

test("new manual entries use catalogue defaults and non-GST sales suppress GST", () => {
  const line = { quantity: "1", rate: "", gst_rate: "18" };
  const purchase = linkCatalogueItem(line, item, true, "regular");
  assert.equal(purchase.rate, "50");
  assert.equal(purchase.gst_rate, "5");
  assert.equal(linkCatalogueItem(line, item, false, "unregistered").gst_rate, "0");
});
