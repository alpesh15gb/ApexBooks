import 'dart:convert';
import 'dart:typed_data';

import 'package:apex_books/core/pdf_output.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/pos/pos_return_controller.dart';
import 'package:apex_books/features/pos/pos_return_models.dart';
import 'package:apex_books/features/pos/pos_screen.dart';
import 'package:apex_books/features/pos/pos_workspace_api.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  testWidgets(
    '390px posted receipt prints both rolls and posts a reviewed linked refund',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 860);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final store = _Pending();
      final api = _StoreApi(store);
      final output = _Output();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PosScreen(
              workspace: _workspace(api, store),
              pdfOutput: output,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await _tap(tester, 'Receipts');
      await _tap(tester, 'POS/26-27/0001');
      await _tap(tester, 'Print 58 mm');
      await _tap(tester, 'Print 80 mm');
      expect(api.pdfTemplates, ['thermal_58', 'thermal_80']);
      expect(output.sent.map((document) => document.rollWidthMm), [58, 80]);
      expect(output.sent.first.pageWidthPoints, closeTo(164.4094, .01));
      expect(output.sent.last.pageWidthPoints, closeTo(226.7717, .01));
      expect(output.sent.last.name, 'apex-POS-26-27-0001-80-mm.pdf');

      await _tap(tester, 'Return items');
      final quantity = find.widgetWithText(
        TextFormField,
        'Return quantity for Counter oats (line 1)',
      );
      await tester.ensureVisible(quantity);
      await tester.enterText(quantity, '3');
      await tester.pumpAndSettle();
      expect(
        find.textContaining('within the remaining amount'),
        findsOneWidget,
      );
      await tester.enterText(quantity, '1');
      await tester.pump(const Duration(milliseconds: 230));
      await tester.pumpAndSettle();
      expect(find.text('Return total ₹62.50'), findsOneWidget);
      await _tap(tester, 'Keep as customer credit');
      await _tap(tester, 'Cash refund');
      await tester.pump(const Duration(milliseconds: 230));
      await tester.pumpAndSettle();
      final submit = find.byKey(const ValueKey('pos-post-return'));
      expect(tester.widget<FilledButton>(submit).onPressed, isNull);
      await _tap(tester, 'I handed this cash refund to the customer.');
      await _tap(tester, 'Post return');
      expect(find.text('Return posted'), findsOneWidget);
      expect(tester.getRect(find.text('Return posted')).bottom, lessThan(860));
      expect(find.text('Refund REF-RETURN'), findsOneWidget);
      expect(api.committed?.body, containsPair('source_version', 3));
      expect(api.committed?.body, containsPair('expected_total', '62.50'));
      expect(api.committed?.body, containsPair('return_stock', true));
      expect(api.committed?.body, containsPair('payment_account', 'cash'));
      expect(api.stockReads, greaterThanOrEqualTo(2));
      expect(store.values, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );

  test('a lost return response survives recreation and replays the exact credit command', () async {
    final store = _Pending();
    final api = _StoreApi(store)..loseResponse = true;
    final workspace = _workspace(api, store);
    final first = _controller(workspace);
    await first.recover();
    await first.start('sale');
    first.changeQuantity(0, '0.500');
    first.changeOptions(returnStock: false, reason: 'Damaged goods');
    await _tick();
    await first.submit();
    expect(first.pending, isNotNull);
    expect(first.pending?.body, containsPair('return_stock', false));
    expect(first.pending?.body, containsPair('payment_account', null));
    expect(first.blocksWrites, isTrue);
    first.dispose();

    final restarted = _controller(workspace);
    addTearDown(restarted.dispose);
    await restarted.recover();
    expect(restarted.canRetry, isTrue);
    await restarted.submit();
    expect(api.posts, hasLength(2));
    expect(api.posts.toSet(), hasLength(1));
    expect(restarted.completed?.creditNumber, 'CN/26-27/0001');
    expect(restarted.completed?.refund, isNull);
    expect(restarted.pending, isNull);
  });

  test(
    'a stale return total discards the quote and reloads eligible quantities',
    () async {
      final store = _Pending();
      final api = _StoreApi(store)..stale = true;
      final controller = _controller(_workspace(api, store));
      addTearDown(controller.dispose);
      await controller.recover();
      await controller.start('sale');
      controller.changeQuantity(0, '1');
      controller.changeOptions(settlement: PosReturnSettlement.cash);
      await _tick();
      controller.confirm(true);
      await controller.submit();
      expect(controller.error, 'Refund total changed.');
      expect(controller.pending, isNull);
      expect(controller.quote, isNull);
      expect(controller.confirmed, isFalse);
      expect(controller.quantities, isEmpty);
      expect(api.receiptReads, 2);
    },
  );

  test(
    'print uses valid server media dimensions and refuses the wrong roll',
    () async {
      final store = _Pending();
      final api = _StoreApi(store)..wrongRoll = true;
      final gateway = WorkspacePosGateway(_workspace(api, store));
      final receipt = await gateway.receipt('sale');
      await expectLater(gateway.receiptPdf(receipt, 80), throwsFormatException);
      await expectLater(gateway.receiptPdf(receipt, 100), throwsA(anything));
    },
  );

  test(
    'bank refund requires an account and a new confirmation when it changes',
    () async {
      final store = _Pending();
      final api = _StoreApi(store);
      final controller = _controller(_workspace(api, store));
      addTearDown(controller.dispose);
      await controller.recover();
      await controller.start('sale');
      controller.changeQuantity(0, '1');
      controller.changeOptions(settlement: PosReturnSettlement.bank);
      expect(controller.quoteError, contains('Choose the bank account'));
      controller.changeOptions(bankId: 'settlement-a');
      await _tick();
      controller.confirm(true);
      expect(controller.ready, isTrue);
      controller.changeOptions(bankId: 'settlement-b');
      await _tick();
      expect(controller.ready, isFalse);
      controller.confirm(true);
      await controller.submit();
      expect(
        api.committed?.body,
        containsPair('bank_account_id', 'settlement-b'),
      );
      expect(controller.completed?.active, isTrue);
    },
  );
}

Future<void> _tick() => Future<void>.delayed(const Duration(milliseconds: 10));

Future<void> _tap(WidgetTester tester, String label) async {
  final target = find.text(label).last;
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

WorkspaceContext _workspace(_StoreApi api, _Pending store) => WorkspaceContext(
  api: api,
  company: const ApexCompany(
    id: 'front',
    name: 'Cash drawer test',
    role: 'owner',
  ),
  pending: store,
  features: const {
    'pos_atomic_returns',
    'pos_stock_summary',
    'thermal_receipts',
  },
  refresh: () async {},
);

PosReturnController _controller(WorkspaceContext workspace) =>
    PosReturnController(
      gateway: WorkspacePosGateway(workspace),
      canWrite: workspace.company.canWrite,
      businessDate: () => '2026-11-16',
      quoteDelay: Duration.zero,
      onSaved: () {},
    );

class _Output implements PdfOutput {
  final sent = <ApexPdf>[];

  @override
  Future<bool> print(ApexPdf document) async {
    sent.add(document);
    return true;
  }
}

class _Pending implements PendingStore {
  final values = <String, Json>{};

  @override
  Future<void> clear(String operation) async => values.remove(operation);

  @override
  Future<Json?> load(String operation) async => values[operation];

  @override
  Future<void> save(String operation, Json data) async =>
      values[operation] = data;
}

class _StoreApi implements ApexApi {
  _StoreApi(this.store);
  final _Pending store;
  final pdfTemplates = <String>[];
  final posts = <String>[];
  int receiptReads = 0;
  int stockReads = 0;
  bool loseResponse = false;
  bool stale = false;
  bool wrongRoll = false;
  PosReturnCommand? committed;

  Json _receipt() => {
    'id': 'sale',
    'kind': 'pos',
    'number': 'POS/26-27/0001',
    'name': 'Walk-in customer',
    'date': '2026-11-16',
    'posted': true,
    'amount': '125.00',
    'data': {
      'version': 3,
      'lines': [
        {'description': 'Counter oats', 'quantity': '2.000'},
      ],
    },
    'return_capacity_lines': [
      {
        'description': 'Counter oats',
        'unit': 'box',
        'remaining_return_quantity': committed == null ? '2.0000' : '1.000',
      },
    ],
  };

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    switch (path) {
      case '/api/companies/front/records':
        return [if (query?['kind'] == 'pos') _receipt()];
      case '/api/companies/front/records/sale':
        receiptReads++;
        return _receipt();
      case '/api/companies/front/bank-accounts':
        return [
          {'id': 'default', 'name': 'Bank clearing'},
        ];
      case '/api/companies/front/pos/stock':
        stockReads++;
        return {'rows': <Json>[]};
      default:
        throw StateError('Unexpected GET $path');
    }
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    if (path.endsWith('/pos/sale/return/preview')) {
      expect(idempotencyKey, isNull);
      final selected = (body['lines'] as List).single as Json;
      expect(selected['source_index'], 0);
      return {'amount': '62.50', 'data': <String, dynamic>{}};
    }
    expect(path, '/api/companies/front/pos/sale/return');
    final saved = PosReturnCommand.fromJson(store.values['pos_return']!);
    expect(saved.key, idempotencyKey);
    expect(saved.body, body);
    posts.add(jsonEncode([path, idempotencyKey, body]));
    if (stale) {
      throw const ApexApiException(
        message: 'Refund total changed.',
        status: 409,
        code: 'POS_REQUOTE_REQUIRED',
      );
    }
    committed = saved;
    if (loseResponse && posts.length == 1) {
      throw const ApexApiException(message: 'Connection interrupted.');
    }
    return {
      'credit_note': {
        'kind': 'credit_note',
        'id': 'note',
        'number': 'CN/26-27/0001',
        'amount': '62.50',
        'posted': true,
        'data': {'applied_to': 'sale'},
      },
      'refund': body['payment_account'] == null
          ? null
          : {
              'kind': 'customer_refund',
              'id': 'refund',
              'number': 'REF-RETURN',
              'amount': '62.50',
              'posted': true,
              'data': {
                'credit_note_id': 'note',
                'payment_account': body['payment_account'],
              },
            },
    };
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async {
    expect(path, '/api/companies/front/documents/sale.pdf');
    final template = query!['template']!;
    pdfTemplates.add(template);
    final width = wrongRoll || template == 'thermal_58'
        ? '164.4094'
        : '226.7717';
    return Uint8List.fromList(
      utf8.encode('%PDF-1.4\n/MediaBox [ 0 0 $width 320 ]\n'),
    );
  }
}
