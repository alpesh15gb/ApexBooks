export const CORE_ENHANCEMENTS = ['low_stock_reorder','party_price_history','party_payment_terms','master_lifecycle','party_shipping_address','party_credit_limits','recurring_drafts','company_book_labels'];
export const supportsFeature = (features, name) => Array.isArray(features) && features.includes(name);
export const routeFeature = { reorder: 'low_stock_reorder', recurring: 'recurring_drafts' };
export function capabilityFeatures(response) {
  return response?.capabilities_version >= 1 && Array.isArray(response.supported_features)
    ? response.supported_features.filter(value => typeof value === 'string') : [];
}
export function supportedMasterData(data, features) {
  const result = { ...data };
  for (const [field, feature] of Object.entries({is_active:'master_lifecycle',shipping_address:'party_shipping_address',credit_limit:'party_credit_limits',payment_terms_days:'party_payment_terms',low_stock_threshold:'low_stock_reorder'})) {
    if (!supportsFeature(features, feature)) delete result[field];
  }
  return result;
}
export function companyDisplayName(company, companies = []) {
  if (!company) return '';
  const base = row => row.book_label?.trim() ? `${row.name} · ${row.book_label.trim()}` : row.name;
  const display = base(company);
  const duplicates = companies.filter(row => base(row)?.trim().toLowerCase() === display?.trim().toLowerCase());
  if (duplicates.length < 2) return display;
  const suffix = String(company.id).slice(-8);
  const identifier = duplicates.filter(row => String(row.id).slice(-8) === suffix).length > 1 ? company.id : suffix;
  return `${display} · Book ${identifier}`;
}
export function companyUpdatePayload(form, features) {
  const { book_label, ...legal } = form;
  return supportsFeature(features, 'company_book_labels') ? { ...legal, book_label: String(book_label || '').trim() } : legal;
}
