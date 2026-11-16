import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../../core/workspace.dart';
import 'books_data.dart';

enum BooksOperation {
  create,
  withPayment,
  amend,
  draft,
  cancel,
  credit,
  advanceApply,
  advanceRefund,
  scheduleCreate,
  scheduleUpdate,
  scheduleOccurrence,
}

class BooksCommand {
  BooksCommand(this.operation, this.recordId, BooksJson body)
    : payload = jsonEncode(body);

  final BooksOperation operation;
  final String recordId;
  final String payload;
  BooksJson get body => booksObject(jsonDecode(payload));

  bool get usesPut =>
      operation == BooksOperation.amend ||
      operation == BooksOperation.draft ||
      operation == BooksOperation.scheduleUpdate;

  String get recordKind => booksText(
    operation == BooksOperation.withPayment
        ? booksObject(body['document'])['kind']
        : body['kind'],
  );

  String get pathSuffix {
    final id = Uri.encodeComponent(recordId);
    return switch (operation) {
      BooksOperation.create => '/records',
      BooksOperation.withPayment => '/records/with-payment',
      BooksOperation.amend => '/documents/$id',
      BooksOperation.draft => '/drafts/$id',
      BooksOperation.cancel => '/records/$id/cancel',
      BooksOperation.credit => '/credits/$id/settle',
      BooksOperation.advanceApply => '/advances/$id/apply',
      BooksOperation.advanceRefund => '/advances/$id/refund',
      BooksOperation.scheduleCreate => '/recurring-templates',
      BooksOperation.scheduleUpdate => '/recurring-templates/$id',
      BooksOperation.scheduleOccurrence =>
        '/recurring-templates/$id/occurrences',
    };
  }

  String get label => switch (operation) {
    BooksOperation.cancel => 'Cancellation',
    BooksOperation.credit ||
    BooksOperation.advanceApply ||
    BooksOperation.advanceRefund => 'Settlement',
    BooksOperation.scheduleCreate ||
    BooksOperation.scheduleUpdate => 'Recurring schedule',
    BooksOperation.scheduleOccurrence => 'Scheduled draft',
    _ => booksKindLabel(recordKind),
  };

  void confirm(BooksRecord record) {
    final requestedKind = recordKind;
    final data = booksObject(body['data'] ?? const <String, dynamic>{});
    final same = record.id == recordId;
    final confirmed = switch (operation) {
      BooksOperation.cancel => same && record.json['cancelled'] == true,
      BooksOperation.amend ||
      BooksOperation.draft => same && record.kind == requestedKind,
      BooksOperation.create ||
      BooksOperation.withPayment => record.kind == requestedKind,
      BooksOperation.credit =>
        record.data['credit_note_id'] == recordId &&
            (data['action'] == 'apply'
                ? record.kind == 'credit_application'
                : record.kind == 'customer_refund' ||
                      record.kind == 'supplier_refund'),
      BooksOperation.advanceApply =>
        record.kind == 'advance_application' &&
            record.data['advance_id'] == recordId,
      BooksOperation.advanceRefund =>
        record.kind == 'advance_refund' &&
            record.data['advance_id'] == recordId,
      BooksOperation.scheduleCreate =>
        record.kind == 'recurring_template' &&
            record.data['source_record_id'] == body['source_record_id'],
      BooksOperation.scheduleUpdate =>
        same &&
            record.kind == 'recurring_template' &&
            record.data['version'] is int &&
            record.data['version'] > body['version'],
      BooksOperation.scheduleOccurrence =>
        const {
              'estimate',
              'proforma',
              'sales_order',
              'purchase_order',
            }.contains(record.kind) &&
            record.json['posted'] != true &&
            record.data['recurring_template_id'] == recordId &&
            record.data['recurring_occurrence_date'] == body['occurrence_date'],
    };
    if (!confirmed) {
      throw const FormatException('Could not verify the saved record');
    }
  }

  BooksRecord response(Object? raw) {
    final json = booksObject(raw);
    return switch (operation) {
      BooksOperation.scheduleCreate ||
      BooksOperation.scheduleUpdate => BooksRecord({
        'kind': 'recurring_template',
        'id': json['id'],
        'name': json['name'],
        'data': json,
      }),
      BooksOperation.scheduleOccurrence => BooksRecord(
        booksObject(json['record']),
      ),
      BooksOperation.withPayment => _documentWithPayment(json),
      _ => BooksRecord(json),
    };
  }

  BooksRecord _documentWithPayment(BooksJson json) {
    final document = BooksRecord(booksObject(json['document']));
    final payment = BooksRecord(booksObject(json['payment']));
    final paymentKind = recordKind == 'sales_invoice'
        ? 'payment_in'
        : 'payment_out';
    if (payment.kind != paymentKind ||
        payment.data['applied_to'] != document.id ||
        payment.id == document.id) {
      throw const FormatException(
        'Could not verify the submitted payment and its linked document',
      );
    }
    return document;
  }
}

class BooksPending {
  const BooksPending(this.command, this.key);

  factory BooksPending.fromJson(Json saved) {
    final operation = BooksOperation.values.byName(
      booksText(saved['operation']),
    );
    final recordId = booksText(saved['record_id']);
    final key = booksText(saved['key']);
    if (!RegExp(r'^flutter-books-[a-f0-9]{32}$').hasMatch(key) ||
        (!const {
              BooksOperation.create,
              BooksOperation.withPayment,
              BooksOperation.scheduleCreate,
            }.contains(operation) &&
            !RegExp(r'^[A-Za-z0-9-]{1,80}$').hasMatch(recordId))) {
      throw const FormatException('Invalid saved accounting request');
    }
    return BooksPending(
      BooksCommand(operation, recordId, booksObject(saved['body'])),
      key,
    );
  }

  final BooksCommand command;
  final String key;

  Json toJson() => {
    'key': key,
    'operation': command.operation.name,
    'record_id': command.recordId,
    'body': command.body,
  };
}

class BooksPosting extends ChangeNotifier {
  BooksPosting(this.workspace);

  static const storageKey = 'books-entry';
  final WorkspaceContext workspace;
  BooksPending? pending;
  bool checking = false;
  bool ready = false;
  bool busy = false;
  String? recoveryError;
  String? message;
  bool _disposed = false;

  String get root =>
      '/api/companies/${Uri.encodeComponent(workspace.company.id)}';
  bool get canStart =>
      workspace.company.canWrite && ready && !busy && pending == null;

  Future<void> recover() async {
    if (_disposed || checking || busy || !workspace.company.canWrite) return;
    checking = true;
    _changed();
    try {
      final stored = await workspace.pending.load(storageKey);
      pending = stored == null ? null : BooksPending.fromJson(stored);
      recoveryError = null;
      ready = true;
    } catch (_) {
      ready = false;
      recoveryError = 'The saved accounting request could not be opened. Try recovery again before posting.';
    } finally {
      checking = false;
      _changed();
    }
  }

  Future<BooksRecord?> submit(BooksCommand command) async {
    if (!canStart || _disposed) return null;
    final random = Random.secure();
    final token = List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    final attempt = BooksPending(command, 'flutter-books-$token');
    busy = true;
    message = null;
    _changed();
    try {
      await workspace.pending.save(storageKey, attempt.toJson());
      pending = attempt;
      if (_disposed) return null;
      return await _send(attempt, retry: false);
    } catch (_) {
      // A storage failure may have persisted a payload without confirming it.
      ready = false;
      recoveryError = 'Could not save a retry copy. Check saved accounting requests before continuing.';
      return null;
    } finally {
      busy = false;
      _changed();
    }
  }

  Future<BooksRecord?> retry() async {
    final attempt = pending;
    if (_disposed ||
        !workspace.company.canWrite ||
        !ready ||
        busy ||
        attempt == null) {
      return null;
    }
    busy = true;
    message = null;
    _changed();
    try {
      return await _send(attempt, retry: true);
    } finally {
      busy = false;
      _changed();
    }
  }

  Future<BooksRecord?> _send(
    BooksPending attempt, {
    required bool retry,
  }) async {
    final command = attempt.command;
    try {
      final path = '$root${command.pathSuffix}';
      final result = command.usesPut
          ? await workspace.api.put(
              path,
              body: command.body,
              idempotencyKey: attempt.key,
            )
          : await workspace.api.post(
              path,
              body: command.body,
              idempotencyKey: attempt.key,
            );
      final record = command.response(result);
      command.confirm(record);
      if (!await _clear()) return null;
      return record;
    } on ApexApiException catch (error) {
      if (!retry &&
          error.status != null &&
          !error.uncertain &&
          await _clear()) {
        message = error.message;
      } else {
        message ??=
            'The posting outcome needs confirmation. Retry the original request. ${error.message}';
      }
    } catch (_) {
      message = 'The posting outcome could not be verified. Retry the original request.';
    }
    return null;
  }

  Future<bool> _clear() async {
    try {
      await workspace.pending.clear(storageKey);
      pending = null;
      return true;
    } catch (_) {
      message = 'Could not clear the original request. Retry it to confirm the posting.';
      return false;
    }
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
