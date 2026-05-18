export const GSTIN_REGEX = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/;
export const PAN_REGEX = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;
export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const PINCODE_REGEX = /^[0-9]{6}$/;
export const IFSC_REGEX = /^[A-Z]{4}0[A-Z0-9]{6}$/;
export const PHONE_REGEX = /^[0-9]{10}$/;
export const STATE_CODE_REGEX = /^[0-9]{2}$/;

export function isValidGstin(gstin: string): boolean {
  return GSTIN_REGEX.test(gstin.toUpperCase());
}

export function isValidPan(pan: string): boolean {
  return PAN_REGEX.test(pan.toUpperCase());
}

export function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email);
}

export function isValidPincode(pincode: string): boolean {
  return PINCODE_REGEX.test(pincode);
}

export function isValidPhone(phone: string): boolean {
  return PHONE_REGEX.test(phone.replace(/\s/g, ''));
}

export function isValidIfsc(ifsc: string): boolean {
  return IFSC_REGEX.test(ifsc.toUpperCase());
}

export function apiErrorToString(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err instanceof Error) return err.message;
  if (err && typeof err === 'object') {
    const e = err as Record<string, unknown>;
    if (typeof e.detail === 'string') return e.detail;
    if (Array.isArray(e.detail)) {
      return (e.detail as Array<{ msg: string }>)
        .map((d) => d.msg)
        .join('; ');
    }
    if (typeof e.message === 'string') return e.message;
  }
  return 'An unexpected error occurred';
}

export const STATE_CODES: Record<string, string> = {
  '01': 'Jammu & Kashmir',
  '02': 'Himachal Pradesh',
  '03': 'Punjab',
  '04': 'Chandigarh',
  '05': 'Uttarakhand',
  '06': 'Haryana',
  '07': 'Delhi',
  '08': 'Rajasthan',
  '09': 'Uttar Pradesh',
  '10': 'Bihar',
  '11': 'Sikkim',
  '12': 'Arunachal Pradesh',
  '13': 'Nagaland',
  '14': 'Manipur',
  '15': 'Mizoram',
  '16': 'Tripura',
  '17': 'Meghalaya',
  '18': 'Assam',
  '19': 'West Bengal',
  '20': 'Jharkhand',
  '21': 'Odisha',
  '22': 'Chhattisgarh',
  '23': 'Madhya Pradesh',
  '24': 'Gujarat',
  '25': 'Daman & Diu',
  '26': 'Dadra & Nagar Haveli',
  '27': 'Maharashtra',
  '28': 'Andhra Pradesh',
  '29': 'Karnataka',
  '30': 'Goa',
  '31': 'Lakshadweep',
  '32': 'Kerala',
  '33': 'Tamil Nadu',
  '34': 'Puducherry',
  '35': 'Andaman & Nicobar',
  '36': 'Telangana',
  '37': 'Andhra Pradesh (New)',
  '38': 'Ladakh',
};

export const BUSINESS_TYPES = [
  'Retail',
  'Wholesale',
  'Manufacturing',
  'Services',
  'E-commerce',
  'Professional',
  'Others',
];

export const REGISTRATION_TYPES = [
  'Regular',
  'Composition',
  'Unregistered',
  'SEZ',
  'Deemed Export',
];

export const ACCOUNT_TYPES = [
  'Asset',
  'Current Asset',
  'Fixed Asset',
  'Bank',
  'Cash',
  'Liability',
  'Current Liability',
  'Long Term Liability',
  'GST Payable',
  'TDS Payable',
  'Equity',
  'Capital',
  'Retained Earnings',
  'Income',
  'Revenue',
  'Sales',
  'Service Revenue',
  'Expense',
  'Cost of Goods Sold',
  'Purchase',
  'Rent',
  'Salary',
  'Depreciation',
];

export const ITEM_TYPES = ['Goods', 'Service', 'Capital Goods'];

export const PAYMENT_MODES = [
  'Cash',
  'Bank Transfer',
  'Cheque',
  'UPI',
  'Credit Card',
  'Debit Card',
  'Online Payment',
  'Others',
];

export const SUPPLY_TYPES = ['B2B', 'B2C', 'SEZ', 'Deemed Export', 'Export'];

export const INVOICE_TYPES = ['Regular', 'Export', 'SEZ'];

export const UNITS = [
  'Nos', 'Kg', 'Gram', 'Meter', 'Liter', 'Box', 'Pack', 'Piece',
  'Dozen', 'Set', 'Hour', 'Day', 'Month', 'Year', 'Service',
];