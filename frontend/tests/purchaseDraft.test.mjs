import test from "node:test";
import assert from "node:assert/strict";
import { purchaseDraftForm } from "../src/purchaseDraft.js";

test("scanning a different supplier clears old identity, addresses and discounts", () => {
  const old = {
    name: "Previous supplier",
    party_id: "old-party",
    party_gstin: "27AAAAA0000A1Z5",
    party_address: "Old address",
    party_phone: "0000000000",
    shipping_address: "Old ship-to",
    supplier_state: "27",
    place_of_supply: "27",
    due_date: "2026-12-01",
    document_discount_percent: "10",
    round_total: true,
  };
  const next = purchaseDraftForm(
    old,
    { supplier_name: "New supplier", invoice_number: "NEW-1" },
    "36",
    "2026-11-01",
  );
  assert.equal(next.name, "New supplier");
  for (const field of [
    "party_id",
    "party_gstin",
    "party_address",
    "party_phone",
    "shipping_address",
    "due_date",
  ])
    assert.equal(next[field], "");
  assert.equal(next.supplier_state, "36");
  assert.equal(next.place_of_supply, "36");
  assert.equal(next.document_discount_percent, "0");
  assert.equal(next.round_total, false);
  assert.equal(next.number, "NEW-1");
  assert.equal(next.date, "2026-11-01");
  assert.equal(old.party_id, "old-party");
});

test("printed supplier GSTIN sets origin independently from destination", () => {
  const next = purchaseDraftForm(
    {},
    {
      supplier_name: "Interstate supplier",
      supplier_gstin: "27AAAAA0000A1Z5",
      supplier_address: "New printed address",
      place_of_supply: "36",
      invoice_number: "INTER-1",
      invoice_date: "2026-10-31",
    },
    "36",
    "2026-11-01",
  );
  assert.equal(next.supplier_state, "27");
  assert.equal(next.place_of_supply, "36");
  assert.equal(next.party_address, "New printed address");
  assert.equal(next.date, "2026-10-31");
  assert.equal(next.party_gstin, "27AAAAA0000A1Z5");
});
