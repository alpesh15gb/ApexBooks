// WhatsApp share and payment-reminder messages (the Vyapar / MyBillBook / Swipe flow).
// Text only: nothing is sent until the user presses send in WhatsApp.
const rupees = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value || 0));

const titles = {
  sales_invoice: "Invoice",
  pos: "Bill",
  estimate: "Estimate",
  proforma: "Proforma invoice",
  sales_order: "Sales order",
  credit_note: "Credit note",
  payment_in: "Payment receipt",
  purchase_order: "Purchase order",
  purchase_bill: "Bill",
  payment_out: "Payment",
  debit_note: "Debit note",
};

export function whatsappPhone(value) {
  const digits = String(value || "").replace(/\D/g, "").replace(/^0+/, "");
  if (digits.length === 10) return "91" + digits;
  return digits.length >= 11 && digits.length <= 15 ? digits : "";
}

export function partyPhone(record, records = []) {
  const party = records.find(
    (row) =>
      row.kind === "party" &&
      (row.id === record.data?.party_id ||
        row.name?.trim().toLowerCase() === record.name?.trim().toLowerCase()),
  );
  return party?.data?.phone || record.data?.phone || record.data?.party_phone || "";
}

export function documentMessage(record, companyName, upiId = "") {
  const title = titles[record.kind] || "Document";
  const lines = [
    `Dear ${record.name || "Customer"},`,
    `${title} ${record.number || ""} dated ${record.date} for ${rupees(record.amount)} from ${companyName}.`.replace("  ", " "),
  ];
  const due = Number(record.outstanding || 0);
  if (["sales_invoice", "pos"].includes(record.kind) && record.posted) {
    lines.push(due > 0 ? `Balance due: ${rupees(due)}${record.data?.due_date ? ` by ${record.data.due_date}` : ""}.` : "Fully paid. Thank you!");
    if (due > 0 && upiId) lines.push(`Pay by UPI: ${upiId}`);
  }
  lines.push("Thank you for your business.");
  return lines.join("\n");
}

export function reminderMessage(record, companyName, upiId = "", today = new Date().toISOString().slice(0, 10)) {
  const due = rupees(record.outstanding);
  const overdue = record.data?.due_date && record.data.due_date < today;
  const lines = [
    `Dear ${record.name || "Customer"},`,
    `This is a gentle reminder that ${due} is ${overdue ? `overdue since ${record.data.due_date}` : "pending"} against ${titles[record.kind] || "invoice"} ${record.number} dated ${record.date}.`,
  ];
  if (upiId) lines.push(`You can pay by UPI: ${upiId}`);
  lines.push(`Please ignore if already paid.\n– ${companyName}`);
  return lines.join("\n");
}

export function whatsappUrl(phone, text) {
  const number = whatsappPhone(phone);
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}

export function canRemind(record) {
  return ["sales_invoice", "pos"].includes(record.kind) && record.posted && !record.cancelled && Number(record.outstanding || 0) > 0;
}

// "Remind all overdue": one message per customer covering every overdue invoice.
export function overdueByParty(records, today = new Date().toISOString().slice(0, 10)) {
  const groups = new Map();
  for (const record of records) {
    if (!canRemind(record) || !record.data?.due_date || record.data.due_date >= today) continue;
    const key = (record.name || "").trim().toLowerCase();
    const group = groups.get(key) || { name: record.name, invoices: [], total: 0, phone: partyPhone(record, records) };
    group.invoices.push(record);
    group.total += Number(record.outstanding || 0);
    if (!group.phone) group.phone = partyPhone(record, records);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => b.total - a.total);
}

export function partyReminderMessage(group, companyName, upiId = "") {
  const lines = [`Dear ${group.name || "Customer"},`, `This is a gentle reminder that ${rupees(group.total)} is overdue:`];
  for (const invoice of group.invoices)
    lines.push(`• ${titles[invoice.kind] || "Invoice"} ${invoice.number} dated ${invoice.date}: ${rupees(invoice.outstanding)} (due ${invoice.data.due_date})`);
  if (upiId) lines.push(`You can pay by UPI: ${upiId}`);
  lines.push(`Please ignore if already paid.\n– ${companyName}`);
  return lines.join("\n");
}
