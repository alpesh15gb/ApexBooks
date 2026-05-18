import { useDashboard } from '@/lib/hooks';
import { StatsCard } from '@/components/ui/StatsCard';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusBadge } from '@/components/ui/Badge';
import { formatCurrency, formatDate, daysOverdue } from '@/utils/format';
import { api } from '@/lib/api';
import { Link, useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts';
import {
  ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown,
  DollarSign, CreditCard, Users, Package,
} from 'lucide-react';
import { useState, useEffect } from 'react';

const PIE_COLORS = ['#10B981', '#F59E0B', '#EF4444', '#6366F1', '#8B5CF6'];

export function DashboardPage() {
  const { data, isLoading, error, refetch } = useDashboard();
  const navigate = useNavigate();
  const [salesTrend, setSalesTrend] = useState<any[]>([]);
  const [expenseBreakdown, setExpenseBreakdown] = useState<any[]>([]);

  useEffect(() => {
    // Load sales trend from recent invoices
    if (data?.recent_invoices) {
      const monthly: Record<string, number> = {};
      data.recent_invoices.forEach(inv => {
        if (inv.invoice_date) {
          const month = inv.invoice_date.substring(0, 7);
          monthly[month] = (monthly[month] || 0) + (inv.grand_total || 0);
        }
      });
      setSalesTrend(Object.entries(monthly).map(([date, amount]) => ({ date, amount })).slice(0, 12));

      // Expense breakdown by status
      const byStatus: Record<string, number> = {};
      data.recent_invoices.forEach(inv => {
        const key = inv.status || 'Unknown';
        byStatus[key] = (byStatus[key] || 0) + (inv.grand_total || 0);
      });
      setExpenseBreakdown(Object.entries(byStatus).map(([name, value]) => ({ name, value })));
    }
  }, [data]);

  if (isLoading) return <CardSkeleton count={4} />;
  if (error) return <ErrorState onRetry={refetch} message="Failed to load dashboard" />;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Your business at a glance" />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard label="Total Sales" value={formatCurrency(data?.total_sales)} icon={<TrendingUp className="h-5 w-5" />} />
        <StatsCard label="Total Purchases" value={formatCurrency(data?.total_purchases)} icon={<TrendingDown className="h-5 w-5" />} />
        <StatsCard label="Receivables" value={formatCurrency(data?.total_receivables)} subtitle="Outstanding from customers" icon={<ArrowUpRight className="h-5 w-5" />} />
        <StatsCard label="Payables" value={formatCurrency(data?.total_payables)} subtitle="Due to vendors" icon={<ArrowDownRight className="h-5 w-5" />} />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sales Trend Chart */}
        <div className="card">
          <div className="card-header">
            <h3 className="font-semibold text-gray-900">Sales Trend</h3>
          </div>
          <div className="card-body">
            {salesTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={salesTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => '₹' + (v / 1000).toFixed(0) + 'k'} />
                  <Tooltip formatter={(v: any) => formatCurrency(Number(v))} />
                  <Bar dataKey="amount" fill="#10B981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-gray-500 py-8 text-center">No sales data yet</p>
            )}
          </div>
        </div>

        {/* Expense Breakdown Pie */}
        <div className="card">
          <div className="card-header">
            <h3 className="font-semibold text-gray-900">Invoice Status</h3>
          </div>
          <div className="card-body">
            {expenseBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={expenseBreakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}>
                    {expenseBreakdown.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: any) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-gray-500 py-8 text-center">No data yet</p>
            )}
          </div>
        </div>
      </div>

      {/* Recent Invoices & Overdue */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Recent Invoices</h3>
            <Link to="/invoices/sales" className="link text-sm">View all</Link>
          </div>
          <div className="divide-y divide-gray-100">
            {data?.recent_invoices?.slice(0, 5).map((inv) => (
              <div key={inv.invoice_id} className="px-6 py-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer" onClick={() => navigate(`/invoices/${inv.invoice_kind}/${inv.invoice_id}`)}>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{inv.invoice_number || 'N/A'}</p>
                  <p className="text-xs text-gray-500">{inv.party_name || 'Unknown'} · {formatDate(inv.invoice_date)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-semibold text-gray-900">{formatCurrency(inv.grand_total)}</span>
                  <StatusBadge status={inv.status} />
                </div>
              </div>
            ))}
            {(!data?.recent_invoices || data.recent_invoices.length === 0) && (
              <div className="px-6 py-8 text-center text-sm text-gray-500">No recent invoices</div>
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
              <div key={inv.invoice_id} className="px-6 py-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer" onClick={() => navigate(`/invoices/${inv.invoice_kind}/${inv.invoice_id}`)}>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">{inv.invoice_number || 'N/A'}</p>
                  <p className="text-xs text-gray-500">{inv.party_name} · Due {formatDate(inv.due_date)}</p>
                </div>
                <span className="text-sm font-semibold text-red-600">{formatCurrency(inv.outstanding_amount)}</span>
              </div>
            ))}
            {(!data?.overdue_invoices || data.overdue_invoices.length === 0) && (
              <div className="px-6 py-8 text-center text-sm text-gray-500">No overdue invoices</div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard label="GST Payable" value={formatCurrency(data?.gst_payable)} icon={<DollarSign className="h-5 w-5" />} />
        <StatsCard label="GST Credit" value={formatCurrency(data?.gst_credit)} icon={<CreditCard className="h-5 w-5" />} />
      </div>
    </div>
  );
}
