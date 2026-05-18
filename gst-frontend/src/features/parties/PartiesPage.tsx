import { useState, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useParties, useDeleteParty } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { SearchInput } from '@/components/ui/SearchInput';
import { Badge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Tabs } from '@/components/ui/Tabs';
import { Modal } from '@/components/ui/Modal';
import { Plus, Edit, Trash2, UserPlus } from 'lucide-react';
import { PartyForm } from './PartyForm';
import type { Party } from '@/types';
import { formatCurrency, formatGstin, formatPhone } from '@/utils/format';
import toast from 'react-hot-toast';
import { Table, MobileCards } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';

export function PartiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const type = searchParams.get('type') || 'Customer';
  const search = searchParams.get('search') || '';

  const { data, isLoading, error, refetch } = useParties(search, type);
  const deleteMutation = useDeleteParty();

  const [showForm, setShowForm] = useState(false);
  const [editingParty, setEditingParty] = useState<Party | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleSearch = useCallback(
    (s: string) => {
      const params = new URLSearchParams(searchParams);
      if (s) params.set('search', s);
      else params.delete('search');
      setSearchParams(params);
    },
    [searchParams, setSearchParams],
  );

  const handleDelete = async () => {
    if (!deleteId) return;
    await deleteMutation.mutateAsync(deleteId);
    setDeleteId(null);
  };

  const handleEdit = (party: Party) => {
    setEditingParty(party);
    setShowForm(true);
  };

  const handleCreate = () => {
    setEditingParty(null);
    setShowForm(true);
  };

  const title = type === 'Vendor' ? 'Vendors' : 'Customers';
  const subtitle = type === 'Vendor'
    ? 'Manage your suppliers and vendors'
    : 'Manage your customers and clients';

  const tabs = [
    { id: 'Customer', label: 'Customers' },
    { id: 'Vendor', label: 'Vendors' },
  ];

  const columns: Column<Party>[] = [
    { key: 'name', header: 'Name', render: (p) => <span className="font-medium text-gray-900">{p.party_name}</span> },
    { key: 'gstin', header: 'GSTIN', render: (p) => <span className="text-gray-600 font-mono text-xs">{formatGstin(p.gstin)}</span>, hideOnMobile: true },
    { key: 'phone', header: 'Phone', render: (p) => {
      const phone = p.contacts?.[0]?.phone;
      return <span className="text-gray-600">{phone ? formatPhone(phone) : '-'}</span>;
    }, hideOnMobile: true },
    { key: 'balance', header: 'Balance', render: (p) => (
      <span className="font-medium">{formatCurrency(p.opening_balance)}</span>
    ), className: 'text-right', hideOnMobile: true },
    { key: 'status', header: 'Status', render: (p) => (
      <Badge variant={p.is_deleted ? 'default' : 'success'}>{p.is_deleted ? 'Inactive' : 'Active'}</Badge>
    ) },
    { key: 'actions', header: '', render: (p) => (
      <div className="flex items-center gap-1 justify-end" onClick={(e) => e.stopPropagation()}>
        <Button variant="ghost" size="sm" onClick={() => handleEdit(p)} aria-label="Edit">
          <Edit className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" onClick={() => p.party_id && setDeleteId(p.party_id)} aria-label="Delete">
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      </div>
    ), className: 'text-right' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Button onClick={handleCreate}>
            <UserPlus className="h-4 w-4" />
            Add {type === 'Vendor' ? 'Vendor' : 'Customer'}
          </Button>
        }
      />

      <Tabs tabs={tabs} active={type} onChange={(id) => {
        const params = new URLSearchParams(searchParams);
        params.set('type', id);
        setSearchParams(params);
      }} />

      <div className="flex items-center gap-4">
        <div className="w-full max-w-xs">
          <SearchInput value={search} onChange={handleSearch} placeholder={`Search ${title.toLowerCase()}...`} />
        </div>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : !data?.items?.length ? (
        <EmptyState
          title={`No ${title.toLowerCase()} found`}
          description={`Add your first ${type.toLowerCase()} to get started.`}
          action={{ label: `Add ${type === 'Vendor' ? 'Vendor' : 'Customer'}`, onClick: handleCreate }}
        />
      ) : (
        <>
          <div className="hidden lg:block">
            <Table
              columns={columns}
              data={data.items}
              keyExtractor={(p) => p.party_id || p.row_id || ''}
              onRowClick={(p) => navigate(`/parties/${p.party_id}`)}
            />
          </div>
          <MobileCards
            columns={columns}
            data={data.items}
            keyExtractor={(p) => p.party_id || p.row_id || ''}
            onRowClick={(p) => navigate(`/parties/${p.party_id}`)}
          />
        </>
      )}

      <Modal
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        title={editingParty ? 'Edit Party' : 'Add Party'}
        size="xl"
      >
        <PartyForm
          party={editingParty}
          partyType={type as 'Customer' | 'Vendor'}
          onSuccess={() => {
            setShowForm(false);
            setEditingParty(null);
            refetch();
          }}
          onCancel={() => {
            setShowForm(false);
            setEditingParty(null);
          }}
        />
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteId}
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        title="Delete party"
        message="Are you sure you want to delete this party? This action cannot be undone."
        confirmLabel="Delete"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}