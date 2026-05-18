import { useState } from 'react';
import { usePayments } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { Table, MobileCards } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { PaymentForm } from './PaymentForm';
import { Plus, Banknote } from 'lucide-react';
import { formatCurrency, formatDate } from '@/utils/format';
import type { Payment } from '@/types';

export function PaymentsPage() {
  const { data, isLoading, error, refetch } = usePayments();
  const [showForm, setShowForm] = useState(false);
  const [paymentType, setPaymentType] = useState<'Receive' | 'Pay'>('Receive');

  const columns: Column<Payment>[] = [
    { key: 'date', header: 'Date', render: (p) => <span>{formatDate(p.payment_date)}</span> },
    { key: 'type', header: 'Type', render: (p) => (
      <span className={p.payment_type === 'Receive' ? 'text-emerald-600 font-medium' : 'text-red-600 font-medium'}>
        {p.payment_type === 'Receive' ? 'Received' : 'Paid'}
      </span>
    )},
    { key: 'party', header: 'Party', render: (p) => <span>{p.party_name || '-'}</span>, hideOnMobile: true },
    { key: 'amount', header: 'Amount', render: (p) => (
      <span className="font-semibold">{formatCurrency(p.amount)}</span>
    ), className: 'text-right' },
    { key: 'mode', header: 'Mode', render: (p) => <span className="text-gray-600">{p.payment_mode || '-'}</span>, hideOnMobile: true },
    { key: 'reference', header: 'Ref No', render: (p) => <span className="font-mono text-xs">{p.reference_no || '-'}</span>, hideOnMobile: true },
    { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payments"
        subtitle="Record and manage payments"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => { setPaymentType('Pay'); setShowForm(true); }}>
              Record Payment
            </Button>
            <Button onClick={() => { setPaymentType('Receive'); setShowForm(true); }}>
              <Plus className="h-4 w-4" />
              Receive Payment
            </Button>
          </div>
        }
      />

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : !data?.items?.length ? (
        <EmptyState
          title="No payments recorded"
          description="Record your first payment received or made."
          action={{ label: 'Record Payment', onClick: () => { setPaymentType('Receive'); setShowForm(true); } }}
          icon={<Banknote className="h-12 w-12" />}
        />
      ) : (
        <>
          <div className="hidden lg:block">
            <Table columns={columns} data={data.items} keyExtractor={(p) => p.payment_id || p.row_id || ''} />
          </div>
          <MobileCards columns={columns} data={data.items} keyExtractor={(p) => p.payment_id || p.row_id || ''} />
        </>
      )}

      <Modal isOpen={showForm} onClose={() => setShowForm(false)} title={paymentType === 'Receive' ? 'Receive Payment' : 'Make Payment'} size="lg">
        <PaymentForm
          paymentType={paymentType}
          onSuccess={() => { setShowForm(false); refetch(); }}
          onCancel={() => setShowForm(false)}
        />
      </Modal>
    </div>
  );
}