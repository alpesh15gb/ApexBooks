import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useReceivePayment, useMakePayment, useParties } from '@/lib/hooks';
import { PAYMENT_MODES } from '@/utils/validation';
import { apiErrorToString } from '@/utils/validation';
import { formatCurrency } from '@/utils/format';
import toast from 'react-hot-toast';
import { useState, useEffect, useCallback } from 'react';
import { Search, Check } from 'lucide-react';

const paymentSchema = z.object({
  party_id: z.string().min(1, 'Select a party'),
  amount: z.string().min(1, 'Amount is required'),
  payment_mode: z.string().optional(),
  payment_date: z.string().min(1, 'Date is required'),
  reference_no: z.string().optional(),
  narration: z.string().optional(),
  tds_amount: z.string().optional(),
});

type PaymentFormData = z.infer<typeof paymentSchema>;

interface PaymentFormProps {
  paymentType: 'Receive' | 'Pay';
  onSuccess: () => void;
  onCancel: () => void;
}

export function PaymentForm({ paymentType, onSuccess, onCancel }: PaymentFormProps) {
  const receiveMutation = useReceivePayment();
  const makeMutation = useMakePayment();
  const mutation = paymentType === 'Receive' ? receiveMutation : makeMutation;
  const { data: partiesData } = useParties();
  const parties = (partiesData as any)?.items || partiesData || [];

  const [selectedPartyInvoices, setSelectedPartyInvoices] = useState<any[]>([]);
  const [allocations, setAllocations] = useState<Record<string, number>>({});
  const [partySearch, setPartySearch] = useState('');

  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<PaymentFormData>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      payment_date: new Date().toISOString().split('T')[0],
      payment_mode: 'Bank Transfer',
    },
  });

  const selectedPartyId = watch('party_id');
  const amount = Number(watch('amount')) || 0;
  const tds = Number(watch('tds_amount')) || 0;

  // Load outstanding invoices when party is selected
  useEffect(() => {
    if (selectedPartyId) {
      const kind = paymentType === 'Receive' ? 'sales' : 'purchase';
      fetch(`/api/v1/invoices/${kind}?status=Unpaid&party_id=${selectedPartyId}`, {
        headers: { 'Content-Type': 'application/json' },
      })
        .then(r => r.json())
        .then(data => {
          const invoices = data?.data?.items || [];
          setSelectedPartyInvoices(invoices.filter((inv: any) => (inv.grand_total - inv.amount_paid) > 0));
        })
        .catch(() => setSelectedPartyInvoices([]));
    } else {
      setSelectedPartyInvoices([]);
    }
  }, [selectedPartyId, paymentType]);

  const toggleInvoice = useCallback((invoiceId: string, outstanding: number) => {
    setAllocations(prev => {
      const next = { ...prev };
      if (next[invoiceId]) {
        delete next[invoiceId];
      } else {
        next[invoiceId] = outstanding;
      }
      return next;
    });
  }, []);

  const updateAllocation = useCallback((invoiceId: string, value: number) => {
    setAllocations(prev => ({ ...prev, [invoiceId]: value }));
  }, []);

  const totalAllocated = Object.values(allocations).reduce((s, v) => s + v, 0);

  const onSubmit = async (data: PaymentFormData) => {
    try {
      const selectedParty = parties.find((p: any) => p.party_id === data.party_id);
      const invoiceIds = Object.keys(allocations);
      const payload: any = {
        payment_type: paymentType,
        payment_date: data.payment_date,
        payment_mode: data.payment_mode || 'Bank Transfer',
        party_id: data.party_id,
        party_name: selectedParty?.party_name || '',
        amount: Number(data.amount),
        tds_amount: Number(data.tds_amount) || 0,
        net_amount: Number(data.amount) - (Number(data.tds_amount) || 0),
        reference_no: data.reference_no || undefined,
        narration: data.narration || undefined,
      };

      if (invoiceIds.length > 0) {
        payload.allocations = invoiceIds.map(id => ({
          invoice_id: id,
          amount: allocations[id],
        }));
      }

      if (paymentType === 'Receive') {
        await receiveMutation.mutateAsync(payload);
      } else {
        await makeMutation.mutateAsync(payload);
      }
      onSuccess();
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  const filteredParties = parties.filter((p: any) =>
    p.party_type === (paymentType === 'Receive' ? 'Customer' : 'Vendor') &&
    (p.party_name?.toLowerCase().includes(partySearch.toLowerCase()) ||
     p.gstin?.includes(partySearch))
  );

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="label">Select Party *</label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              className="input pl-9 mb-1"
              placeholder="Search parties..."
              value={partySearch}
              onChange={e => setPartySearch(e.target.value)}
            />
          </div>
          <select
            className="input w-full"
            value={selectedPartyId || ''}
            onChange={e => setValue('party_id', e.target.value)}
          >
            <option value="">Select a party</option>
            {filteredParties.map((p: any) => (
              <option key={p.party_id} value={p.party_id}>{p.party_name}{p.gstin ? ` (${p.gstin})` : ''}</option>
            ))}
          </select>
          {errors.party_id && <p className="text-sm text-red-600">{errors.party_id.message}</p>}
        </div>
        <Select label="Payment Mode" options={PAYMENT_MODES.map((m) => ({ value: m, label: m }))} {...register('payment_mode')} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Payment Date" type="date" error={errors.payment_date?.message} required {...register('payment_date')} />
        <Input label="Reference No" placeholder="Cheque / UPI ref" {...register('reference_no')} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Amount" type="number" step="0.01" placeholder="0" error={errors.amount?.message} required {...register('amount')} />
        <Input label="TDS Amount" type="number" step="0.01" placeholder="0" {...register('tds_amount')} />
      </div>

      {/* Outstanding Invoices */}
      {selectedPartyInvoices.length > 0 && (
        <div className="border rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-4 py-2 border-b">
            <p className="text-sm font-medium text-gray-700">Outstanding Invoices</p>
          </div>
          <div className="divide-y divide-gray-100 max-h-48 overflow-y-auto">
            {selectedPartyInvoices.map((inv: any) => {
              const outstanding = inv.grand_total - (inv.amount_paid || 0);
              const isSelected = !!allocations[inv.invoice_id];
              return (
                <div key={inv.invoice_id} className={`px-4 py-2 flex items-center gap-3 hover:bg-gray-50 cursor-pointer ${isSelected ? 'bg-brand-50' : ''}`}
                     onClick={() => toggleInvoice(inv.invoice_id, outstanding)}>
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${isSelected ? 'bg-brand-600 border-brand-600' : 'border-gray-300'}`}>
                    {isSelected && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900">{inv.invoice_number}</p>
                    <p className="text-xs text-gray-500">{formatCurrency(outstanding)} outstanding</p>
                  </div>
                  {isSelected && (
                    <input
                      type="number"
                      step="0.01"
                      className="input w-28 text-sm text-right"
                      value={allocations[inv.invoice_id]}
                      onClick={e => e.stopPropagation()}
                      onChange={e => updateAllocation(inv.invoice_id, Number(e.target.value) || 0)}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {totalAllocated > 0 && (
        <div className="bg-brand-50 rounded-lg p-3 text-sm">
          <span className="font-medium">Allocated: </span>
          <span className="text-brand-700 font-semibold">{formatCurrency(totalAllocated)}</span>
          {Math.abs(totalAllocated - amount) > 0.01 && (
            <span className="text-amber-600 ml-2">(differs from amount by {formatCurrency(Math.abs(totalAllocated - amount))})</span>
          )}
        </div>
      )}

      <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-600">Amount</span>
          <span className="font-medium">{amount.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-600">TDS</span>
          <span className="font-medium">-{tds.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-base font-semibold border-t border-gray-200 pt-1">
          <span>Net Amount</span>
          <span>{(amount - tds).toFixed(2)}</span>
        </div>
      </div>

      <Input label="Narration" placeholder="Optional notes" {...register('narration')} />

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={mutation.isPending}>
          {paymentType === 'Receive' ? 'Receive' : 'Make'} Payment
        </Button>
      </div>
    </form>
  );
}
