
export function matchCounterProduct(items, value) {
  const code = value.trim();
  if (!code) return { message: "Enter a barcode or product name." };
  const barcodes = items.filter(item => item.data?.barcode === code);
  const matches = barcodes.length ? barcodes : items.filter(item =>
    item.name.trim().toLowerCase() === code.toLowerCase(),
  );
  if (matches.length === 1) return { item: matches[0] };
  if (matches.length) return { message: "Multiple products match. Select the correct product below." };
  return { message: "No exact barcode or name match. Select a product below." };
}

export function toPaise(value) {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(String(value));
  if (!match) return null;
  const paise = Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0"));
  return Number.isSafeInteger(paise) ? paise : null;
}

export function counterTender(total, method, bankShare, cashReceived) {
  const amount = toPaise(total);
  if (amount === null || amount <= 0) return null;
  const bank = method === "split" ? toPaise(bankShare) : method === "bank" ? amount : 0;
  if (bank === null || (method === "split" && (bank <= 0 || bank >= amount))) return null;
  const cash = amount - bank;
  const tender = cash && cashReceived !== "" ? toPaise(cashReceived) : cash;
  if (tender === null) return null;
  return { cash, bank, tender, change: tender - cash };
}

