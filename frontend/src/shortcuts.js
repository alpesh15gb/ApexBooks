// Keyboard-first billing (Tally / QuickBooks style). Alt+<key>; ignored while a dialog or editor is open.
export const SHORTCUTS = [
  { key: "n", action: "create", target: "sales_invoice", label: "New sales invoice" },
  { key: "e", action: "create", target: "estimate", label: "New estimate" },
  { key: "r", action: "create", target: "payment_in", label: "Record payment received" },
  { key: "p", action: "create", target: "purchase_bill", label: "New purchase bill" },
  { key: "x", action: "create", target: "expense", label: "New expense" },
  { key: "s", action: "create", target: "pos", label: "Open POS" },
  { key: "h", action: "go", target: "dashboard", label: "Dashboard" },
  { key: "i", action: "go", target: "sales_invoice", label: "Sales invoices" },
  { key: "c", action: "go", target: "party", label: "Parties" },
  { key: "t", action: "go", target: "item", label: "Items" },
  { key: "d", action: "go", target: "day_book", label: "Day book" },
  { key: "g", action: "go", target: "reports", label: "Reports" },
];

/** The shortcut for a keydown event, or null. `blocked` is true while a modal/editor is open. */
export function shortcutFor(event, blocked = false) {
  if (blocked || !event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return null;
  const key = String(event.key || "").toLowerCase();
  return SHORTCUTS.find((s) => s.key === key) || null;
}

/** "?" opens the shortcut list, but not while typing in a field. */
export function isHelpKey(event) {
  const tag = String(event.target?.tagName || "").toLowerCase();
  const typing = ["input", "textarea", "select"].includes(tag) || event.target?.isContentEditable;
  return event.key === "?" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey;
}
