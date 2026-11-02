/** Copy catalogue tax identity into an unposted, unrelated purchase-order seed. */
export function reorderDraft(rows, records) {
  return { data: { lines: rows.map(row => {
    const item = records.find(item => item.id === row.item_id && item.kind === 'item');
    if (!item) throw new Error('Wait for the item catalogue to finish loading, then review the order again.');
    if (item.data?.is_active === false) throw new Error('An item is now inactive. Refresh the reorder review before continuing.');
    return { item_id: row.item_id, description: row.name, unit: row.unit, quantity: row.quantity,
      rate: row.purchase_rate || '0', gst_rate: item.data?.gst_rate || '0', hsn: item.data?.hsn || '',
      tax_treatment: item.data?.tax_treatment || (Number(item.data?.gst_rate || 0) ? 'taxable' : 'nil_rated'),
      discount_percent: '0', price_includes_tax: false };
  }) } };
}
