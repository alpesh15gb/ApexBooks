import { useState } from 'react';
import { useJournals, useCreateJournal } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { Modal } from '@/components/ui/Modal';
import { Table, MobileCards } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { Plus, BookOpen } from 'lucide-react';
import { formatCurrency, formatDate } from '@/utils/format';
import type { JournalEntry } from '@/types';
import { JournalForm } from './JournalForm';

export function JournalPage() {
  const { data, isLoading, error, refetch } = useJournals();
  const [showForm, setShowForm] = useState(false);

  const columns: Column<JournalEntry>[] = [
    { key: 'date', header: 'Date', render: (j) => <span>{formatDate(j.entry_date)}</span> },
    { key: 'reference', header: 'Reference', render: (j) => <span className="font-mono text-xs">{j.reference || '-'}</span> },
    { key: 'narration', header: 'Narration', render: (j) => <span className="text-gray-600 max-w-[200px] truncate block">{j.narration || '-'}</span> },
    { key: 'debit', header: 'Total Debit', render: (j) => <span className="font-medium text-red-600">{formatCurrency(j.total_debit)}</span>, className: 'text-right' },
    { key: 'credit', header: 'Total Credit', render: (j) => <span className="font-medium text-emerald-600">{formatCurrency(j.total_credit)}</span>, className: 'text-right' },
    { key: 'balanced', header: '', render: (j) => (
      j.total_debit === j.total_credit
        ? <Badge variant="success">Balanced</Badge>
        : <Badge variant="danger">Unbalanced</Badge>
    ) },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Journal Entries"
        subtitle="Record accounting journal entries"
        actions={
          <Button onClick={() => setShowForm(true)}>
            <Plus className="h-4 w-4" />
            New Entry
          </Button>
        }
      />

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : !data?.items?.length ? (
        <EmptyState
          title="No journal entries"
          description="Create your first journal entry."
          action={{ label: 'New Entry', onClick: () => setShowForm(true) }}
          icon={<BookOpen className="h-12 w-12" />}
        />
      ) : (
        <>
          <div className="hidden lg:block">
            <Table columns={columns} data={data.items} keyExtractor={(j) => j.row_id || ''} />
          </div>
          <MobileCards columns={columns} data={data.items} keyExtractor={(j) => j.row_id || ''} />
        </>
      )}

      <Modal isOpen={showForm} onClose={() => setShowForm(false)} title="New Journal Entry" size="xl">
        <JournalForm onSuccess={() => { setShowForm(false); refetch(); }} onCancel={() => setShowForm(false)} />
      </Modal>
    </div>
  );
}