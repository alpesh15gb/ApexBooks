import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/receipt_correction.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class _Pending implements PendingStore {
  final requests = <String, Json>{};

  @override
  Future<Json?> load(String operation) async => requests[operation];
  @override
  Future<void> save(String operation, Json data) async =>
      requests[operation] = data;
  @override
  Future<void> clear(String operation) async => requests.remove(operation);
}

class _Api implements ApexApi {
  final posts = <(String, Json, String?)>[];

  static final original = {
    'id': 'october',
    'date': '2026-10-29',
    'bank': 'DCB BANK',
    'utr': 'UTR-OCT',
    'amount': '48499',
    'booked': '48499',
    'unallocated': '30799',
    'receipts': [
      {
        'id': 'hosting',
        'number': 'PIN-1',
        'purpose': 'services',
        'amount': '17700',
        'advance_available': '0',
        'direct': [],
        'settlements': [
          {
            'id': 'application',
            'kind': 'advance_application',
            'number': 'ADV-4267A7F7',
            'amount': '17700',
            'allocations': [
              {'invoice': '2026-27/34'},
            ],
          },
        ],
      },
    ],
  };

  @override
  Future<Object?> get(String path, {Map<String, String>? query}) async => {
    'anchor_credit_id': 'october',
    'credits': [original],
    'invoices': [],
  };

  @override
  Future<Object?> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    posts.add((path, body, idempotencyKey));
    if (path.endsWith('/preview')) {
      return {
        'snapshot': 'server-snapshot',
        'before': [original],
        'after': [
          {...original, 'unallocated': '48499', 'receipts': []},
        ],
        'invoices_before': [
          {'number': '2026-27/34', 'outstanding': '0'},
        ],
        'invoices_after': [
          {'number': '2026-27/34', 'outstanding': '17700'},
        ],
      };
    }
    if (posts.length == 2) {
      throw const ApexApiException(message: 'Connection lost');
    }
    return {'id': 'completed-correction'};
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async =>
      Uint8List(0);
}

void main() {
  final record = BooksRecord({
    'id': 'application',
    'kind': 'advance_application',
    'posted': true,
    'data': {'payment_kind': 'payment_in'},
  });

  testWidgets(
    'previews an advance unlink and retries the same posting after reopening',
    (tester) async {
      final api = _Api();
      final pending = _Pending();
      final workspace = WorkspaceContext(
        api: api,
        pending: pending,
        features: {receiptCorrectionsFeature},
        refresh: () async {},
        company: const ApexCompany(
          id: 'company',
          name: 'Keystone',
          role: 'editor',
        ),
      );
      expect(canCorrectReceipt(workspace, record), isTrue);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showDialog<bool>(
                  context: context,
                  builder: (_) => ReceiptCorrectionDialog(
                    workspace: workspace,
                    record: record,
                  ),
                ),
                child: const Text('Open correction'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open correction'));
      await tester.pumpAndSettle();
      final unlink = find.widgetWithText(
        CheckboxListTile,
        'Unlink ADV-4267A7F7',
      );
      expect(tester.widget<CheckboxListTile>(unlink).value, isTrue);
      final reason = find.byType(TextFormField);
      await tester.ensureVisible(reason);
      await tester.enterText(reason, 'Keystone confirmed bank credit');
      await tester.tap(find.text('Preview correction'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Unallocated ₹48,499.00'), findsOneWidget);
      expect((api.posts.first.$2['credits'] as List).single['unlink'], [
        'application',
      ]);
      await tester.tap(find.text('Post correction'));
      await tester.pumpAndSettle();
      expect(find.text('Connection lost'), findsOneWidget);
      await tester.tap(find.text('Close'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Open correction'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Retry correction'));
      await tester.pumpAndSettle();
      expect(api.posts[1].$3, isNotNull);
      expect(api.posts[2], api.posts[1]);
      expect(pending.requests, isEmpty);
      expect(find.text('Correct allocation'), findsNothing);
    },
  );
}
