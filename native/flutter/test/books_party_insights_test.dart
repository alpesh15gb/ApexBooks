import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_party_insights.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class _ReadOnlyApi implements ApexApi {
  final calls = <(String, Map<String, String>?)>[];

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    calls.add((path, query));
    if (path.endsWith('/due-date')) {
      return {
        'party_id': 'customer',
        'document_date': '2026-04-01',
        'suggested_due_date': '2026-04-30',
      };
    }
    if (path.endsWith('/item-prices')) {
      return {
        'party_id': 'customer',
        'item_id': 'item',
        'side': 'sales',
        'default_rate': '25.00',
        'history': [
          {
            'rate': '20.00',
            'number': 'INV-10',
            'date': '2026-04-01',
            'price_includes_tax': true,
          },
        ],
      };
    }
    return {
      'party_id': 'customer',
      'as_of': '2026-04-01',
      'credit_limit': '100.00',
      'projected_exposure': '120.00',
      'exceeded': true,
    };
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => throw UnimplementedError();
}

class _UnusedPending implements PendingStore {
  @override
  Future<Json?> load(String operation) => throw UnimplementedError();
  @override
  Future<void> save(String operation, Json data) => throw UnimplementedError();
  @override
  Future<void> clear(String operation) => throw UnimplementedError();
}

void main() {
  testWidgets(
    'terms, price choices and credit warning use company-scoped server figures',
    (tester) async {
      final api = _ReadOnlyApi();
      final workspace = WorkspaceContext(
        api: api,
        company: const ApexCompany(id: 'shop', name: 'Shop', role: 'owner'),
        pending: _UnusedPending(),
        features: const {},
        refresh: () async {},
      );
      expect(
        await suggestedBooksDueDate(workspace, 'customer', '2026-04-01'),
        DateTime(2026, 4, 30),
      );
      BooksPriceChoice? chosen;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: Column(
                children: [
                  BooksPartyCredit(
                    workspace: workspace,
                    party: 'customer',
                    day: '2026-04-01',
                    amount: '40.00',
                  ),
                  TextButton(
                    onPressed: () async {
                      chosen = await showBooksPriceHistory(
                        context,
                        workspace,
                        'customer',
                        'item',
                        purchase: false,
                      );
                    },
                    child: const Text('Past prices'),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Customer credit limit exceeded'), findsOneWidget);
      await tester.tap(find.text('Past prices'));
      await tester.pumpAndSettle();
      expect(chosen, isNull);
      await tester.tap(find.text('₹20.00'));
      await tester.pumpAndSettle();
      expect(chosen, (rate: '20.00', inclusive: true));
      expect(api.calls.map((call) => call.$1), [
        '/api/companies/shop/parties/customer/due-date',
        '/api/companies/shop/parties/customer/credit-status',
        '/api/companies/shop/parties/customer/item-prices',
      ]);
      expect(api.calls.last.$2, {'item_id': 'item', 'side': 'sales'});
    },
  );
}
