import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { Tabs } from '@/components/ui/Tabs';
import { useReport } from '@/lib/hooks';
import { Button } from '@/components/ui/Button';
import { formatCurrency, formatDate } from '@/utils/format';
import { Download } from 'lucide-react';

const REPORT_TABS = [
  { id: 'trial-balance', label: 'Trial Balance' },
  { id: 'profit-loss', label: 'Profit & Loss' },
  { id: 'balance-sheet', label: 'Balance Sheet' },
  { id: 'cash-flow', label: 'Cash Flow' },
  { id: 'accounts-receivable', label: 'Receivables' },
  { id: 'accounts-payable', label: 'Payables' },
  { id: 'gst-payable', label: 'GST Payable' },
  { id: 'daybook', label: 'Daybook' },
  { id: 'stock-summary', label: 'Stock' },
];

export function ReportsPage() {
  const [report, setReport] = useState('trial-balance');
  const { data, isLoading, error, refetch } = useReport(report);

  const title = REPORT_TABS.find((t) => t.id === report)?.label || 'Report';

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        subtitle="Financial statements and management reports"
        actions={
          <Button variant="secondary" size="sm">
            <Download className="h-4 w-4" />
            Export
          </Button>
        }
      />

      <Tabs tabs={REPORT_TABS} active={report} onChange={setReport} />

      <div className="card">
        <div className="card-header">
          <h3 className="font-semibold text-gray-900">{title}</h3>
        </div>
        <div className="card-body">
          {isLoading ? (
            <CardSkeleton count={3} />
          ) : error ? (
            <ErrorState onRetry={refetch} message="Failed to load report" />
          ) : (
            <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">
              {data ? JSON.stringify(data, null, 2) : 'No data available for this report.'}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}