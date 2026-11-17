import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/books_entry_draft.dart';
import 'package:apex_books/features/books/books_entry_posting.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  _newEntryTests();

  test('payment amendment verifies original allocations and adds only this payment’s exact share back', () async {
    final payment = _record(
      'payment',
      'payment_in',
      amount: '45.25',
      data: {'version': 9},
      extra: {
        'allocations': [
          {'document_id': 'original', 'amount': '20.10'},
          {'document_id': 'original', 'amount': '25.15'},
        ],
      },
    );
    final old = _record(
      'original',
      'sales_invoice',
      extra: {'outstanding': '0.00'},
    );
    final other = _record(
      'another',
      'opening_receivable',
      extra: {'outstanding': '10.50'},
    );
    final foreign = _record(
      'wrong-party',
      'sales_invoice',
      name: 'Another party',
      extra: {'outstanding': '500.00'},
    );
    final draft = _amend(payment);
    expect(draft.needsAmendmentData, isTrue);
    expect(draft.command, throwsStateError);
    final requested = <String>[];
    await draft.loadPaymentAmendment((id) async {
      requested.add(id);
      return old;
    });
    expect(requested, ['original']);
    expect(draft.allocations.single.amount, '45.25');
    expect(draft.allocationCapacity(old), BigInt.from(4525));
    expect(draft.allocationCapacity(other), BigInt.from(1050));
    draft.allocations.clear();
    draft.addAllocation(foreign);
    expect(draft.allocations, isEmpty);
    draft.addAllocation(other);
    draft.addAllocation(old);
    expect(draft.allocations.map((row) => row.amount), ['10.50', '34.75']);
    expect(draft.get('name'), 'Corner Shop');
    expect(draft.issue(), isNull);
    var body = draft.command().body;
    expect(body['amount'], '45.25');
    expect(body['data']['version'], 9);
    expect(body['data']['allocations'], [
      {'document_id': 'another', 'amount': '10.50'},
      {'document_id': 'original', 'amount': '34.75'},
    ]);
    draft.allocations.last.amount = '45.26';
    expect(draft.issue(), 'An allocation exceeds its document balance.');
    draft.allocations.last.amount = '40.00';
    draft.set('date', '2026-05-31');
    expect(draft.issue(), 'Payment date cannot be before a linked document.');
    draft.set('date', '2026-06-01');
    draft.set('payment_account', 'bank');
    expect(draft.issue(), 'Choose the bank account.');
    draft.set('bank_account_id', 'default');
    expect(draft.issue(), isNull);
    body = draft.command().body;
    expect(body['amount'], '50.50');
    expect(body['data']['payment_account'], 'bank');
  });

  test('legacy bank clears to the saved default and advance classification stays intact', () async {
    final advance = _record(
      'advance',
      'payment_in',
      amount: '20.00',
      data: {'is_advance': true, 'payment_account': 'bank'},
      extra: {'allocations': []},
    );
    final draft = _amend(advance);
    await draft.loadPaymentAmendment(
      (id) => throw StateError('advance has no allocations'),
    );
    expect(draft.get('bank_account_id'), 'default');
    expect(draft.issue(), 'Choose what this advance is for.');
    draft.set('advance_supply', 'services');
    expect(draft.issue(), 'Enter the advance GST rate from 0 to 100 percent.');
    draft.set('advance_gst_rate', '12.50');
    expect(draft.issue(), isNull);
    final body = draft.command().body;
    expect(body['amount'], '20.00');
    expect(body['data']['advance_supply'], 'services');
    expect(body['data']['is_advance'], isTrue);
    expect(body['data'].containsKey('allocations'), isFalse);
  });

  test('unverifiable historical payment does not turn into an empty editable payment', () async {
    final payment = _record(
      'payment',
      'payment_out',
      amount: '50.00',
      extra: {
        'allocations': [
          {'document_id': 'bill', 'amount': '49.00'},
        ],
      },
    );
    final draft = _amend(payment);
    await expectLater(
      draft.loadPaymentAmendment((id) => throw StateError('should not fetch')),
      throwsFormatException,
    );
    expect(draft.needsAmendmentData, isTrue);
    expect(draft.command, throwsStateError);
  });

  test('supplier return restores only original quantity to the exact duplicate-item source line', () async {
    final original = {
      'description': 'Cable',
      'item_id': 'item-1',
      'quantity': '0.325',
      'rate': '40.00',
      'gst_rate': '18',
      'tax_treatment': 'taxable',
      'itc_treatment': 'pending_review',
      'source_line_id': '0:source',
      'source_document_id': 'bill-1',
    };
    final note = _record(
      'debit',
      'debit_note',
      data: {
        'applied_to': 'bill-1',
        'version': 4,
        'lines': [original],
      },
    );
    final bill = _record(
      'bill-1',
      'purchase_bill',
      extra: {
        'return_capacity_lines': [
          {
            ...original,
            'quantity': '0.975',
            'remaining_return_quantity': '0.10',
          },
          {
            ...original,
            'source_line_id': '1:source',
            'quantity': '2.00',
            'remaining_return_quantity': '2.00',
          },
        ],
      },
    );
    final draft = _amend(note);
    await draft.loadNoteAmendment((id) async {
      expect(id, 'bill-1');
      return bill;
    });
    expect(draft.sourceLines[0]['remaining_return_quantity'], '0.425');
    expect(draft.sourceLines[1]['remaining_return_quantity'], '2.00');
    draft.lines.single.set('quantity', '0.426');
    expect(
      draft.issue(),
      'A return quantity exceeds the available source quantity.',
    );
    draft.lines.single.set('quantity', '0.425');
    expect(draft.issue(), isNull);
    final command = draft.command();
    expect(command.body['data']['applied_to'], 'bill-1');
    expect(command.body['data']['lines'][0]['source_line_id'], '0:source');
    expect(command.body['data']['version'], 4);
    expect(draft.previewBody(command)['data']['editing_record_id'], 'debit');
  });

  test('unknown historical sales return identity and POS returns remain details-only', () async {
    final line = {'description': 'Cable', 'quantity': '1', 'rate': '20.00'};
    final note = _record(
      'credit',
      'credit_note',
      data: {
        'applied_to': 'invoice',
        'lines': [line],
      },
    );
    final invoice = _record(
      'invoice',
      'sales_invoice',
      extra: {
        'return_capacity_lines': [
          {...line, 'remaining_return_quantity': '0.00'},
          {...line, 'remaining_return_quantity': '0.00'},
        ],
      },
    );
    final draft = _amend(note);
    await expectLater(
      draft.loadNoteAmendment((id) async => invoice),
      throwsFormatException,
    );
    expect(draft.needsAmendmentData, isTrue);
    final pos = _record('invoice', 'pos', extra: invoice.json);
    await expectLater(
      draft.loadNoteAmendment(
        (id) async => BooksRecord({...pos.json, 'kind': 'pos'}),
      ),
      throwsFormatException,
    );
  });
  test(
    'amended sales return can add only uniquely identifiable source lines',
    () async {
      final unit = {
        'description': 'Unique cable',
        'quantity': '0.125',
        'rate': '25.00',
      };
      final soldDuplicate = {
        'description': 'Duplicate cable',
        'item_id': 'dup-item',
        'quantity': '2',
        'rate': '25.00',
        'remaining_return_quantity': '2',
      };
      final note = _record(
        'credit',
        'credit_note',
        data: {
          'applied_to': 'invoice',
          'lines': [unit],
        },
      );
      final source = _record(
        'invoice',
        'sales_invoice',
        extra: {
          'return_capacity_lines': [
            {
              ...unit,
              'quantity': '0.325',
              'remaining_return_quantity': '0.100',
            },
            soldDuplicate,
            {...soldDuplicate, 'rate': '50.00'},
          ],
        },
      );
      final draft = _amend(note);
      await draft.loadNoteAmendment((id) async => source);
      expect(draft.sourceLines.first['remaining_return_quantity'], '0.225');
      expect(
        draft.sourceLines
            .skip(1)
            .every((line) => line['remaining_return_quantity'] == null),
        isTrue,
      );
      draft.addSourceLine(draft.sourceLines.last);
      expect(draft.lines, hasLength(1));
    },
  );
}

void _newEntryTests() {
  const company = ApexCompany(
    id: 'shop',
    name: 'Corner Shop',
    role: 'owner',
    stateCode: '27',
    taxMode: 'regular',
  );

  test('a new return cannot exceed the remaining source quantity', () {
    final line = {
      'description': 'Cable',
      'quantity': '3',
      'rate': '20.00',
      'gst_rate': '18',
      'source_line_id': '0:invoice',
      'source_document_id': 'invoice',
    };
    final invoice = _record(
      'invoice',
      'sales_invoice',
      data: {
        'lines': [line],
      },
      extra: {
        'return_capacity_lines': [
          {...line, 'remaining_return_quantity': '2'},
        ],
      },
    );
    final draft = BooksEntryDraft(
      BooksEntryIntent('credit_note', source: invoice),
      company,
    );
    // The remaining quantity is filled in, as on the web.
    expect(draft.lines.single.get('quantity'), '2');
    draft.lines.single.set('quantity', '3');
    expect(
      draft.issue(),
      'A return quantity exceeds the available source quantity.',
    );
    draft.lines.single.set('quantity', '2');
    expect(
      draft.issue(),
      isNot('A return quantity exceeds the available source quantity.'),
    );
  });

  test('editing a one-time party document does not send party fields it never had', () {
    final bill = _record(
      'bill',
      'purchase_bill',
      data: {
        'version': 3,
        'notes': 'Old note',
        'lines': [
          {'description': 'Tape', 'quantity': '1', 'rate': '10', 'gst_rate': '0'},
        ],
      },
    );
    final draft = _amend(bill);
    draft.set('notes', 'New note');
    final data = draft.command().body['data'] as Json;
    expect(data['notes'], 'New note');
    for (final key in ['party_id', 'party_gstin', 'party_phone', 'due_date']) {
      expect(data.containsKey(key), isFalse, reason: key);
    }
    draft.set('notes', '');
    expect((draft.command().body['data'] as Json)['notes'], '');
  });

  test('new item lines start at 18% GST only for regular GST companies', () {
    final regular = BooksEntryDraft(
      const BooksEntryIntent('purchase_bill'),
      company,
    );
    expect(regular.lines.single.get('gst_rate'), '18');
    expect(regular.blankLine().get('gst_rate'), '18');
    final unregistered = BooksEntryDraft(
      const BooksEntryIntent('purchase_bill'),
      const ApexCompany(
        id: 'shop',
        name: 'Corner Shop',
        role: 'owner',
        stateCode: '27',
        taxMode: 'unregistered',
      ),
    );
    expect(unregistered.lines.single.get('gst_rate'), '0');
  });
}

BooksEntryDraft _amend(BooksRecord record) => BooksEntryDraft(
  BooksEntryIntent(
    record.kind,
    source: record,
    operation: BooksOperation.amend,
  ),
  const ApexCompany(
    id: 'shop',
    name: 'Corner Shop',
    role: 'owner',
    stateCode: '27',
    taxMode: 'regular',
  ),
);

BooksRecord _record(
  String id,
  String kind, {
  String name = 'Corner Shop',
  String amount = '100.00',
  Json data = const {},
  Json extra = const {},
}) => BooksRecord({
  'id': id,
  'kind': kind,
  'number': 'QA-$id',
  'name': name,
  'amount': amount,
  'date': '2026-06-01',
  'posted': true,
  'data': data,
  ...extra,
});
