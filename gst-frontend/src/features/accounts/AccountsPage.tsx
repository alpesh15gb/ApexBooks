import { useState } from 'react';
import { useAccounts, useCreateAccount, useDeleteAccount } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Modal } from '@/components/ui/Modal';
import { Table, MobileCards } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { AccountForm } from './AccountForm';
import { Plus, Edit, Trash2, Calculator } from 'lucide-react';
import type { Account } from '@/types';

export function AccountsPage() {
  const { data, isLoading, error, refetch } = useAccounts();
  const deleteMutation = useDeleteAccount();

  const [showForm, setShowForm] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!deleteId) return;
    await deleteMutation.mutateAsync(deleteId);
    setDeleteId(null);
  };

  const columns: Column<Account>[] = [
    { key: 'code', header: 'Code', render: (a) => <span className="font-mono text-xs font-medium">{a.code}</span> },
    { key: 'name', header: 'Account Name', render: (a) => <span className="font-medium">{a.name}</span> },
    { key: 'type', header: 'Type', render: (a) => <Badge variant="neutral">{a.account_type}</Badge> },
    { key: 'status', header: 'Status', render: (a) => (
      <Badge variant={a.is_active !== false ? 'success' : 'default'}>{a.is_active !== false ? 'Active' : 'Inactive'}</Badge>
    ) },
    { key: 'actions', header: '', render: (a) => (
      <div className="flex items-center gap-1 justify-end" onClick={(e) => e.stopPropagation()}>
        <Button variant="ghost" size="sm" onClick={() => { setEditingAccount(a); setShowForm(true); }}>
          <Edit className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" onClick={() => a.id && setDeleteId(a.id)}>
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      </div>
    ), className: 'text-right' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Chart of Accounts"
        subtitle="Manage your accounting chart of accounts"
        actions={
          <Button onClick={() => { setEditingAccount(null); setShowForm(true); }}>
            <Plus className="h-4 w-4" />
            Add Account
          </Button>
        }
      />

      {isLoading ? <TableSkeleton /> : error ? <ErrorState onRetry={refetch} /> : !data?.length ? (
        <EmptyState title="No accounts" description="Create your first account." action={{ label: 'Add Account', onClick: () => setShowForm(true) }} icon={<Calculator className="h-12 w-12" />} />
      ) : (
        <>
          <div className="hidden lg:block">
            <Table columns={columns} data={data} keyExtractor={(a) => a.id || a.row_id || ''} />
          </div>
          <MobileCards columns={columns} data={data} keyExtractor={(a) => a.id || a.row_id || ''} />
        </>
      )}

      <Modal isOpen={showForm} onClose={() => { setShowForm(false); setEditingAccount(null); }} title={editingAccount ? 'Edit Account' : 'Add Account'}>
        <AccountForm account={editingAccount} onSuccess={() => { setShowForm(false); setEditingAccount(null); refetch(); }} onCancel={() => { setShowForm(false); setEditingAccount(null); }} />
      </Modal>

      <ConfirmDialog isOpen={!!deleteId} onConfirm={handleDelete} onCancel={() => setDeleteId(null)} title="Delete account" message="Are you sure?" confirmLabel="Delete" loading={deleteMutation.isPending} />
    </div>
  );
}