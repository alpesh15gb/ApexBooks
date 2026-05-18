import { useState } from 'react';
import { useAuditLogs } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { Tabs } from '@/components/ui/Tabs';
import { Table } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { formatDateTime } from '@/utils/format';
import { Badge } from '@/components/ui/Badge';
import type { AuditLog } from '@/types';

const ADMIN_TABS = [
  { id: 'audit', label: 'Audit Log' },
];

export function AdminPage() {
  const [tab] = useState('audit');
  const { data, isLoading, error, refetch } = useAuditLogs();

  const columns: Column<AuditLog>[] = [
    { key: 'time', header: 'Timestamp', render: (l) => <span>{formatDateTime(l.created_at)}</span> },
    { key: 'actor', header: 'Actor', render: (l) => <span className="font-mono text-xs">{l.actor_id || 'System'}</span> },
    { key: 'resource', header: 'Resource', render: (l) => <Badge variant="neutral">{l.resource || '-'}</Badge> },
    { key: 'action', header: 'Action', render: (l) => <span className="font-medium">{l.action || '-'}</span> },
    { key: 'details', header: 'Details', render: (l) => (
      <span className="text-xs text-gray-500 max-w-[300px] truncate block">
        {l.details ? JSON.stringify(l.details).slice(0, 100) : '-'}
      </span>
    ), hideOnMobile: true },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="Administration" subtitle="Audit logs and system management" />

      <Tabs tabs={ADMIN_TABS} active={tab} onChange={() => {}} />

      {isLoading ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState onRetry={refetch} />
      ) : (
        <Table
          columns={columns}
          data={data?.items || []}
          keyExtractor={(l) => l.row_id || l.id || ''}
        />
      )}
    </div>
  );
}