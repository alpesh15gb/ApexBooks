// Setup checklist steps (plain JS so it can be unit-tested).
export function setupSteps({ company, records, branding }) {
  const parties = records.filter(row => row.kind === 'party').length;
  const items = records.filter(row => row.kind === 'item').length;
  const invoices = records.filter(row => ['sales_invoice', 'pos'].includes(row.kind) && row.posted && !row.cancelled).length;
  const registered = company?.tax_mode === 'regular' || company?.tax_mode === 'composition';
  const business = !!company?.address?.trim() && (!registered || !!company?.gstin);
  const paymentDetails = !!(branding && (branding.bank_name || branding.account_number || branding.upi_id));
  return [
    { key: 'business', title: 'Business details', note: business ? (registered ? 'Address and GSTIN appear on your documents.' : 'Your address appears on your documents.') : registered ? 'Add your business address and GSTIN to your documents.' : 'Add your address so it prints on invoices.', complete: business, go: 'settings', label: business ? 'Review' : 'Add details' },
    { key: 'payment', title: 'Bank & UPI on invoices', note: paymentDetails ? 'Bank / UPI details print on invoices' : 'Add bank account and UPI ID so customers can pay you.', complete: paymentDetails, go: 'settings', label: paymentDetails ? 'Review' : 'Add bank & UPI' },
    { key: 'party', title: 'Customers & suppliers', note: parties ? `${parties} ${parties === 1 ? "party" : "parties"} ready` : 'Save contacts once, use them on every document.', complete: parties > 0, create: 'party', go: 'party', label: parties ? 'View parties' : 'Add a party' },
    { key: 'item', title: 'Items & services', note: items ? `${items} ${items === 1 ? "item" : "items"} in your catalogue` : 'Set prices, tax and optional stock tracking.', complete: items > 0, create: 'item', go: 'item', label: items ? 'View catalogue' : 'Add an item' },
    { key: 'invoice', title: 'First invoice', note: invoices ? `${invoices} ${invoices === 1 ? "invoice" : "invoices"} posted` : 'Bill a customer and share it on WhatsApp.', complete: invoices > 0, create: 'sales_invoice', go: 'sales_invoice', label: invoices ? 'View invoices' : 'Create invoice' },
  ];
}
