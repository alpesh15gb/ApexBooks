// Compare decimal values exactly, including equivalent exponent notation, without
// converting accounting amounts through binary floating-point arithmetic.
function decimalIdentity(value) {
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  const match = String(value).trim().match(/^\+?(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/);
  if (!match) return null;
  const integer = match[1] || '0';
  const fraction = match[2] || match[3] || '';
  const significant = (integer + fraction).replace(/^0+/, '');
  const coefficient = significant.replace(/0+$/, '');
  if (!coefficient || coefficient.length > 100) return null;
  const exponent = Number(match[4] || 0) - fraction.length + significant.length - coefficient.length;
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 1000) return null;
  return `${coefficient}e${exponent}`;
}

export function verifySettlementResponse(response, { family, action, paymentKind, sourceId, body }) {
  const application = action === 'apply';
  const kind = family === 'advance'
    ? application ? 'advance_application' : 'advance_refund'
    : application ? 'credit_application' : paymentKind === 'payment_in' ? 'customer_refund' : 'supplier_refund';
  const sourceField = family === 'advance' ? 'advance_id' : 'credit_note_id';
  const amount = decimalIdentity(body.amount);
  const data = response?.data;
  if (!response || typeof response.id !== 'string' || !response.id.trim() || response.id.trim() === 'null' || response.posted !== true ||
      response.kind !== kind || response.date !== body.date || !amount || decimalIdentity(response.amount) !== amount ||
      !data || data[sourceField] !== sourceId ||
      ((application || family === 'advance') && data.payment_kind !== paymentKind) ||
      (application && data.applied_to !== body.data.applied_to) ||
      (!application && (data.payment_account !== body.data.payment_account ||
        data.bank_account_id !== (body.data.bank_account_id || 'default')))) {
    throw new Error('The settlement response could not be verified. Keep this request and retry to recover its confirmed result.');
  }
  return response;
}
