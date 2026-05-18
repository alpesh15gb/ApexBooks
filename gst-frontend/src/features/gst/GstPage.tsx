import { useState } from 'react';
import { useTaxRates, useHsnCodes } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Tabs } from '@/components/ui/Tabs';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { SearchInput } from '@/components/ui/SearchInput';
import { Badge } from '@/components/ui/Badge';
import { formatNumber } from '@/utils/format';
import { Table } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import type { HsnCode, TaxRate } from '@/types';

const GST_TABS = [
  { id: 'rates', label: 'Tax Rates' },
  { id: 'hsn', label: 'HSN Codes' },
];

export function GstPage() {
  const [tab, setTab] = useState('rates');
  const [hsnSearch, setHsnSearch] = useState('');
  const { data: taxRates, isLoading: ratesLoading, error: ratesError, refetch: refetchRates } = useTaxRates();
  const { data: hsnCodes, isLoading: hsnLoading, error: hsnError, refetch: refetchHsn } = useHsnCodes(hsnSearch);

  const rateColumns: Column<TaxRate>[] = [
    { key: 'rate', header: 'GST Rate', render: (r) => <span className="font-semibold">{formatNumber(r.rate, 1)}%</span> },
    { key: 'type', header: 'Type', render: (r) => <Badge variant="neutral">{r.type}</Badge> },
  ];

  const hsnColumns: Column<HsnCode>[] = [
    { key: 'code', header: 'Code', render: (h) => <span className="font-mono font-medium">{h.code}</span> },
    { key: 'description', header: 'Description', render: (h) => <span className="text-gray-700">{h.description}</span> },
    { key: 'rate', header: 'GST Rate', render: (h) => <span>{formatNumber(h.gst_rate, 1)}%</span> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title="GST Compliance" subtitle="Tax rates, HSN/SAC codes, and returns" />

      <Tabs tabs={GST_TABS} active={tab} onChange={setTab} />

      {tab === 'rates' && (
        <>
          {ratesLoading ? <TableSkeleton /> : ratesError ? <ErrorState onRetry={refetchRates} /> : (
            <Table columns={rateColumns} data={taxRates || []} keyExtractor={(rate) => `${rate.type}-${rate.rate}`} />
          )}
        </>
      )}

      {tab === 'hsn' && (
        <>
          <div className="w-full max-w-xs">
            <SearchInput value={hsnSearch} onChange={setHsnSearch} placeholder="Search HSN/SAC codes..." />
          </div>
          {hsnLoading ? <TableSkeleton /> : hsnError ? <ErrorState onRetry={refetchHsn} /> : (
            <Table columns={hsnColumns} data={hsnCodes || []} keyExtractor={(h) => h.code} />
          )}
        </>
      )}
    </div>
  );
}
