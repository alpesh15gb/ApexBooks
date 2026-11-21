// discount_amount is an INPUT; calculated `discount` is never a substitute.
// Presence matters: an explicit zero fixed discount still opens in rupee mode.
export function lineDiscountMode(line) {
  return Object.hasOwn(line, 'discount_amount') ? 'amount' : 'percent';
}
export function serializeLineDiscount(line) {
  const result = { ...line };
  if (lineDiscountMode(line) === 'amount') {
    delete result.discount_percent;
    result.discount_amount = String(line.discount_amount ?? '0');
  } else {
    delete result.discount_amount;
    result.discount_percent = String(line.discount_percent ?? '0');
  }
  return result;
}
export function changeLineDiscount(line, field, value) {
  if (field === 'discount_mode') {
    const result = { ...line };
    delete result.discount_percent; delete result.discount_amount;
    // Switching is a deliberate new input, never a percentage/rupee conversion.
    return { ...result, [value === 'amount' ? 'discount_amount' : 'discount_percent']: '0' };
  }
  return serializeLineDiscount({ ...line, [field]: value });
}
