import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import type {
  Party,
  Item,
  Invoice,
  Payment,
  JournalEntry,
  Account,
} from '@/types';
import toast from 'react-hot-toast';
import { apiErrorToString } from '@/utils/validation';

function useList<T>(key: string[], fn: () => Promise<T>) {
  return useQuery<T>({ queryKey: key, queryFn: fn });
}

function useMutate<TData, TArgs>(
  fn: (args: TArgs) => Promise<TData>,
  invalidateKeys: string[][],
  successMsg?: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      invalidateKeys.forEach((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      );
      if (successMsg) toast.success(successMsg);
    },
    onError: (err) => {
      toast.error(apiErrorToString(err));
    },
  });
}

// ---- Parties ----
export function useParties(search?: string, type?: string) {
  return useList(['parties', search || '', type || ''], () =>
    api.listParties({ search, type }),
  );
}

export function useParty(id: string) {
  return useQuery({
    queryKey: ['party', id],
    queryFn: () => api.getParty(id),
    enabled: !!id,
  });
}

export function useCreateParty() {
  return useMutate(
    (data: Partial<Party>) => api.createParty(data),
    [['parties']],
    'Party created successfully',
  );
}

export function useUpdateParty() {
  return useMutate(
    ({ id, data }: { id: string; data: Partial<Party> }) =>
      api.updateParty(id, data),
    [['parties'], ['party']],
    'Party updated successfully',
  );
}

export function useDeleteParty() {
  return useMutate(
    (id: string) => api.deleteParty(id),
    [['parties']],
    'Party deleted successfully',
  );
}

// ---- Items ----
export function useItems(search?: string) {
  return useList(['items', search || ''], () => api.listItems({ search }));
}

export function useItem(id: string) {
  return useQuery({
    queryKey: ['item', id],
    queryFn: () => api.getItem(id),
    enabled: !!id,
  });
}

export function useCreateItem() {
  return useMutate(
    (data: Partial<Item>) => api.createItem(data),
    [['items']],
    'Item created successfully',
  );
}

export function useUpdateItem() {
  return useMutate(
    ({ id, data }: { id: string; data: Partial<Item> }) =>
      api.updateItem(id, data),
    [['items'], ['item']],
    'Item updated successfully',
  );
}

export function useDeleteItem() {
  return useMutate(
    (id: string) => api.deleteItem(id),
    [['items']],
    'Item deleted successfully',
  );
}

// ---- Invoices ----
export function useInvoices(kind: 'sales' | 'purchase', status?: string) {
  return useList(['invoices', kind, status || ''], () =>
    api.listInvoices(kind, { status }),
  );
}

export function useInvoice(kind: 'sales' | 'purchase', id: string) {
  return useQuery({
    queryKey: ['invoice', kind, id],
    queryFn: () => api.getInvoice(kind, id),
    enabled: !!id,
  });
}

export function useCreateInvoice() {
  return useMutate(
    ({ kind, data }: { kind: 'sales' | 'purchase'; data: Partial<Invoice> }) =>
      api.createInvoice(kind, data),
    [['invoices']],
    'Invoice created successfully',
  );
}

export function useUpdateInvoice() {
  return useMutate(
    ({
      kind,
      id,
      data,
    }: {
      kind: 'sales' | 'purchase';
      id: string;
      data: Partial<Invoice>;
    }) => api.updateInvoice(kind, id, data),
    [['invoices'], ['invoice']],
    'Invoice updated successfully',
  );
}

export function useSubmitInvoice() {
  return useMutate(
    ({ kind, id }: { kind: 'sales' | 'purchase'; id: string }) =>
      api.submitInvoice(kind, id),
    [['invoices'], ['invoice']],
    'Invoice submitted successfully',
  );
}

export function useCancelInvoice() {
  return useMutate(
    ({ kind, id }: { kind: 'sales' | 'purchase'; id: string }) =>
      api.cancelInvoice(kind, id),
    [['invoices'], ['invoice']],
    'Invoice cancelled successfully',
  );
}

// ---- Payments ----
export function usePayments() {
  return useList(['payments'], () => api.listPayments());
}

export function usePayment(id: string) {
  return useQuery({
    queryKey: ['payment', id],
    queryFn: () => api.getPayment(id),
    enabled: !!id,
  });
}

export function useReceivePayment() {
  return useMutate(
    (data: Partial<Payment>) => api.receivePayment(data),
    [['payments']],
    'Payment received successfully',
  );
}

export function useMakePayment() {
  return useMutate(
    (data: Partial<Payment>) => api.makePayment(data),
    [['payments']],
    'Payment made successfully',
  );
}

// ---- Journal ----
export function useJournals() {
  return useList(['journals'], () => api.listJournals());
}

export function useJournal(id: string) {
  return useQuery({
    queryKey: ['journal', id],
    queryFn: () => api.getJournal(id),
    enabled: !!id,
  });
}

export function useCreateJournal() {
  return useMutate(
    (data: Partial<JournalEntry>) => api.createJournal(data),
    [['journals']],
    'Journal entry created successfully',
  );
}

// ---- Accounts ----
export function useAccounts(search?: string) {
  return useList(['accounts', search || ''], () =>
    api.listAccounts({ search }),
  );
}

export function useCreateAccount() {
  return useMutate(
    (data: Partial<Account>) => api.createAccount(data),
    [['accounts']],
    'Account created successfully',
  );
}

export function useUpdateAccount() {
  return useMutate(
    ({ id, data }: { id: string; data: Partial<Account> }) =>
      api.updateAccount(id, data),
    [['accounts']],
    'Account updated successfully',
  );
}

export function useDeleteAccount() {
  return useMutate(
    (id: string) => api.deleteAccount(id),
    [['accounts']],
    'Account deleted successfully',
  );
}

// ---- Dashboard ----
export function useDashboard() {
  return useList(['dashboard'], () => api.getDashboard());
}

// ---- GST ----
export function useHsnCodes(search?: string) {
  return useList(['hsn-codes', search || ''], () =>
    api.getHsnCodes({ search }),
  );
}

export function useTaxRates() {
  return useList(['tax-rates'], () => api.getTaxRates());
}

// ---- Settings ----
export function useSettings() {
  return useList(['settings'], () => api.getSettings());
}

export function useUpdateSettings() {
  return useMutate(
    ({ category, data }: { category: string; data: Record<string, unknown> }) =>
      api.updateSettings(category, data),
    [['settings']],
    'Settings saved successfully',
  );
}

// ---- Audit ----
export function useAuditLogs() {
  return useList(['audit-logs'], () => api.getAuditLogs());
}

// ---- Reports ----
export function useReport(name: string, params?: Record<string, string | number | boolean | undefined>) {
  return useList(['report', name], () => api.getReport(name, params));
}
