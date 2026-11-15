const MONEY = /^(\d{1,13})(?:\.(\d{1,2}))?$/;
const wholeRupees = new Intl.NumberFormat('en-IN');

export function parseRegisterMoney(value) {
  const match = MONEY.exec(String(value ?? '').trim());
  if (!match) return null;
  return BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0'));
}

function decimalParts(paise) {
  const absolute = paise < 0n ? -paise : paise;
  return {
    sign: paise < 0n ? '-' : '',
    rupees: absolute / 100n,
    fraction: String(absolute % 100n).padStart(2, '0'),
  };
}

function decimal(paise) {
  const { sign, rupees, fraction } = decimalParts(paise);
  return `${sign}${rupees}.${fraction}`;
}

export function formatRegisterMoney(paise) {
  const { sign, rupees, fraction } = decimalParts(paise);
  return `${sign}₹${wholeRupees.format(rupees)}.${fraction}`;
}

function tenderAmounts(record) {
  const amount = parseRegisterMoney(record.amount);
  if (amount === null || amount === 0n) return null;
  const method = record.data?.payment_account ?? 'cash';
  if (method === 'cash') return { cash: amount, bank: 0n };
  if (method === 'bank') return { cash: 0n, bank: amount };
  if (method === 'split' && record.kind === 'pos') {
    const cash = parseRegisterMoney(record.data.cash_amount);
    const bank = parseRegisterMoney(record.data.bank_amount);
    if (cash > 0n && bank > 0n && cash + bank === amount) return { cash, bank };
  }
  return null;
}

function activePosting(record) {
  return record?.posted && !record.cancelled;
}

export function summarizePosDay(records, date) {
  const byId = new Map(records.map(record => [record.id, record]));
  const day = {
    saleCount: 0, refundCount: 0, cancelledCount: 0, unresolvedCount: 0,
    cashSales: 0n, bankSales: 0n, cashRefunds: 0n, bankRefunds: 0n, rows: [],
  };
  for (const record of records) {
    if (record.date !== date) continue;
    let source = record;
    const refund = record.kind === 'customer_refund';
    if (refund) {
      const credit = byId.get(record.data?.credit_note_id);
      source = credit?.kind === 'credit_note' ? byId.get(credit.data?.applied_to) : null;
      if (!activePosting(credit) || !activePosting(source)) continue;
    }
    if (source?.kind !== 'pos') continue;
    if (record.cancelled) {
      if (!refund) day.cancelledCount += 1;
      continue;
    }
    if (!activePosting(record)) continue;
    if (refund) day.refundCount += 1;
    else day.saleCount += 1;
    const tender = tenderAmounts(record);
    if (!tender) {
      day.unresolvedCount += 1;
      continue;
    }
    if (refund) {
      day.cashRefunds += tender.cash;
      day.bankRefunds += tender.bank;
    } else {
      day.cashSales += tender.cash;
      day.bankSales += tender.bank;
    }
    day.rows.push({
      kind: refund ? 'Refund' : 'Sale',
      number: record.number || record.id,
      receipt: source.number || source.id,
      ...tender,
    });
  }
  return day;
}

export const cashCountFields = [
  { key: 'openingFloat', label: 'Opening float', required: true },
  { key: 'cashIn', label: 'Other cash added' },
  { key: 'cashOut', label: 'Other cash removed' },
  { key: 'cashCounted', label: 'Cash counted', required: true },
];

export function reconcilePosCash(day, entries) {
  const invalidFields = [];
  const figures = {};
  for (const { key, required } of cashCountFields) {
    const value = entries[key]?.trim() || '';
    const amount = value || required ? parseRegisterMoney(value) : 0n;
    if (value && amount === null) invalidFields.push(key);
    figures[key] = amount;
  }
  const { openingFloat, cashIn, cashOut, cashCounted } = figures;
  const expected = day.unresolvedCount || [openingFloat, cashIn, cashOut].includes(null)
    ? null
    : openingFloat + day.cashSales - day.cashRefunds + cashIn - cashOut;
  return {
    ...figures,
    invalidFields,
    expected,
    variance: expected === null || cashCounted === null ? null : cashCounted - expected,
  };
}

function csvText(value) {
  const text = String(value ?? '');
  // Company names and document numbers can begin with spreadsheet formulas.
  const safe = /^[\s\u0000-\u001F]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)
    ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function posCloseCsv({ companyName, date, day, reconciliation }) {
  const { openingFloat, cashIn, cashOut, cashCounted, expected, variance } = reconciliation;
  if (variance === null) throw new Error('Enter valid drawer counts before exporting.');
  const header = [
    ['Company', csvText(companyName)],
    ['Business date', csvText(date)],
    ['Scope', 'Company-wide POS sales and linked refunds'],
    ['Posted sales', day.saleCount],
    ['Posted linked refunds', day.refundCount],
    ['Cancelled receipts excluded', day.cancelledCount],
    ['Figure', 'INR'],
  ];
  const totals = [
    ['Cash sales', day.cashSales], ['Cash refunds', day.cashRefunds],
    ['Bank / UPI / card sales', day.bankSales], ['Bank / UPI / card refunds', day.bankRefunds],
    ['Opening float', openingFloat], ['Other cash added', cashIn], ['Other cash removed', cashOut],
    ['Expected cash', expected], ['Counted cash', cashCounted], ['Cash over / short', variance],
  ].map(([label, value]) => [label, decimal(value)]);
  const detail = [
    ['Type', 'Document number', 'Original POS receipt', 'Cash (INR)', 'Bank / UPI / card (INR)'],
    ...day.rows.map(row => [row.kind, csvText(row.number), csvText(row.receipt), decimal(row.cash), decimal(row.bank)]),
  ];
  return '\ufeff' + [...header, ...totals, [], ...detail].map(row => row.join(',')).join('\r\n') + '\r\n';
}
