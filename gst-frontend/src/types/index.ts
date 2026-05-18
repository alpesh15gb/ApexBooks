export interface User {
  user_id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  company: CompanyCreate;
}

export interface CompanyCreate {
  company_name: string;
  gstin: string;
  pan?: string;
  state_code: string;
  address: Address;
  business_type: string;
  registration_type?: string;
  fiscal_year_start?: string;
  e_invoice_applicable?: boolean;
  e_way_bill_applicable?: boolean;
}

export interface Address {
  type?: string;
  line1: string;
  line2?: string;
  city: string;
  pincode: string;
  state_code: string;
  state_name?: string;
  country?: string;
}

export interface Contact {
  name: string;
  email?: string;
  phone?: string;
  designation?: string;
  is_primary?: boolean;
}

export interface BankAccount {
  bank_name: string;
  account_no: string;
  ifsc?: string;
  account_type?: string;
}

export type PartyType = 'Customer' | 'Vendor';
export type InvoiceKind = 'sales' | 'purchase';
export type PaymentType = 'Receive' | 'Pay';
export type InvoiceStatus = 'Draft' | 'Submitted' | 'Paid' | 'Partially Paid' | 'Overdue' | 'Cancelled' | 'Amended' | 'Void';
export type PaymentStatus = 'Unpaid' | 'Partially Paid' | 'Paid' | 'Overdue';

export interface Party {
  row_id?: number;
  tenant_id?: string;
  id?: string;
  party_id?: string;
  party_type: PartyType;
  party_name: string;
  gstin?: string;
  pan?: string;
  party_category?: string;
  registration_type?: string;
  state_code?: string;
  credit_limit?: number;
  credit_days?: number;
  opening_balance?: number;
  tds_applicable?: boolean;
  tds_section?: string;
  currency?: string;
  opening_balance_date?: string;
  tags?: string[];
  addresses?: Address[];
  contacts?: Contact[];
  bank_accounts?: BankAccount[];
  custom_fields?: Record<string, unknown>;
  is_deleted?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Item {
  row_id?: number;
  id?: string;
  item_id?: string;
  item_code: string;
  item_name: string;
  item_type: string;
  hsn_code?: string;
  sac_code?: string;
  unit_of_measure?: string;
  gst_rate?: number;
  cess_rate?: number;
  selling_price?: number;
  purchase_price?: number;
  description?: string;
  is_nil_rated?: boolean;
  is_exempt?: boolean;
  is_non_gst?: boolean;
  stock_keeping_unit?: boolean;
  custom_fields?: Record<string, unknown>;
  is_deleted?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface InvoiceLine {
  id?: number;
  line_no: number;
  item_id?: string;
  item_code?: string;
  item_name: string;
  hsn_code?: string;
  sac_code?: string;
  quantity: number;
  unit?: string;
  unit_price: number;
  discount_amount?: number;
  discount_percent?: number;
  taxable_value?: number;
  gst_rate?: number;
  cgst_amount?: number;
  sgst_amount?: number;
  igst_amount?: number;
  cess_amount?: number;
  total_amount?: number;
}

export interface Invoice {
  row_id?: number;
  id?: string;
  invoice_id?: string;
  invoice_kind: InvoiceKind;
  invoice_number?: string;
  invoice_type?: string;
  invoice_date: string;
  due_date?: string;
  party_id?: string;
  party_name?: string;
  party_gstin?: string;
  place_of_supply?: string;
  supply_type?: string;
  reverse_charge?: boolean;
  subtotal?: number;
  total_discount?: number;
  total_cgst?: number;
  total_sgst?: number;
  total_igst?: number;
  total_cess?: number;
  round_off?: number;
  grand_total?: number;
  amount_paid?: number;
  outstanding_amount?: number;
  status?: InvoiceStatus;
  payment_status?: PaymentStatus;
  irn?: string;
  e_invoice_status?: string;
  eway_bill_no?: string;
  billing_address?: Address;
  shipping_address?: Address;
  notes?: string;
  custom_fields?: Record<string, unknown>;
  lines?: InvoiceLine[];
  created_at?: string;
  updated_at?: string;
}

export interface Payment {
  row_id?: number;
  id?: string;
  payment_id?: string;
  payment_type: PaymentType;
  payment_mode?: string;
  payment_date: string;
  party_id?: string;
  party_name?: string;
  amount: number;
  tds_amount?: number;
  net_amount?: number;
  reference_no?: string;
  narration?: string;
  allocations?: PaymentAllocation[];
  status?: string;
  currency?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PaymentAllocation {
  invoice_id: string;
  amount: number;
}

export interface JournalEntry {
  row_id?: number;
  id?: string;
  entry_date: string;
  reference?: string;
  narration?: string;
  entries: JournalLine[];
  total_debit?: number;
  total_credit?: number;
  created_at?: string;
}

export interface JournalLine {
  account: string;
  debit: number;
  credit: number;
}

export interface Account {
  row_id?: number;
  id?: string;
  code: string;
  name: string;
  account_type: string;
  is_active?: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface AuditLog {
  row_id?: number;
  id?: string;
  resource?: string;
  action?: string;
  actor_id?: string;
  details?: Record<string, unknown>;
  created_at?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  detail: string | ValidationErrorDetail[];
}

export interface ValidationErrorDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface DashboardStats {
  total_sales?: number;
  total_purchases?: number;
  total_receivables?: number;
  total_payables?: number;
  bank_balance?: number;
  cash_balance?: number;
  gst_payable?: number;
  gst_credit?: number;
  recent_invoices?: Invoice[];
  overdue_invoices?: Invoice[];
  sales_trend?: { date: string; amount: number }[];
}

export interface CompanySettings {
  business: Record<string, unknown>;
  invoice: Record<string, unknown>;
  gst: Record<string, unknown>;
  accounting: Record<string, unknown>;
  inventory: Record<string, unknown>;
  payments: Record<string, unknown>;
  [key: string]: Record<string, unknown>;
}

export interface HsnCode {
  code: string;
  description: string;
  gst_rate: number;
}

export interface TaxRate {
  rate: number;
  type: string;
}

export interface GstrSummary {
  [key: string]: unknown;
}

export interface ReportData {
  [key: string]: unknown;
}