const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** 2024-04-05 -> 05-Apr-2024, as Tally writes dates. */
export function ledgerDate(iso) {
  const [year, month, day] = String(iso || "").split("-");
  const name = MONTHS[Number(month) - 1];
  return name ? `${day}-${name}-${year}` : String(iso || "");
}

/** Indian grouping with two decimals; blank stays blank so an empty debit or credit cell stays empty. */
export function ledgerAmount(value) {
  if (value === "" || value === null || value === undefined) return "";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value));
}

export function ledgerBalance(amount, side) {
  return `${ledgerAmount(amount || 0)}${side ? ` ${side}` : ""}`;
}
