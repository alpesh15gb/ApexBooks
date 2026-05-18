import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useCreateParty, useUpdateParty } from '@/lib/hooks';
import { apiErrorToString, STATE_CODES } from '@/utils/validation';
import type { Party } from '@/types';
import toast from 'react-hot-toast';

const partySchema = z.object({
  party_name: z.string().min(1, 'Name is required'),
  gstin: z.string().length(15, 'GSTIN must be 15 characters').optional().or(z.literal('')),
  pan: z.string().length(10, 'PAN must be 10 characters').optional().or(z.literal('')),
  state_code: z.string().optional(),
  party_category: z.string().optional(),
  registration_type: z.string().optional(),
  credit_limit: z.string().optional(),
  credit_days: z.string().optional(),
  opening_balance: z.string().optional(),
  tds_applicable: z.boolean().optional(),
  contact_name: z.string().optional(),
  contact_phone: z.string().optional(),
  contact_email: z.string().optional(),
  address_line1: z.string().optional(),
  address_city: z.string().optional(),
  address_pincode: z.string().optional(),
});

type PartyFormData = z.infer<typeof partySchema>;

interface PartyFormProps {
  party?: Party | null;
  partyType: 'Customer' | 'Vendor';
  onSuccess: () => void;
  onCancel: () => void;
}

export function PartyForm({ party, partyType, onSuccess, onCancel }: PartyFormProps) {
  const createMutation = useCreateParty();
  const updateMutation = useUpdateParty();
  const isEditing = !!party;

  const defaultAddress = party?.addresses?.[0];
  const defaultContact = party?.contacts?.[0];

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PartyFormData>({
    resolver: zodResolver(partySchema),
    defaultValues: {
      party_name: party?.party_name || '',
      gstin: party?.gstin || '',
      pan: party?.pan || '',
      state_code: party?.state_code || '',
      party_category: party?.party_category || '',
      registration_type: party?.registration_type || '',
      credit_limit: party?.credit_limit?.toString() || '',
      credit_days: party?.credit_days?.toString() || '',
      opening_balance: party?.opening_balance?.toString() || '',
      tds_applicable: party?.tds_applicable || false,
      contact_name: defaultContact?.name || '',
      contact_phone: defaultContact?.phone || '',
      contact_email: defaultContact?.email || '',
      address_line1: defaultAddress?.line1 || '',
      address_city: defaultAddress?.city || '',
      address_pincode: defaultAddress?.pincode || '',
    },
  });

  const onSubmit = async (data: PartyFormData) => {
    try {
      const payload: Partial<Party> = {
        party_type: partyType,
        party_name: data.party_name,
        gstin: data.gstin || undefined,
        pan: data.pan || undefined,
        state_code: data.state_code || undefined,
        party_category: data.party_category || undefined,
        registration_type: data.registration_type || undefined,
        credit_limit: data.credit_limit ? Number(data.credit_limit) : 0,
        credit_days: data.credit_days ? Number(data.credit_days) : 0,
        opening_balance: data.opening_balance ? Number(data.opening_balance) : 0,
        tds_applicable: data.tds_applicable || false,
        contacts: data.contact_name
          ? [{ name: data.contact_name, phone: data.contact_phone, email: data.contact_email }]
          : [],
        addresses: data.address_line1
          ? [{ line1: data.address_line1, city: data.address_city || '', pincode: data.address_pincode || '', state_code: data.state_code || '' }]
          : [],
      };

      if (isEditing && party?.party_id) {
        await updateMutation.mutateAsync({ id: party.party_id, data: payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onSuccess();
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  const stateOptions = Object.entries(STATE_CODES).map(([value, label]) => ({ value, label: `${value} - ${label}` }));

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Party Name" placeholder="Full name" error={errors.party_name?.message} required {...register('party_name')} />
        <Input label="GSTIN" placeholder="27AAAAA0000A1Z5" error={errors.gstin?.message} {...register('gstin')} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="PAN" placeholder="AAAAA0000A" error={errors.pan?.message} {...register('pan')} />
        <Select label="State" placeholder="Select state" options={stateOptions} {...register('state_code')} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="Category" placeholder="Retail / Wholesale" {...register('party_category')} />
        <Input label="Registration Type" placeholder="Regular" {...register('registration_type')} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Input label="Credit Limit" type="number" placeholder="0" {...register('credit_limit')} />
        <Input label="Credit Days" type="number" placeholder="0" {...register('credit_days')} />
        <Input label="Opening Balance" type="number" placeholder="0" {...register('opening_balance')} />
      </div>

      <hr className="border-gray-200" />
      <p className="text-sm font-medium text-gray-700">Contact Information</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Input label="Contact Person" placeholder="Name" {...register('contact_name')} />
        <Input label="Phone" placeholder="9876543210" {...register('contact_phone')} />
        <Input label="Email" type="email" placeholder="email@example.com" {...register('contact_email')} />
      </div>

      <hr className="border-gray-200" />
      <p className="text-sm font-medium text-gray-700">Address</p>
      <Input label="Address Line" placeholder="Building, Street" {...register('address_line1')} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input label="City" placeholder="Mumbai" {...register('address_city')} />
        <Input label="Pincode" placeholder="400001" {...register('address_pincode')} />
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={isSubmitting || createMutation.isPending || updateMutation.isPending}>
          {isEditing ? 'Update' : 'Create'} Party
        </Button>
      </div>
    </form>
  );
}