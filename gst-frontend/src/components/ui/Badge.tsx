import type { StatusVariant } from '@/utils/status';

const variantClasses: Record<StatusVariant, string> = {
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
  info: 'badge-info',
  neutral: 'badge-neutral',
  default: 'badge-default',
};

interface BadgeProps {
  variant?: StatusVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = 'default', children, className = '' }: BadgeProps) {
  return (
    <span className={`${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | undefined }) {
  if (!status) return <Badge variant="neutral">Unknown</Badge>;

  const map: Record<string, StatusVariant> = {
    Draft: 'neutral',
    Submitted: 'info',
    Paid: 'success',
    'Partially Paid': 'warning',
    Unpaid: 'neutral',
    Overdue: 'danger',
    Active: 'success',
    Inactive: 'default',
    Cancelled: 'default',
    Amended: 'warning',
    Void: 'default',
    Completed: 'success',
    Pending: 'warning',
    Failed: 'danger',
  };

  return <Badge variant={map[status] || 'default'}>{status}</Badge>;
}