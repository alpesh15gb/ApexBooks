import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/banking/bank_data.dart';
import 'package:apex_books/features/banking/banking_screen.dart';
import 'package:apex_books/features/masters/masters_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

const _base = '/api/companies/shop';

class _StoredRequests implements PendingStore {
  final values = <String, Json>{};
  @override
  Future<Json?> load(String operation) async => values[operation];
  @override
  Future<void> save(String operation, Json data) async =>
      values[operation] = data;
  @override
  Future<void> clear(String operation) async => values.remove(operation);
}

class _ShopApi implements ApexApi, ApexWriteApi {
  final parties = <Json>[];
  final transferKeys = <String?>[];
  final transfers = <String, Json>{};
  final allocations = <Json>[];
  Json? masterCreate;
  Json? masterUpdate;
  Json? transfer;
  Json? opening;

  Json get statement => {
    'id': 'statement',
    'description': 'Deposit',
    'amount': '40.00',
    'date': '2026-04-02',
    'remaining_amount': decimalMoney(
      BigInt.from(4000) -
          allocations.fold<BigInt>(
            BigInt.zero,
            (total, row) => total + signedMoney(row['amount'] as String)!,
          ),
    ),
    'allocations': allocations,
  };

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '$_base/parties/party/ledger') {
      expect(query?['from_date'], isNotEmpty);
      expect(query?['to_date'], isNotEmpty);
      return {
        'opening': {'amount': '25.00', 'side': 'Dr'},
        'closing': {'amount': '120.00', 'side': 'Dr'},
        'rows': [
          {
            'id': 'invoice',
            'date': '2026-04-02',
            'particulars': 'To Sales',
            'voucher_type': 'Sales',
            'voucher_number': 'INV-1',
            'debit': '95.00',
            'balance': '120.00',
            'balance_side': 'Dr',
          },
        ],
      };
    }
    if (path == '$_base/records' && query?['kind'] == 'party') return parties;
    if (path == '$_base/records') {
      return [
        {
          'id': 'pos',
          'name': 'Retail checkout',
          'number': 'POS-1',
          'kind': 'pos',
          'date': '2026-04-02',
          'posted': true,
          'amount': '100.00',
          'data': {'payment_account': 'split', 'bank_amount': '40.00'},
        },
      ];
    }
    if (path == '$_base/bank-accounts') {
      return [
        {'id': 'default', 'name': 'Clearing'},
        {'id': 'bank', 'name': 'Settlement bank'},
      ];
    }
    if (path == '$_base/cash-book') {
      return {
        'opening': {'cash': '0', 'bank': '0'},
        'closing': {'cash': '0', 'bank': '40'},
        'rows': [],
      };
    }
    if (path == '$_base/bank-reconciliation') {
      return {
        'bank_account_id': query?['bank_account_id'],
        'as_of': query?['as_of'],
        'opening_balance': '0',
        'statement_closing_balance': '40',
        'ledger_closing_balance': '40',
        'difference': '0',
        'unmatched': allocations.isEmpty ? 1 : 0,
      };
    }
    if (path == '$_base/bank-reconciliation/reviews') return [];
    if (path == '$_base/bank-statement') return [statement];
    throw StateError('Unexpected GET $path');
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    if (path == '$_base/opening-balances') {
      expect(idempotencyKey, isNotEmpty);
      opening = body;
      return {'id': 'opening', 'posted': true};
    }
    if (path == '$_base/records' && body['kind'] == 'party') {
      masterCreate = body;
      final row = {'id': 'party', 'name': body['name'], 'data': body['data']};
      parties.add(row);
      return row;
    }
    if (path == '$_base/records' && body['kind'] == 'bank_transfer') {
      transfer = body;
      transferKeys.add(idempotencyKey);
      final prior = transfers[idempotencyKey];
      if (prior != null) return prior;
      final result = {'id': 'transfer', 'posted': true};
      transfers[idempotencyKey!] = result;
      throw const ApexApiException(message: 'Response lost');
    }
    if (path == '$_base/bank-statement/statement/allocations') {
      final row = {
        'id': 'match',
        'name': 'Retail checkout',
        'number': 'POS-1',
        ...body,
      };
      allocations.add(row);
      return row;
    }
    throw StateError('Unexpected POST $path');
  }

  @override
  Future<dynamic> put(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    expect(path, '$_base/masters/party');
    masterUpdate = body;
    parties[0] = {'id': 'party', 'name': body['name'], 'data': body};
    return parties[0];
  }

  @override
  Future<dynamic> patch(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async => throw UnimplementedError();

  @override
  Future<dynamic> delete(String path, {Map<String, String>? query}) async {
    expect(path, '$_base/bank-statement/allocations/match');
    allocations.clear();
    return {};
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async =>
      throw UnimplementedError();
}

WorkspaceContext _workspace(_ShopApi api, _StoredRequests store) =>
    WorkspaceContext(
      api: api,
      company: const ApexCompany(id: 'shop', name: 'Test shop', role: 'owner'),
      pending: store,
      features: const {'master_lifecycle'},
      refresh: () async {},
    );

Future<void> _tap(WidgetTester tester, Finder target) async {
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  test('Statement CSV preserves signed cents and quoted bank descriptions', () {
    final rows = statementEntries(
      'Date,Description,Amount,Reference\r\n2026-04-02,"Payment, received",12.10,0001\n2026-04-03,"A ""quoted"" charge",-0.20,2',
    );
    expect(rows[0], {
      'date': '2026-04-02',
      'description': 'Payment, received',
      'amount': '12.10',
      'reference': '0001',
    });
    expect(rows[1]['description'], 'A "quoted" charge');
    expect(rows[1]['amount'], '-0.20');
    expect(
      () => statementEntries('Date,Description,Amount\n2026-02-30,Invalid,9'),
      throwsFormatException,
    );
  });

  testWidgets('Creates a customer and archives the same master', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(900, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = _ShopApi();
    final store = _StoredRequests();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: MastersScreen(workspace: _workspace(api, store))),
      ),
    );
    await tester.pumpAndSettle();
    // Parties use the web app's single directory: one "Add party" form, type "Both" by default.
    await _tap(tester, find.text('Add party').first);
    await tester.enterText(
      find.widgetWithText(TextField, 'Party name'),
      'Test customer',
    );
    await tester.enterText(find.widgetWithText(TextField, 'Phone'), '071020');
    await _tap(tester, find.text('Save party'));
    expect(api.masterCreate?['data']['party_type'], 'both');
    expect(api.masterCreate?['data']['phone'], '071020');
    expect(store.values, isEmpty);
    // The party name opens its statement, as on the web.
    await _tap(tester, find.text('Test customer'));
    expect(find.text('Closing balance'), findsWidgets);
    expect(find.text('₹120.00 Dr'), findsWidgets);
    expect(find.text('To Sales'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await _tap(tester, find.text('Edit'));
    await _tap(tester, find.text('Active for new transactions'));
    await _tap(tester, find.text('Save party'));
    expect(api.masterUpdate?['name'], 'Test customer');
    expect(api.masterUpdate?['is_active'], false);
    // "All entries" keeps archived parties visible with their history badge.
    expect(find.text('Test customer'), findsOneWidget);
    expect(find.text('Archived · history retained'), findsOneWidget);
  });

  testWidgets('Recovers an interrupted transfer using the identical key', (
    tester,
  ) async {
    final api = _ShopApi();
    final store = _StoredRequests();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: BankingScreen(workspace: _workspace(api, store))),
      ),
    );
    await tester.pumpAndSettle();
    await _tap(tester, find.text('Record transfer'));
    await tester.enterText(
      find.widgetWithText(TextField, 'Amount (₹)'),
      '10.50',
    );
    await _tap(tester, find.text('Review transfer'));
    await _tap(tester, find.text('Post transfer'));
    expect(find.text('Response lost'), findsOneWidget);
    expect(api.transfer?['data']['direction'], 'cash_to_bank');
    expect(api.transfer?['amount'], '10.50');
    expect(store.values, isNotEmpty);
    await _tap(tester, find.text('Retry original'));
    expect(api.transferKeys[0], api.transferKeys[1]);
    expect(api.transfers, hasLength(1));
    expect(store.values, isEmpty);
    expect(find.text('Transfer posted.'), findsOneWidget);
  });

  testWidgets('Posts an owner cash opening separately from statement opening', (
    tester,
  ) async {
    final api = _ShopApi();
    final store = _StoredRequests();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: BankingScreen(workspace: _workspace(api, store))),
      ),
    );
    await tester.pumpAndSettle();
    await _tap(tester, find.text('Opening balance'));
    await tester.enterText(
      find.widgetWithText(TextField, 'Opening amount (₹)'),
      '145.25',
    );
    await _tap(tester, find.text('Review opening'));
    await _tap(tester, find.text('Post opening'));
    expect(api.opening?['amount'], '145.25');
    expect(api.opening?['data'], {'balance_kind': 'cash'});
    expect(store.values, isEmpty);
    expect(find.text('Opening balance posted.'), findsOneWidget);
  });

  testWidgets('Matches and removes only the bank share of a split sale', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(900, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = _ShopApi();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: BankingScreen(workspace: _workspace(api, _StoredRequests())),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await _tap(tester, find.text('Reconciliation'));
    await _tap(tester, find.text('Deposit'));
    await _tap(tester, find.text('Match transaction'));
    await _tap(tester, find.text('Retail checkout'));
    final amount = find.widgetWithText(TextField, 'Amount to match (₹)');
    expect(tester.widget<TextField>(amount).controller!.text, '40.00');
    await tester.enterText(amount, '20.00');
    await _tap(tester, find.text('Match amount'));
    expect(api.allocations.single['amount'], '20.00');
    expect(api.allocations.single['record_id'], 'pos');
    if (find.byTooltip('Remove allocation').evaluate().isEmpty) {
      await _tap(tester, find.text('Deposit'));
    }
    await _tap(tester, find.text('Match transaction'));
    expect(find.text('No eligible transactions match.'), findsOneWidget);
    await _tap(tester, find.text('Cancel'));
    await _tap(tester, find.byTooltip('Remove allocation'));
    await _tap(tester, find.text('Remove match'));
    expect(api.allocations, isEmpty);
  });
}
