import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useInvoice, useSubmitInvoice, useCancelInvoice } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/Button';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { formatCurrency, formatDate, formatNumber } from '@/utils/format';
import { ArrowLeft, Send, XCircle, FileText, Download } from 'lucide-react';

export function InvoiceDetailPage() {
  const { kind, id } = useParams<{ kind: 'sales' | 'purchase'; id: string }>();
  const navigate = useNavigate();
  const { data: invoice, isLoading, error, refetch } = useInvoice(kind || 'sales', id || '');
  const submitMutation = useSubmitInvoice();
  const cancelMutation = useCancelInvoice();

  const [showSubmit, setShowSubmit] = useState(false);
  const [showCancel, setShowCancel] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="card p-6 space-y-4">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-full" />
        </div>
      </div>
    );
  }

  if (error || !invoice) {
    return <ErrorState onRetry={refetch} message="Failed to load invoice" />;
  }

  const isSales = kind === 'sales';

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader
        title={invoice.invoice_number || 'Invoice'}
        subtitle={`${isSales ? 'Sales' : 'Purchase'} Invoice · ${formatDate(invoice.invoice_date)}`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => navigate(`/invoices/${kind}`)}>
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            {invoice.status === 'Draft' && (
              <>
                <Button onClick={() => navigate(`/invoices/${kind}/${id}/edit`)}>
                  <FileText className="h-4 w-4" />
                  Edit
                </Button>
                <Button onClick={() => setShowSubmit(true)}>
                  <Send className="h-4 w-4" />
                  Submit
                </Button>
                <Button variant="danger" onClick={() => setShowCancel(true)}>
                  <XCircle className="h-4 w-4" />
                  Cancel
                </Button>
              </>
            )}
          </div>
        }
      />

      <div className="card">
        <div className="card-header flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Invoice Details</h3>
          <div className="flex items-center gap-2">
            <StatusBadge status={invoice.status} />
            <StatusBadge status={invoice.payment_status} />
          </div>
        </div>
        <div className="card-body">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
            <div>
              <p className="text-xs text-gray-500 uppercase">Invoice Number</p>
              <p className="font-medium text-gray-900">{invoice.invoice_number || 'N/A'}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase">Date</p>
              <p className="font-medium text-gray-900">{formatDate(invoice.invoice_date)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase">Due Date</p>
              <p className="font-medium text-gray-900">{formatDate(invoice.due_date)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase">Place of Supply</p>
              <p className="font-medium text-gray-900">{invoice.place_of_supply || '-'}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-6">
            <div>
              <p className="text-xs text-gray-500 uppercase">{isSales ? 'Customer' : 'Vendor'}</p>
              <p className="font-medium text-gray-900">{invoice.party_name || 'N/A'}</p>
              {invoice.party_gstin && (
                <p className="text-xs font-mono text-gray-500">{invoice.party_gstin}</p>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase">Supply Type</p>
              <p className="font-medium text-gray-900">{invoice.supply_type || '-'}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3 className="font-semibold text-gray-900">Line Items</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th className="text-left">#</th>
                <th className="text-left">Item</th>
                <th className="text-right">HSN</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Rate</th>
                <th className="text-right">Disc</th>
                <th className="text-right">Taxable</th>
                <th className="text-right">GST</th>
                <th className="text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines?.map((line, i) => (
                <tr key={i}>
                  <td className="text-gray-500">{line.line_no || i + 1}</td>
                  <td className="font-medium">{line.item_name}</td>
                  <td className="text-right font-mono text-xs">{line.hsn_code || '-'}</td>
                  <td className="text-right">{formatNumber(line.quantity, 2)}</td>
                  <td className="text-right">{formatCurrency(line.unit_price)}</td>
                  <td className="text-right">{line.discount_percent ? `${line.discount_percent}%` : '-'}</td>
                  <td className="text-right">{formatCurrency(line.taxable_value)}</td>
                  <td className="text-right">{line.gst_rate ? `${line.gst_rate}%` : '-'}</td>
                  <td className="text-right font-medium">{formatCurrency(line.total_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-gray-100 px-6 py-4">
          <div className="ml-auto w-full sm:w-72 space-y-1">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Subtotal</span>
              <span>{formatCurrency(invoice.subtotal)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">CGST</span>
              <span>{formatCurrency(invoice.total_cgst)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">SGST</span>
              <span>{formatCurrency(invoice.total_sgst)}</span>
            </div>
            {invoice.total_igst ? (
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">IGST</span>
                <span>{formatCurrency(invoice.total_igst)}</span>
              </div>
            ) : null}
            <div className="flex justify-between text-lg font-bold border-t border-gray-200 pt-2">
              <span>Grand Total</span>
              <span>{formatCurrency(invoice.grand_total)}</span>
            </div>
            <div className="flex justify-between text-sm pt-1">
              <span className="text-gray-600">Paid</span>
              <span className="font-medium text-emerald-600">{formatCurrency(invoice.amount_paid)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Outstanding</span>
              <span className="font-medium text-red-600">{formatCurrency(invoice.outstanding_amount)}</span>
            </div>
          </div>
        </div>
      </div>

      {invoice.notes && (
        <div className="card">
          <div className="card-header"><h3 className="font-semibold text-gray-900">Notes</h3></div>
          <div className="card-body">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{invoice.notes}</p>
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={showSubmit}
        onConfirm={async () => {
          if (kind && id) {
            await submitMutation.mutateAsync({ kind, id });
            setShowSubmit(false);
          }
        }}
        onCancel={() => setShowSubmit(false)}
        title="Submit Invoice"
        message="This will post the invoice to the general ledger and change its status to Submitted. Continue?"
        confirmLabel="Submit"
        variant="warning"
        loading={submitMutation.isPending}
      />

      <ConfirmDialog
        isOpen={showCancel}
        onConfirm={async () => {
          if (kind && id) {
            await cancelMutation.mutateAsync({ kind, id });
            setShowCancel(false);
          }
        }}
        onCancel={() => setShowCancel(false)}
        title="Cancel Invoice"
        message="Are you sure you want to cancel this invoice?"
        confirmLabel="Cancel Invoice"
        loading={cancelMutation.isPending}
      />
    </div>
  );
}