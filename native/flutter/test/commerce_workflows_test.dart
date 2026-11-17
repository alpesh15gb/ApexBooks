import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/commerce/commerce_commands.dart';
import 'package:apex_books/features/commerce/commerce_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

const root = '/api/companies/shop/commerce/connections';
const connectionId = 'store-1';

class _Pending implements PendingStore {
  final saved = <String, Json>{};
  @override
  Future<Json?> load(String operation) async => saved[operation];
  @override
  Future<void> save(String operation, Json data) async =>
      saved[operation] = data;
  @override
  Future<void> clear(String operation) async => saved.remove(operation);
}

class _MockCommerce implements ApexApi, ApexWriteApi {
  _MockCommerce({this.hasConnection = true, this.loseFirstCommand = false});
  bool hasConnection;
  bool loseFirstCommand;
  String status = 'active';
  bool verified = true;
  final sentCommands = <Json>[];
  final accepted = <String, Json>{};
  Json? connected;

  Json get connection => {
    'id': connectionId,
    'name': 'Test store',
    'base_url': 'https://store.example.invalid',
    'channel': 'retail',
    'status': status,
    'currency': 'INR',
    'config': {'verified': verified},
  };

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path == root) return hasConnection ? [connection] : [];
    if (path == '/api/companies/shop/bank-accounts') {
      return [
        {'id': 'default', 'name': 'Bank clearing'},
        {'id': 'settlement', 'name': 'Settlement bank'},
      ];
    }
    if (path == '/api/companies/shop/records' && query?['kind'] == 'party') {
      return [
        {'id': 'cust-1', 'name': 'Asha Traders', 'kind': 'party'},
      ];
    }
    if (path == '/api/companies/shop/records/record-19') {
      return {
        'id': 'record-19',
        'kind': 'sales_invoice',
        'posted': true,
        'outstanding': '100.00',
        'date': '2026-04-01',
      };
    }
    if (path == '/api/companies/shop/records/advance-19') {
      return {
        'id': 'advance-19',
        'kind': 'payment_in',
        'posted': true,
        'advance_remaining': '40.00',
        'date': '2026-04-01',
        'data': {'is_advance': true},
      };
    }
    if (path == '/api/companies/shop/records/credit-19') {
      return {
        'id': 'credit-19',
        'kind': 'credit_note',
        'posted': true,
        'credit_remaining': '20.00',
        'date': '2026-04-01',
        'data': {'return_stock': false},
      };
    }
    if (path == '$root/$connectionId/workspace') {
      return {
        'connection': connection,
        'orders': [
          {
            'id': 'local-order',
            'external_id': '19',
            'number': 'ORDER-19',
            'party_id': 'cust-1',
            'status': 'processing',
            'amount': '100.00',
            'snapshot': {
              'items': [
                {
                  'id': '25',
                  'name': 'Counter cable',
                  'quantity': '4',
                  'shipped': '1',
                  'invoiced': '2',
                },
              ],
            },
          },
        ],
        'stock': [
          {
            'external_id': '42',
            'name': 'Counter cable',
            'sku': 'SKU-CABLE',
            'track_stock': true,
          },
        ],
        'links': [
          {
            'id': 'invoice-link',
            'entity_type': 'invoice',
            'external_id': 'inv-19',
            'record_id': 'record-19',
            'snapshot': {
              'order_id': '19',
              'amount': '100.00',
              'date': '2026-04-01',
            },
          },
          {
            'id': 'capture-link',
            'entity_type': 'capture',
            'external_id': 'cap-19',
            'record_id': 'advance-19',
            'snapshot': {
              'order_id': '19',
              'amount': '100.00',
              'date': '2026-04-01',
              '_result': {'advance': true},
            },
          },
          {
            'id': 'refund-link',
            'entity_type': 'refund',
            'external_id': 'refund-19',
            'record_id': 'refund-record',
            'snapshot': {
              'order_id': '19',
              'amount': '20.00',
              'date': '2026-04-01',
            },
          },
          {
            'id': 'credit-link',
            'entity_type': 'credit',
            'external_id': 'cre-19',
            'record_id': 'credit-19',
            'snapshot': {
              'order_id': '19',
              'amount': '20.00',
              'date': '2026-04-01',
              'lines': [
                {'product_id': '42', 'quantity': '2.5'},
              ],
            },
          },
        ],
        'inbox': [],
        'outbox': [],
        'reconciliations': [
          {
            'status': 'review',
            'created_at': '2026-04-03T11:00:00Z',
            'report': {
              'stock_differences': [
                {'product_id': 'p-1', 'expected': '5', 'actual': '4'},
              ],
              'financial_differences': [
                {'total': 'invoice_total', 'expected': '100', 'actual': '75'},
              ],
            },
          },
        ],
        'summary': {'inbox': {}, 'outbox': {}},
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
    if (path == root) {
      connected = body;
      hasConnection = true;
      status = 'draft';
      verified = false;
      return {...connection, 'setup_secret': 'synthetic-only-secret'};
    }
    if (path == '$root/$connectionId/verify') {
      verified = true;
      return {'verified': true};
    }
    if (path == '$root/$connectionId/commands') {
      sentCommands.add(body);
      final id = body['command_id'] as String;
      final old = accepted[id];
      if (old != null) return old;
      final reply = {
        'id': 'delivery-id',
        'connection_id': connectionId,
        'status': 'pending',
        ...body,
      };
      accepted[id] = reply;
      if (loseFirstCommand) {
        throw const ApexApiException(message: 'Response interrupted');
      }
      return reply;
    }
    throw StateError('Unexpected POST $path');
  }

  @override
  Future<dynamic> put(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    expect(path, '$root/$connectionId/state');
    status = body['status'] as String;
    return connection;
  }

  @override
  Future<dynamic> patch(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async => throw UnimplementedError();
  @override
  Future<dynamic> delete(String path, {Map<String, String>? query}) async =>
      throw UnimplementedError();
  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async =>
      throw UnimplementedError();
}

WorkspaceContext _scope(
  _MockCommerce api,
  _Pending store, [
  String role = 'owner',
]) => WorkspaceContext(
  api: api,
  company: ApexCompany(
    id: 'shop',
    name: 'Test books',
    role: role,
    stateCode: '36',
    taxMode: 'regular',
  ),
  pending: store,
  features: const {},
  refresh: () async {},
);

Future<void> _tap(WidgetTester tester, String label) async {
  final finder = find.text(label).last;
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _field(WidgetTester tester, String title, String value) async {
  final finder = find.widgetWithText(TextField, title);
  await tester.ensureVisible(finder);
  await tester.enterText(finder, value);
  await tester.pumpAndSettle();
}

Future<void> _show(WidgetTester tester, WorkspaceContext scope) async {
  tester.view.physicalSize = const Size(900, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: CommerceScreen(workspace: scope)),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test(
    'A reopened scoped queue recovers the identical accepted command',
    () async {
      final api = _MockCommerce(loseFirstCommand: true);
      final store = _Pending();
      final scope = _scope(api, store, 'editor');
      final queue = CommerceCommandQueue(scope);
      await queue.load();
      await expectLater(
        queue.submit(connectionId, 'order.invoice', {
          'order_id': '19',
          'items': {'25': 2},
        }),
        throwsA(isA<ApexApiException>()),
      );
      expect(store.saved, isNotEmpty);
      queue.dispose();

      final opened = CommerceCommandQueue(scope);
      await opened.load();
      expect(opened.canSubmit, isFalse);
      await expectLater(opened.retry('different-store'), throwsStateError);
      await opened.retry(connectionId);
      expect(api.sentCommands[1], api.sentCommands[0]);
      expect(api.accepted, hasLength(1));
      expect(store.saved, isEmpty);
      opened.dispose();
    },
  );

  testWidgets(
    'Creates, verifies and activates a connection without saving its setup secret',
    (tester) async {
      final api = _MockCommerce(hasConnection: false);
      final store = _Pending();
      await _show(tester, _scope(api, store));
      await _tap(tester, 'Connect Bagisto');
      await _field(tester, 'Store name', 'Test store');
      await _field(tester, 'Store origin', 'https://store.example.invalid/');
      await _field(tester, 'Store channel', 'retail');
      await _tap(tester, 'Create connection');
      expect(find.text('synthetic-only-secret'), findsOneWidget);
      expect(store.saved, isEmpty);
      expect(api.connected?['base_url'], 'https://store.example.invalid');
      await _tap(tester, 'Done');
      expect(find.text('synthetic-only-secret'), findsNothing);
      await _tap(tester, 'Verify bridge');
      await _tap(tester, 'Confirm');
      expect(api.verified, isTrue);
      await _tap(tester, 'Activate');
      await _tap(tester, 'Confirm');
      expect(api.status, 'active');
      await _tap(tester, 'Pause');
      await _tap(tester, 'Confirm');
      expect(api.status, 'paused');
    },
  );

  testWidgets(
    'Requires order command review and queues the exact shipment quantities',
    (tester) async {
      final api = _MockCommerce();
      await _show(tester, _scope(api, _Pending(), 'editor'));
      await _tap(tester, 'Orders');
      await _tap(tester, 'Open order');
      await _tap(tester, 'Create invoice');
      await _tap(tester, 'Create shipment');
      await _field(tester, 'Quantity for Counter cable (up to 3)', '4');
      await _tap(tester, 'Review command');
      expect(api.sentCommands, isEmpty);
      expect(
        find.textContaining('within the available balance'),
        findsOneWidget,
      );
      await _field(tester, 'Quantity for Counter cable (up to 3)', '2');
      await _field(tester, 'Tracking number (optional)', 'TRACK-01');
      await _tap(tester, 'Review command');
      expect(find.text('2 units on order ORDER-19'), findsOneWidget);
      expect(api.sentCommands, isEmpty);
      await _tap(tester, 'Queue reviewed command');
      expect(api.sentCommands.single['operation'], 'order.ship');
      expect(api.sentCommands.single['payload'], {
        'order_id': '19',
        'items': {'25': 2},
        'carrier': '',
        'tracking': 'TRACK-01',
      });
    },
  );

  testWidgets('Orders list the customer name instead of the id', (tester) async {
    await _show(tester, _scope(_MockCommerce(), _Pending(), 'editor'));
    await _tap(tester, 'Orders');
    expect(find.text('Asha Traders'), findsOneWidget);
  });

  testWidgets('Viewers can inspect reconciliation without action controls', (
    tester,
  ) async {
    final api = _MockCommerce();
    await _show(tester, _scope(api, _Pending(), 'viewer'));
    expect(find.text('Connect Bagisto'), findsNothing);
    expect(find.text('Verify bridge'), findsNothing);
    await _tap(tester, 'Reconciliation');
    expect(find.text('Reconcile now'), findsNothing);
    expect(
      find.text('1 stock differences · 1 financial differences'),
      findsOneWidget,
    );
    await _tap(tester, 'Review · 2026-04-03');
    expect(find.text('Product p-1'), findsOneWidget);
    expect(find.text('Invoice total'), findsOneWidget);
  });

  testWidgets(
    'Requires provider confirmation and links a payment to the source invoice',
    (tester) async {
      final api = _MockCommerce();
      await _show(tester, _scope(api, _Pending(), 'editor'));
      await _tap(tester, 'Payments');
      await _tap(tester, 'Record confirmed payment or refund');
      await _tap(tester, 'Store order');
      await _tap(tester, 'ORDER-19');
      await _tap(tester, 'Source invoice');
      await _tap(tester, 'inv-19 · ₹100.00');
      await _field(tester, 'Bank or provider reference', 'PROVIDER-047');
      await _field(tester, 'Confirmed amount (₹)', '40.25');
      await _tap(tester, 'Review evidence');
      expect(api.sentCommands, isEmpty);
      expect(
        find.text(
          'Confirm the provider movement and enter its exact reference.',
        ),
        findsOneWidget,
      );
      await _tap(tester, 'I confirmed the money was received');
      await _tap(tester, 'Review evidence');
      await _tap(tester, 'Queue reviewed evidence');
      expect(api.sentCommands.single['operation'], 'payment.capture');
      expect(api.sentCommands.single['payload'], {
        'source_id': 'PROVIDER-047',
        'confirmed': true,
        'data': {
          'order_id': '19',
          'date': businessDate(),
          'amount': '40.25',
          'allocations': [
            {'invoice_id': 'inv-19', 'amount': '40.25'},
          ],
        },
      });
    },
  );

  testWidgets(
    'Records a reviewed provider payout only when fees and refunds reconcile',
    (tester) async {
      final api = _MockCommerce();
      await _show(tester, _scope(api, _Pending(), 'editor'));
      await _tap(tester, 'Payments');
      await _tap(tester, 'Record gateway payout');
      await _tap(tester, 'Destination bank account');
      await _tap(tester, 'Settlement bank');
      await _tap(tester, 'cap-19 · ₹100.00');
      await _tap(tester, 'refund-19 · ₹20.00');
      await _field(tester, 'Provider fee excluding GST (₹)', '5.25');
      await _field(tester, 'Bank or provider reference', 'PAYOUT-019');
      await _field(tester, 'Bank deposit (₹)', '75.00');
      await _tap(tester, 'I confirmed the payout reached the receiving bank');
      await _tap(tester, 'Review evidence');
      expect(
        find.textContaining('must equal the bank deposit'),
        findsOneWidget,
      );
      expect(api.sentCommands, isEmpty);
      await _field(tester, 'Bank deposit (₹)', '74.75');
      await _tap(tester, 'I confirmed the payout reached the receiving bank');
      await _tap(tester, 'Review evidence');
      await _tap(tester, 'Queue reviewed evidence');
      expect(api.sentCommands.single['operation'], 'settlement.record');
      expect(api.sentCommands.single['payload'], {
        'source_id': 'PAYOUT-019',
        'confirmed': true,
        'data': {
          'date': businessDate(),
          'bank_account_id': 'settlement',
          'gross': '100.00',
          'net': '74.75',
          'fee': '5.25',
          'capture_ids': ['cap-19'],
          'refund_ids': ['refund-19'],
        },
      });
    },
  );

  testWidgets(
    'Records service advances and rechecks the remaining amount before a refund',
    (tester) async {
      final api = _MockCommerce();
      await _show(tester, _scope(api, _Pending(), 'editor'));
      await _tap(tester, 'Payments');
      await _tap(tester, 'Record customer advance');
      await _tap(tester, 'Store order');
      await _tap(tester, 'ORDER-19');
      await _tap(tester, 'Goods');
      await _tap(tester, 'Services');
      await _field(tester, 'Advance GST rate (%)', '18.00');
      await _field(tester, 'Bank or provider reference', 'ADVANCE-019');
      await _field(tester, 'Confirmed amount (₹)', '250.00');
      await _tap(tester, 'I confirmed the advance was received');
      await _tap(tester, 'Review evidence');
      await _tap(tester, 'Queue reviewed evidence');
      expect(api.sentCommands.single['payload']['data'], {
        'order_id': '19',
        'date': businessDate(),
        'amount': '250.00',
        'advance_supply': 'services',
        'advance_gst_rate': '18.00',
        'place_of_supply': '36',
      });

      await _tap(tester, 'Record advance refund');
      await _tap(tester, 'Store order');
      await _tap(tester, 'ORDER-19');
      await _tap(tester, 'Source advance');
      await _tap(tester, 'cap-19 · ₹100.00');
      await _field(tester, 'Bank or provider reference', 'ADVANCE-REFUND-019');
      await _field(tester, 'Confirmed amount (₹)', '45.00');
      await _tap(tester, 'I confirmed the advance was refunded');
      await _tap(tester, 'Review evidence');
      expect(
        find.text('The refund exceeds the remaining customer advance.'),
        findsOneWidget,
      );
      expect(api.sentCommands, hasLength(1));
      await _field(tester, 'Confirmed amount (₹)', '35.00');
      await _tap(tester, 'I confirmed the advance was refunded');
      await _tap(tester, 'Review evidence');
      await _tap(tester, 'Queue reviewed evidence');
      expect(api.sentCommands.last['operation'], 'payment.refund');
      expect(api.sentCommands.last['payload']['data'], {
        'order_id': '19',
        'date': businessDate(),
        'capture_id': 'cap-19',
        'amount': '35.00',
      });
    },
  );

  testWidgets('Records goods against a separately posted credit note', (
    tester,
  ) async {
    final api = _MockCommerce();
    await _show(tester, _scope(api, _Pending(), 'editor'));
    await _tap(tester, 'Payments');
    await _tap(tester, 'Record goods received');
    await _tap(tester, 'Store order');
    await _tap(tester, 'ORDER-19');
    await _tap(tester, 'Source credit note');
    await _tap(tester, 'cre-19 · ₹20.00');
    await _field(tester, 'Product 42 · Credited 2.5', '1.250');
    await _field(tester, 'Receiving reference', 'RECEIVING-019');
    await _tap(tester, 'I confirmed these goods were physically received');
    await _tap(tester, 'Review evidence');
    await _tap(tester, 'Queue reviewed evidence');
    expect(api.sentCommands.single['operation'], 'return.receive');
    expect(api.sentCommands.single['payload']['data'], {
      'order_id': '19',
      'date': businessDate(),
      'credit_id': 'cre-19',
      'lines': [
        {'product_id': '42', 'quantity': '1.250'},
      ],
    });
  });

  testWidgets('Phone width shows every Ecommerce section without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = _MockCommerce();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CommerceScreen(workspace: _scope(api, _Pending(), 'editor')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Ecommerce'), findsOneWidget);
    for (final section in [
      'Overview',
      'Catalogue',
      'Orders',
      'Payments',
      'Deliveries',
      'Reconciliation',
    ]) {
      await _tap(tester, section);
      expect(tester.takeException(), isNull, reason: section);
    }
  });
}
