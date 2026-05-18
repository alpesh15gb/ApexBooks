import { useState, useCallback } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useInvoices } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { SearchInput } from '@/components/ui/SearchInput';
import { StatusBadge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { Table, MobileCards } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { Tabs } from '@/components/ui/Tabs';
import { Plus, FileText, Receipt, CheckSquare, Send, Loader } from 'lucide-react';
import { formatCurrency, formatDate, daysOverdue } from '@/utils/format';
import type { Invoice } from '@/types';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';

const STATUS_TABS = [
  { id: '', label: 'All' },
  { id: 'Draft', label: 'Draft' },
  { id: 'Submitted', label: 'Submitted' },
  { id: 'Paid', label: 'Paid' },
  { id: 'Overdue', label: 'Overdue' },
];

export function InvoicesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const routeParams = useParams<{ kind: 'sales' | 'purchase' }>();
  const navigate = useNavigate();
  const kind = routeParams.kind === 'purchase' ? 'purchase' : 'sales';
  const status = searchParams.get('status') || '';
  const search = searchParams.get('search') || '';

  const { data, isLoading, error, refetch } = useInvoices(kind, status);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkSubmitting, setBulkSubmitting] = useState(false);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (!data?.items?.length) return;
    if (selectedIds.size === data.items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data.items.map((i: Invoice) => i.invoice_id || '').filter(Boolean)));
    }
  }, [data, selectedIds]);

  const handleBulkSubmit = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setBulkSubmitting(true);
    try {
      const res = await api.post('/invoices/bulk-submit', { invoice_ids: ids });
      const results = (res as any)?.results || [];
      const success = results.filter((r: any) => r.status === 'submitted').length;
      toast.success(`${success} of ${ids.length} submitted`);
      refetch();
      setSelectedIds(new Set());
    } catch (err: any) {
      toast.error(err?.message || 'Bulk submit failed');
    } finally {
      setBulkSubmitting(false);
    }
  }, [selectedIds, refetch]);

  const handleSearch = useCallback(
    (s: string) => {
      const params = new URLSearchParams(searchParams);
      if (s) params.set('search', s);
      else params.delete('search');
      setSearchParams(params);
    },
    [searchParams, setSearchParams],
  );

  const title = kind === 'sales' ? 'Sales Invoices' : 'Purchase Bills';
  const subtitle = kind === 'sales' ? 'Manage your sales invoices' : 'Manage your purchase bills';

  const tabs = [
    { id: 'sales', label: 'Sales' },
    { id: 'purchase', label: 'Purchases' },
  ];

  const columns: Column<Invoice>[] = [
    { key: 'select', header: '', render: (inv) => (
      <input type="checkbox" className="rounded border-gray-300" checked={selectedIds.has(inv.invoice_id || '')}
             onChange={(e) => { e.stopPropagation(); toggleSelect(inv.invoice_id || ''); }}
             onClick={(e) => e.stopPropagation()} />
    ), className: 'w-10' },
    { key: 'number', header: 'Invoice', render: (inv) => (
      <div>
        <p className="font-medium text-gray-900">{inv.invoice_number || 'N/A'}</p>
        <p className="text-xs text-gray-500">{formatDate(inv.invoice_date)}</p>
      </div>
    )},
    { key: 'party', header: 'Party', render: (inv) => (
      <span className="text-gray-700">{inv.party_name || '-'}</span>
    ), hideOnMobile: true },
    { key: 'amount', header: 'Amount', render: (inv) => (
      <span className="font-semibold">{formatCurrency(inv.grand_total)}</span>
    ), className: 'text-right' },
    { key: 'status', header: 'Status', render: (inv) => <StatusBadge status={inv.status} /> },
    { key: 'payment', header: 'Payment', render: (inv) => (
      <div>
        <StatusBadge status={inv.payment_status} />
        {inv.payment_status === 'Overdue' && inv.due_date && (
          <p className="text-xs text-red-600 mt-0.5">{daysOverdue(inv.due_date)}d overdue</p>
        )}
      </div>
    ), hideOnMobile: true },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Button onClick={() => navigate(`/invoices/${kind}/new`)}>
            <Plus className="h-4 w-4" />
            New {kind === 'sales' ? 'Invoice' : 'Bill'}
          </Button>
        }
      />

      <Tabs
        tabs={tabs}
        active={kind}
        onChange={(id) => {
          navigate(`/invoices/${id}`);
        }}
      />

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="w-full max-w-xs">
          <SearchInput value={search} onChange={handleSearch} placeholder={`Search ${title.toLowerCase()}...`} />
        </div>
        <Tabs
          tabs={STATUS_TABS}
          active={status}
          onChange={(id) => {
            const params = new URLSearchParams(searchParams);
            if (id) params.set('status', id);
            else params.delete('status');
            setSearchParams(params);
          }}
        />
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : !data?.items?.length ? (
        <EmptyState
          title={`No ${kind === 'sales' ? 'invoices' : 'bills'} found`}
          description={kind === 'sales' ? 'Create your first sales invoice.' : 'Record your first purchase bill.'}
          action={{ label: `New ${kind === 'sales' ? 'Invoice' : 'Bill'}`, onClick: () => navigate(`/invoices/${kind}/new`) }}
          icon={kind === 'sales' ? <FileText className="h-12 w-12" /> : <Receipt className="h-12 w-12" />}
        />
      ) : (
        <>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-3 px-4 py-2 bg-brand-50 rounded-lg border border-brand-200">
              <CheckSquare className="h-4 w-4 text-brand-600" />
              <span className="text-sm font-medium text-brand-700">{selectedIds.size} selected</span>
              <Button size="sm" onClick={handleBulkSubmit} loading={bulkSubmitting}>
                <Send className="h-4 w-4" /> Submit Selected
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>Clear</Button>
            </div>
          )}
          <div className="hidden lg:block">
            <Table
              columns={columns}
              data={data.items}
              keyExtractor={(inv) => inv.invoice_id || inv.row_id || ''}
              onRowClick={(inv) => navigate(`/invoices/${kind}/${inv.invoice_id}`)}
            />
          </div>
          <MobileCards
            columns={columns}
            data={data.items}
            keyExtractor={(inv) => inv.invoice_id || inv.row_id || ''}
            onRowClick={(inv) => navigate(`/invoices/${kind}/${inv.invoice_id}`)}
          />
        </>
      )}
    </div>
  );
}
