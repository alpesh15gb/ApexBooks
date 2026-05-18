import { useSettings, useUpdateSettings } from '@/lib/hooks';
import { PageHeader } from '@/components/ui/PageHeader';
import { CardSkeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { Tabs } from '@/components/ui/Tabs';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useState } from 'react';

const SETTINGS_TABS = [
  { id: 'business', label: 'Business' },
  { id: 'invoice', label: 'Invoice' },
  { id: 'gst', label: 'GST' },
  { id: 'accounting', label: 'Accounting' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'payments', label: 'Payments' },
];

interface SettingsFormData {
  [key: string]: string | number | null | undefined;
}

function BusinessForm({ data, onSave, isSaving }: { data: any; onSave: (data: any) => void; isSaving: boolean }) {
  const [form, setForm] = useState<SettingsFormData>(data || {
    business_name: '',
    legal_name: '',
    gstin: '',
    pan: '',
    business_type: 'Proprietorship',
    address_line1: '',
    city: '',
    state: '',
    pincode: '',
    phone: '',
    email: '',
    website: '',
    default_currency: 'INR',
    financial_year_start: 4,
    timezone: 'Asia/Kolkata',
    language: 'en',
  });

  const handleChange = (field: string, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Business Name"
          value={form.business_name || ''}
          onChange={(e) => handleChange('business_name', e.target.value)}
          placeholder="Enter business name"
        />
        <Input
          label="Legal Name"
          value={form.legal_name || ''}
          onChange={(e) => handleChange('legal_name', e.target.value)}
          placeholder="Enter legal name"
        />
        <Input
          label="GSTIN"
          value={form.gstin || ''}
          onChange={(e) => handleChange('gstin', e.target.value.toUpperCase())}
          placeholder="22AAAAA0000A1Z5"
          maxLength={15}
        />
        <Input
          label="PAN"
          value={form.pan || ''}
          onChange={(e) => handleChange('pan', e.target.value.toUpperCase())}
          placeholder="AAAAA0000A"
          maxLength={10}
        />
        <div>
          <label className="label">Business Type</label>
          <select
            className="input w-full"
            value={form.business_type || 'Proprietorship'}
            onChange={(e) => handleChange('business_type', e.target.value)}
          >
            <option value="Proprietorship">Proprietorship</option>
            <option value="Partnership">Partnership</option>
            <option value="Private Limited">Private Limited</option>
            <option value="Public Limited">Public Limited</option>
            <option value="LLP">LLP</option>
          </select>
        </div>
        <Input
          label="Email"
          type="email"
          value={form.email || ''}
          onChange={(e) => handleChange('email', e.target.value)}
          placeholder="contact@business.com"
        />
        <Input
          label="Phone"
          type="tel"
          value={form.phone || ''}
          onChange={(e) => handleChange('phone', e.target.value)}
          placeholder="+91 98765 43210"
        />
        <Input
          label="Website"
          type="url"
          value={form.website || ''}
          onChange={(e) => handleChange('website', e.target.value)}
          placeholder="https://example.com"
        />
        <Input
          label="Address Line 1"
          value={form.address_line1 || ''}
          onChange={(e) => handleChange('address_line1', e.target.value)}
          placeholder="Street address"
        />
        <Input
          label="City"
          value={form.city || ''}
          onChange={(e) => handleChange('city', e.target.value)}
          placeholder="City"
        />
        <Input
          label="State"
          value={form.state || ''}
          onChange={(e) => handleChange('state', e.target.value)}
          placeholder="State"
        />
        <Input
          label="Pincode"
          value={form.pincode || ''}
          onChange={(e) => handleChange('pincode', e.target.value)}
          placeholder="123456"
          maxLength={6}
        />
        <div>
          <label className="label">Financial Year Start</label>
          <select
            className="input w-full"
            value={form.financial_year_start || 4}
            onChange={(e) => handleChange('financial_year_start', parseInt(e.target.value))}
          >
            <option value={1}>January</option>
            <option value={4}>April</option>
            <option value={7}>July</option>
            <option value={10}>October</option>
          </select>
        </div>
        <Input
          label="Timezone"
          value={form.timezone || 'Asia/Kolkata'}
          onChange={(e) => handleChange('timezone', e.target.value)}
          placeholder="Asia/Kolkata"
        />
      </div>
      <div className="flex justify-end gap-2 pt-4">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

function InvoiceForm({ data, onSave, isSaving }: { data: any; onSave: (data: any) => void; isSaving: boolean }) {
  const sales = data?.sales || {};
  const purchase = data?.purchase || {};
  const template = data?.template || {};

  const [form, setForm] = useState({
    sales: {
      series: sales.series || { prefix: 'INV', starting_number: 1, auto_numbering: true, number_reset_yearly: true },
      default_due_days: sales.default_due_days || 0,
      show_bank_details: sales.show_bank_details ?? true,
      show_hsn_sac: sales.show_hsn_sac ?? true,
    },
    purchase: {
      series: purchase.series || { prefix: 'PUR', starting_number: 1, auto_numbering: true, number_reset_yearly: true },
      vendor_bill_number_mandatory: purchase.vendor_bill_number_mandatory ?? true,
    },
    template: {
      template_style: template.template_style || 'Modern',
      primary_color: template.primary_color || '#10B981',
      terms_and_conditions: template.terms_and_conditions || '',
    },
  });

  const handleChange = (section: string, field: string, value: any) => {
    setForm((prev: any) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value,
      },
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      sales: form.sales,
      purchase: form.purchase,
      template: form.template,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Sales Invoice</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Series Prefix"
            value={form.sales.series.prefix}
            onChange={(e) => handleChange('sales', 'series', { ...form.sales.series, prefix: e.target.value })}
            placeholder="INV"
          />
          <Input
            label="Starting Number"
            type="number"
            value={form.sales.series.starting_number}
            onChange={(e) => handleChange('sales', 'series', { ...form.sales.series, starting_number: parseInt(e.target.value) })}
          />
          <Input
            label="Default Due Days"
            type="number"
            value={form.sales.default_due_days}
            onChange={(e) => handleChange('sales', 'default_due_days', parseInt(e.target.value))}
          />
          <div className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              id="auto_numbering"
              checked={form.sales.series.auto_numbering}
              onChange={(e) => handleChange('sales', 'series', { ...form.sales.series, auto_numbering: e.target.checked })}
            />
            <label htmlFor="auto_numbering" className="label">Auto-numbering</label>
          </div>
          <div className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              id="show_bank"
              checked={form.sales.show_bank_details}
              onChange={(e) => handleChange('sales', 'show_bank_details', e.target.checked)}
            />
            <label htmlFor="show_bank" className="label">Show bank details</label>
          </div>
          <div className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              id="show_hsn"
              checked={form.sales.show_hsn_sac}
              onChange={(e) => handleChange('sales', 'show_hsn_sac', e.target.checked)}
            />
            <label htmlFor="show_hsn" className="label">Show HSN/SAC</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Purchase Invoice</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Series Prefix"
            value={form.purchase.series.prefix}
            onChange={(e) => handleChange('purchase', 'series', { ...form.purchase.series, prefix: e.target.value })}
            placeholder="PUR"
          />
          <Input
            label="Starting Number"
            type="number"
            value={form.purchase.series.starting_number}
            onChange={(e) => handleChange('purchase', 'series', { ...form.purchase.series, starting_number: parseInt(e.target.value) })}
          />
          <div className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              id="vendor_bill_mandatory"
              checked={form.purchase.vendor_bill_number_mandatory}
              onChange={(e) => handleChange('purchase', 'vendor_bill_number_mandatory', e.target.checked)}
            />
            <label htmlFor="vendor_bill_mandatory" className="label">Vendor bill number mandatory</label>
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

function GSTForm({ data, onSave, isSaving }: { data: any; onSave: (data: any) => void; isSaving: boolean }) {
  const core = data?.core || {};
  const einvoice = data?.einvoice || {};
  const ewaybill = data?.ewaybill || {};

  const [form, setForm] = useState({
    core: {
      enabled: core.enabled ?? true,
      scheme: core.scheme || 'regular',
      inclusive_exclusive: core.inclusive_exclusive || 'exclusive',
      reverse_charge: core.reverse_charge ?? false,
    },
    einvoice: {
      enabled: einvoice.enabled ?? false,
      auto_generate_irn: einvoice.auto_generate_irn ?? true,
      auto_cancel_irn: einvoice.auto_cancel_irn ?? true,
    },
    ewaybill: {
      enabled: ewaybill.enabled ?? false,
      auto_generation: ewaybill.auto_generation ?? true,
    },
  });

  const handleChange = (section: string, field: string, value: any) => {
    setForm((prev: any) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value,
      },
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      core: form.core,
      einvoice: form.einvoice,
      ewaybill: form.ewaybill,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">GST Core Settings</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="gst_enabled"
              checked={form.core.enabled}
              onChange={(e) => handleChange('core', 'enabled', e.target.checked)}
            />
            <label htmlFor="gst_enabled" className="label">GST Enabled</label>
          </div>
          <div>
            <label className="label">Scheme</label>
            <select
              className="input w-full"
              value={form.core.scheme}
              onChange={(e) => handleChange('core', 'scheme', e.target.value)}
            >
              <option value="regular">Regular</option>
              <option value="composition">Composition</option>
            </select>
          </div>
          <div>
            <label className="label">Tax Inclusive/Exclusive</label>
            <select
              className="input w-full"
              value={form.core.inclusive_exclusive}
              onChange={(e) => handleChange('core', 'inclusive_exclusive', e.target.value)}
            >
              <option value="exclusive">Exclusive</option>
              <option value="inclusive">Inclusive</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="reverse_charge"
              checked={form.core.reverse_charge}
              onChange={(e) => handleChange('core', 'reverse_charge', e.target.checked)}
            />
            <label htmlFor="reverse_charge" className="label">Reverse Charge</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">E-Invoice Settings</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="einvoice_enabled"
              checked={form.einvoice.enabled}
              onChange={(e) => handleChange('einvoice', 'enabled', e.target.checked)}
            />
            <label htmlFor="einvoice_enabled" className="label">E-Invoice Enabled</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto_generate_irn"
              checked={form.einvoice.auto_generate_irn}
              onChange={(e) => handleChange('einvoice', 'auto_generate_irn', e.target.checked)}
            />
            <label htmlFor="auto_generate_irn" className="label">Auto-generate IRN</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto_cancel_irn"
              checked={form.einvoice.auto_cancel_irn}
              onChange={(e) => handleChange('einvoice', 'auto_cancel_irn', e.target.checked)}
            />
            <label htmlFor="auto_cancel_irn" className="label">Auto-cancel IRN</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">E-Way Bill Settings</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="ewaybill_enabled"
              checked={form.ewaybill.enabled}
              onChange={(e) => handleChange('ewaybill', 'enabled', e.target.checked)}
            />
            <label htmlFor="ewaybill_enabled" className="label">E-Way Bill Enabled</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto_generation"
              checked={form.ewaybill.auto_generation}
              onChange={(e) => handleChange('ewaybill', 'auto_generation', e.target.checked)}
            />
            <label htmlFor="auto_generation" className="label">Auto-generate E-Way Bill</label>
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

function AccountingForm({ data, onSave, isSaving }: { data: any; onSave: (data: any) => void; isSaving: boolean }) {
  const ledgerDefaults = data?.ledger_defaults || {};
  const journal = data?.journal || {};
  const financialControls = data?.financial_controls || {};

  const [form, setForm] = useState({
    ledger_defaults: {
      default_sales_ledger: ledgerDefaults.default_sales_ledger || 'Accounts Receivable',
      default_purchase_ledger: ledgerDefaults.default_purchase_ledger || 'Accounts Payable',
      cash_ledger: ledgerDefaults.cash_ledger || 'Cash',
      round_off_ledger: ledgerDefaults.round_off_ledger || 'Round Off',
    },
    journal: {
      auto_journal_posting: journal.auto_journal_posting ?? true,
      allow_edit_locked_entries: journal.allow_edit_locked_entries ?? false,
      allow_backdated_entries: journal.allow_backdated_entries ?? true,
      require_voucher_approval: journal.require_voucher_approval ?? false,
    },
    financial_controls: {
      lock_books_till_date: financialControls.lock_books_till_date || null,
      audit_mode: financialControls.audit_mode ?? false,
      freeze_transactions_before: financialControls.freeze_transactions_before || null,
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      ledger_defaults: form.ledger_defaults,
      journal: form.journal,
      financial_controls: form.financial_controls,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Ledger Defaults</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Default Sales Ledger"
            value={form.ledger_defaults.default_sales_ledger}
            onChange={(e) => setForm(prev => ({ ...prev, ledger_defaults: { ...prev.ledger_defaults, default_sales_ledger: e.target.value } }))}
          />
          <Input
            label="Default Purchase Ledger"
            value={form.ledger_defaults.default_purchase_ledger}
            onChange={(e) => setForm(prev => ({ ...prev, ledger_defaults: { ...prev.ledger_defaults, default_purchase_ledger: e.target.value } }))}
          />
          <Input
            label="Cash Ledger"
            value={form.ledger_defaults.cash_ledger}
            onChange={(e) => setForm(prev => ({ ...prev, ledger_defaults: { ...prev.ledger_defaults, cash_ledger: e.target.value } }))}
          />
          <Input
            label="Round Off Ledger"
            value={form.ledger_defaults.round_off_ledger}
            onChange={(e) => setForm(prev => ({ ...prev, ledger_defaults: { ...prev.ledger_defaults, round_off_ledger: e.target.value } }))}
          />
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Journal Settings</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto_journal"
              checked={form.journal.auto_journal_posting}
              onChange={(e) => setForm(prev => ({ ...prev, journal: { ...prev.journal, auto_journal_posting: e.target.checked } }))}
            />
            <label htmlFor="auto_journal" className="label">Auto journal posting</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="allow_backdated"
              checked={form.journal.allow_backdated_entries}
              onChange={(e) => setForm(prev => ({ ...prev, journal: { ...prev.journal, allow_backdated_entries: e.target.checked } }))}
            />
            <label htmlFor="allow_backdated" className="label">Allow backdated entries</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="edit_locked"
              checked={form.journal.allow_edit_locked_entries}
              onChange={(e) => setForm(prev => ({ ...prev, journal: { ...prev.journal, allow_edit_locked_entries: e.target.checked } }))}
            />
            <label htmlFor="edit_locked" className="label">Allow edit locked entries</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="require_approval"
              checked={form.journal.require_voucher_approval}
              onChange={(e) => setForm(prev => ({ ...prev, journal: { ...prev.journal, require_voucher_approval: e.target.checked } }))}
            />
            <label htmlFor="require_approval" className="label">Require voucher approval</label>
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

function InventoryForm({ data, onSave, isSaving }: { data: any; onSave: (data: any) => void; isSaving: boolean }) {
  const controls = data?.controls || {};
  const pricing = data?.pricing || {};
  const valuation = data?.valuation || {};

  const [form, setForm] = useState({
    controls: {
      allow_negative_stock: controls.allow_negative_stock ?? false,
      batch_tracking: controls.batch_tracking ?? false,
      expiry_tracking: controls.expiry_tracking ?? false,
      serial_number_tracking: controls.serial_number_tracking ?? false,
      barcode_enabled: controls.barcode_enabled ?? false,
      auto_sku_generation: controls.auto_sku_generation ?? true,
    },
    pricing: {
      enable_wholesale: pricing.enable_wholesale ?? false,
      enable_retail: pricing.enable_retail ?? false,
      enable_dealer: pricing.enable_dealer ?? false,
      enable_custom_pricing: pricing.enable_custom_pricing ?? false,
    },
    valuation: {
      method: valuation?.method || 'fifo',
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      controls: form.controls,
      pricing: form.pricing,
      valuation: form.valuation,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Inventory Controls</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="negative_stock"
              checked={form.controls.allow_negative_stock}
              onChange={(e) => setForm(prev => ({ ...prev, controls: { ...prev.controls, allow_negative_stock: e.target.checked } }))}
            />
            <label htmlFor="negative_stock" className="label">Allow negative stock</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="batch_tracking"
              checked={form.controls.batch_tracking}
              onChange={(e) => setForm(prev => ({ ...prev, controls: { ...prev.controls, batch_tracking: e.target.checked } }))}
            />
            <label htmlFor="batch_tracking" className="label">Batch tracking</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="expiry_tracking"
              checked={form.controls.expiry_tracking}
              onChange={(e) => setForm(prev => ({ ...prev, controls: { ...prev.controls, expiry_tracking: e.target.checked } }))}
            />
            <label htmlFor="expiry_tracking" className="label">Expiry tracking</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="serial_tracking"
              checked={form.controls.serial_number_tracking}
              onChange={(e) => setForm(prev => ({ ...prev, controls: { ...prev.controls, serial_number_tracking: e.target.checked } }))}
            />
            <label htmlFor="serial_tracking" className="label">Serial number tracking</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="barcode_enabled"
              checked={form.controls.barcode_enabled}
              onChange={(e) => setForm(prev => ({ ...prev, controls: { ...prev.controls, barcode_enabled: e.target.checked } }))}
            />
            <label htmlFor="barcode_enabled" className="label">Barcode enabled</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto_sku"
              checked={form.controls.auto_sku_generation}
              onChange={(e) => setForm(prev => ({ ...prev, controls: { ...prev.controls, auto_sku_generation: e.target.checked } }))}
            />
            <label htmlFor="auto_sku" className="label">Auto SKU generation</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Pricing Levels</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="wholesale"
              checked={form.pricing.enable_wholesale}
              onChange={(e) => setForm(prev => ({ ...prev, pricing: { ...prev.pricing, enable_wholesale: e.target.checked } }))}
            />
            <label htmlFor="wholesale" className="label">Wholesale pricing</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="retail"
              checked={form.pricing.enable_retail}
              onChange={(e) => setForm(prev => ({ ...prev, pricing: { ...prev.pricing, enable_retail: e.target.checked } }))}
            />
            <label htmlFor="retail" className="label">Retail pricing</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="dealer"
              checked={form.pricing.enable_dealer}
              onChange={(e) => setForm(prev => ({ ...prev, pricing: { ...prev.pricing, enable_dealer: e.target.checked } }))}
            />
            <label htmlFor="dealer" className="label">Dealer pricing</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="custom_pricing"
              checked={form.pricing.enable_custom_pricing}
              onChange={(e) => setForm(prev => ({ ...prev, pricing: { ...prev.pricing, enable_custom_pricing: e.target.checked } }))}
            />
            <label htmlFor="custom_pricing" className="label">Custom pricing</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Valuation Method</h4>
        <div>
          <label className="label">Stock Valuation</label>
          <select
            className="input w-full"
            value={form.valuation.method}
            onChange={(e) => setForm(prev => ({ ...prev, valuation: { ...prev.valuation, method: e.target.value } }))}
          >
            <option value="fifo">FIFO (First In First Out)</option>
            <option value="weighted_average">Weighted Average</option>
          </select>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

function PaymentsForm({ data, onSave, isSaving }: { data: any; onSave: (data: any) => void; isSaving: boolean }) {
  const upi = data?.upi || {};
  const gateways = data?.gateways || {};
  const banking = data?.banking || {};
  const reminders = data?.reminders || {};

  const [form, setForm] = useState({
    upi: {
      enabled: upi.enabled ?? false,
      qr_codes: upi.qr_codes || [],
    },
    gateways: {
      razorpay: gateways.razorpay ?? false,
      phonepe: gateways.phonepe ?? false,
      cashfree: gateways.cashfree ?? false,
      stripe: gateways.stripe ?? false,
    },
    banking: {
      auto_reconciliation: banking.auto_reconciliation ?? false,
      import_bank_statements: banking.import_bank_statements ?? false,
    },
    reminders: {
      whatsapp_enabled: reminders.whatsapp_enabled ?? false,
      sms_enabled: reminders.sms_enabled ?? false,
      email_enabled: reminders.email_enabled ?? true,
      days_before_due: reminders.days_before_due || 3,
      days_after_due: reminders.days_after_due || 7,
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      upi: form.upi,
      gateways: form.gateways,
      banking: form.banking,
      reminders: form.reminders,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Payment Gateways</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="razorpay"
              checked={form.gateways.razorpay}
              onChange={(e) => setForm(prev => ({ ...prev, gateways: { ...prev.gateways, razorpay: e.target.checked } }))}
            />
            <label htmlFor="razorpay" className="label">Razorpay</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="phonepe"
              checked={form.gateways.phonepe}
              onChange={(e) => setForm(prev => ({ ...prev, gateways: { ...prev.gateways, phonepe: e.target.checked } }))}
            />
            <label htmlFor="phonepe" className="label">PhonePe</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="cashfree"
              checked={form.gateways.cashfree}
              onChange={(e) => setForm(prev => ({ ...prev, gateways: { ...prev.gateways, cashfree: e.target.checked } }))}
            />
            <label htmlFor="cashfree" className="label">Cashfree</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="stripe"
              checked={form.gateways.stripe}
              onChange={(e) => setForm(prev => ({ ...prev, gateways: { ...prev.gateways, stripe: e.target.checked } }))}
            />
            <label htmlFor="stripe" className="label">Stripe</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Banking</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="auto_reconciliation"
              checked={form.banking.auto_reconciliation}
              onChange={(e) => setForm(prev => ({ ...prev, banking: { ...prev.banking, auto_reconciliation: e.target.checked } }))}
            />
            <label htmlFor="auto_reconciliation" className="label">Auto reconciliation</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="import_statements"
              checked={form.banking.import_bank_statements}
              onChange={(e) => setForm(prev => ({ ...prev, banking: { ...prev.banking, import_bank_statements: e.target.checked } }))}
            />
            <label htmlFor="import_statements" className="label">Import bank statements</label>
          </div>
        </div>
      </div>

      <div className="card-border rounded-lg p-4 bg-gray-50">
        <h4 className="font-semibold mb-3">Payment Reminders</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="email_reminder"
              checked={form.reminders.email_enabled}
              onChange={(e) => setForm(prev => ({ ...prev, reminders: { ...prev.reminders, email_enabled: e.target.checked } }))}
            />
            <label htmlFor="email_reminder" className="label">Email reminders</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="sms_reminder"
              checked={form.reminders.sms_enabled}
              onChange={(e) => setForm(prev => ({ ...prev, reminders: { ...prev.reminders, sms_enabled: e.target.checked } }))}
            />
            <label htmlFor="sms_reminder" className="label">SMS reminders</label>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="whatsapp_reminder"
              checked={form.reminders.whatsapp_enabled}
              onChange={(e) => setForm(prev => ({ ...prev, reminders: { ...prev.reminders, whatsapp_enabled: e.target.checked } }))}
            />
            <label htmlFor="whatsapp_reminder" className="label">WhatsApp reminders</label>
          </div>
          <Input
            label="Days Before Due"
            type="number"
            value={form.reminders.days_before_due}
            onChange={(e) => setForm(prev => ({ ...prev, reminders: { ...prev.reminders, days_before_due: parseInt(e.target.value) } }))}
          />
          <Input
            label="Days After Due"
            type="number"
            value={form.reminders.days_after_due}
            onChange={(e) => setForm(prev => ({ ...prev, reminders: { ...prev.reminders, days_after_due: parseInt(e.target.value) } }))}
          />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>
    </form>
  );
}

export function SettingsPage() {
  const [tab, setTab] = useState('business');
  const { data, isLoading, error, refetch } = useSettings();
  const updateSettings = useUpdateSettings();

  const handleSave = (category: string, formData: any) => {
    updateSettings.mutate(
      { category, data: formData },
      {
        onSuccess: () => {
          refetch();
        },
      },
    );
  };

  const renderForm = () => {
    const categoryData = data?.[tab];

    switch (tab) {
      case 'business':
        return <BusinessForm data={categoryData} onSave={(data) => handleSave('business', data)} isSaving={updateSettings.isPending} />;
      case 'invoice':
        return <InvoiceForm data={categoryData} onSave={(data) => handleSave('invoice', data)} isSaving={updateSettings.isPending} />;
      case 'gst':
        return <GSTForm data={categoryData} onSave={(data) => handleSave('gst', data)} isSaving={updateSettings.isPending} />;
      case 'accounting':
        return <AccountingForm data={categoryData} onSave={(data) => handleSave('accounting', data)} isSaving={updateSettings.isPending} />;
      case 'inventory':
        return <InventoryForm data={categoryData} onSave={(data) => handleSave('inventory', data)} isSaving={updateSettings.isPending} />;
      case 'payments':
        return <PaymentsForm data={categoryData} onSave={(data) => handleSave('payments', data)} isSaving={updateSettings.isPending} />;
      default:
        return <div className="p-4 text-gray-500">Unknown settings category</div>;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" subtitle="Configure your company and application settings" />

      <Tabs tabs={SETTINGS_TABS} active={tab} onChange={setTab} />

      <div className="card">
        <div className="card-header">
          <h3 className="font-semibold text-gray-900 capitalize">{tab} Settings</h3>
        </div>
        <div className="card-body">
          {isLoading ? (
            <CardSkeleton count={3} />
          ) : error ? (
            <ErrorState onRetry={refetch} />
          ) : (
            renderForm()
          )}
        </div>
      </div>
    </div>
  );
}
