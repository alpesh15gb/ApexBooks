import { masterImportActor } from "./masterImportRecovery.js";

const uuid = /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i;

// The exact request lives in this tab, scoped to the signed-in actor and
// company. Server authorization and idempotency still govern every replay.
export function companyRequestRecovery(companyId, token, storage, flow) {
  const actor = masterImportActor(token || "");
  if (!actor) return null;

  const slot = `${flow === "sale" ? "apex-pos-pending" : flow === "return" ? "apex-pos-return" : "apex-purchase-receipt"}:${actor}:${companyId}`;
  const receiving = flow === "purchase-receipt";
  const read = () => {
    const raw = storage.getItem(slot);
    if (!raw) return null;
    try {
      const saved = JSON.parse(raw);
      const body = JSON.parse(saved.body);
      if (!uuid.test(saved.key)) throw Error("Invalid operation key");
      const operation = { key: saved.key, body: saved.body };
      if (flow === "sale" && body.kind === "pos" && Array.isArray(body.data?.lines) && body.data.lines.length) {
        return operation;
      }
      if (flow === "return" && uuid.test(saved.saleId) && Array.isArray(body.lines) && body.lines.length) {
        return { ...operation, saleId: saved.saleId };
      }
      if (receiving && uuid.test(saved.orderId) && Array.isArray(body.lines) && body.lines.length && Number.isInteger(body.source_version)) {
        return { ...operation, orderId: saved.orderId };
      }
    } catch { /* Keep the record in place for review. */ }
    throw Error(receiving
      ? "The pending receipt could not be read. Verify the original bill before receiving another delivery."
      : "A pending POS transaction could not be read. Verify the original transaction before recording another.");
  };
  return {
    read,
    save(operation) {
      if (read()) throw Error(receiving ? "Recover the previous supplier bill first." : "Recover the previous sale before starting checkout.");
      storage.setItem(slot, JSON.stringify(operation));
    },
    clear(key) {
      if (read()?.key === key) storage.removeItem(slot);
    },
  };
}
