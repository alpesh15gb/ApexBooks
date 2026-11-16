import 'dart:async';

import 'package:flutter/foundation.dart';

import 'pos_controller.dart';
import 'pos_models.dart';
import 'pos_return_models.dart';

abstract interface class PosReturnGateway {
  Future<PosReceipt> receipt(String id);
  Future<PosQuote> previewReturn(String receiptId, PosJson body, String date);
  Future<PosReturnResult> postReturn(PosReturnCommand command);
  Future<PosReturnCommand?> loadReturnPending();
  Future<void> saveReturnPending(PosReturnCommand command);
  Future<void> clearReturnPending(PosReturnCommand command);
}

class PosReturnController extends ChangeNotifier {
  PosReturnController({
    required this.gateway,
    required this.canWrite,
    required this.businessDate,
    required this.onSaved,
    this.onFeedback,
    this.quoteDelay = const Duration(milliseconds: 200),
  });

  final PosReturnGateway gateway;
  final bool canWrite;
  final String Function() businessDate;
  final VoidCallback onSaved;
  final VoidCallback? onFeedback;
  final Duration quoteDelay;

  PosReceipt? source;
  PosReturnCommand? pending;
  PosReturnResult? completed;
  PosQuote? quote;
  String receiptId = '';
  String? error;
  String? quoteError;
  String? storageError;
  bool checkedPending = false;
  bool loadingSource = false;
  bool posting = false;
  bool quoting = false;
  bool returnStock = true;
  bool confirmed = false;
  PosReturnSettlement settlement = PosReturnSettlement.credit;
  String reason = '';
  String bankId = '';
  final Map<int, String> quantities = {};

  bool _disposed = false;
  bool _checkingPending = false;
  int _sourceRevision = 0;
  int _quoteRevision = 0;
  Timer? _quoteRequest;

  bool get blocksWrites =>
      canWrite && (!checkedPending || pending != null || posting);
  bool get editable =>
      canWrite &&
      checkedPending &&
      !posting &&
      pending == null &&
      !loadingSource &&
      source?.posted == true;
  bool get ready =>
      editable &&
      quote != null &&
      (settlement == PosReturnSettlement.credit || confirmed);
  bool get canRetry =>
      canWrite && checkedPending && !posting && pending != null;
  List<PosReturnLine> get lines => [
    for (final (index, line)
        in (source?.returnCapacity ?? const <PosJson>[]).indexed)
      PosReturnLine(index, line),
  ];

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  Future<void> recover() async {
    if (!canWrite || _checkingPending || posting) return;
    _checkingPending = true;
    checkedPending = false;
    storageError = null;
    _emit();
    try {
      pending = await gateway.loadReturnPending();
      checkedPending = true;
    } catch (_) {
      storageError = 'Saved return activity could not be checked.';
    } finally {
      _checkingPending = false;
      _emit();
    }
  }

  Future<void> start(String id) async {
    if (!canWrite || pending != null || posting) return;
    receiptId = id;
    reason = bankId = '';
    settlement = PosReturnSettlement.credit;
    returnStock = true;
    completed = null;
    error = null;
    await _loadSource(id);
  }

  Future<void> reload() async {
    if (receiptId.isEmpty || pending != null || posting) return;
    await _loadSource(receiptId);
  }

  Future<void> _loadSource(String id) async {
    final revision = ++_sourceRevision;
    loadingSource = true;
    source = null;
    quantities.clear();
    _invalidateQuote();
    _emit();
    try {
      final loaded = await gateway.receipt(id);
      if (_disposed || revision != _sourceRevision) return;
      if (!loaded.posted || loaded.id != id) {
        throw const PosFailure(
          'This receipt is unavailable for returns.',
          uncertain: false,
        );
      }
      source = loaded;
    } catch (failure) {
      if (_disposed || revision != _sourceRevision) return;
      error = failure is PosFailure
          ? failure.message
          : 'Could not load the receipt and its remaining quantities.';
    } finally {
      if (!_disposed && revision == _sourceRevision) {
        loadingSource = false;
        _emit();
      }
    }
  }

  void changeQuantity(int index, String value) {
    if (!editable) return;
    quantities[index] = value;
    refreshQuote();
  }

  void changeOptions({
    PosReturnSettlement? settlement,
    bool? returnStock,
    String? reason,
    String? bankId,
  }) {
    if (!editable) return;
    if (settlement != null) this.settlement = settlement;
    if (returnStock != null) this.returnStock = returnStock;
    if (reason != null) this.reason = reason;
    if (bankId != null) this.bankId = bankId;
    refreshQuote();
  }

  void confirm(bool value) {
    if (!editable || quote == null) return;
    confirmed = value;
    _emit();
  }

  PosJson? _body(String date) {
    final selected = <PosJson>[];
    for (final line in lines) {
      final raw = quantities[line.index]?.trim() ?? '';
      if (raw.isEmpty) continue;
      final quantity = parsePosDecimal(raw, 3, wholeDigits: 12);
      if (quantity == 0) continue;
      final maximum = line.quantity;
      if (quantity == null || maximum == null || quantity > maximum) {
        quoteError =
            'Enter a quantity within the remaining amount for ${line.description}.';
        return null;
      }
      selected.add({
        'source_index': line.index,
        'quantity': posDecimalText(quantity, 3),
      });
    }
    if (selected.isEmpty) return null;
    if (settlement == PosReturnSettlement.bank && bankId.isEmpty) {
      quoteError = 'Choose the bank account used to refund the customer.';
      return null;
    }
    return {
      'date': date,
      'source_version': source?.data['version'] ?? 0,
      'lines': selected,
      'return_stock': returnStock,
      'payment_account': settlement == PosReturnSettlement.credit
          ? null
          : settlement.name,
      if (settlement == PosReturnSettlement.bank) 'bank_account_id': bankId,
      'reason': reason.trim(),
    };
  }

  void _invalidateQuote() {
    _quoteRevision++;
    _quoteRequest?.cancel();
    quote = null;
    quoteError = null;
    confirmed = false;
    quoting = false;
  }

  void refreshQuote() {
    _invalidateQuote();
    error = null;
    if (!editable) {
      _emit();
      return;
    }
    final date = businessDate();
    final body = _body(date);
    if (body == null) {
      _emit();
      return;
    }
    final revision = _quoteRevision;
    final id = receiptId;
    quoting = true;
    _emit();
    _quoteRequest = Timer(quoteDelay, () async {
      try {
        final value = await gateway.previewReturn(id, body, date);
        if (_disposed || revision != _quoteRevision) return;
        if (value.paise <= 0) {
          throw const PosFailure(
            'The return needs a positive total before it can be posted.',
          );
        }
        quote = value;
      } catch (failure) {
        if (_disposed || revision != _quoteRevision) return;
        quoteError = failure is PosFailure
            ? failure.message
            : 'Could not check the return total.';
      } finally {
        if (!_disposed && revision == _quoteRevision) {
          quoting = false;
          _emit();
        }
      }
    });
  }

  Future<void> submit() async {
    if (canRetry) {
      await _send(pending!);
      return;
    }
    if (!ready) return;
    final reviewed = quote!;
    if (reviewed.date != businessDate()) {
      refreshQuote();
      error = 'The business date changed. Review the return again.';
      _emit();
      return;
    }
    final body = _body(reviewed.date);
    if (body == null) return;
    body['expected_total'] = reviewed.amount;
    await _send(PosReturnCommand.create(receiptId, body));
  }

  Future<void> _send(PosReturnCommand command) async {
    posting = true;
    error = null;
    _emit();
    var reloadSource = false;
    try {
      if (pending == null) {
        try {
          await gateway.saveReturnPending(command);
        } catch (_) {
          checkedPending = false;
          storageError = 'Could not save the retry details. Check saved returns before continuing.';
          return;
        }
        pending = command;
      }
      try {
        completed = await gateway.postReturn(command);
      } catch (failure) {
        if (failure is PosFailure && !failure.uncertain) {
          if (!await _clear(command)) return;
          _invalidateQuote();
          error = failure.message;
          reloadSource = failure.requote || failure.status == 404;
        } else {
          error = 'The return response was interrupted. Retry the original return before refunding the customer again.';
        }
        return;
      }
      if (!await _clear(command)) return;
      _invalidateQuote();
      source = null;
      quantities.clear();
      if (!_disposed) onSaved();
    } finally {
      posting = false;
      if (reloadSource && !_disposed) {
        await _loadSource(command.receiptId);
      }
      _emit();
      if (!_disposed && (error != null || storageError != null)) {
        onFeedback?.call();
      }
    }
  }

  Future<bool> _clear(PosReturnCommand command) async {
    try {
      await gateway.clearReturnPending(command);
      pending = null;
      return true;
    } catch (_) {
      error = 'Could not clear the saved return. Retry the original return to finish recovery.';
      return false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _quoteRequest?.cancel();
    super.dispose();
  }
}
