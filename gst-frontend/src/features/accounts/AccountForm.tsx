import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useCreateAccount, useUpdateAccount } from '@/lib/hooks';
import { ACCOUNT_TYPES } from '@/utils/validation';
import { apiErrorToString } from '@/utils/validation';
import type { Account } from '@/types';
import toast from 'react-hot-toast';

const schema = z.object({
  code: z.string().min(1, 'Code is required'),
  name: z.string().min(1, 'Name is required'),
  account_type: z.string().min(1, 'Type is required'),
  description: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

interface AccountFormProps {
  account?: Account | null;
  onSuccess: () => void;
  onCancel: () => void;
}

export function AccountForm({ account, onSuccess, onCancel }: AccountFormProps) {
  const createMutation = useCreateAccount();
  const updateMutation = useUpdateAccount();

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: account?.code || '',
      name: account?.name || '',
      account_type: account?.account_type || 'Expense',
      description: account?.description || '',
    },
  });

  const onSubmit = async (data: FormData) => {
    try {
      if (account?.id) {
        await updateMutation.mutateAsync({ id: account.id, data });
      } else {
        await createMutation.mutateAsync(data);
      }
      onSuccess();
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Input label="Code" placeholder="ACC-001" error={errors.code?.message} required {...register('code')} />
        <Select label="Type" options={ACCOUNT_TYPES.map((t) => ({ value: t, label: t }))} {...register('account_type')} />
      </div>
      <Input label="Account Name" placeholder="Account name" error={errors.name?.message} required {...register('name')} />
      <Input label="Description" placeholder="Optional description" {...register('description')} />
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit">{account ? 'Update' : 'Create'} Account</Button>
      </div>
    </form>
  );
}