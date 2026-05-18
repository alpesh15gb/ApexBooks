import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useCreateItem, useUpdateItem } from '@/lib/hooks';
import { apiErrorToString, ITEM_TYPES, UNITS } from '@/utils/validation';
import type { Item } from '@/types';
import toast from 'react-hot-toast';

const itemSchema = z.object({
  item_name: z.string().min(1, 'Name is required'),
  item_code: z.string().min(1, 'Code is required'),
  item_type: z.string().min(1, 'Type is required'),
  hsn_code: z.string().optional().or(z.literal('')),
  sac_code: z.string().optional().or(z.literal('')),
  unit_of_measure: z.string().optional(),
  gst_rate: z.string().optional(),
  cess_rate: z.string().optional(),
  selling_price: z.string().optional(),
  purchase_price: z.string().optional(),
  description: z.string().optional(),
  is_nil_rated: z.boolean().optional(),
  is_exempt: z.boolean().optional(),
  is_non_gst: z.boolean().optional(),
});

type ItemFormData = z.infer<typeof itemSchema>;

interface ItemFormProps {
  item?: Item | null;
  onSuccess: () => void;
  onCancel: () => void;
}

export function ItemForm({ item, onSuccess, onCancel }: ItemFormProps) {
  const createMutation = useCreateItem();
  const updateMutation = useUpdateItem();

  const { register, handleSubmit, formState: { errors } } = useForm<ItemFormData>({
    resolver: zodResolver(itemSchema),
    defaultValues: {
      item_name: item?.item_name || '',
      item_code: item?.item_code || '',
      item_type: item?.item_type || 'Goods',
      hsn_code: item?.hsn_code || '',
      sac_code: item?.sac_code || '',
      unit_of_measure: item?.unit_of_measure || 'Nos',
      gst_rate: item?.gst_rate?.toString() || '',
      cess_rate: item?.cess_rate?.toString() || '',
      selling_price: item?.selling_price?.toString() || '',
      purchase_price: item?.purchase_price?.toString() || '',
      description: item?.description || '',
      is_nil_rated: item?.is_nil_rated || false,
      is_exempt: item?.is_exempt || false,
      is_non_gst: item?.is_non_gst || false,
    },
  });

  const onSubmit = async (data: ItemFormData) => {
    try {
      const payload: Partial<Item> = {
        item_name: data.item_name,
        item_code: data.item_code,
        item_type: data.item_type,
        hsn_code: data.hsn_code || undefined,
        sac_code: data.sac_code || undefined,
        unit_of_measure: data.unit_of_measure || 'Nos',
        gst_rate: data.gst_rate ? Number(data.gst_rate) : 0,
        cess_rate: data.cess_rate ? Number(data.cess_rate) : 0,
        selling_price: data.selling_price ? Number(data.selling_price) : 0,
        purchase_price: data.purchase_price ? Number(data.purchase_price) : 0,
        description: data.description || undefined,
        is_nil_rated: data.is_nil_rated || false,
        is_exempt: data.is_exempt || false,
        is_non_gst: data.is_non_gst || false,
      };

      if (item?.item_id) {
        await updateMutation.mutateAsync({ id: item.item_id, data: payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onSuccess();
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Item Name" placeholder="Product / Service name" error={errors.item_name?.message} required {...register('item_name')} />
        <Input label="Item Code" placeholder="SKU-001" error={errors.item_code?.message} required {...register('item_code')} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Select label="Type" options={ITEM_TYPES.map((t) => ({ value: t, label: t }))} {...register('item_type')} />
        <Select label="Unit" options={UNITS.map((u) => ({ value: u, label: u }))} {...register('unit_of_measure')} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="HSN Code" placeholder="8471" {...register('hsn_code')} helperText="For goods" />
        <Input label="SAC Code" placeholder="9983" {...register('sac_code')} helperText="For services" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Input label="GST Rate (%)" type="number" step="0.1" placeholder="18" {...register('gst_rate')} />
        <Input label="Cess Rate (%)" type="number" step="0.1" placeholder="0" {...register('cess_rate')} />
        <Input label="Description" placeholder="Optional description" {...register('description')} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Selling Price" type="number" step="0.01" placeholder="0" {...register('selling_price')} />
        <Input label="Purchase Price" type="number" step="0.01" placeholder="0" {...register('purchase_price')} />
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={createMutation.isPending || updateMutation.isPending}>
          {item ? 'Update' : 'Create'} Item
        </Button>
      </div>
    </form>
  );
}