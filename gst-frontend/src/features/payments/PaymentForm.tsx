import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useReceivePayment, useMakePayment } from '@/lib/hooks';
import { PAYMENT_MODES } from '@/utils/validation';
import { apiErrorToString } from '@/utils/validation';
import toast from 'react-hot-toast';

const paymentSchema = z.object({
  party_name: z.string().min(1, 'Party name is required'),
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

  const { register, handleSubmit, watch, formState: { errors } } = useForm<PaymentFormData>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      payment_date: new Date().toISOString().split('T')[0],
      payment_mode: 'Bank Transfer',
    },
  });

  const amount = Number(watch('amount')) || 0;
  const tds = Number(watch('tds_amount')) || 0;

  const onSubmit = async (data: PaymentFormData) => {
    try {
      const payload = {
        payment_type: paymentType,
        payment_date: data.payment_date,
        payment_mode: data.payment_mode || 'Bank Transfer',
        party_name: data.party_name,
        amount: Number(data.amount),
        tds_amount: Number(data.tds_amount) || 0,
        net_amount: Number(data.amount) - (Number(data.tds_amount) || 0),
        reference_no: data.reference_no || undefined,
        narration: data.narration || undefined,
      };

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

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Party Name" placeholder="Name" error={errors.party_name?.message} required {...register('party_name')} />
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