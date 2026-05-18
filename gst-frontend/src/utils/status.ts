import { type InvoiceStatus, type PaymentStatus } from '@/types';

export type StatusVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral';

export function invoiceStatusVariant(status: InvoiceStatus | string | undefined): StatusVariant {
  switch (status) {
    case 'Draft': return 'neutral';
    case 'Submitted': return 'info';
    case 'Paid': return 'success';
    case 'Partially Paid': return 'warning';
    case 'Overdue': return 'danger';
    case 'Cancelled': return 'default';
    case 'Amended': return 'warning';
    case 'Void': return 'default';
    default: return 'default';
  }
}

export function paymentStatusVariant(status: PaymentStatus | string | undefined): StatusVariant {
  switch (status) {
    case 'Paid': return 'success';
    case 'Partially Paid': return 'warning';
    case 'Unpaid': return 'neutral';
    case 'Overdue': return 'danger';
    default: return 'default';
  }
}

export function partyStatusVariant(isActive: boolean | undefined): StatusVariant {
  return isActive !== false ? 'success' : 'default';
}

export function itemStatusVariant(isDeleted: boolean | undefined): StatusVariant {
  return isDeleted ? 'default' : 'success';
}

export function paymentModeLabel(mode: string | undefined): string {
  if (!mode) return '-';
  const map: Record<string, string> = {
    'Bank Transfer': 'Bank',
    'Credit Card': 'Card',
    'Debit Card': 'Card',
    'Online Payment': 'Online',
  };
  return map[mode] || mode;
}