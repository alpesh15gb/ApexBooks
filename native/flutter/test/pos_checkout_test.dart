import 'dart:async';

import 'package:apex_books/features/pos/pos_controller.dart';
import 'package:apex_books/features/pos/pos_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('hold, resume, discard and clear keep sales apart and in memory', () async {
    final controller = _counter(_CounterApi());
    addTearDown(controller.dispose);
    await controller.initialize();
    controller.changeBilling(customer: 'Asha');
    controller.scan('00123');
    await _tick();
    expect(controller.canHold, isTrue);
    controller.holdSale();
    expect(controller.cart, isEmpty);
    expect(controller.customer, isEmpty);
    expect(controller.held.sales, hasLength(1));

    controller.scan('00123');
    await _tick();
    controller.recallSale(controller.held.sales.single);
    expect(controller.held.sales, hasLength(1), reason: 'cart is not empty');
    controller.clearSale();
    expect(controller.cart, isEmpty);

    final saved = controller.held.sales.single;
    controller.recallSale(saved);
    expect(controller.held.sales, isEmpty);
    expect(controller.customer, 'Asha');
    expect(controller.cart.single.product.barcode, '00123');
    controller.holdSale();
    controller.discardHeld(controller.held.sales.single);
    expect(controller.held.sales, isEmpty);
  });

  test('billing details travel in the sale body only when entered', () async {
    final api = _CounterApi();
    final controller = _counter(api);
    addTearDown(controller.dispose);
    await controller.initialize();
    controller.scan('00123');
    await _tick();
    controller.changeBilling(
      address: '12 Mill Road',
      gstin: '27abcde1234f1z5',
      phone: '98200',
      place: '27',
    );
    controller.changePayment(cashText: '125');
    await _tick();
    await controller.submit();
    final data = api.posted.single.body['data'] as Map<String, dynamic>;
    expect(data['party_address'], '12 Mill Road');
    expect(data['party_gstin'], '27ABCDE1234F1Z5');
    expect(data['party_phone'], '98200');
    expect(data['place_of_supply'], '27');
  });

  test('empty cash tendered means the exact amount', () {
    final payment = PosPayment.evaluate(12500, PosTender.cash, '', '');
    expect(payment.valid, isTrue);
    expect(payment.change, 0);
  });

  test('barcode is exact and monetary calculations use paise', () async {
    final api = _CounterApi();
    final controller = _counter(api);
    addTearDown(controller.dispose);
    await controller.initialize();

    expect(controller.scan('123'), false);
    expect(controller.scan('00123\r\n'), true);
    expect(controller.cart.single.product.barcode, '00123');
    await _tick();
    expect(controller.quote?.paise, 12500);

    controller.changePayment(cashText: '124.99');
    expect(controller.ready, false);
    expect(controller.payment.error, 'Cash still due ₹0.01');
    controller.changePayment(cashText: '200.00');
    expect(controller.payment.change, 7500);
    await controller.submit();

    expect(controller.cart, isEmpty);
    expect(controller.completed?.number, 'POS/26-27/0001');
    expect(api.calls, ['persist', 'post', 'clear']);
    expect(
      api.posted.single.body['data'],
      containsPair('expected_total', '125.00'),
    );
    expect(
      api.posted.single.body['data'],
      containsPair('require_available_stock', true),
    );
    expect(
      api.posted.single.body['data'],
      containsPair('expected_register_session', null),
    );
  });

  test(
    'an older quote never re-enables checkout after a cart change',
    () async {
      final api = _CounterApi()..deferQuotes = true;
      final controller = _counter(api);
      addTearDown(controller.dispose);
      await controller.initialize();
      controller.scan('00123');
      await _tick();
      controller.scan('00123');
      await _tick();
      expect(api.quoteResponses, hasLength(2));
      api.quoteResponses.first.complete(_quote('125.00'));
      await _tick();
      expect(controller.quote, isNull);
      expect(controller.ready, false);
      api.quoteResponses.last.complete(_quote('250.00'));
      await _tick();
      expect(controller.quote?.paise, 25000);
    },
  );

  test(
    'a late checkout receipt uses the same key, body and register',
    () async {
      final api = _CounterApi()..loseFirstResponse = true;
      final first = _counter(api);
      await first.initialize();
      first.scan('00123');
      await _tick();
      first.changePayment(method: PosTender.split);
      first.changePayment(bankText: '40', cashText: '100');
      expect(first.ready, false);
      first.changePayment(confirmed: true);
      expect(first.ready, true);
      final change = first.payment.change;
      await first.submit();
      expect(change, 1500);
      expect(first.pending, isNotNull);
      expect(first.editable, false);
      first.changeLine(first.cart.single, quantity: '100');
      expect(first.cart.single.quantity, '1');
      first.dispose();

      final restarted = _counter(api);
      addTearDown(restarted.dispose);
      await restarted.initialize();
      expect(restarted.ready, true);
      expect(restarted.pending?.payload, api.posted.single.payload);
      await restarted.submit();
      expect(api.posted.map((sale) => sale.key).toSet(), hasLength(1));
      expect(api.posted.map((sale) => sale.payload).toSet(), hasLength(1));
      expect(
        api.posted.first.body['data'],
        containsPair('bank_amount', '40.00'),
      );
      expect(api.calls, ['persist', 'post', 'post', 'clear']);
      expect(restarted.completed?.number, 'POS/26-27/0001');
      expect(api.saved, isNull);
    },
  );

  test('a stock or total rejection requires a fresh quote', () async {
    final api = _CounterApi()..requireRequote = true;
    final controller = _counter(api);
    addTearDown(controller.dispose);
    await controller.initialize();
    controller.scan('00123');
    await _tick();
    controller.changePayment(method: PosTender.bank);
    controller.changePayment(confirmed: true);
    await controller.submit();
    await _tick();
    expect(controller.pending, isNull);
    expect(controller.bankConfirmed, false);
    expect(controller.quote?.paise, 13000);
    expect(controller.ready, false);
    expect(controller.status, 'Checkout total changed.');
  });

  test('no sale is sent when secure retry state cannot be saved', () async {
    final api = _CounterApi()..failPersistence = true;
    final controller = _counter(api);
    addTearDown(controller.dispose);
    await controller.initialize();
    controller.scan('00123');
    await _tick();
    controller.changePayment(cashText: '125');
    await controller.submit();
    expect(api.posted, isEmpty);
    expect(controller.ready, false);
    expect(controller.recoveryError, contains('could not be saved'));
  });
}

Future<void> _tick() => Future<void>.delayed(const Duration(milliseconds: 10));

PosController _counter(_CounterApi api) => PosController(
  gateway: api,
  features: const {
    'pos_require_available_stock',
    'pos_stock_summary',
    'pos_split_tender',
    'pos_register_sessions',
  },
  canWrite: true,
  regularTax: false,
  stateCode: '27',
  businessDate: () => '2026-11-16',
  quoteDelay: Duration.zero,
);

PosQuote _quote(String amount) => PosQuote.fromJson({
  'amount': amount,
  'data': {'pos_register_session_id': null},
}, '2026-11-16');

class _CounterApi implements PosGateway {
  final posted = <PosPendingSale>[];
  final calls = <String>[];
  final quoteResponses = <Completer<PosQuote>>[];
  PosPendingSale? saved;
  bool deferQuotes = false;
  bool loseFirstResponse = false;
  bool requireRequote = false;
  bool failPersistence = false;

  @override
  Future<List<PosBank>> banks() async => [
    PosBank.fromJson({'id': 'settlement', 'name': 'Synthetic bank'}),
  ];

  @override
  Future<void> clearPending(PosPendingSale sale) async {
    calls.add('clear');
    saved = null;
  }

  @override
  Future<PosPendingSale?> loadPending() async => saved;

  @override
  Future<PosReceipt> post(PosPendingSale sale) async {
    calls.add('post');
    posted.add(sale);
    if (requireRequote) {
      throw const PosFailure(
        'Checkout total changed.',
        uncertain: false,
        requote: true,
      );
    }
    if (loseFirstResponse && posted.length == 1) {
      throw const PosFailure('Connection interrupted');
    }
    return PosReceipt.fromJson({
      'id': 'sale',
      'kind': 'pos',
      'number': 'POS/26-27/0001',
      'amount': '125.00',
      'posted': true,
      'data': <String, dynamic>{},
    });
  }

  @override
  Future<List<PosProduct>> products() async => [
    PosProduct.fromJson({
      'id': 'oats',
      'name': 'Store oats',
      'data': {'barcode': '00123', 'sale_rate': '125.00', 'track_stock': true},
    }),
  ];

  @override
  Future<PosQuote> quote(PosJson body, String date) {
    if (deferQuotes) {
      final response = Completer<PosQuote>();
      quoteResponses.add(response);
      return response.future;
    }
    return Future.value(
      _quote(requireRequote && posted.isNotEmpty ? '130.00' : '125.00'),
    );
  }

  @override
  Future<List<PosReceipt>> receipts(int offset) async => [];

  @override
  Future<void> savePending(PosPendingSale sale) async {
    calls.add('persist');
    if (failPersistence) throw StateError('Storage unavailable');
    saved = PosPendingSale.fromJson(sale.toJson());
  }

  @override
  Future<Map<String, String>> stock() async => {'oats': '2'};
}
