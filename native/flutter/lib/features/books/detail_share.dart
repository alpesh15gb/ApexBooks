import 'books_data.dart';
import 'books_entry_draft.dart' show booksPositive;

/// WhatsApp share and reminder messages, worded like the web app's whatsappShare.js.
/// Text only: nothing is sent until the person presses send in WhatsApp.
const _titles = {
  'sales_invoice': 'Invoice',
  'pos': 'Bill',
  'estimate': 'Estimate',
  'proforma': 'Proforma invoice',
  'sales_order': 'Sales order',
  'credit_note': 'Credit note',
  'payment_in': 'Payment receipt',
  'purchase_order': 'Purchase order',
  'purchase_bill': 'Bill',
  'payment_out': 'Payment',
  'debit_note': 'Debit note',
};

const detailShareable = {
  'sales_invoice',
  'pos',
  'estimate',
  'proforma',
  'sales_order',
  'credit_note',
  'payment_in',
  'purchase_order',
};

bool detailCanShare(BooksRecord record) =>
    detailShareable.contains(record.kind) && record.json['cancelled'] != true;

bool detailCanRemind(BooksRecord record) =>
    const {'sales_invoice', 'pos'}.contains(record.kind) &&
    record.json['posted'] == true &&
    record.json['cancelled'] != true &&
    booksPositive(record.json['outstanding']);

String _rupees(Object? value) => booksMoney(value);

String detailDocumentMessage(BooksRecord record, String company, String upi) {
  final title = _titles[record.kind] ?? 'Document';
  final name = record.party.isEmpty ? 'Customer' : record.party;
  final lines = [
    'Dear $name,',
    '$title ${record.number} dated ${record.date} for ${_rupees(record.json['amount'])} from $company.'
        .replaceAll('  ', ' '),
  ];
  if (const {'sales_invoice', 'pos'}.contains(record.kind) &&
      record.json['posted'] == true) {
    final due = booksPositive(record.json['outstanding']);
    final dueDate = booksText(record.data['due_date']);
    lines.add(
      due
          ? 'Balance due: ${_rupees(record.json['outstanding'])}${dueDate.isNotEmpty ? ' by $dueDate' : ''}.'
          : 'Fully paid. Thank you!',
    );
    if (due && upi.isNotEmpty) lines.add('Pay by UPI: $upi');
  }
  lines.add('Thank you for your business.');
  return lines.join('\n');
}

String detailReminderMessage(
  BooksRecord record,
  String company,
  String upi,
  String today,
) {
  final dueDate = booksText(record.data['due_date']);
  final overdue = dueDate.isNotEmpty && dueDate.compareTo(today) < 0;
  final name = record.party.isEmpty ? 'Customer' : record.party;
  final lines = [
    'Dear $name,',
    'This is a gentle reminder that ${_rupees(record.json['outstanding'])} is ${overdue ? 'overdue since $dueDate' : 'pending'} against ${_titles[record.kind] ?? 'invoice'} ${record.number} dated ${record.date}.',
    if (upi.isNotEmpty) 'You can pay by UPI: $upi',
    'Please ignore if already paid.\n– $company',
  ];
  return lines.join('\n');
}
