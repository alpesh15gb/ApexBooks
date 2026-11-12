import { newestRecordFirst } from './registerOrder.js';

// Current work queues are independent of the chart's reporting period.
export function dashboardWork(records, today) {
  const active = records.filter(record => !record.cancelled && !record.data?.cancelled);
  const invoices = active.filter(record => record.kind === 'sales_invoice' && record.posted);
  const bills = active.filter(record => record.kind === 'purchase_bill' && record.posted);
  const overdue = invoices.filter(record => Number(record.outstanding) > 0 && record.data?.due_date && record.data.due_date < today);
  const openBills = bills.filter(record => Number(record.outstanding) > 0);
  const quotes = active.filter(record => record.kind === 'estimate' && !record.converted_to);
  return { overdue, openBills, quotes };
}

export function recentTransactions(records) {
  return records.filter(record => !['party', 'item', 'bank_account'].includes(record.kind))
    .slice().sort(newestRecordFirst)
    .slice(0, 6);
}
