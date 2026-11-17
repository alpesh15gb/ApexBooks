import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/books_edit_details.dart';
import 'package:apex_books/features/books/books_entry_draft.dart';
import 'package:apex_books/features/books/books_entry_posting.dart';
import 'package:apex_books/features/books/books_register.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  testWidgets(
    'Books financially amends a posted receipt using verified allocations',
    (tester) async {
      final receipt = BooksRecord({
        ..._record('receipt', 'payment_in', {'version': 4}).json,
        'number': 'PIN-19',
        'allocations': [
          {'document_id': 'first-invoice', 'amount': '125.50'},
        ],
      });
      final first = BooksRecord({
        ..._record(
          'first-invoice',
          'sales_invoice',
          {},
          outstanding: '0.00',
        ).json,
        'number': 'INV-FIRST',
      });
      final second = BooksRecord({
        ..._record(
          'second-invoice',
          'sales_invoice',
          {},
          outstanding: '100.00',
        ).json,
        'number': 'INV-SECOND',
      });
      final exactFirst = Completer<Json>();
      final storage = _MemoryPending();
      final loaded = <String>[];
      var wrote = false;
      final api = _Api(
        read: (path, query) {
          final id = path.split('/').last;
          if (id == 'records') {
            return query?['kind'] == 'sales_invoice'
                ? [first.json, second.json]
                : [receipt.json];
          }
          if (id == 'receipt') return receipt.json;
          loaded.add(id);
          return id == first.id ? exactFirst.future : second.json;
        },
        write: (method, path, body, key) async {
          expect(method, 'PUT');
          expect(path, '/api/companies/shop/documents/receipt');
          expect(body['name'], 'Corner Shop');
          expect(body['amount'], '125.50');
          expect(body['data']['version'], 4);
          expect(body['data']['allocations'], [
            {'document_id': 'first-invoice', 'amount': '75.50'},
            {'document_id': 'second-invoice', 'amount': '50.00'},
          ]);
          expect(storage.saved?['key'], key);
          wrote = true;
          return receipt.json;
        },
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: BooksRegister(workspace: _workspace(api, storage)),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('PIN-19'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Amend entry'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Amend entry'));
      await tester.pump();
      expect(
        find.text('Checking the original document links…'),
        findsOneWidget,
      );
      expect(find.text('Allocated amount (₹)'), findsNothing);
      exactFirst.complete(first.json);
      await tester.pumpAndSettle();
      await _field(tester, 'Allocated amount (₹)', '75.50');
      await tester.scrollUntilVisible(
        find.text('Choose invoice or bill'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Choose invoice or bill'));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('INV-SECOND'));
      await tester.pumpAndSettle();
      expect(loaded, [first.id, second.id]);
      await tester.tap(find.text('Review entry'));
      await tester.pumpAndSettle();
      expect(find.textContaining('INV-SECOND'), findsOneWidget);
      await tester.tap(find.text('Save amendment'));
      await tester.pumpAndSettle();
      expect(wrote, isTrue);
      expect(storage.saved, isNull);
      expect(find.text('PIN-19 saved.'), findsOneWidget);
    },
  );

  testWidgets('editing a draft from the register list loads its item lines', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final line = {
      'description': 'Installation Service',
      'quantity': 2,
      'rate': '500',
      'gst_rate': 0,
    };
    final compact = BooksRecord({
      ..._record('quote', 'estimate', {'lines': <Json>[]}).json,
      'number': 'EST-7',
      'posted': false,
    });
    final full = BooksRecord({
      ...compact.json,
      'data': {
        'lines': [line],
      },
    });
    final loaded = <String>[];
    final api = _Api(
      read: (path, query) {
        final id = path.split('/').last;
        if (id == 'records') {
          expect(query?['compact'], 'true');
          return [compact.json];
        }
        loaded.add(id);
        return full.json;
      },
      write: (method, path, body, key) async => throw UnimplementedError(),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BooksRegister(
            workspace: _workspace(api, _MemoryPending()),
            kind: 'estimate',
            title: 'Estimates',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('More actions for EST-7'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit draft'));
    await tester.pumpAndSettle();
    expect(loaded, ['quote']);
    expect(find.text('Installation Service'), findsOneWidget);
    expect(find.text('500'), findsOneWidget);
  });

  testWidgets('a receipt shows its allocation clear of the amount field and totals the footer', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final invoice = BooksRecord({
      ..._record('inv', 'sales_invoice', {
        'lines': <Json>[],
      }, outstanding: '125.50').json,
      'number': 'INV-9',
    });
    final api = _Api(
      read: (path, query) {
        final id = path.split('/').last;
        if (id == 'records') return [invoice.json];
        return invoice.json;
      },
      write: (method, path, body, key) async => throw UnimplementedError(),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BooksRegister(
            workspace: _workspace(api, _MemoryPending()),
            kind: 'sales_invoice',
            title: 'Sales invoices',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Collect payment').first);
    await tester.pumpAndSettle();
    final title = find.text('INV-9 · Corner Shop');
    expect(title, findsOneWidget);
    final field = _findField('Allocated amount (₹)');
    expect(
      tester.getRect(title).bottom,
      lessThanOrEqualTo(tester.getRect(field).top),
    );
    expect(
      tester.widget<Text>(
        find.byKey(const ValueKey('books-entry-footer-total')),
      ).data,
      '₹125.50',
    );
  });

  test('detail amendments preserve posted identity and omit financial inputs for receipts, payouts and notes', () {
    for (final kind in [
      'payment_in',
      'payment_out',
      'credit_note',
      'debit_note',
    ]) {
      final original = _record('posted-entry', kind, {
        'version': 7,
        'notes': 'Original note',
        'applied_to': 'linked-1',
        'lines': [
          {'quantity': '2', 'gst_rate': '18'},
        ],
      });
      final command = booksDetailAmendment(
        original,
        'REF-001',
        'Reviewed with supplier',
      );
      expect(command.operation, BooksOperation.amend);
      expect(command.pathSuffix, '/documents/posted-entry');
      expect(command.body, {
        'kind': kind,
        'name': original.party,
        'date': original.date,
        'amount': '125.50',
        'number': 'REF-001',
        'data': {'version': 7, 'notes': 'Reviewed with supplier'},
      });
    }
  });

  testWidgets(
    'posted receipt details save through PUT and return to the record',
    (tester) async {
      final original = _record('receipt', 'payment_in', {
        'version': 4,
        'notes': 'Original note',
      });
      final saved = BooksRecord({
        ...original.json,
        'data': {'version': 5, 'notes': 'QA receipt memo'},
      });
      final storage = _MemoryPending();
      var changed = false;
      final api = _Api(
        read: (path, query) => path.endsWith('/records/receipt')
            ? (changed ? saved.json : original.json)
            : [original.json],
        write: (method, path, body, key) async {
          expect(method, 'PUT');
          expect(path, '/api/companies/shop/documents/receipt');
          expect(body, {
            'kind': 'payment_in',
            'name': original.party,
            'date': original.date,
            'amount': '125.50',
            'number': original.number,
            'data': {'version': 4, 'notes': 'QA receipt memo'},
          });
          expect(storage.saved?['key'], key);
          changed = true;
          return saved.json;
        },
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: BooksRegister(workspace: _workspace(api, storage)),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text(original.number));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Edit details'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Edit details'));
      await tester.pumpAndSettle();
      await _field(tester, 'Notes', 'QA receipt memo');
      await tester.tap(find.text('Save details'));
      await tester.pumpAndSettle();
      expect(changed, isTrue);
      expect(storage.saved, isNull);
      expect(find.text('${original.number} saved.'), findsOneWidget);
    },
  );

  test('with-payment keeps both legs in one durable payload and verifies the linked payment', () async {
    final draft = BooksEntryDraft(
      const BooksEntryIntent('purchase_bill'),
      _company(),
    );
    draft.setPartyName('Corner Shop');
    draft.lines.single
      ..set('description', 'Supplies')
      ..set('rate', '60.00');
    draft.payAtEntry = true;
    draft.set('pay_amount', '25.50');
    draft.set('payment_account', 'bank');
    draft.set('bank_account_id', 'bank-id');
    expect(draft.issue(), isNull);
    final command = draft.command();
    expect(command.operation, BooksOperation.withPayment);
    expect(draft.previewBody(command)['kind'], 'purchase_bill');
    expect(
      draft.previewBody(command)['data'].containsKey('payment_account'),
      isFalse,
    );
    expect(command.body['payment'], {
      'payment_account': 'bank',
      'bank_account_id': 'bank-id',
      'amount': '25.50',
    });
    final storage = _MemoryPending();
    String? originalKey;
    final api = _Api(
      write: (method, path, body, key) async {
        expect(path, '/api/companies/shop/records/with-payment');
        expect(storage.saved?['body'], command.body);
        expect(body, command.body);
        if (originalKey == null) {
          originalKey = key;
          throw const ApexApiException(status: 504, message: 'Connection lost');
        }
        expect(key, originalKey);
        return {
          'document': _record('bill', 'purchase_bill', {}).json,
          'payment': _record('payment', 'payment_out', {
            'applied_to': 'bill',
          }).json,
        };
      },
    );
    final workspace = _workspace(api, storage);
    final first = BooksPosting(workspace);
    await first.recover();
    expect(await first.submit(command), isNull);
    first.dispose();
    final resumed = BooksPosting(workspace);
    await resumed.recover();
    expect((await resumed.retry())?.id, 'bill');
    expect(storage.saved, isNull);
    resumed.dispose();
  });

  test('invoice and draft retain exact item and version inputs', () {
    final invoice = BooksEntryDraft(
      const BooksEntryIntent('sales_invoice'),
      _company(),
    );
    invoice.setPartyName('Corner retail');
    invoice.lines.single.chooseItem(
      _record('tracked', 'item', {
        'sale_rate': '199.99',
        'gst_rate': '18',
        'hsn': '8544',
        'unit': 'pcs',
      }),
      purchase: false,
      regular: true,
    );
    invoice.lines.single.set('quantity', '1.125');
    expect(invoice.issue(), isNull);
    expect(invoice.command().body, containsPair('amount', '0'));
    final data = booksObject(invoice.command().body['data']);
    expect(data['lines'][0], containsPair('item_id', 'tracked'));
    expect(data['lines'][0], containsPair('quantity', '1.125'));
    expect(data['lines'][0], containsPair('rate', '199.99'));

    final source = _record('estimate-a', 'estimate', {
      'version': 4,
      'lines': data['lines'],
    });
    final amend = BooksEntryDraft(
      BooksEntryIntent(
        'estimate',
        source: source,
        operation: BooksOperation.draft,
      ),
      _company(),
    );
    expect(amend.command().pathSuffix, '/drafts/estimate-a');
    expect(amend.command().usesPut, isTrue);
    expect(amend.command().body['data']['version'], 4);
    final convert = BooksEntryDraft(
      BooksEntryIntent('sales_invoice', source: source, convert: true),
      _company(),
    );
    expect(convert.command().body['number'], isEmpty);
    expect(convert.command().body['data']['source_document_id'], 'estimate-a');
    expect(convert.command().body['data'].containsKey('version'), isFalse);
  });

  test(
    'allocation totals use exact paise and remain limited to the same party',
    () {
      final first = _record(
        'bill-a',
        'purchase_bill',
        {},
        outstanding: '19.99',
      );
      final second = _record(
        'bill-b',
        'purchase_bill',
        {},
        outstanding: '10.01',
      );
      final other = _record(
        'bill-c',
        'purchase_bill',
        {},
        party: 'Other shop',
        outstanding: '0.01',
      );
      final draft = BooksEntryDraft(
        BooksEntryIntent('payment_out', source: first),
        _company(),
      );
      draft.addAllocation(second);
      draft.addAllocation(other);
      draft.addAllocation(first);
      expect(draft.amount, '30.00');
      expect(draft.command().body['data']['allocations'], [
        {'document_id': 'bill-a', 'amount': '19.99'},
        {'document_id': 'bill-b', 'amount': '10.01'},
      ]);
      draft.switchAdvance(true);
      draft.setPartyName('Corner Shop');
      draft.set('amount', '2.01');
      expect(draft.issue(), isNull);
      expect(draft.command().body['data'], containsPair('is_advance', true));
      expect(draft.command().body['data'].containsKey('allocations'), isFalse);
    },
  );

  test(
    'supplier debit note preserves exact source identity and GST treatment',
    () {
      final source = _record('bill-1', 'purchase_bill', {
        'place_of_supply': '27',
        'supplier_state': '29',
        'lines': [
          {
            'description': 'Trackpad',
            'source_line_id': '0:verified',
            'source_document_id': 'bill-1',
            'quantity': '4',
            'remaining_return_quantity': '0.500',
            'rate': '40.00',
            'discount_amount': '15.00',
            'gst_rate': '18',
            'itc_treatment': 'ineligible',
          },
        ],
      });
      final draft = BooksEntryDraft(
        BooksEntryIntent('debit_note', source: source),
        _company(),
      );
      draft.addSourceLine(draft.sourceLines.single);
      draft.returnStock = false;
      expect(draft.issue(), isNull);
      final request = booksObject(draft.command().body['data']);
      expect(request['applied_to'], 'bill-1');
      expect(request['return_stock'], isFalse);
      expect(request['supplier_state'], '29');
      expect(
        request['lines'][0],
        allOf(
          containsPair('source_line_id', '0:verified'),
          containsPair('quantity', '0.500'),
          containsPair('discount_amount', '0'),
          containsPair('itc_treatment', 'ineligible'),
        ),
      );
    },
  );

  test('uncertain posting is persisted first and retries the exact command across restart', () async {
    final storage = _MemoryPending();
    final requests = <(String, String)>[];
    final api = _Api(
      write: (method, path, body, key) async {
        expect(path, '/api/companies/shop/records');
        expect(storage.saved?['body'], body);
        expect(storage.saved?['key'], key);
        requests.add((key!, jsonEncode(body)));
        if (requests.length == 1) {
          throw const ApexApiException(status: 504, message: 'Timed out');
        }
        return _record('result', 'payment_in', {}).json;
      },
    );
    final session = _workspace(api, storage);
    final before = BooksPosting(session);
    await before.recover();
    final body = <String, dynamic>{
      'kind': 'payment_in',
      'name': 'Corner Shop',
      'amount': '22.00',
      'data': {'is_advance': true},
    };
    expect(
      await before.submit(BooksCommand(BooksOperation.create, '', body)),
      isNull,
    );
    expect(before.pending, isNotNull);
    before.dispose();
    body['amount'] = '70.00';
    final recovered = BooksPosting(session);
    await recovered.recover();
    expect(recovered.canStart, isFalse);
    expect((await recovered.retry())?.id, 'result');
    expect(requests[0], requests[1]);
    expect(storage.saved, isNull);
    recovered.dispose();
  });

  test('write-rejected command clears only on a definitive first attempt and verifies the response', () async {
    final storage = _MemoryPending();
    var calls = 0;
    final api = _Api(
      write: (method, path, body, key) async {
        calls++;
        expect(method, 'PUT');
        expect(path, '/api/companies/shop/documents/old');
        if (calls == 1) {
          throw const ApexApiException(
            status: 409,
            message: 'Reload this record',
          );
        }
        return _record('wrong-id', 'sales_invoice', {}).json;
      },
    );
    final posting = BooksPosting(_workspace(api, storage));
    await posting.recover();
    final amendment = BooksCommand(BooksOperation.amend, 'old', {
      'kind': 'sales_invoice',
      'data': {'version': 2},
    });
    expect(await posting.submit(amendment), isNull);
    expect(storage.saved, isNull);
    expect(posting.message, 'Reload this record');
    expect(await posting.submit(amendment), isNull);
    expect(storage.saved, isNotNull);
    posting.dispose();
  });

  testWidgets(
    'owner reviews the server quote, then posts the exact reviewed invoice through Books at 320dp',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 740);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final storage = _MemoryPending();
      Json? reviewed;
      var posts = 0;
      final completion = Completer<Json>();
      final invoice = _record('saved-id', 'sales_invoice', {
        'lines': [
          {'description': 'Counter cable'},
        ],
      });
      final api = _Api(
        read: (path, query) =>
            path.endsWith('/records/saved-id') ? invoice.json : <Json>[],
        write: (method, path, body, key) async {
          if (path.endsWith('/preview')) {
            expect(key, isNull);
            expect(storage.saved, isNull);
            reviewed = body;
            return {
              'amount': '125.50',
              'data': {'taxable': '125.50'},
            };
          }
          posts++;
          expect(path, '/api/companies/shop/records');
          expect(body, reviewed);
          expect(storage.saved?['key'], key);
          return completion.future;
        },
      );
      final workspace = _workspace(api, storage);
      Widget render(int revision) => MaterialApp(
        home: Scaffold(
          body: BooksRegister(workspace: workspace, revision: revision),
        ),
      );
      await tester.pumpWidget(render(0));
      await tester.pumpAndSettle();
      await tester.tap(find.text('New entry'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sales invoice'));
      await tester.pumpAndSettle();
      await _field(tester, 'Customer / description', 'Corner Shop');
      await _field(tester, 'Item / service 1', 'Counter cable');
      await _field(tester, 'Rate ₹', '125.50');
      await tester.tap(find.text('Review entry'));
      await tester.pumpAndSettle();
      expect(find.text('Calculated by Apex Books'), findsOneWidget);
      expect(find.text('₹125.50'), findsWidgets);
      expect(
        find.byKey(const ValueKey('books-entry-footer-total')),
        findsOneWidget,
      );
      expect(find.text('Total  ₹125.50').hitTestable(), findsOneWidget);
      expect(posts, 0);
      await tester.tap(find.text('Post entry'));
      await tester.pump();
      expect(storage.saved, isNotNull);
      await tester.pumpWidget(render(1));
      await tester.pump();
      expect(posts, 1);
      expect(find.text('Review before saving'), findsOneWidget);
      expect(find.textContaining('awaiting confirmation'), findsNothing);
      completion.complete(invoice.json);
      await tester.pumpAndSettle();
      expect(posts, 1);
      expect(find.text('INV/2026/10 saved.'), findsOneWidget);
      expect(storage.saved, isNull);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'desktop invoice keeps line controls, quoted total and posting action aligned',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1200, 820);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final line = {
        'description': 'Counter installation',
        'unit': 'units',
        'quantity': '2',
        'rate': '60',
        'taxable': '120',
        'tax': '21.60',
      };
      final invoice = _record(
        'desktop-invoice',
        'sales_invoice',
        {
          'lines': [line],
          'due_date': '2026-06-05',
        },
        amount: '141.60',
        outstanding: '141.60',
      );
      final api = _Api(
        read: (path, query) =>
            path.endsWith('/records/desktop-invoice') ? invoice.json : <Json>[],
        write: (_, path, body, key) async {
          if (path.endsWith('/preview')) {
            return {
              'amount': '141.60',
              'data': {
                'taxable': '120',
                'lines': [line],
              },
            };
          }
          expect(key, isNotEmpty);
          return invoice.json;
        },
      );
      final recovery = Completer<Json?>();
      final storage = _MemoryPending(recovery: recovery.future);
      final workspace = _workspace(api, storage);
      Widget render(int request) => MaterialApp(
        home: Scaffold(
          body: BooksRegister(workspace: workspace, entryRequest: request),
        ),
      );

      await tester.pumpWidget(render(1));
      expect(find.byType(SimpleDialog), findsNothing);
      recovery.complete(null);
      await tester.pumpAndSettle();
      expect(find.byType(SimpleDialog), findsOneWidget);
      await tester.tap(find.text('Sales invoice'));
      await tester.pumpAndSettle();

      final description = _findKey('line-0-description');
      final quantity = _findKey('line-0-quantity');
      final rate = _findKey('line-0-rate');
      final discount = _findKey('line-0-discount_percent');
      expect(tester.getTopLeft(description).dy, tester.getTopLeft(quantity).dy);
      expect(tester.getTopLeft(rate).dy, tester.getTopLeft(discount).dy);
      expect(
        tester.getTopLeft(description).dx,
        lessThan(tester.getTopLeft(rate).dx),
      );
      expect(
        tester.getTopLeft(_findField('Customer / description')).dx,
        lessThan(tester.getTopLeft(_findField('Reference number')).dx),
      );
      await _field(tester, 'Customer / description', 'Corner Shop');
      await _fieldKey(tester, 'line-0-description', 'Counter installation');
      await _fieldKey(tester, 'line-0-quantity', '2');
      await _fieldKey(tester, 'line-0-rate', '60');

      await tester.pumpWidget(render(2));
      await tester.pumpAndSettle();
      expect(find.byType(SimpleDialog), findsNothing);
      expect(find.text('Counter installation'), findsOneWidget);

      await tester.tap(find.text('Review entry'));
      await tester.pumpAndSettle();
      final post = find.text('Post entry');
      final footerTotal = find.byKey(
        const ValueKey('books-entry-footer-total'),
      );
      expect(find.text('Total  ₹141.60').hitTestable(), findsOneWidget);
      expect(
        tester.getCenter(footerTotal).dx,
        lessThan(tester.getCenter(post).dx),
      );
      expect(
        (tester.getCenter(footerTotal).dy - tester.getCenter(post).dy).abs(),
        lessThan(8),
      );
      await tester.tap(post);
      await tester.pumpAndSettle();

      expect(find.text('Posted'), findsOneWidget);
      expect(find.text('Current outstanding'), findsOneWidget);
      expect(find.text('2026-06-05'), findsOneWidget);
      expect(find.text('Counter installation'), findsOneWidget);
      expect(find.text('2 units'), findsOneWidget);
      expect(find.text('INV/2026/10 saved.'), findsOneWidget);

      await tester.pumpWidget(render(3));
      await tester.pumpAndSettle();
      expect(find.byType(SimpleDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}

Finder _findField(String label) => find.byWidgetPredicate(
  (widget) => widget is TextField && widget.decoration?.labelText == label,
);

Future<void> _field(WidgetTester tester, String label, String value) async {
  final field = _findField(label);
  await tester.scrollUntilVisible(
    field,
    100,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.enterText(field, value);
  await tester.pumpAndSettle();
}

BooksRecord _record(
  String id,
  String kind,
  Json data, {
  String party = 'Corner Shop',
  String amount = '125.50',
  String? outstanding,
}) => BooksRecord({
  'id': id,
  'kind': kind,
  'number': 'INV/2026/10',
  'amount': amount,
  'name': party,
  'date': '2026-06-01',
  'posted': true,
  'outstanding': ?outstanding,
  'data': data,
});

ApexCompany _company() => const ApexCompany(
  id: 'shop',
  name: 'Corner Shop',
  role: 'owner',
  stateCode: '27',
  taxMode: 'regular',
);
WorkspaceContext _workspace(_Api api, _MemoryPending pending) =>
    WorkspaceContext(
      api: api,
      company: _company(),
      pending: pending,
      features: const {'document_cancellation'},
      refresh: () async {},
    );

class _MemoryPending implements PendingStore {
  _MemoryPending({this.recovery});

  final Future<Json?>? recovery;
  Json? saved;

  @override
  Future<void> clear(String operation) async => saved = null;
  @override
  Future<Json?> load(String operation) async =>
      recovery == null ? saved : await recovery;
  @override
  Future<void> save(String operation, Json data) async => saved = data;
}

class _Api implements ApexApi, ApexWriteApi {
  _Api({this.read, required this.write});
  final Object? Function(String, Json?)? read;
  final Future<Object?> Function(String, String, Json, String?) write;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async =>
      read?.call(path, query) ?? <Json>[];
  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => write('POST', path, body, idempotencyKey);
  @override
  Future<dynamic> put(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => write('PUT', path, body, idempotencyKey);
  @override
  Future<dynamic> patch(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => throw UnimplementedError();
  @override
  Future<dynamic> delete(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
}

Finder _findKey(String key) => find.byKey(ValueKey(key));

Future<void> _fieldKey(WidgetTester tester, String key, String value) async {
  final field = _findKey(key);
  await tester.scrollUntilVisible(
    field,
    100,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.enterText(field, value);
  await tester.pumpAndSettle();
}
