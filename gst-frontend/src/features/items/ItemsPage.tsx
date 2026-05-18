import { useState } from 'react';
import { useItems, useDeleteItem } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { SearchInput } from '@/components/ui/SearchInput';
import { Badge } from '@/components/ui/Badge';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Modal } from '@/components/ui/Modal';
import { Table, MobileCards } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { ItemForm } from './ItemForm';
import { Plus, Edit, Trash2, Package } from 'lucide-react';
import { formatCurrency, formatNumber } from '@/utils/format';
import type { Item } from '@/types';

export function ItemsPage() {
  const [search, setSearch] = useState('');
  const { data, isLoading, error, refetch } = useItems(search);
  const deleteMutation = useDeleteItem();

  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState<Item | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!deleteId) return;
    await deleteMutation.mutateAsync(deleteId);
    setDeleteId(null);
  };

  const columns: Column<Item>[] = [
    { key: 'name', header: 'Name', render: (item) => (
      <div>
        <p className="font-medium text-gray-900">{item.item_name}</p>
        <p className="text-xs text-gray-500">{item.item_code}</p>
      </div>
    )},
    { key: 'type', header: 'Type', render: (item) => <Badge variant="neutral">{item.item_type}</Badge>, hideOnMobile: true },
    { key: 'hsn', header: 'HSN/SAC', render: (item) => <span className="font-mono text-xs">{item.hsn_code || item.sac_code || '-'}</span>, hideOnMobile: true },
    { key: 'rate', header: 'GST Rate', render: (item) => <span>{formatNumber(item.gst_rate, 1)}%</span>, hideOnMobile: true },
    { key: 'selling', header: 'Selling Price', render: (item) => <span className="font-medium">{formatCurrency(item.selling_price)}</span>, className: 'text-right' },
    { key: 'purchase', header: 'Purchase Price', render: (item) => <span className="font-medium">{formatCurrency(item.purchase_price)}</span>, className: 'text-right', hideOnMobile: true },
    { key: 'actions', header: '', render: (item) => (
      <div className="flex items-center gap-1 justify-end" onClick={(e) => e.stopPropagation()}>
        <Button variant="ghost" size="sm" onClick={() => { setEditingItem(item); setShowForm(true); }} aria-label="Edit">
          <Edit className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" onClick={() => item.item_id && setDeleteId(item.item_id)} aria-label="Delete">
          <Trash2 className="h-4 w-4 text-red-500" />
        </Button>
      </div>
    ), className: 'text-right' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Items"
        subtitle="Manage your products and services"
        actions={
          <Button onClick={() => { setEditingItem(null); setShowForm(true); }}>
            <Plus className="h-4 w-4" />
            Add Item
          </Button>
        }
      />

      <div className="w-full max-w-xs">
        <SearchInput value={search} onChange={setSearch} placeholder="Search items..." />
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : !data?.items?.length ? (
        <EmptyState
          title="No items found"
          description="Add your first item to start tracking products and services."
          action={{ label: 'Add Item', onClick: () => { setEditingItem(null); setShowForm(true); } }}
          icon={<Package className="h-12 w-12" />}
        />
      ) : (
        <>
          <div className="hidden lg:block">
            <Table columns={columns} data={data.items} keyExtractor={(i) => i.item_id || i.row_id || ''} />
          </div>
          <MobileCards columns={columns} data={data.items} keyExtractor={(i) => i.item_id || i.row_id || ''} />
        </>
      )}

      <Modal
        isOpen={showForm}
        onClose={() => { setShowForm(false); setEditingItem(null); }}
        title={editingItem ? 'Edit Item' : 'Add Item'}
        size="lg"
      >
        <ItemForm
          item={editingItem}
          onSuccess={() => { setShowForm(false); setEditingItem(null); refetch(); }}
          onCancel={() => { setShowForm(false); setEditingItem(null); }}
        />
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteId}
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        title="Delete item"
        message="Are you sure you want to delete this item?"
        confirmLabel="Delete"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}