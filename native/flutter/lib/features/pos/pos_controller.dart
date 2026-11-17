import 'dart:async';

import 'package:flutter/foundation.dart';

import 'pos_models.dart';

abstract interface class PosGateway {
  Future<List<PosProduct>> products();
  Future<Map<String, String>> stock();
  Future<List<PosBank>> banks();
  Future<PosQuote> quote(PosJson body, String date);
  Future<PosReceipt> post(PosPendingSale sale);
  Future<List<PosReceipt>> receipts(int offset);
  Future<PosPendingSale?> loadPending();
  Future<void> savePending(PosPendingSale sale);
  Future<void> clearPending(PosPendingSale sale);
}

/// Optional gateway capabilities the web POS also uses; fakes may omit them.
abstract interface class PosPartyGateway {
  Future<List<PosParty>> parties();
}

abstract interface class PosLocationGateway {
  /// Shelf id to name, from the company's inventory setup.
  Future<Map<String, String>> locations();
}

class PosFailure implements Exception {
  const PosFailure(
    this.message, {
    this.uncertain = true,
    this.requote = false,
    this.status,
  });

  final String message;
  final bool uncertain;
  final bool requote;
  final int? status;
}

class PosController extends ChangeNotifier {
  PosController({
    required this.gateway,
    required this.features,
    required this.canWrite,
    required this.regularTax,
    required this.stateCode,
    required this.businessDate,
    this.quoteDelay = const Duration(milliseconds: 220),
    this.unregistered = false,
    PosHeldStore? heldStore,
  }) : placeOfSupply = stateCode,
       held = heldStore ?? PosHeldStore();

  final PosGateway gateway;
  final Set<String> features;
  final bool canWrite;
  final bool regularTax;
  final String stateCode;
  final String Function() businessDate;
  final Duration quoteDelay;
  final bool unregistered;
  final PosHeldStore held;

  final List<PosLine> cart = [];
  List<PosProduct> products = [];
  List<PosBank> banks = [];
  List<PosReceipt> receipts = [];
  Map<String, String> stock = {};
  List<PosParty> parties = [];
  Map<String, String> locationNames = {};

  PosQuote? quote;
  PosPendingSale? pending;
  PosReceipt? completed;
  PosTender tender = PosTender.cash;
  String cashText = '';
  String bankText = '';
  String bankId = '';
  String customer = '';
  String billingAddress = '';
  String billingGstin = '';
  String billingPhone = '';
  String placeOfSupply;
  bool bankConfirmed = false;
  bool inclusive = false;
  bool round = false;

  bool checkingPending = true;
  bool pendingAvailable = false;
  bool loadingProducts = false;
  bool loadingStock = false;
  bool loadingReceipts = false;
  bool hasMoreReceipts = true;
  bool quoting = false;
  bool posting = false;
  String? status;
  String? recoveryError;
  String? productsError;
  String? stockError;
  String? bankError;
  String? receiptsError;
  String? quoteError;

  bool _disposed = false;
  int _revision = 0;
  int _stockRevision = 0;
  Timer? _quoteTimer;

  bool get strictStock => features.contains('pos_require_available_stock');
  bool get stockSummary => features.contains('pos_stock_summary');
  bool get splitSupported => features.contains('pos_split_tender');
  bool get registerSupported => features.contains('pos_register_sessions');
  bool get editable =>
      canWrite && pendingAvailable && pending == null && !posting;

  PosPayment get payment =>
      PosPayment.evaluate(quote?.paise ?? 0, tender, cashText, bankText);
  bool get needsBank => tender != PosTender.cash;

  /// The server needs a two-digit state code unless the company is unregistered.
  bool get billingValid =>
      unregistered || RegExp(r'^[0-9]{2}$').hasMatch(placeOfSupply);

  bool get ready =>
      canWrite &&
      pendingAvailable &&
      !posting &&
      (pending != null ||
          (quote != null &&
              billingValid &&
              payment.valid &&
              (!needsBank || (bankId.isNotEmpty && bankConfirmed))));

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  String _message(Object problem, String fallback) =>
      problem is PosFailure ? problem.message : fallback;

  Future<void> initialize() => Future.wait([
    recoverPending(),
    loadProducts(),
    loadStock(),
    loadBanks(),
    loadCounterSetup(),
  ]);

  /// Customer suggestions and shelf names. Both are conveniences, so a
  /// failure leaves them empty instead of blocking the counter.
  Future<void> loadCounterSetup() async {
    final source = gateway;
    try {
      if (source is PosLocationGateway) {
        locationNames = await (source as PosLocationGateway).locations();
        _emit();
      }
    } catch (_) {
      locationNames = {};
    }
    try {
      if (source is PosPartyGateway && canWrite) {
        parties = await (source as PosPartyGateway).parties();
        _emit();
      }
    } catch (_) {
      parties = [];
    }
  }

  Future<void> recoverPending() async {
    checkingPending = true;
    recoveryError = null;
    _emit();
    try {
      pending = await gateway.loadPending();
      pendingAvailable = true;
      if (pending != null) {
        status = 'A sale is awaiting confirmation. Retry the original sale before taking another payment.';
      }
    } catch (_) {
      pendingAvailable = false;
      recoveryError = 'Saved checkout state is unavailable. Retry recovery before posting a sale.';
    } finally {
      checkingPending = false;
      _emit();
    }
  }

  Future<void> loadProducts() async {
    if (loadingProducts) return;
    loadingProducts = true;
    productsError = null;
    _emit();
    try {
      products = await gateway.products();
    } catch (error) {
      productsError = _message(error, 'Could not load products.');
    } finally {
      loadingProducts = false;
      _emit();
    }
  }

  Future<void> loadStock() async {
    if (!stockSummary) return;
    final revision = ++_stockRevision;
    loadingStock = true;
    stockError = null;
    _emit();
    try {
      final next = await gateway.stock();
      if (revision == _stockRevision) stock = next;
    } catch (error) {
      if (revision == _stockRevision) {
        stock = {};
        stockError = _message(error, 'Book stock is unavailable.');
      }
    } finally {
      if (revision == _stockRevision) {
        loadingStock = false;
        _emit();
      }
    }
  }

  Future<void> loadBanks() async {
    if (!canWrite) return;
    bankError = null;
    try {
      banks = await gateway.banks();
      if (!banks.any((bank) => bank.id == bankId)) {
        bankId = banks.isEmpty ? '' : banks.first.id;
        bankConfirmed = false;
      }
    } catch (error) {
      bankError = _message(error, 'Could not load bank accounts.');
    }
    _emit();
  }

  Future<void> loadReceipts({bool reset = false}) async {
    if (loadingReceipts || (!reset && !hasMoreReceipts)) return;
    final offset = reset ? 0 : receipts.length;
    loadingReceipts = true;
    receiptsError = null;
    _emit();
    try {
      final next = await gateway.receipts(offset);
      receipts = reset ? next : [...receipts, ...next];
      hasMoreReceipts = next.length == 50;
    } catch (error) {
      receiptsError = _message(error, 'Could not load receipts.');
    } finally {
      loadingReceipts = false;
      _emit();
    }
  }

  bool scan(String value) {
    if (!editable) return false;
    final code = value.trim();
    if (code.isEmpty) return false;
    var matches = products.where((product) => product.barcode == code).toList();
    if (matches.isEmpty) {
      matches = products
          .where(
            (product) => product.name.trim().toLowerCase() == code.toLowerCase(),
          )
          .toList();
    }
    if (matches.length == 1) {
      add(matches.single);
      return true;
    }
    status = matches.isEmpty
        ? 'No exact barcode or name match. Select a product below.'
        : 'Multiple products match. Select the correct product below.';
    _emit();
    return false;
  }

  void add(PosProduct product) {
    if (!editable) return;
    final index = cart.indexWhere((line) => line.product.id == product.id);
    if (index < 0) {
      if (cart.isEmpty) completed = null;
      cart.add(PosLine(product));
    } else {
      final line = cart[index];
      final milli = line.quantityMilli;
      if (milli == null) {
        status =
            'Correct the quantity for ${product.name} before adding another unit.';
        _emit();
        return;
      }
      if (milli > 999999999998999) {
        status = 'The quantity for ${product.name} has reached its limit.';
        _emit();
        return;
      }
      line.quantity = posDecimalText(
        milli + 1000,
        3,
      ).replaceFirst(RegExp(r'\.?0+$'), '');
    }
    _reviseQuote();
  }

  void remove(PosLine line) {
    if (!editable) return;
    cart.remove(line);
    _reviseQuote();
  }

  void changeLine(
    PosLine line, {
    String? quantity,
    String? rate,
    String? discount,
  }) {
    if (!editable) return;
    if (quantity != null) line.quantity = quantity;
    if (rate != null) line.rate = rate;
    if (discount != null) line.discount = discount;
    _reviseQuote();
  }

  void changeBilling({
    String? customer,
    bool? inclusive,
    bool? round,
    String? address,
    String? gstin,
    String? phone,
    String? place,
  }) {
    if (!editable) return;
    if (customer != null) {
      this.customer = customer;
      // Typing an existing customer's exact name fills their billing details,
      // and any other name clears them (as the web POS does).
      final name = customer.trim().toLowerCase();
      final party = parties
          .where((row) => row.name.toLowerCase() == name)
          .firstOrNull;
      billingAddress = party?.address ?? '';
      billingGstin = party?.gstin ?? '';
      billingPhone = party?.phone ?? '';
      placeOfSupply = billingGstin.length >= 2
          ? billingGstin.substring(0, 2)
          : stateCode;
    }
    if (address != null) billingAddress = address;
    if (gstin != null) billingGstin = gstin.toUpperCase();
    if (phone != null) billingPhone = phone;
    if (place != null) placeOfSupply = place;
    if (inclusive != null) this.inclusive = inclusive;
    if (round != null) this.round = round;
    _reviseQuote();
  }

  void changePayment({
    PosTender? method,
    String? cashText,
    String? bankText,
    String? bankId,
    bool? confirmed,
  }) {
    if (!editable) return;
    if (method != null && method != tender) {
      tender = method;
      this.cashText = '';
      this.bankText = '';
      bankConfirmed = false;
    }
    if (cashText != null) this.cashText = cashText;
    if (bankText != null) {
      this.bankText = bankText;
      bankConfirmed = false;
    }
    if (bankId != null) {
      this.bankId = bankId;
      bankConfirmed = false;
    }
    if (confirmed != null) bankConfirmed = confirmed;
    _emit();
  }

  PosJson _body(String date) => {
    'kind': 'pos',
    'name': customer.trim().isEmpty ? 'Walk-in customer' : customer.trim(),
    'date': date,
    'data': <String, dynamic>{
      'lines': [
        for (final line in cart)
          line.toJson(regularTax: regularTax, inclusive: inclusive),
      ],
      'place_of_supply': placeOfSupply,
      if (billingAddress.trim().isNotEmpty)
        'party_address': billingAddress.trim(),
      if (billingGstin.trim().isNotEmpty) 'party_gstin': billingGstin.trim(),
      if (billingPhone.trim().isNotEmpty) 'party_phone': billingPhone.trim(),
      'round_total': round,
      if (strictStock) 'require_available_stock': true,
    },
  };

  PosJson _paymentBody(PosQuote current) {
    final body = _body(current.date);
    final data = posObject(body['data']);
    final amounts = payment;
    data['payment_account'] = tender.name;
    data['expected_total'] = current.amount;
    if (registerSupported &&
        current.data.containsKey('pos_register_session_id')) {
      data['expected_register_session'] =
          current.data['pos_register_session_id'];
    }
    if (needsBank) data['bank_account_id'] = bankId;
    if (tender == PosTender.split) {
      data['bank_amount'] = posDecimalText(amounts.bank, 2);
    }
    if (tender != PosTender.bank) {
      data['tender_amount'] = posDecimalText(amounts.tendered, 2);
    }
    return body;
  }

  void _reviseQuote({bool immediate = false, bool keepStatus = false}) {
    final revision = ++_revision;
    _quoteTimer?.cancel();
    quote = null;
    quoteError = null;
    bankConfirmed = false;
    if (!keepStatus) status = null;
    quoting = cart.isNotEmpty && editable;
    _emit();
    if (!quoting) return;
    if (cart.any((line) => !line.valid)) {
      quoteError =
          'Enter a valid quantity, unit price and discount for each line.';
      quoting = false;
      _emit();
      return;
    }
    if (!strictStock && cart.any((line) => line.product.tracked)) {
      quoteError = 'This server cannot verify stock safely. Ask an owner to update Apex Books before selling tracked items.';
      quoting = false;
      _emit();
      return;
    }
    final date = businessDate();
    final body = _body(date);
    _quoteTimer = Timer(immediate ? Duration.zero : quoteDelay, () async {
      try {
        final result = await gateway.quote(body, date);
        if (_disposed || revision != _revision) return;
        if (registerSupported &&
            !result.data.containsKey('pos_register_session_id')) {
          throw const PosFailure(
            'The server did not confirm the register state.',
          );
        }
        quote = result;
      } catch (error) {
        if (_disposed || revision != _revision) return;
        quoteError = _message(error, 'Could not confirm the total. Try again.');
      } finally {
        if (!_disposed && revision == _revision) {
          quoting = false;
          _emit();
        }
      }
    });
  }

  void refreshQuote() => _reviseQuote(immediate: true);

  // ---- Held sales, clear sale and dismissing the receipt banner ----

  bool get canHold =>
      editable && cart.isNotEmpty && held.sales.length < PosHeldStore.limit;

  void _resetSale() {
    cart.clear();
    cashText = bankText = '';
    bankConfirmed = false;
    customer = '';
    billingAddress = billingGstin = billingPhone = '';
    placeOfSupply = stateCode;
    tender = PosTender.cash;
    inclusive = round = false;
    _reviseQuote();
  }

  void clearSale() {
    if (!editable) return;
    _resetSale();
  }

  void holdSale() {
    if (!canHold) return;
    held.sales.add(
      PosHeldSale(
        lines: [for (final line in cart) line.copy()],
        customer: customer,
        address: billingAddress,
        gstin: billingGstin,
        phone: billingPhone,
        place: placeOfSupply,
        tender: tender,
        bankId: bankId,
        inclusive: inclusive,
        round: round,
      ),
    );
    _resetSale();
  }

  void recallSale(PosHeldSale saved) {
    if (!editable || cart.isNotEmpty || !held.sales.remove(saved)) return;
    completed = null;
    cart.addAll(saved.lines);
    customer = saved.customer;
    billingAddress = saved.address;
    billingGstin = saved.gstin;
    billingPhone = saved.phone;
    placeOfSupply = saved.place;
    tender = saved.tender;
    if (banks.any((bank) => bank.id == saved.bankId)) bankId = saved.bankId;
    inclusive = saved.inclusive;
    round = saved.round;
    cashText = bankText = '';
    _reviseQuote();
  }

  void discardHeld(PosHeldSale saved) {
    if (!editable) return;
    held.sales.remove(saved);
    _emit();
  }

  void dismissCompleted() {
    completed = null;
    _emit();
  }

  Future<void> submit() async {
    if (!ready) return;
    final current = quote;
    if (pending == null && current?.date != businessDate()) {
      status = 'The business date changed. Review the updated sale total.';
      _reviseQuote(immediate: true, keepStatus: true);
      return;
    }
    final existing = pending;
    final sale = existing ?? PosPendingSale.create(_paymentBody(current!));
    posting = true;
    status = null;
    _emit();
    var requote = false;
    try {
      if (existing == null) {
        try {
          await gateway.savePending(sale);
        } catch (_) {
          // The persistence attempt may have completed before returning an error.
          pendingAvailable = false;
          recoveryError = 'The retry key could not be saved. Check saved checkout state before proceeding.';
          return;
        }
        pending = sale;
      }
      final result = await gateway.post(sale);
      completed = result;
      if (!await _clear(sale)) return;
      cart.clear();
      quote = null;
      customer = cashText = bankText = '';
      billingAddress = billingGstin = billingPhone = '';
      placeOfSupply = stateCode;
      tender = PosTender.cash;
      bankConfirmed = false;
      inclusive = round = false;
      unawaited(loadStock());
      if (receipts.isNotEmpty) unawaited(loadReceipts(reset: true));
    } catch (error) {
      if (error is PosFailure && !error.uncertain) {
        if (!await _clear(sale)) return;
        status = error.message;
        requote = error.requote;
      } else {
        status = 'Sale confirmation was interrupted. Retry the original sale before taking another payment.';
      }
    } finally {
      posting = false;
      if (requote) {
        _reviseQuote(immediate: true, keepStatus: true);
        unawaited(loadStock());
      }
      _emit();
    }
  }

  Future<bool> _clear(PosPendingSale sale) async {
    try {
      await gateway.clearPending(sale);
      pending = null;
      return true;
    } catch (_) {
      status = 'Could not clear the saved checkout. Retry the original sale to finish recovery.';
      return false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _quoteTimer?.cancel();
    super.dispose();
  }
}
