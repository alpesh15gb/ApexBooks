export const isActiveMaster = record => record?.data?.is_active !== false;
export function availableMasters(records, kind, retainedIds = []) {
  return records.filter(record => record.kind === kind && (isActiveMaster(record) || retainedIds.includes(record.id)));
}
export const partyShippingAddress = party => party?.data?.shipping_address || party?.data?.address || '';
/** Keep a deliberate delivery override; only replace blank/default-derived text. */
export function shippingForPartySelection(current, previousDefault, nextDefault) {
  return current === '' || current === previousDefault ? nextDefault : current;
}
