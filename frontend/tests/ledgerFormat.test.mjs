import test from "node:test";
import assert from "node:assert/strict";
import { ledgerAmount, ledgerBalance, ledgerDate } from "../src/ledgerFormat.js";

test("dates read as Tally writes them", () => {
  assert.equal(ledgerDate("2024-04-05"), "05-Apr-2024");
  assert.equal(ledgerDate("2026-12-31"), "31-Dec-2026");
  assert.equal(ledgerDate(""), "");
});

test("amounts use lakh grouping and blank cells stay blank", () => {
  assert.equal(ledgerAmount("351888"), "3,51,888.00");
  assert.equal(ledgerAmount(""), "");
});

test("balances carry Dr or Cr", () => {
  assert.equal(ledgerBalance("82840", "Dr"), "82,840.00 Dr");
  assert.equal(ledgerBalance("700", "Cr"), "700.00 Cr");
  assert.equal(ledgerBalance("0", ""), "0.00");
});
