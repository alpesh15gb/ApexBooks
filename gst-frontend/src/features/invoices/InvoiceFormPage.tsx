import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input, Select } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/PageHeader';
import { useCreateInvoice, useUpdateInvoice, useInvoice, useParties, useSettings, useItems } from '@/lib/hooks';
import { apiErrorToString, STATE_CODES, SUPPLY_TYPES } from '@/utils/validation';
import { formatCurrency, formatDate } from '@/utils/format';
import { Trash2, Plus, ArrowLeft, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';

const lineSchema = z.object({
  item_name: z.string().min(1, 'Required'),
  hsn_code: z.string().optional(),
  quantity: z.string().min(1, 'Required'),
  unit: z.string().optional(),
  unit_price: z.string().min(1, 'Required'),
  gst_rate: z.string().optional(),
  discount_percent: z.string().optional(),
});

const invoiceSchema = z.object({
  invoice_date: z.string().min(1, 'Date is required'),
  due_date: z.string().optional().or(z.literal('')),
  party_id: z.string().optional(),
  party_name: z.string().optional(),
  party_gstin: z.string().optional().or(z.literal('')),
  place_of_supply: z.string().optional(),
  supply_type: z.string().optional(),
  reverse_charge: z.boolean().optional(),
  notes: z.string().optional(),
  lines: z.array(lineSchema).min(1, 'At least one line item is required'),
}).refine(data => data.party_id || data.party_name, {
  message: 'Select an existing party or enter a new party name',
  path: ['party_id'],
});

type InvoiceFormData = z.infer<typeof invoiceSchema>;

export function InvoiceFormPage() {
  const navigate = useNavigate();
  const { kind, id } = useParams<{ kind: 'sales' | 'purchase'; id?: string }>();
  const isEdit = !!id;
  const createMutation = useCreateInvoice();
  const updateMutation = useUpdateInvoice();
  const { data: existingInvoice, isLoading: loadingInvoice } = useInvoice(kind as 'sales' | 'purchase', id || '');
  const { data: partiesData } = useParties();
  const { data: settingsData } = useSettings();
  const { data: itemsData } = useItems();

  const parties = (partiesData as any)?.items || partiesData || [];
  const items = (itemsData as any)?.items || itemsData || [];
  const [partySearch, setPartySearch] = useState('');
  const [selectedParty, setSelectedParty] = useState<any>(null);
  const sellerStateCode = String(settingsData?.business?.state_code || '27');

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<InvoiceFormData>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: {
      invoice_date: new Date().toISOString().split('T')[0],
      supply_type: 'B2B',
      place_of_supply: sellerStateCode,
      lines: [{ item_name: '', hsn_code: '', quantity: '1', unit: 'Nos', unit_price: '0', gst_rate: '18', discount_percent: '0' }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'lines' });
  const lines = watch('lines');
  const selectedPartyId = watch('party_id');

  // Update party GSTIN when party changes
  useEffect(() => {
    if (selectedPartyId && parties.length > 0) {
      const party = parties.find((p: any) => p.party_id === selectedPartyId || p.id === selectedPartyId);
      if (party) {
        setValue('party_gstin', party.gstin || '');
        setValue('party_name', party.party_name || '');
        if (party.state_code) {
          setValue('place_of_supply', party.state_code);
        }
      }
    }
  }, [selectedPartyId, parties, setValue]);

  // When user types party_name manually, auto-clear party selection
  useEffect(() => {
    const sub = watch((value, { name }) => {
      if (name === 'party_name' && value.party_name) {
        setValue('party_id', '');
      }
      if (name === 'party_id' && value.party_id) {
        setValue('party_name', '');
      }
    });
    return () => sub.unsubscribe();
  }, [watch, setValue]);

  // Auto-fill item details when item name matches
  const handleItemSelect = useCallback((index: number, itemName: string) => {
    if (!items || items.length === 0 || !itemName) return;
    const item = items.find((i: any) =>
      i.item_name?.toLowerCase() === itemName.toLowerCase() ||
      i.item_code?.toLowerCase() === itemName.toLowerCase()
    );
    if (item) {
      setValue(`lines.${index}.hsn_code`, item.hsn_code || '');
      setValue(`lines.${index}.unit_price`, String(item.selling_price || 0));
      setValue(`lines.${index}.gst_rate`, String(item.gst_rate || 18));
      setValue(`lines.${index}.unit`, item.unit_of_measure || 'Nos');
    }
  }, [items, setValue]);

  // Load existing invoice data when editing
  useEffect(() => {
    if (isEdit && existingInvoice) {
      const inv = existingInvoice as any;
      setValue('invoice_date', inv.invoice_date || new Date().toISOString().split('T')[0]);
      setValue('due_date', inv.due_date || '');
      setValue('party_id', inv.party_id || '');
      setValue('party_name', inv.party_name || '');
      setValue('party_gstin', inv.party_gstin || '');
      setValue('place_of_supply', inv.place_of_supply || '');
      setValue('supply_type', inv.supply_type || 'B2B');
      setValue('reverse_charge', inv.reverse_charge || false);
      setValue('notes', inv.notes || '');
      if (inv.line_items?.length) {
        setValue('lines', inv.line_items.map((li: any) => ({
          item_name: li.item_name || '',
          hsn_code: li.hsn_code || '',
          quantity: String(li.quantity || 0),
          unit: li.unit || 'Nos',
          unit_price: String(li.unit_price || 0),
          gst_rate: String(li.gst_rate || 18),
          discount_percent: String(li.discount_percent || 0),
        })));
      }
    }
  }, [isEdit, existingInvoice, setValue]);

  const calculateLineTotal = (line: typeof lines[number]) => {
    const qty = Number(line.quantity) || 0;
    const price = Number(line.unit_price) || 0;
    const disc = Number(line.discount_percent) || 0;
    const taxable = qty * price * (1 - disc / 100);
    const gstRate = Number(line.gst_rate) || 0;
    const gst = taxable * (gstRate / 100);
    return { taxable, gst, total: taxable + gst };
  };

  const totals = lines?.reduce(
    (acc, line) => {
      const { taxable, gst, total } = calculateLineTotal(line);
      return {
        taxable: acc.taxable + taxable,
        gst: acc.gst + gst,
        total: acc.total + total,
      };
    },
    { taxable: 0, gst: 0, total: 0 },
  );

  const onSubmit = async (data: InvoiceFormData) => {
    if (!kind) return;
    try {
      const selectedParty = parties.find((p: any) => p.party_id === data.party_id || p.id === data.party_id);
      const payload = {
        invoice_kind: kind,
        invoice_date: data.invoice_date,
        due_date: data.due_date || undefined,
        party_id: data.party_id,
        party_name: selectedParty?.party_name || data.party_name || '',
        party_gstin: data.party_gstin || selectedParty?.gstin || undefined,
        seller_state_code: sellerStateCode,
        place_of_supply: data.place_of_supply || sellerStateCode,
        supply_type: data.supply_type || 'B2B',
        reverse_charge: data.reverse_charge || false,
        notes: data.notes || undefined,
        line_items: data.lines.map((line, i) => {
          const qty = Number(line.quantity) || 0;
          const price = Number(line.unit_price) || 0;
          const disc = Number(line.discount_percent) || 0;
          const taxable = qty * price * (1 - disc / 100);
          const gstRate = Number(line.gst_rate) || 0;
          return {
            line_no: i + 1,
            item_name: line.item_name,
            hsn_code: line.hsn_code || undefined,
            quantity: qty,
            unit: line.unit || 'Nos',
            unit_price: price,
            discount_percent: disc,
            taxable_value: taxable,
            gst_rate: gstRate,
            cgst_amount: taxable * (gstRate / 200),
            sgst_amount: taxable * (gstRate / 200),
            total_amount: taxable + taxable * (gstRate / 100),
          };
        }),
      };

      if (isEdit && id) {
        await updateMutation.mutateAsync({ kind, id, data: payload });
      } else {
        await createMutation.mutateAsync({ kind, data: payload });
      }
      navigate(`/invoices/${kind}`);
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  if (!kind) return <ErrorState message="Invoice type not specified" />;

  if (isEdit && loadingInvoice) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <PageHeader title="Edit Invoice" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader
        title={isEdit ? (kind === 'sales' ? 'Edit Sales Invoice' : 'Edit Purchase Bill') : (kind === 'sales' ? 'New Sales Invoice' : 'New Purchase Bill')}
        actions={
          <Button variant="ghost" onClick={() => navigate(`/invoices/${kind}`)}>
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        }
      />

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        <div className="card">
          <div className="card-header">
            <h3 className="font-semibold text-gray-900">Invoice Details</h3>
          </div>
          <div className="card-body grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Input label="Invoice Date" type="date" error={errors.invoice_date?.message} required {...register('invoice_date')} />
            <Input label="Due Date" type="date" {...register('due_date')} />
            <Select label="Supply Type" options={SUPPLY_TYPES.map((t) => ({ value: t, label: t }))} {...register('supply_type')} />
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="font-semibold text-gray-900">{kind === 'sales' ? 'Customer' : 'Vendor'} Details</h3>
          </div>
          <div className="card-body grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Select Party</label>
              <input className="input mb-1 text-sm" placeholder="Search existing party..." value={partySearch}
                     onChange={e => setPartySearch(e.target.value)} />
              <select className="input w-full text-sm"
                value={selectedPartyId || ''}
                onChange={e => {
                  const pid = e.target.value;
                  setValue('party_id', pid);
                  setValue('party_name', pid ? '' : '');
                  if (pid) setPartySearch('');
                }}>
                <option value="">-- Select existing --</option>
                {parties
                  .filter((p: any) => p.party_name?.toLowerCase().includes(partySearch.toLowerCase()) || p.gstin?.includes(partySearch))
                  .map((p: any) => (
                    <option key={p.party_id} value={p.party_id}>{p.party_name}{p.gstin ? ` (${p.gstin})` : ''}</option>
                  ))}
              </select>
              {errors.party_id && <p className="text-xs text-red-600 mt-1">{errors.party_id.message}</p>}
            </div>
            <div className="space-y-2">
              <label className="label">Or New Party Name</label>
              <Input placeholder="Type new party name for on-the-fly creation"
                value={watch('party_name') || ''}
                onChange={e => {
                  setValue('party_name', e.target.value);
                  if (e.target.value) setValue('party_id', ''); // Clear selection
                }}
              />
            <Input label="GSTIN" placeholder="Auto-filled or enter manually" {...register('party_gstin')} />
            <div>
              <label className="label">Place of Supply</label>
              <select className="input w-full" {...register('place_of_supply')}>
                <option value="">Select state</option>
                {Object.entries(STATE_CODES).map(([v, l]) => (
                  <option key={v} value={v}>{v} - {l}</option>
                ))}
              </select>
            </div>
          </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Line Items</h3>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => append({ item_name: '', hsn_code: '', quantity: '1', unit: 'Nos', unit_price: '0', gst_rate: '18', discount_percent: '0' })}
            >
              <Plus className="h-4 w-4" />
              Add Line
            </Button>
          </div>
          <div className="overflow-x-auto">
            {errors.lines?.root && (
              <p className="text-sm text-red-600 px-6 pt-2">{errors.lines.root.message}</p>
            )}
            <table className="table">
              <thead>
                <tr>
                  <th className="min-w-[180px]">Item</th>
                  <th className="w-20">HSN</th>
                  <th className="w-20 text-right">Qty</th>
                  <th className="w-20">Unit</th>
                  <th className="w-24 text-right">Rate</th>
                  <th className="w-20 text-right">Disc%</th>
                  <th className="w-20 text-right">GST%</th>
                  <th className="w-24 text-right">Amount</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {fields.map((field, i) => {
                  const line = lines?.[i];
                  const { total } = calculateLineTotal(line || { quantity: '0', unit_price: '0', discount_percent: '0', gst_rate: '0' });
                  return (
                    <tr key={field.id}>
                      <td>
                        <input className="input text-sm" placeholder="Item name" list="item-suggestions"
                          {...register(`lines.${i}.item_name`)}
                          onBlur={(e) => handleItemSelect(i, e.target.value)}
                        />
                        <datalist id="item-suggestions">
                          {items.map((item: any) => (
                            <option key={item.item_id} value={item.item_name} data-hsn={item.hsn_code} data-rate={item.gst_rate} data-price={item.selling_price} />
                          ))}
                        </datalist>
                        {errors.lines?.[i]?.item_name && <p className="text-xs text-red-600">{errors.lines[i]?.item_name?.message}</p>}
                      </td>
                      <td><input className="input text-sm" placeholder="HSN" {...register(`lines.${i}.hsn_code`)} /></td>
                      <td><input className="input text-sm text-right" type="number" step="any" min="0" {...register(`lines.${i}.quantity`)} /></td>
                      <td><input className="input text-sm" {...register(`lines.${i}.unit`)} /></td>
                      <td><input className="input text-sm text-right" type="number" step="any" min="0" {...register(`lines.${i}.unit_price`)} /></td>
                      <td><input className="input text-sm text-right" type="number" step="any" min="0" {...register(`lines.${i}.discount_percent`)} /></td>
                      <td><input className="input text-sm text-right" type="number" step="any" min="0" {...register(`lines.${i}.gst_rate`)} /></td>
                      <td className="text-right font-medium text-sm">{formatCurrency(total)}</td>
                      <td>
                        {fields.length > 1 && (
                          <button type="button" className="btn-ghost p-1" onClick={() => remove(i)} aria-label="Remove line">
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="border-t border-gray-100 px-6 py-4">
            <div className="ml-auto w-full sm:w-64 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Taxable</span>
                <span className="font-medium">{formatCurrency(totals?.taxable || 0)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">GST</span>
                <span className="font-medium">{formatCurrency(totals?.gst || 0)}</span>
              </div>
              <div className="flex justify-between text-base font-semibold border-t border-gray-200 pt-1">
                <span>Total</span>
                <span>{formatCurrency(totals?.total || 0)}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-body">
            <Input label="Notes (optional)" placeholder="Any additional notes..." {...register('notes')} />
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => navigate(`/invoices/${kind}`)}>
            Cancel
          </Button>
          <Button type="submit" loading={createMutation.isPending || updateMutation.isPending}>
            <Save className="h-4 w-4" />
            {isEdit ? 'Update' : 'Save'} {kind === 'sales' ? 'Invoice' : 'Bill'}
          </Button>
        </div>
      </form>
    </div>
  );
}
