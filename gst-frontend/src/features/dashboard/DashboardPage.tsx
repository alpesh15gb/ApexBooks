import { useDashboard } from '@/lib/hooks';
import { StatsCard } from '@/components/ui/StatsCard';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { formatCurrency } from '@/utils/format';
import { Invoice } from '@/types';
import { StatusBadge } from '@/components/ui/Badge';
import { formatDate } from '@/utils/format';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ArrowDownRight, DollarSign, CreditCard, TrendingUp, TrendingDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function DashboardPage() {
  const { data, isLoading, error, refetch } = useDashboard();
  const navigate = useNavigate();

  if (isLoading) return <CardSkeleton count={4} />;
  if (error) return <ErrorState onRetry={refetch} message="Failed to load dashboard" />;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Your business at a glance" />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          label="Total Sales"
          value={formatCurrency(data?.total_sales)}
          icon={<TrendingUp className="h-5 w-5" />}
        />
        <StatsCard
          label="Total Purchases"
          value={formatCurrency(data?.total_purchases)}
          icon={<TrendingDown className="h-5 w-5" />}
        />
        <StatsCard
          label="Receivables"
          value={formatCurrency(data?.total_receivables)}
          subtitle="Outstanding from customers"
          icon={<ArrowUpRight className="h-5 w-5" />}
        />
        <StatsCard
          label="Payables"
          value={formatCurrency(data?.total_payables)}
          subtitle="Due to vendors"
          icon={<ArrowDownRight className="h-5 w-5" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Recent Invoices</h3>
            <Link to="/invoices/sales" className="link text-sm">View all</Link>
          </div>
          <div className="divide-y divide-gray-100">
            {data?.recent_invoices?.slice(0, 5).map((inv) => (
              <div
                key={inv.invoice_id}
                className="px-6 py-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer"
                onClick={() => navigate(`/invoices/${inv.invoice_kind}/${inv.invoice_id}`)}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {inv.invoice_number || 'N/A'}
                  </p>
                  <p className="text-xs text-gray-500">
                    {inv.party_name || 'Unknown'} · {formatDate(inv.invoice_date)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-semibold text-gray-900">
                    {formatCurrency(inv.grand_total)}
                  </span>
                  <StatusBadge status={inv.status} />
                </div>
              </div>
            ))}
            {(!data?.recent_invoices || data.recent_invoices.length === 0) && (
              <div className="px-6 py-8 text-center text-sm text-gray-500">
                No recent invoices
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Overdue Invoices</h3>
            <Link to="/invoices/sales?status=Overdue" className="link text-sm">View all</Link>
          </div>
          <div className="divide-y divide-gray-100">
            {data?.overdue_invoices?.slice(0, 5).map((inv) => (
              <div
                key={inv.invoice_id}
                className="px-6 py-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer"
                onClick={() => navigate(`/invoices/${inv.invoice_kind}/${inv.invoice_id}`)}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {inv.invoice_number || 'N/A'}
                  </p>
                  <p className="text-xs text-gray-500">
                    {inv.party_name} · Due {formatDate(inv.due_date)}
                  </p>
                </div>
                <span className="text-sm font-semibold text-red-600">
                  {formatCurrency(inv.outstanding_amount)}
                </span>
              </div>
            ))}
            {(!data?.overdue_invoices || data.overdue_invoices.length === 0) && (
              <div className="px-6 py-8 text-center text-sm text-gray-500">
                No overdue invoices
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          label="GST Payable"
          value={formatCurrency(data?.gst_payable)}
          icon={<CreditCard className="h-5 w-5" />}
        />
        <StatsCard
          label="GST Credit"
          value={formatCurrency(data?.gst_credit)}
          icon={<DollarSign className="h-5 w-5" />}
        />
      </div>
    </div>
  );
}