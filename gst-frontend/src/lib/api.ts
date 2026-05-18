import type {
  ApiError,
  AuditLog,
  DashboardStats,
  HsnCode,
  Invoice,
  Item,
  JournalEntry,
  Party,
  Payment,
  Account,
  CompanySettings,
  GstrSummary,
  TaxRate,
  User,
  PaginatedResponse,
  ReportData,
} from '@/types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const ACCESS_TOKEN_KEY = 'apexbooks_access_token';

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (typeof window !== 'undefined') {
    if (token) sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
    else sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getStoredAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const h: Record<string, string> = {
      'Content-Type': 'application/json',
      ...extra,
    };
    if (accessToken) {
      h['Authorization'] = `Bearer ${accessToken}`;
    }
    return h;
  }

  private async handleResponse<T>(res: Response): Promise<T> {
    const body = await readBody(res);

    if (!res.ok) {
      if (res.status === 401) {
        const refreshed = await this.tryRefresh();
        if (refreshed) {
          throw new RetryError();
        }
        clearAuth();
        window.location.href = '/login';
        throw new ApiClientError('Session expired. Please login again.', 401);
      }
      throw new ApiClientError(apiMessage(body, res.status), res.status, body);
    }

    if (res.status === 204) return undefined as T;
    return unwrapResponse<T>(body);
  }

  private async tryRefresh(): Promise<boolean> {
    if (refreshPromise) return refreshPromise;
    refreshPromise = this._doRefresh();
    const result = await refreshPromise;
    refreshPromise = null;
    return result;
  }

  private async _doRefresh(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
      });
      if (!res.ok) return false;
      const data = await res.json();
      const token = data?.data?.access_token || data?.access_token;
      if (token) {
        setAccessToken(token);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    params?: Record<string, string | number | boolean | undefined>,
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (params) {
      const searchParams = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== '') {
          searchParams.set(key, String(value));
        }
      }
      const qs = searchParams.toString();
      if (qs) url += `?${qs}`;
    }

    try {
      const res = await fetch(url, {
        method,
        headers: this.headers(),
        body: body ? JSON.stringify(body) : undefined,
      });
      return await this.handleResponse<T>(res);
    } catch (err) {
      if (err instanceof RetryError) {
        return this.request<T>(method, path, body, params);
      }
      if (err instanceof ApiClientError) throw err;
      throw new ApiClientError(
        'Network error. Please check your connection.',
        0,
      );
    }
  }

  get<T>(path: string, params?: Record<string, string | number | boolean | undefined>) {
    return this.request<T>('GET', path, undefined, params);
  }

  post<T>(path: string, body?: unknown) {
    return this.request<T>('POST', path, body);
  }

  put<T>(path: string, body?: unknown) {
    return this.request<T>('PUT', path, body);
  }

  delete<T>(path: string) {
    return this.request<T>('DELETE', path);
  }

  // ---- Auth ----
  login(email: string, password: string) {
    return this.post<{ access_token: string; refresh_token?: string; token_type?: string; tenant_id?: string }>('/auth/login', { email, password });
  }

  register(data: { email: string; password: string; full_name: string; company: Record<string, unknown> }) {
    return this.post<User>('/auth/register', data);
  }

  getMe() {
    return this.get<User>('/auth/me');
  }

  forgotPassword(email: string) {
    return this.post<{ message: string }>('/auth/forgot-password', { email });
  }

  resetPassword(data: { email: string; otp: string; new_password: string }) {
    return this.post<{ message: string }>('/auth/reset-password', data);
  }

  logout() {
    return this.post<{ message: string }>('/auth/logout');
  }

  // ---- Parties ----
  listParties(params?: { search?: string; type?: string; page?: number; page_size?: number }) {
    return this.get<unknown>('/parties', params as Record<string, string | number | boolean | undefined>).then(toPaginatedResponse<Party>);
  }

  getParty(id: string) {
    return this.get<Party>(`/parties/${id}`);
  }

  createParty(data: Partial<Party>) {
    return this.post<Party>('/parties', data);
  }

  updateParty(id: string, data: Partial<Party>) {
    return this.put<Party>(`/parties/${id}`, data);
  }

  deleteParty(id: string) {
    return this.delete<void>(`/parties/${id}`);
  }

  getPartyLedger(id: string) {
    return this.get<{ entries: unknown[]; balance: number }>(`/parties/${id}/ledger`);
  }

  getPartyOutstanding(id: string) {
    return this.get<{ outstanding: number }>(`/parties/${id}/outstanding`);
  }

  // ---- Items ----
  listItems(params?: { search?: string; page?: number; page_size?: number }) {
    return this.get<unknown>('/items', params as Record<string, string | number | boolean | undefined>).then(toPaginatedResponse<Item>);
  }

  getItem(id: string) {
    return this.get<Item>(`/items/${id}`);
  }

  createItem(data: Partial<Item>) {
    return this.post<Item>('/items', data);
  }

  updateItem(id: string, data: Partial<Item>) {
    return this.put<Item>(`/items/${id}`, data);
  }

  deleteItem(id: string) {
    return this.delete<void>(`/items/${id}`);
  }

  // ---- Invoices ----
  listInvoices(kind: 'sales' | 'purchase', params?: { status?: string; search?: string; page?: number; page_size?: number }) {
    return this.get<unknown>(`/invoices/${kind}`, { kind, ...params } as Record<string, string | number | boolean | undefined>).then(toPaginatedResponse<Invoice>);
  }

  getInvoice(kind: 'sales' | 'purchase', id: string) {
    return this.get<Invoice>(`/invoices/${kind}/${id}`, { kind });
  }

  createInvoice(kind: 'sales' | 'purchase', data: Partial<Invoice>) {
    return this.post<Invoice>(`/invoices/${kind}`, data);
  }

  updateInvoice(kind: 'sales' | 'purchase', id: string, data: Partial<Invoice>) {
    return this.put<Invoice>(`/invoices/${kind}/${id}`, data);
  }

  submitInvoice(kind: 'sales' | 'purchase', id: string) {
    return this.post<Invoice>(`/invoices/${kind}/${id}/submit`);
  }

  cancelInvoice(kind: 'sales' | 'purchase', id: string) {
    return this.post<Invoice>(`/invoices/${kind}/${id}/cancel`);
  }

  // ---- Payments ----
  listPayments(params?: { page?: number; page_size?: number }) {
    return this.get<unknown>('/payments', params as Record<string, string | number | boolean | undefined>).then(toPaginatedResponse<Payment>);
  }

  getPayment(id: string) {
    return this.get<Payment>(`/payments/${id}`);
  }

  receivePayment(data: Partial<Payment>) {
    return this.post<Payment>('/payments/receive', data);
  }

  makePayment(data: Partial<Payment>) {
    return this.post<Payment>('/payments/made', data);
  }

  updatePayment(id: string, data: Partial<Payment>) {
    return this.put<Payment>(`/payments/${id}`, data);
  }

  voidPayment(id: string) {
    return this.delete<void>(`/payments/${id}`);
  }

  reconcilePayment(id: string, allocations: { invoice_id: string; amount: number }[]) {
    return this.post<Payment>(`/payments/${id}/reconcile`, { allocations });
  }

  // ---- Journal ----
  listJournals(params?: { from_date?: string; to_date?: string; page?: number; page_size?: number }) {
    return this.get<unknown>('/accounts/journal', params as Record<string, string | number | boolean | undefined>).then(toPaginatedResponse<JournalEntry>);
  }

  getJournal(id: string) {
    return this.get<JournalEntry>(`/accounts/journal/${id}`);
  }

  createJournal(data: Partial<JournalEntry>) {
    return this.post<JournalEntry>('/accounts/journal', data);
  }

  // ---- Accounts (COA) ----
  listAccounts(params?: { search?: string }) {
    return this.get<unknown>('/accounts/coa', params as Record<string, string | number | boolean | undefined>).then((res) =>
      toArray<Account>(res).map((account) => ({
        ...account,
        id: account.id || account.code,
        is_active: account.is_active ?? true,
      })),
    );
  }

  getAccount(id: string) {
    return this.get<Account>(`/accounts/coa/${id}`);
  }

  createAccount(data: Partial<Account>) {
    return this.post<Account>('/accounts/coa', data);
  }

  updateAccount(id: string, data: Partial<Account>) {
    return this.put<Account>(`/accounts/coa/${id}`, data);
  }

  deleteAccount(id: string) {
    return this.delete<void>(`/accounts/coa/${id}`);
  }

  // ---- Reports ----
  getReport(name: string, params?: Record<string, string | number | boolean | undefined>) {
    return this.get<ReportData>(`/accounts/reports/${name}`, params);
  }

  // ---- Dashboard ----
  async getDashboard(): Promise<DashboardStats> {
    const [sales, purchases, receivables, payables, gstPayable] = await Promise.allSettled([
      this.listInvoices('sales'),
      this.listInvoices('purchase'),
      this.getReport('accounts-receivable'),
      this.getReport('accounts-payable'),
      this.getReport('gst-payable'),
    ]);

    const salesItems = settledValue(sales)?.items || [];
    const purchaseItems = settledValue(purchases)?.items || [];
    const receivablesReport = settledValue(receivables);
    const payablesReport = settledValue(payables);
    const gstReport = settledValue(gstPayable);

    return {
      total_sales: sumBy(salesItems, 'grand_total'),
      total_purchases: sumBy(purchaseItems, 'grand_total'),
      total_receivables: numberFrom(receivablesReport, ['total_receivable', 'total_receivables', 'balance']) || sumBy(salesItems, 'outstanding_amount'),
      total_payables: numberFrom(payablesReport, ['total_payable', 'total_payables', 'balance']) || sumBy(purchaseItems, 'outstanding_amount'),
      gst_payable: numberFrom(gstReport, ['gst_payable', 'total_payable', 'net_payable']),
      gst_credit: numberFrom(gstReport, ['gst_credit', 'itc_available', 'input_credit']),
      recent_invoices: [...salesItems, ...purchaseItems]
        .sort((a, b) => String(b.invoice_date || '').localeCompare(String(a.invoice_date || '')))
        .slice(0, 8),
      overdue_invoices: [...salesItems, ...purchaseItems]
        .filter((invoice) => invoice.payment_status === 'Overdue' || invoice.status === 'Overdue')
        .slice(0, 8),
    };
  }

  // ---- GST ----
  getHsnCodes(params?: { search?: string }) {
    return this.get<HsnCode[]>('/hsn-codes', params as Record<string, string | number | boolean | undefined>);
  }

  getTaxRates() {
    return this.get<TaxRate[]>('/tax-rates');
  }

  getGstr1(table: string, month: string, year: string) {
    return this.get<GstrSummary>(`/gst/gstr1/${table}/${month}/${year}`);
  }

  getGstr3b(path: string, month: string, year: string) {
    return this.get<GstrSummary>(`/gst/gstr3b/${path}/${month}/${year}`);
  }

  // ---- Settings ----
  getSettings() {
    return this.get<CompanySettings>('/settings/');
  }

  updateSettings(category: string, data: Record<string, unknown>) {
    return this.put<CompanySettings>(`/settings/${category}`, data);
  }

  // ---- Admin / Audit ----
  getAuditLogs(params?: { resource?: string; action?: string; limit?: number; offset?: number; start_date?: string; end_date?: string }) {
    return this.get<PaginatedResponse<AuditLog>>('/admin/audit-logs', params as Record<string, string | number | boolean | undefined>);
  }
}

class ApiClientError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.detail = detail;
  }
}

class RetryError extends Error {
  constructor() {
    super('Retry after refresh');
    this.name = 'RetryError';
  }
}

function clearAuth() {
  setAccessToken(null);
  if (typeof window !== 'undefined') {
    localStorage.removeItem('apexbooks_access_token');
    localStorage.removeItem('apexbooks_refresh_token');
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

export const api = new ApiClient(BASE_URL);
export { ApiClientError };

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function unwrapResponse<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body) {
    const envelope = body as { success?: boolean; data?: unknown; error?: unknown; message?: string };
    if (envelope.success === false) {
      throw new ApiClientError(apiMessage(body, 400), 400, envelope.error || body);
    }
    return envelope.data as T;
  }
  return body as T;
}

function apiMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const payload = body as {
      detail?: ApiError['detail'];
      message?: string;
      error?: { message?: string; code?: string; details?: unknown };
    };
    if (payload.error?.message) return payload.error.message;
    if (payload.message) return payload.message;
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) return payload.detail.map((d) => d.msg).join('; ');
  }
  if (status === 403) return 'You do not have permission to perform this action.';
  if (status === 422) return 'Please check the form values and try again.';
  if (status >= 500) return 'The server is temporarily unavailable. Please try again.';
  return `Request failed with status ${status}`;
}

function toPaginatedResponse<T>(data: unknown): PaginatedResponse<T> {
  if (Array.isArray(data)) {
    return { items: data as T[], total: data.length, page: 1, page_size: data.length, total_pages: 1 };
  }
  if (data && typeof data === 'object') {
    const payload = data as Record<string, unknown>;
    const items = Array.isArray(payload.items) ? payload.items : Array.isArray(payload.data) ? payload.data : [];
    return {
      items: items as T[],
      total: Number(payload.total ?? items.length),
      page: Number(payload.page ?? 1),
      page_size: Number(payload.page_size ?? items.length),
      total_pages: Number(payload.total_pages ?? 1),
    };
  }
  return { items: [], total: 0, page: 1, page_size: 0, total_pages: 1 };
}

function toArray<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).items)) {
    return (data as Record<string, unknown>).items as T[];
  }
  return [];
}

function settledValue<T>(result: PromiseSettledResult<T>): T | undefined {
  return result.status === 'fulfilled' ? result.value : undefined;
}

function sumBy<T>(items: T[], key: keyof T): number {
  return items.reduce((total, item) => total + Number((item[key] as unknown) || 0), 0);
}

function numberFrom(data: unknown, keys: string[]): number {
  if (!data || typeof data !== 'object') return 0;
  const payload = data as Record<string, unknown>;
  for (const key of keys) {
    const value = Number(payload[key]);
    if (!Number.isNaN(value) && value !== 0) return value;
  }
  return 0;
}
