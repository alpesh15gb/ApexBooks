import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/pos/pos_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

void main() {
  testWidgets(
    'Android camera denial returns to typing and detections add a barcode once',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 860);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final pending = _TestPending();
      final api = _TestApi(pending);
      var deny = true;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PosScreen(
              workspace: WorkspaceContext(
                api: api,
                company: const ApexCompany(
                  id: 'front',
                  name: 'Camera test',
                  role: 'owner',
                  stateCode: '27',
                  taxMode: 'unregistered',
                ),
                pending: pending,
                features: const {'pos_require_available_stock'},
                refresh: () async {},
              ),
              cameraPreview: (context, onDetect, onError) {
                if (deny) {
                  return onError(
                    context,
                    const MobileScannerException(
                      errorCode: MobileScannerErrorCode.permissionDenied,
                    ),
                  );
                }
                return Column(
                  children: [
                    TextButton(
                      onPressed: () => onDetect(
                        const BarcodeCapture(
                          barcodes: [
                            Barcode(rawValue: '000472'),
                            Barcode(rawValue: '9999'),
                          ],
                        ),
                      ),
                      child: const Text('Detect more than one code'),
                    ),
                    TextButton(
                      onPressed: () {
                        const frame = BarcodeCapture(
                          barcodes: [Barcode(rawValue: '000472')],
                        );
                        onDetect(frame);
                        onDetect(frame);
                      },
                      child: const Text('Detect the leading-zero barcode'),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final launch = find.text('Scan with camera');
      await tester.tap(launch);
      await tester.pumpAndSettle();
      expect(find.textContaining('Camera access was denied'), findsOneWidget);
      expect(find.byKey(const ValueKey('pos-barcode')), findsOneWidget);
      await tester.tap(find.text('Use barcode field'));
      await tester.pumpAndSettle();
      final scanner = find.byKey(const ValueKey('pos-barcode'));
      expect(tester.widget<TextField>(scanner).focusNode!.hasFocus, isTrue);
      expect(find.text('Camera scanner'), findsNothing);
      await tester.enterText(scanner, '00472');
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(scanner).controller!.text, '00472');

      deny = false;
      await tester.tap(launch);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Detect more than one code'));
      await tester.pumpAndSettle();
      expect(find.text('Aim the camera at one barcode.'), findsOneWidget);
      expect(api.quoteCalls, 0);
      await tester.tap(find.text('Detect the leading-zero barcode'));
      await tester.pump(const Duration(milliseconds: 240));
      await tester.pumpAndSettle();

      expect(find.text('Camera scanner'), findsNothing);
      expect(tester.widget<TextField>(scanner).controller!.text, isEmpty);
      final quantity = find.widgetWithText(TextField, 'Qty');
      expect(tester.widget<TextField>(quantity).controller!.text, '1');
      expect(api.quoteCalls, 1);
      expect(api.sales, 0);
      expect(tester.takeException(), isNull);
    },
    variant: const TargetPlatformVariant({TargetPlatform.android}),
  );

  testWidgets(
    'narrow checkout scans a leading zero and posts the confirmed cash sale',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 860);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final pending = _TestPending();
      final api = _TestApi(pending);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PosScreen(
              workspace: WorkspaceContext(
                api: api,
                company: const ApexCompany(
                  id: 'front',
                  name: 'Counter test',
                  role: 'owner',
                  stateCode: '27',
                  taxMode: 'unregistered',
                ),
                pending: pending,
                features: const {
                  'pos_require_available_stock',
                  'pos_stock_summary',
                  'pos_register_sessions',
                },
                refresh: () async {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Book stock: 2'), findsOneWidget);
      expect(find.text('000472'), findsOneWidget);
      final scanner = find.byKey(const ValueKey('pos-barcode'));
      await tester.enterText(scanner, '000472');
      await tester.testTextInput.receiveAction(TextInputAction.go);
      await tester.pump(const Duration(milliseconds: 240));
      await tester.pumpAndSettle();
      expect(find.text('₹125.00'), findsWidgets);
      expect(api.quoteCalls, 1);

      final cash = find.descendant(
        of: find.byKey(const ValueKey('pos-cash')),
        matching: find.byType(TextField),
      );
      final paymentShortcut = find.byKey(const ValueKey('pos-go-to-payment'));
      expect(tester.getRect(paymentShortcut).bottom, lessThan(860));
      await tester.tap(paymentShortcut);
      await tester.pumpAndSettle();
      expect(tester.getRect(cash).top, greaterThanOrEqualTo(0));
      expect(tester.getRect(cash).bottom, lessThan(860));
      expect(paymentShortcut, findsNothing);
      await tester.enterText(cash, '200');
      await tester.pumpAndSettle();
      expect(find.text('Change ₹75.00'), findsOneWidget);
      final button = find.byKey(const ValueKey('pos-complete-sale'));
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      await tester.tap(button);
      await tester.pumpAndSettle();

      expect(api.sales, 1);
      expect(pending.value, isNull);
      expect(find.text('Sale completed'), findsOneWidget);
      expect(tester.getRect(find.text('Sale completed')).bottom, lessThan(860));
      expect(find.text('Change ₹75.00'), findsOneWidget);
      expect(find.text('Book stock: 1'), findsOneWidget);

      final receipts = find.text('Receipts');
      await tester.ensureVisible(receipts);
      await tester.pumpAndSettle();
      await tester.tap(receipts);
      await tester.pumpAndSettle();
      final search = find.widgetWithText(TextField, 'Search loaded receipts');
      await tester.enterText(search, 'missing');
      await tester.pumpAndSettle();
      expect(find.text('No receipts match this search.'), findsOneWidget);
      await tester.enterText(search, '0001');
      await tester.pumpAndSettle();
      await tester.tap(find.text('POS/26-27/0001'));
      await tester.pumpAndSettle();
      expect(api.receiptReads, 1);
      expect(find.text('Posted'), findsOneWidget);
      expect(find.text('1 × Counter oats'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('wide checkout keeps stock, cart and tender side by side', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1150, 900);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final pending = _TestPending();
    final api = _TestApi(pending);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PosScreen(
            workspace: WorkspaceContext(
              api: api,
              company: const ApexCompany(
                id: 'front',
                name: 'Counter test',
                role: 'owner',
                stateCode: '27',
                taxMode: 'unregistered',
              ),
              pending: pending,
              features: const {
                'pos_require_available_stock',
                'pos_stock_summary',
                'pos_split_tender',
              },
              refresh: () async {},
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    const productKey = ValueKey('product-oats');
    final product = find.byKey(productKey);
    final source = find.descendant(of: product, matching: find.text('000472'));
    final addProduct = find.descendant(
      of: product,
      matching: find.byIcon(Icons.add),
    );
    final sale = find.text('Current sale');
    expect(tester.getRect(source).right, lessThan(tester.getRect(sale).left));
    expect(
      tester.getRect(product).right - tester.getRect(addProduct).right,
      lessThan(20),
    );
    expect(find.byKey(const ValueKey('pos-go-to-payment')), findsNothing);
    await tester.tap(product);
    await tester.pump(const Duration(milliseconds: 240));
    await tester.pumpAndSettle();

    final quantity = find.widgetWithText(TextField, 'Qty');
    final plus = find.byWidgetPredicate(
      (widget) =>
          widget is IconButton &&
          widget.tooltip == 'Increase quantity for Counter oats',
    );
    final minus = find.byWidgetPredicate(
      (widget) =>
          widget is IconButton &&
          widget.tooltip == 'Decrease quantity for Counter oats',
    );
    expect(tester.widget<TextField>(quantity).controller!.text, '1');
    expect(tester.widget<IconButton>(minus).onPressed, isNull);
    await tester.tap(plus);
    await tester.pump(const Duration(milliseconds: 240));
    expect(tester.widget<TextField>(quantity).controller!.text, '2');
    await tester.tap(minus);
    await tester.pump(const Duration(milliseconds: 240));
    expect(tester.widget<TextField>(quantity).controller!.text, '1');
    await tester.enterText(quantity, '1.5');

    await tester.tap(find.text('Price and discount'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Rate (₹)'), '100');
    await tester.enterText(
      find.widgetWithText(TextField, 'Discount amount (₹)'),
      '10',
    );
    await tester.pump(const Duration(milliseconds: 240));
    await tester.pumpAndSettle();
    expect(
      tester.widget<Text>(find.byKey(const ValueKey('pos-total'))).data,
      '₹140.00',
    );
    expect(
      tester.getRect(find.byKey(const ValueKey('pos-complete-sale'))).right -
          tester.getRect(find.byKey(const ValueKey('pos-total'))).right,
      lessThan(20),
    );

    await tester.tap(find.text('Cash'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cash + bank / UPI / card').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Bank / UPI / card amount (₹)'),
      '60',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Cash tendered (₹)'),
      '100',
    );
    await tester.pumpAndSettle();
    expect(find.text('Cash share ₹80.00 · Change ₹20.00'), findsOneWidget);
    final complete = find.byKey(const ValueKey('pos-complete-sale'));
    final cash = find.widgetWithText(TextField, 'Cash tendered (₹)');
    await tester.tap(find.text('Bank, UPI or card payment received'));
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(complete).onPressed, isNotNull);
    await tester.tap(cash);
    tester.view.physicalSize = const Size(390, 860);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('pos-go-to-payment')), findsOneWidget);
    expect(tester.widget<TextField>(quantity).controller!.text, '1.5');
    expect(tester.widget<TextField>(cash).controller!.text, '100');
    expect(tester.widget<FilledButton>(complete).onPressed, isNotNull);
    expect(find.text('Cash share ₹80.00 · Change ₹20.00'), findsOneWidget);
    tester.view.physicalSize = const Size(1150, 900);
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(cash).controller!.text, '100');
    expect(tester.widget<FilledButton>(complete).onPressed, isNotNull);
    expect(api.sales, 0);
    expect(tester.takeException(), isNull);
  });
}

class _TestPending implements PendingStore {
  Json? value;

  @override
  Future<void> clear(String operation) async => value = null;

  @override
  Future<Json?> load(String operation) async => value;

  @override
  Future<void> save(String operation, Json data) async => value = data;
}

class _TestApi implements ApexApi {
  _TestApi(this.pending);
  final _TestPending pending;
  int sales = 0;
  int quoteCalls = 0;
  int receiptReads = 0;

  Json _receipt({bool detail = false}) => {
    'kind': 'pos',
    'id': 'sale',
    'number': 'POS/26-27/0001',
    'name': 'Walk-in customer',
    'date': '2026-11-16',
    'amount': '125.00',
    'posted': true,
    'data': {
      'payment_account': 'cash',
      'change_amount': '75.00',
      if (detail)
        'lines': [
          {'quantity': '1', 'description': 'Counter oats'},
        ],
    },
  };

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    switch (path) {
      case '/api/companies/front/records':
        if (query?['kind'] == 'pos') return [_receipt()];
        expect(query?['kind'], 'item');
        return [
          {
            'id': 'oats',
            'name': 'Counter oats',
            'kind': 'item',
            'data': {
              'barcode': '000472',
              'sale_rate': '125.00',
              'track_stock': true,
              'unit': 'box',
            },
          },
        ];
      case '/api/companies/front/pos/stock':
        return {
          'rows': [
            {'item_id': 'oats', 'closing_quantity': '${2 - sales}'},
          ],
        };
      case '/api/companies/front/bank-accounts':
        return [
          {'id': 'default', 'name': 'Bank clearing'},
        ];
      case '/api/companies/front/records/sale':
        receiptReads++;
        return _receipt(detail: true);
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
    final data = body['data'] as Json;
    expect(data['require_available_stock'], true);
    if (path.endsWith('/documents/preview')) {
      quoteCalls++;
      final lines = data['lines'] as List;
      final line = lines.single as Json;
      expect(line['item_id'], 'oats');
      final amount =
          (double.parse(line['quantity'] as String) *
                      double.parse(line['rate'] as String) -
                  double.parse((line['discount_amount'] ?? '0') as String))
              .toStringAsFixed(2);
      return {
        'amount': amount,
        'data': {'taxable': amount, 'pos_register_session_id': null},
      };
    }
    expect(path, '/api/companies/front/records');
    expect(pending.value?['key'], idempotencyKey);
    expect(data['expected_register_session'], isNull);
    expect(data.containsKey('expected_register_session'), true);
    expect(data['expected_total'], '125.00');
    expect(data['tender_amount'], '200.00');
    sales++;
    return _receipt();
  }
}
