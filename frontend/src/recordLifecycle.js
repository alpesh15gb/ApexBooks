export function relatedRecordActions(record, canWrite) {
  if (!canWrite || !record.posted || record.cancelled) return [];
  const actions = [];
  if (record.kind === 'sales_invoice' && Number(record.outstanding) > 0)
    actions.push({ kind: 'payment_in', label: 'Collect payment' });
  if (record.kind === 'purchase_bill' && Number(record.outstanding) > 0)
    actions.push({ kind: 'payment_out', label: 'Pay bill' });
  if (['sales_invoice', 'pos'].includes(record.kind))
    actions.push({ kind: 'credit_note', label: 'Sales return' });
  if (record.kind === 'purchase_bill')
    actions.push({ kind: 'debit_note', label: 'Purchase return' });
  return actions;
}

export function settlementLabel(record) {
  if (!record.posted || record.cancelled || !['sales_invoice', 'purchase_bill', 'pos'].includes(record.kind)) return '';
  if (record.outstanding === undefined || record.outstanding === null || !Number.isFinite(Number(record.outstanding))) return '';
  const balance = Number(record.outstanding || 0);
  if (balance <= 0) return 'Settled';
  return balance < Number(record.amount) ? 'Part settled' : 'Unpaid';
}
