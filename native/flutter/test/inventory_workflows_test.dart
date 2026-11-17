import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/inventory/inventory_models.dart';
import 'package:apex_books/features/inventory/inventory_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

const base = '/api/companies/counter';

class MemoryPending implements PendingStore {
  Json? saved;

  @override
  Future<Json?> load(String operation) async => saved;

  @override
  Future<void> save(String operation, Json data) async => saved = data;

  @override
  Future<void> clear(String operation) async => saved = null;
}

class InventoryApi implements ApexApi {
  bool loseFirstReceipt = false;
  bool showCancelledOrder = false;
  String quantity = '7.000';
  final receipts = <String, Json>{};
  final posted = <({String path, String? key, Json body})>[];

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == '$base/records' && query?['kind'] == 'item') {
      return [
        {
          'id': 'switch',
          'name': 'Board switch',
          'data': {
            'barcode': '00119',
            'sku': 'SW-A',
            'unit': 'pcs',
            'track_stock': true,
            'location_ids': ['rack'],
          },
        },
        {
          'id': 'plug',
          'name': 'Wall plug',
          'data': {'barcode': '119', 'track_stock': false},
        },
      ];
    }
    if (path == '$base/records' && query?['kind'] == 'party') {
      return [
        {
          'id': 'supplier-1',
          'name': 'Switch supplier',
          'data': {'party_type': 'supplier', 'phone': '9000000001'},
        },
      ];
    }
    if (path == '$base/records' && query?['kind'] == 'purchase_order') {
      return [
        {
          'id': 'order',
          'number': 'PO-1',
          'name': 'Switch supplier',
          'amount': '300.00',
          'date': '2026-04-01',
        },
        if (showCancelledOrder)
          {
            'id': 'cancelled',
            'number': 'PO-2',
            'name': 'Plug supplier',
            'amount': '50.00',
            'date': '2026-04-01',
            'cancelled': true,
          },
      ];
    }
    if (path == '$base/pos/stock') {
      return {
        'date': '2026-04-03',
        'rows': [
          {'item_id': 'switch', 'closing_quantity': quantity},
        ],
      };
    }
    if (path == '$base/reports/reorder') {
      return {
        'as_of': '2026-04-03',
        'total_low_stock': 1,
        'rows': [
          {
            'item_id': 'switch',
            'name': 'Board switch',
            'unit': 'pcs',
            'on_hand': '7',
            'low_stock_threshold': '9',
            'suggested_quantity': '2',
            'valuation_status': 'valued',
          },
        ],
      };
    }
    if (path == '$base/reports/stock/switch/movements') {
      if (query?['before_id'] == 'movement-1') {
        expect(query?['before_date'], '2026-04-03');
        return {
          'rows': [
            {
              'id': 'movement-2',
              'kind': 'stock_opening',
              'date': '2026-04-01',
              'number': 'OPEN-1',
              'quantity': '10.000',
              'cost_value': '120.00',
            },
          ],
          'next': null,
        };
      }
      return {
        'rows': [
          {
            'id': 'movement-1',
            'kind': 'pos',
            'date': '2026-04-03',
            'number': 'POS-1',
            'quantity': '-3.000',
            'cost_value': '-36.00',
          },
        ],
        'next': {'id': 'movement-1', 'date': '2026-04-03'},
      };
    }
    if (path == '$base/inventory-setup') {
      return {
        'locations': [
          {'id': 'rack', 'name': 'Rack 2'},
        ],
      };
    }
    if (path == '$base/records/bill') {
      return {
        ...receipts.values.first,
        'name': 'Switch supplier',
        'kind': 'purchase_bill',
        'data': {},
      };
    }
    if (path == '$base/purchase-orders/order/receiving') {
      return {
        'source_version': 2,
        'status': receipts.isEmpty ? 'open' : 'partial',
        'lines': [
          {
            'line_index': 0,
            'description': 'Board switch',
            'unit': 'pcs',
            'rate': '100.00',
            'gst_rate': '0',
            'ordered_quantity': '3',
            'received_quantity': receipts.isEmpty ? '0' : '2',
            'remaining_quantity': receipts.isEmpty ? '3' : '1',
          },
        ],
        'receipts': receipts.values.toList(),
      };
    }
    if (path == '$base/stock/counts/switch') {
      return {
        'item_id': 'switch',
        'date': '2026-04-03',
        'on_hand': quantity,
        'stock_snapshot': 'snapshot',
      };
    }
    throw StateError('Unexpected GET $path');
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    posted.add((path: path, key: idempotencyKey, body: body));
    if (path == '$base/records' && body['kind'] == 'purchase_order') {
      return {'id': 'new-po', 'number': 'PO-9', 'kind': 'purchase_order'};
    }
    if (path == '$base/purchase-orders/order/receipts/preview') {
      return {
        'amount': '200.00',
        'data': {
          'lines': [
            {'description': 'Board switch', 'quantity': '2', 'rate': '100.00'},
          ],
        },
      };
    }
    if (path == '$base/purchase-orders/order/receipts') {
      final existing = receipts[idempotencyKey];
      if (existing != null) return existing;
      final receipt = {
        'id': 'bill',
        'number': 'PB-1',
        'date': '2026-04-03',
        'amount': '200.00',
        'posted': true,
      };
      receipts[idempotencyKey!] = receipt;
      if (loseFirstReceipt) {
        throw const ApexApiException(message: 'Connection interrupted');
      }
      return receipt;
    }
    if (path == '$base/stock/counts') {
      quantity = '${body['counted_quantity']}';
      return {'id': 'count', 'stock_posted': true};
    }
    if (path == '$base/stock/opening') {
      quantity = '${body['quantity']}';
      return {'id': 'opening', 'posted': true};
    }
    throw StateError('Unexpected POST $path');
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async =>
      throw UnimplementedError();
}

Future<void> pumpInventory(
  WidgetTester tester,
  InventoryApi api,
  MemoryPending store, {
  String role = 'owner',
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: InventoryScreen(
          workspace: WorkspaceContext(
            api: api,
            company: ApexCompany(id: 'counter', name: 'Test store', role: role),
            pending: store,
            features: const {
              'pos_stock_summary',
              'inventory_setup',
              'stock_counts',
              'low_stock_reorder',
              'stock_movement_history',
              'purchase_order_receiving',
            },
            refresh: () async {},
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> click(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Desktop registers expose stock columns and filter order state', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1180, 840);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await pumpInventory(
      tester,
      InventoryApi()..showCancelledOrder = true,
      MemoryPending(),
    );
    expect(find.byKey(const ValueKey('inventory-item-table')), findsOneWidget);
    expect(find.text('SKU / BARCODE'), findsOneWidget);
    expect(find.text('SHELF LOCATIONS'), findsOneWidget);
    expect(find.text('ON HAND'), findsOneWidget);
    final item = find.byKey(const ValueKey('inventory-item-row-switch'));
    expect(
      find.descendant(of: item, matching: find.text('7 pcs')),
      findsOneWidget,
    );
    await click(tester, find.text('Purchase orders'));
    expect(find.byKey(const ValueKey('inventory-order-table')), findsOneWidget);
    expect(find.text('PO-1'), findsOneWidget);
    expect(find.text('PO-2'), findsOneWidget);
    tester.view.physicalSize = const Size(390, 844);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('inventory-order-cards')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('inventory-order-row-order')),
      findsOneWidget,
    );
    tester.view.physicalSize = const Size(1180, 840);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('inventory-order-table')), findsOneWidget);
    await click(tester, find.text('All orders'));
    await click(tester, find.text('Open orders'));
    expect(find.text('PO-1'), findsOneWidget);
    expect(find.text('PO-2'), findsNothing);
    await click(
      tester,
      find.byKey(const ValueKey('inventory-order-row-order')),
    );
    expect(find.text('Awaiting delivery'), findsOneWidget);
    await click(tester, find.byKey(const ValueKey('receiving-start')));
    final quantity = find.byKey(const ValueKey('receiving-quantity-0'));
    final rate = find.byKey(const ValueKey('receiving-rate-0'));
    expect(tester.getTopLeft(quantity).dy, tester.getTopLeft(rate).dy);
    expect(
      tester.getTopLeft(rate).dx,
      greaterThan(tester.getTopLeft(quantity).dx),
    );
    await tester.enterText(quantity, '1');
    tester.view.physicalSize = const Size(390, 844);
    await tester.pumpAndSettle();
    final quantityInput = find.descendant(
      of: quantity,
      matching: find.byType(EditableText),
    );
    expect(tester.widget<EditableText>(quantityInput).controller.text, '1');
    expect(tester.takeException(), isNull);
  });

  testWidgets('Phone stock cards lead into the stacked supplier bill form', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 750);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = InventoryApi();
    await pumpInventory(tester, api, MemoryPending());
    expect(find.byKey(const ValueKey('inventory-item-cards')), findsOneWidget);
    expect(find.byKey(const ValueKey('inventory-item-table')), findsNothing);
    await click(tester, find.text('Purchase orders'));
    expect(find.byKey(const ValueKey('inventory-order-cards')), findsOneWidget);
    await click(
      tester,
      find.byKey(const ValueKey('inventory-order-row-order')),
    );
    expect(find.text('Purchase order'), findsOneWidget);
    expect(find.text('PO-1'), findsOneWidget);
    await click(tester, find.byKey(const ValueKey('receiving-start')));
    final quantity = find.byKey(const ValueKey('receiving-quantity-0'));
    final rate = find.byKey(const ValueKey('receiving-rate-0'));
    expect(
      tester.getTopLeft(rate).dy,
      greaterThan(tester.getTopLeft(quantity).dy),
    );
    await tester.ensureVisible(quantity);
    await tester.enterText(quantity, '2');
    await tester.ensureVisible(rate);
    await tester.enterText(rate, '95.00');
    await click(tester, find.byKey(const ValueKey('receiving-review')));
    expect(
      api.posted.single.path,
      '$base/purchase-orders/order/receipts/preview',
    );
    expect(api.posted.single.body['lines'], [
      {'line_index': 0, 'quantity': '2', 'rate': '95.00'},
    ]);
    expect(find.byKey(const ValueKey('receiving-post')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'Filters items by assigned shelf without changing company stock balances',
    (tester) async {
      await pumpInventory(tester, InventoryApi(), MemoryPending());
      await click(tester, find.text('All shelves'));
      await click(tester, find.text('Rack 2').last);
      expect(find.text('Board switch'), findsOneWidget);
      expect(find.text('Wall plug'), findsNothing);
      expect(find.text('7 pcs'), findsOneWidget);
      expect(
        find.text('Stock quantities cover the full company'),
        findsOneWidget,
      );
      await click(tester, find.text('Rack 2').first);
      await click(tester, find.text('Unassigned shelf'));
      expect(find.text('Wall plug'), findsOneWidget);
      expect(find.text('Board switch'), findsNothing);
    },
  );

  testWidgets('Pages through the signed quantities in an item’s stock ledger', (
    tester,
  ) async {
    await pumpInventory(tester, InventoryApi(), MemoryPending());
    await click(tester, find.text('Board switch'));
    await click(tester, find.text('Stock movements'));
    expect(find.text('POS sale POS-1'), findsOneWidget);
    expect(find.text('-3'), findsOneWidget);
    await click(tester, find.text('Load older movements'));
    expect(find.text('Opening stock OPEN-1'), findsOneWidget);
    expect(find.text('+10'), findsOneWidget);
    expect(find.text('Load older movements'), findsNothing);
  });

  testWidgets('Opens low stock suggestions and the affected item', (
    tester,
  ) async {
    final api = InventoryApi();
    await pumpInventory(tester, api, MemoryPending());
    await click(tester, find.text('Low stock & reorder'));
    expect(find.text('1 item at or below its threshold'), findsOneWidget);
    expect(find.text('Suggest 2 pcs'), findsOneWidget);
    expect(find.text('On hand 7 · Threshold 9'), findsOneWidget);
    await click(tester, find.text('Board switch'));
    expect(find.text('7 pcs on hand'), findsOneWidget);
    expect(api.posted, isEmpty);
  });

  testWidgets('Creates a purchase order draft from selected suggestions', (
    tester,
  ) async {
    final api = InventoryApi();
    await pumpInventory(tester, api, MemoryPending());
    await click(tester, find.text('Low stock & reorder'));
    expect(find.text('0 selected · Draft only, no stock or payment movement'),
        findsOneWidget);
    await click(tester, find.byType(Checkbox));
    await click(tester, find.text('Create purchase order'));
    expect(api.posted, isEmpty);
    await tester.tap(find.text('Supplier'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Switch supplier').last);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Create purchase order').last);
    await tester.pumpAndSettle();
    final post = api.posted.single;
    expect(post.path, '$base/records');
    expect(post.key, isNotNull);
    expect(post.body['kind'], 'purchase_order');
    expect(post.body['name'], 'Switch supplier');
    final data = post.body['data'] as Map;
    expect(data['party_id'], 'supplier-1');
    expect((data['lines'] as List).single['item_id'], 'switch');
    expect((data['lines'] as List).single['quantity'], '2');
    expect(find.textContaining('Purchase order PO-9 created'), findsOneWidget);
  });

  testWidgets(
    'Records opening quantity with a cost, leaving the physical count separate',
    (tester) async {
      final api = InventoryApi()..quantity = '0.000';
      await pumpInventory(tester, api, MemoryPending());
      await click(tester, find.text('Board switch'));
      await click(tester, find.text('Opening stock'));
      await tester.enterText(
        find.widgetWithText(TextField, 'Quantity'),
        '4.250',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Unit cost (₹)'),
        '12.50',
      );
      await click(tester, find.text('Review stock entry'));
      await click(tester, find.text('Post stock entry'));
      expect(find.text('Opening stock posted.'), findsOneWidget);
      expect(find.text('4.25 pcs on hand'), findsOneWidget);
      expect(api.posted.single.path, '$base/stock/opening');
      expect(api.posted.single.key, isNotEmpty);
      expect(api.posted.single.body['unit_cost'], '12.50');
      expect(api.posted.single.body['quantity'], '4.250');
    },
  );

  test(
    'Decimal inventory input preserves supported quantity and money precision',
    () {
      expect(
        inventoryDecimal('999999999999.999', 3),
        BigInt.parse('999999999999999'),
      );
      expect(inventoryDecimal('9999999999999.000', 3), isNull);
      expect(inventoryDecimal('0.0001', 3), isNull);
      expect(inventoryDecimal(' 0.01 ', 2), BigInt.one);
      expect(inventoryAmount('12345678.01'), '₹1,23,45,678.01');
    },
  );

  testWidgets(
    'Scans a leading-zero barcode, shows current stock and records a loss',
    (tester) async {
      final api = InventoryApi();
      await pumpInventory(tester, api, MemoryPending());
      expect(find.text('7 pcs'), findsOneWidget);
      await tester.enterText(find.byType(TextField).first, 'SW-A Rack 2');
      await tester.pumpAndSettle();
      expect(find.text('Board switch'), findsOneWidget);
      expect(find.text('Wall plug'), findsNothing);
      await tester.enterText(find.byType(TextField).first, '00119');
      await tester.testTextInput.receiveAction(TextInputAction.search);
      await tester.pumpAndSettle();
      expect(find.text('7 pcs on hand'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextField, 'Counted quantity'),
        '5',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Reason for difference'),
        'Damaged packaging',
      );
      await click(tester, find.text('Review adjustment'));
      expect(find.text('Decrease by 2 pcs'), findsOneWidget);
      await click(tester, find.text('Record stock count'));
      expect(find.text('Stock count recorded.'), findsOneWidget);
      expect(find.text('5 pcs on hand'), findsOneWidget);
      expect(api.posted.single.body, {
        'item_id': 'switch',
        'date': '2026-04-03',
        'stock_snapshot': 'snapshot',
        'counted_quantity': '5',
        'reason': 'Damaged packaging',
      });
      expect(api.posted.single.key, isNotEmpty);
    },
  );

  testWidgets(
    'Keeps a reviewed supplier bill across reopen and retries the same request',
    (tester) async {
      tester.view.physicalSize = const Size(900, 1100);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = InventoryApi()..loseFirstReceipt = true;
      final store = MemoryPending();
      await pumpInventory(tester, api, store);
      await click(tester, find.text('Purchase orders'));
      await click(tester, find.text('Switch supplier'));
      await click(tester, find.text('Receive items'));
      await tester.enterText(
        find.byKey(const ValueKey('receiving-quantity-0')),
        '2',
      );
      await click(tester, find.text('Review supplier bill'));
      expect(find.text('Supplier bill total ₹200.00'), findsOneWidget);
      await click(tester, find.text('Post supplier bill'));
      expect(find.text('Connection interrupted'), findsOneWidget);
      expect(store.saved, isNotNull);
      expect(api.receipts, hasLength(1));
      final first = api.posted.last;
      expect(first.body['expected_total'], '200.00');
      expect(first.body['source_version'], 2);
      expect(first.body['lines'], [
        {'line_index': 0, 'quantity': '2'},
      ]);

      await tester.pumpWidget(const SizedBox());
      await pumpInventory(tester, api, store);
      await click(tester, find.text('Retry original'));
      expect(api.posted.last.key, first.key);
      expect(api.posted.last.body, first.body);
      expect(store.saved, isNull);
      expect(api.receipts, hasLength(1));
      await click(tester, find.text('Purchase orders'));
      await click(tester, find.text('Switch supplier'));
      expect(find.text('Partially received'), findsOneWidget);
      expect(find.text('PB-1'), findsOneWidget);
      await click(tester, find.text('PB-1'));
      expect(find.text('Return to receiving'), findsOneWidget);
    },
  );

  testWidgets('A viewer sees receiving balances without write controls', (
    tester,
  ) async {
    final api = InventoryApi();
    await pumpInventory(tester, api, MemoryPending(), role: 'viewer');
    await click(tester, find.text('Purchase orders'));
    await click(tester, find.text('Switch supplier'));
    expect(find.text('Awaiting delivery'), findsOneWidget);
    expect(find.text('Receive items'), findsNothing);
    expect(api.posted, isEmpty);
  });
}
