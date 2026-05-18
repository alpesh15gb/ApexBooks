import { useState, useCallback } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { Tabs } from '@/components/ui/Tabs';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { formatCurrency, formatDate } from '@/utils/format';
import { api } from '@/lib/api';
import {
  Download, FileSpreadsheet, FileText, Printer,
  ChevronDown, ChevronRight, Search, Calendar,
  RefreshCw, Filter,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiErrorToString } from '@/utils/validation';

const REPORT_TABS = [
  { id: 'profit_loss', label: 'P&L' },
  { id: 'balance_sheet', label: 'Balance Sheet' },
  { id: 'trial_balance', label: 'Trial Balance' },
  { id: 'general_ledger', label: 'General Ledger' },
  { id: 'receivables_aging', label: 'Aging' },
  { id: 'gst_summary', label: 'GST' },
  { id: 'hsn_summary', label: 'HSN/SAC' },
  { id: 'sales_by_customer', label: 'Sales' },
];

interface ReportRow {
  [key: string]: unknown;
}

function ReportTable({ data }: { data: ReportRow[] }) {
  if (!data || data.length === 0) {
    return <p className="text-sm text-gray-500 py-8 text-center">No data available</p>;
  }

  const headers = Object.keys(data[0]);
  const moneyKeys = headers.filter(h =>
    ['amount', 'total', 'balance', 'debit', 'credit', 'tax', 'value', 'price',
     'gst', 'receivable', 'payable', 'outstanding', 'income', 'expense',
     'profit', 'sales', 'purchase'].some(k => h.toLowerCase().includes(k))
  );
  const percentKeys = headers.filter(h => h.toLowerCase().includes('rate') || h.toLowerCase().includes('percent'));

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {headers.map(h => (
              <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap">
                {h.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {data.map((row, i) => (
            <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
              {headers.map(h => {
                const val = row[h];
                let display: string;

                if (val === null || val === undefined) {
                  display = '-';
                } else if (moneyKeys.includes(h) && typeof val === 'number') {
                  display = formatCurrency(val);
                } else if (percentKeys.includes(h) && typeof val === 'number') {
                  display = val + '%';
                } else if (typeof val === 'number') {
                  display = val.toLocaleString('en-IN', { maximumFractionDigits: 2 });
                } else {
                  display = String(val);
                }

                const isMoney = moneyKeys.includes(h);
                return (
                  <td key={h} className={`px-4 py-2.5 text-sm whitespace-nowrap ${isMoney ? 'text-right font-medium tabular-nums' : 'text-gray-700'}`}>
                    {display}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryCard({ label, value, subtitle }: { label: string; value: string; subtitle?: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-xl font-bold text-gray-900 mt-1">{value}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="font-semibold text-gray-900">{title}</h3>
      </div>
      <div className="card-body p-0">{children}</div>
    </div>
  );
}

export function ReportsPage() {
  const [report, setReport] = useState('trial_balance');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  const runReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number | boolean | undefined> = { report_type: report };
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const result = await api.getReport(report, params);
      setData(result);
    } catch (err) {
      setError(apiErrorToString(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [report, fromDate, toDate]);

  const exportReport = async (format: string) => {
    try {
      const res = await fetch('/api/v1/reports/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_type: report, from_date: fromDate || null, to_date: toDate || null, format }),
      });
      const json = await res.json();
      if (json.success) {
        window.open(json.data.download_url, '_blank');
        toast.success('Export downloaded');
      } else {
        toast.error(json.error?.message || 'Export failed');
      }
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  const renderContent = () => {
    if (loading) return <CardSkeleton count={5} />;
    if (error) return <ErrorState onRetry={runReport} message={error} />;
    if (!data) return <p className="text-sm text-gray-500 py-8 text-center">Click Run Report to generate</p>;

    // Extract rows from various report structures
    const rows: ReportRow[] =
      data.accounts || data.entries || data.income || data.expenses ||
      data.assets || data.liabilities || data.equity || data.items ||
      data.rows || [];

    const buckets = data.buckets;
    const sectionData = data.output_gst;

    return (
      <div className="space-y-4">
        {/* Summary cards for financial reports */}
        {data.gross_income !== undefined && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SummaryCard label="Gross Income" value={formatCurrency(data.gross_income)} />
            <SummaryCard label="Total Expenses" value={formatCurrency(data.total_expenses)} />
            <SummaryCard label="Net Profit" value={formatCurrency(data.net_profit)} subtitle={data.net_profit >= 0 ? 'Profitable' : 'Loss'} />
          </div>
        )}
        {data.total_assets !== undefined && (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <SummaryCard label="Total Assets" value={formatCurrency(data.total_assets)} />
            <SummaryCard label="Total Liabilities" value={formatCurrency(data.total_liabilities)} />
            <SummaryCard label="Equity" value={formatCurrency(data.total_equity)} />
            <SummaryCard label="Balanced" value={data.balance_sheet_balanced ? 'Yes' : 'No'} />
          </div>
        )}
        {data.total_debit !== undefined && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SummaryCard label="Total Debit" value={formatCurrency(data.total_debit)} />
            <SummaryCard label="Total Credit" value={formatCurrency(data.total_credit)} />
            <SummaryCard label="Balanced" value={data.verification?.balanced ? 'Yes' : 'No'} />
          </div>
        )}

        {/* Table data */}
        {rows.length > 0 && <SectionCard title="Details"><ReportTable data={rows} /></SectionCard>}

        {/* Aging buckets */}
        {buckets && (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            {Object.entries(buckets).map(([bucket, bdata]: [string, any]) => (
              <SummaryCard key={bucket} label={bucket + ' Days'} value={formatCurrency(bdata.total)} subtitle={bdata.items.length + ' invoices'} />
            ))}
          </div>
        )}

        {/* GST section */}
        {sectionData && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SummaryCard label="Output GST" value={formatCurrency(sectionData.total_tax)} />
            <SummaryCard label="Input ITC" value={formatCurrency(data.input_gst_itc?.total_itc || 0)} />
            <SummaryCard label="Net Payable" value={formatCurrency(data.net_gst_payable)} />
          </div>
        )}

        {/* Metrics footer */}
        {data.metrics && (
          <p className="text-xs text-gray-400 text-right">
            Generated in {data.metrics.query_time_ms}ms · {data.metrics.row_count} rows
          </p>
        )}
      </div>
    );
  };

  const title = REPORT_TABS.find(t => t.id === report)?.label || 'Report';

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        subtitle="Financial statements and management reports"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => exportReport('csv')}>
              <FileText className="h-4 w-4" /> CSV
            </Button>
            <Button variant="secondary" size="sm" onClick={() => exportReport('xlsx')}>
              <FileSpreadsheet className="h-4 w-4" /> Excel
            </Button>
            <Button size="sm" onClick={() => window.print()}>
              <Printer className="h-4 w-4" /> Print
            </Button>
          </div>
        }
      />

      <Tabs tabs={REPORT_TABS} active={report} onChange={setReport} />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4 bg-white p-4 rounded-lg border border-gray-200">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-gray-400" />
          <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-40" />
          <span className="text-gray-400">to</span>
          <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-40" />
        </div>
        <Button onClick={runReport} loading={loading}>
          <RefreshCw className="h-4 w-4" /> Run Report
        </Button>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="font-semibold text-gray-900">{title}</h3>
        </div>
        <div className="card-body">
          {renderContent()}
        </div>
      </div>
    </div>
  );
}
