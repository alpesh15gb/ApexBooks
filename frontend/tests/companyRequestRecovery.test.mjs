import assert from "node:assert/strict";
import test from "node:test";
import { companyRequestRecovery } from "../src/companyRequestRecovery.js";

const token = actor => `header.${btoa(JSON.stringify({ sub: actor }))}.signature`;
const command = {
  key: "53d29cf9-1a7c-4b1e-a065-6b687bf131e8",
  orderId: "051c625e-7faa-4cca-9afa-5ea22004e805",
  body: JSON.stringify({ source_version: 0, lines: [{ line_index: 0, quantity: "2.000" }] }),
};

test("the tab can recover a supplier bill by actor and company without changing the original bytes", () => {
  const values = new Map();
  const storage = {
    getItem: key => values.get(key),
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  const original = companyRequestRecovery("company-a", token("actor-a"), storage, "purchase-receipt");
  original.save(command);
  assert.deepEqual(companyRequestRecovery("company-a", token("actor-a"), storage, "purchase-receipt").read(), command);
  assert.equal(companyRequestRecovery("company-a", token("actor-b"), storage, "purchase-receipt").read(), null);
  assert.equal(companyRequestRecovery("company-b", token("actor-a"), storage, "purchase-receipt").read(), null);
  assert.equal(companyRequestRecovery("company-a", token("actor-a"), storage, "sale").read(), null);
  assert.throws(() => original.save(command), /previous supplier bill/);
  original.clear("another key");
  assert.deepEqual(original.read(), command);
  original.clear(command.key);
  assert.equal(original.read(), null);
});
