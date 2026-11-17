import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_entry_posting.dart';
import 'package:apex_books/features/books/books_recurring.dart';
import 'package:apex_books/features/commerce/commerce_screen.dart';
import 'package:apex_books/features/inventory/inventory_posting.dart';
import 'package:apex_books/features/inventory/inventory_receiving.dart';
import 'package:apex_books/features/inventory/inventory_reorder.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import 'support/harness.dart';

/// Answers a few paths with hand-made data (the seeded company has none of it) and
/// everything else from the recordings.
class _Overlay implements ApexApi, ApexWriteApi {
  _Overlay(this.base, this.answers);
  final ApexApi base;
  final Map<String, Object?> answers;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    for (final entry in answers.entries) {
      if (path.endsWith(entry.key)) return entry.value;
    }
    return base.get(path, query: query);
  }

  @override
  Future<dynamic> post(String path, {required Json body, String? idempotencyKey}) async => <String, dynamic>{};
  @override
  Future<dynamic> put(String path, {required Json body, String? idempotencyKey}) async => <String, dynamic>{};
  @override
  Future<dynamic> patch(String path, {required Json body, String? idempotencyKey}) async => <String, dynamic>{};
  @override
  Future<dynamic> delete(String path, {Map<String, String>? query}) async => <String, dynamic>{};
  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async => Uint8List(0);
}

WorkspaceContext _with(Map<String, Object?> answers) {
  final real = shotWorkspace();
  return WorkspaceContext(
    api: _Overlay(real.api, answers),
    company: real.company,
    pending: real.pending,
    features: real.features,
    refresh: real.refresh,
  );
}

final _templates = {
  'templates': [
    {
      'id': 't1',
      'name': 'Monthly stationery',
      'draft_kind': 'purchase_order',
      'party_name': 'Reliable Supplies Pvt Ltd',
      'is_active': true,
      'interval': 1,
      'frequency': 'monthly',
      'start_date': '2026-10-17',
      'next_due': '2026-11-17',
      'generated_count': 1,
      'last_generated_date': '2026-10-17',
      'version': 1,
    },
  ],
};
final _due = {
  'business_date': '2026-11-17',
  'rows': [
    {
      'id': 't1',
      'name': 'Monthly stationery',
      'draft_kind': 'purchase_order',
      'party_name': 'Reliable Supplies Pvt Ltd',
      'next_due': '2026-11-17',
      'overdue_days': 0,
    },
  ],
};

void main() {
  for (final (suffix, size) in [('', desktop), ('-phone', phone)]) {
    testWidgets('recurring$suffix', (tester) async {
      final ws = _with({'/recurring-templates/due': _due, '/recurring-templates': _templates});
      final posting = BooksPosting(ws);
      await shot(
        tester,
        'tools-recurring$suffix',
        BooksRecurring(posting: posting, onBack: () {}, onGenerated: (_) {}, showBack: false),
        size: size,
      );
    });

    testWidgets('reorder$suffix', (tester) async {
      final ws = _with({
        '/reports/reorder': {
          'as_of': '2026-11-17',
          'total_low_stock': 2,
          'rows': [
            {'item_id': 'a', 'name': 'Board switch', 'unit': 'pcs', 'on_hand': '7', 'low_stock_threshold': '9', 'suggested_quantity': '2', 'valuation_status': 'valued'},
            {'item_id': 'b', 'name': 'Wall plug', 'unit': 'pcs', 'on_hand': '3', 'low_stock_threshold': '10', 'suggested_quantity': '7', 'valuation_status': 'valued'},
          ],
        },
      });
      await shot(
        tester,
        'tools-reorder$suffix',
        InventoryReorderPage(workspace: ws, openItem: (_) async {}),
        size: size,
        before: (tester) async {
          await tester.tap(find.byType(Checkbox).first);
          await tester.pump(const Duration(milliseconds: 200));
        },
      );
    });

    testWidgets('receiving$suffix', (tester) async {
      final ws = _with({
        '/purchase-orders/po1/receiving': {
          'status': 'partial',
          'source_version': 1,
          'receipts': [],
          'lines': [
            {'line_index': 0, 'description': 'Board switch', 'unit': 'pcs', 'ordered_quantity': '10', 'received_quantity': '4', 'remaining_quantity': '6', 'rate': '100.00', 'gst_rate': '18'},
            {'line_index': 1, 'description': 'Wall plug', 'unit': 'pcs', 'ordered_quantity': '5', 'received_quantity': '5', 'remaining_quantity': '0', 'rate': '20.00', 'gst_rate': '18'},
          ],
        },
      });
      final posting = InventoryPosting(ws);
      await posting.load();
      await shot(
        tester,
        'tools-receiving$suffix',
        InventoryReceivingPage(
          posting: posting,
          order: const {'id': 'po1', 'number': 'PO-1', 'name': 'Reliable Supplies Pvt Ltd', 'date': '2026-11-01', 'amount': '1100.00'},
          today: '2026-11-17',
        ),
        size: size,
        before: (tester) async {
          final start = find.byKey(const ValueKey('receiving-start'));
          if (start.evaluate().isNotEmpty) await tester.tap(start);
          await tester.pump(const Duration(milliseconds: 200));
        },
      );
    });

    testWidgets('commerce-orders$suffix', (tester) async {
      final connection = {'id': 'c1', 'name': 'Demo store', 'channel': 'default', 'status': 'active', 'base_url': 'https://store.example.invalid', 'config': {'verified': true}};
      final ws = _with({
        '/commerce/connections': [connection],
        '/commerce/connections/c1/workspace': {
          'connection': connection,
          'orders': [
            {
              'id': 'o1',
              'external_id': '19',
              'number': 'ORDER-19',
              'status': 'processing',
              'amount': '1180.00',
              'party_id': '6e2c566a-50ce-49e6-b951-2181904b6eb2',
              'snapshot': {
                'customer_id': '77',
                'items': [
                  {'id': '25', 'name': 'Counter cable', 'sku': 'SKU-CABLE', 'quantity': '4', 'shipped': '1', 'invoiced': '2'},
                  {'id': '26', 'name': 'Board switch', 'sku': 'SW-A', 'quantity': '2', 'shipped': '0', 'invoiced': '0'},
                ],
              },
            },
          ],
          'stock': [],
          'links': [],
          'inbox': [],
          'outbox': [],
          'reconciliations': [],
          'summary': {'inbox': {}, 'outbox': {}},
        },
      });
      await shot(
        tester,
        'tools-commerce-orders$suffix',
        CommerceScreen(workspace: ws),
        size: size,
        before: (tester) async {
          await tester.tap(find.text('Orders').first);
          await tester.pump(const Duration(milliseconds: 300));
          await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
          await tester.pump(const Duration(milliseconds: 300));
          await tester.tap(find.text('Open order').first);
          await tester.pump(const Duration(milliseconds: 400));
        },
      );
    });
  }
}
