import { useState } from 'react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { useCreateJournal } from '@/lib/hooks';
import { apiErrorToString } from '@/utils/validation';
import { formatCurrency } from '@/utils/format';
import { Trash2, Plus } from 'lucide-react';
import toast from 'react-hot-toast';

interface JournalLineInput {
  account: string;
  debit: string;
  credit: string;
}

export function JournalForm({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const mutation = useCreateJournal();
  const [entryDate, setEntryDate] = useState(new Date().toISOString().split('T')[0]);
  const [reference, setReference] = useState('');
  const [narration, setNarration] = useState('');
  const [lines, setLines] = useState<JournalLineInput[]>([
    { account: '', debit: '0', credit: '0' },
    { account: '', debit: '0', credit: '0' },
  ]);

  const totalDebit = lines.reduce((sum, l) => sum + (Number(l.debit) || 0), 0);
  const totalCredit = lines.reduce((sum, l) => sum + (Number(l.credit) || 0), 0);
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01;

  const addLine = () => setLines([...lines, { account: '', debit: '0', credit: '0' }]);

  const updateLine = (i: number, field: keyof JournalLineInput, value: string) => {
    const updated = [...lines];
    updated[i] = { ...updated[i], [field]: value };
    setLines(updated);
  };

  const removeLine = (i: number) => {
    if (lines.length <= 2) return;
    setLines(lines.filter((_, idx) => idx !== i));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isBalanced) {
      toast.error('Debit and Credit totals must be equal');
      return;
    }
    if (!entryDate) {
      toast.error('Entry date is required');
      return;
    }

    try {
      await mutation.mutateAsync({
        entry_date: entryDate,
        reference: reference || undefined,
        narration: narration || undefined,
        entries: lines.map((l) => ({
          account: l.account,
          debit: Number(l.debit) || 0,
          credit: Number(l.credit) || 0,
        })),
      });
      onSuccess();
    } catch (err) {
      toast.error(apiErrorToString(err));
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Input label="Entry Date" type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} required />
        <Input label="Reference" placeholder="Ref number" value={reference} onChange={(e) => setReference(e.target.value)} />
        <Input label="Narration" placeholder="Description" value={narration} onChange={(e) => setNarration(e.target.value)} />
      </div>

      <div className="border rounded-lg overflow-hidden">
        <table className="table">
          <thead>
            <tr>
              <th className="min-w-[200px]">Account</th>
              <th className="w-32 text-right">Debit</th>
              <th className="w-32 text-right">Credit</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, i) => (
              <tr key={i}>
                <td>
                  <input
                    className="input text-sm"
                    placeholder="Account name"
                    value={line.account}
                    onChange={(e) => updateLine(i, 'account', e.target.value)}
                    required
                  />
                </td>
                <td>
                  <input
                    className="input text-sm text-right"
                    type="number"
                    step="0.01"
                    placeholder="0"
                    value={line.debit}
                    onChange={(e) => updateLine(i, 'debit', e.target.value)}
                  />
                </td>
                <td>
                  <input
                    className="input text-sm text-right"
                    type="number"
                    step="0.01"
                    placeholder="0"
                    value={line.credit}
                    onChange={(e) => updateLine(i, 'credit', e.target.value)}
                  />
                </td>
                <td>
                  {lines.length > 2 && (
                    <button type="button" className="btn-ghost p-1" onClick={() => removeLine(i)} aria-label="Remove line">
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <Button type="button" variant="secondary" size="sm" onClick={addLine}>
          <Plus className="h-4 w-4" />
          Add Line
        </Button>
        <div className="text-right space-y-1">
          <div className="flex gap-6 text-sm">
            <span className="text-gray-600">Total Debit: <span className="font-semibold text-red-600">{formatCurrency(totalDebit)}</span></span>
            <span className="text-gray-600">Total Credit: <span className="font-semibold text-emerald-600">{formatCurrency(totalCredit)}</span></span>
          </div>
          <p className={`text-xs font-medium ${isBalanced ? 'text-emerald-600' : 'text-red-600'}`}>
            {isBalanced ? 'Balanced' : `Difference: ${formatCurrency(Math.abs(totalDebit - totalCredit))}`}
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={mutation.isPending} disabled={!isBalanced}>
          Save Entry
        </Button>
      </div>
    </form>
  );
}