import test from 'node:test';
import assert from 'node:assert/strict';
import { canRemind, documentMessage, partyPhone, reminderMessage, whatsappPhone, whatsappUrl } from '../src/whatsappShare.js';

const invoice = { kind: 'sales_invoice', number: 'INV/1', name: 'Rahul', date: '2026-11-01', amount: '1180', outstanding: '180', posted: true, data: { due_date: '2026-11-03' } };

test('Indian mobile numbers get the 91 prefix and junk is dropped', () => {
  assert.equal(whatsappPhone('98765 43210'), '919876543210');
  assert.equal(whatsappPhone('+91-98765-43210'), '919876543210');
  assert.equal(whatsappPhone('09876543210'), '919876543210');
  assert.equal(whatsappPhone('12345'), '');
  assert.equal(whatsappUrl('', 'hi'), 'https://wa.me/?text=hi');
});

test('party phone comes from the saved party first', () => {
  const records = [{ kind: 'party', id: 'p1', name: 'Rahul ', data: { phone: '9000000001' } }];
  assert.equal(partyPhone(invoice, records), '9000000001');
  assert.equal(partyPhone({ ...invoice, data: { phone: '9000000002' } }, []), '9000000002');
});

test('invoice message states the balance and UPI ID only while money is due', () => {
  const text = documentMessage(invoice, 'Sharma Traders', 'sharma@upi');
  assert.match(text, /Invoice INV\/1 dated 2026-11-01 for ₹1,180\.00 from Sharma Traders/);
  assert.match(text, /Balance due: ₹180\.00 by 2026-11-03/);
  assert.match(text, /sharma@upi/);
  const paid = documentMessage({ ...invoice, outstanding: '0' }, 'Sharma Traders', 'sharma@upi');
  assert.match(paid, /Fully paid/);
  assert.doesNotMatch(paid, /sharma@upi/);
});

test('reminders only for posted, uncancelled invoices with a balance, and say when overdue', () => {
  assert.equal(canRemind(invoice), true);
  assert.equal(canRemind({ ...invoice, outstanding: '0' }), false);
  assert.equal(canRemind({ ...invoice, cancelled: true }), false);
  assert.equal(canRemind({ ...invoice, kind: 'purchase_bill' }), false);
  assert.match(reminderMessage(invoice, 'Sharma Traders', '', '2026-11-10'), /overdue since 2026-11-03/);
  assert.match(reminderMessage(invoice, 'Sharma Traders', '', '2026-11-02'), /is pending/);
});

test('overdue reminders group a customer’s overdue invoices, largest first', async () => {
  const { overdueByParty, partyReminderMessage } = await import('../src/whatsappShare.js');
  const rows = [
    { kind: 'party', id: 'p1', name: 'Rahul', data: { phone: '9000000001' } },
    invoice,
    { ...invoice, number: 'INV/2', outstanding: '500', data: { due_date: '2026-11-02' } },
    { ...invoice, number: 'INV/3', name: 'Mehta', outstanding: '900', data: { due_date: '2026-11-01' } },
    { ...invoice, number: 'INV/4', outstanding: '50', data: { due_date: '2026-12-30' } },
    { ...invoice, number: 'INV/5', outstanding: '0', data: { due_date: '2026-11-01' } },
  ];
  const groups = overdueByParty(rows, '2026-11-10');
  assert.deepEqual(groups.map(g => [g.name, g.total, g.invoices.length]), [['Mehta', 900, 1], ['Rahul', 680, 2]]);
  assert.equal(groups[1].phone, '9000000001');
  const text = partyReminderMessage(groups[1], 'Sharma Traders', 'sharma@upi');
  assert.match(text, /₹680\.00 is overdue/);
  assert.match(text, /INV\/1 dated 2026-11-01: ₹180\.00 \(due 2026-11-03\)/);
  assert.match(text, /INV\/2/);
  assert.match(text, /sharma@upi/);
});
