// Dashboard amounts can be hidden on this device. Hiding needs no password; showing them again does.
const KEY = "apex.dashboard.amountsHidden";
export const MASKED_AMOUNT = "₹ ••••••";

function deviceStorage() {
  try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; }
}
export function readAmountsHidden(storage = deviceStorage()) {
  try { return storage?.getItem(KEY) === "1"; } catch { return false; }
}
export function writeAmountsHidden(hidden, storage = deviceStorage()) {
  try { if (hidden) storage?.setItem(KEY, "1"); else storage?.removeItem(KEY); } catch { /* private mode: the preference lasts for this session only */ }
}
export const amountText = (hidden, formatted) => (hidden ? MASKED_AMOUNT : formatted);
// A server without the password check (404/405) cannot reveal by password, so it must not strand the user behind masked figures.
export const revealUnsupported = (error) => error?.status === 404 || error?.status === 405;
