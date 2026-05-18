import { Skeleton } from './Skeleton';

interface StatsCardProps {
  label: string;
  value: string;
  subtitle?: string;
  trend?: { value: string; positive: boolean };
  icon?: React.ReactNode;
  loading?: boolean;
}

export function StatsCard({ label, value, subtitle, trend, icon, loading }: StatsCardProps) {
  if (loading) {
    return (
      <div className="card p-6 space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
    );
  }

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-500 truncate">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-gray-900">{value}</p>
          {subtitle && (
            <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
          )}
          {trend && (
            <p
              className={`mt-1 text-xs font-medium ${
                trend.positive ? 'text-emerald-600' : 'text-red-600'
              }`}
            >
              {trend.value}
            </p>
          )}
        </div>
        {icon && <div className="text-gray-400 shrink-0">{icon}</div>}
      </div>
    </div>
  );
}