import 'dart:async';

import '../../core/pdf_output.dart';
import '../../core/workspace.dart';
import 'pos_controller.dart';
import 'pos_models.dart';
import 'pos_register_controller.dart';
import 'pos_register_models.dart';
import 'pos_return_controller.dart';
import 'pos_return_models.dart';

class WorkspacePosGateway
    implements PosGateway, PosRegisterGateway, PosReturnGateway {
  WorkspacePosGateway(this.workspace);

  final WorkspaceContext workspace;
  static const operation = 'pos_checkout';
  static const registerOperation = 'pos_register';
  static const returnOperation = 'pos_return';
  static final _storageOperations = Expando<Future<void>>();

  Future<T> _call<T>(
    Future<T> Function() action, {
    bool posting = false,
  }) async {
    try {
      return await action();
    } on ApexApiException catch (error) {
      // A permission failure does not check whether an earlier retry key posted.
      final denied = error.status == 401 || error.status == 403;
      final detail = error.message.toLowerCase();
      final conflictingKey =
          error.status == 409 &&
          (detail.contains('idempotency key') ||
              detail.contains('retry key') ||
              detail == 'earlier return refund requires review');
      throw PosFailure(
        error.message,
        uncertain: error.uncertain || posting && (denied || conflictingKey),
        requote: error.code == 'POS_REQUOTE_REQUIRED',
        status: error.status,
      );
    }
  }

  Future<List<dynamic>> _records(String kind, int offset, int limit) async =>
      posList(
        await workspace.api.get(
          '${workspace.path}/records',
          query: {
            'kind': kind,
            'compact': 'true',
            'limit': '$limit',
            'offset': '$offset',
          },
        ),
      );

  @override
  Future<List<PosProduct>> products() => _call(() async {
    const limit = 500;
    final products = <String, PosProduct>{};
    var offset = 0;
    while (true) {
      final page = await _records('item', offset, limit);
      var added = 0;
      for (final row in page) {
        final product = PosProduct.fromJson(posObject(row));
        if (product.id.isEmpty || product.name.isEmpty) continue;
        if (!products.containsKey(product.id)) added++;
        products[product.id] = product;
      }
      if (page.length < limit || added == 0) break;
      offset += page.length;
    }
    return products.values.where((product) => product.active).toList()..sort(
      (left, right) =>
          left.name.toLowerCase().compareTo(right.name.toLowerCase()),
    );
  });

  @override
  Future<Map<String, String>> stock() => _call(() async {
    final summary = posObject(
      await workspace.api.get('${workspace.path}/pos/stock'),
    );
    return {
      for (final row in posList(summary['rows']).map(posObject))
        if (row['item_id'] is String && row['closing_quantity'] != null)
          row['item_id'] as String: posText(row['closing_quantity']),
    };
  });

  @override
  Future<List<PosBank>> banks() => _call(() async {
    final response = await workspace.api.get('${workspace.path}/bank-accounts');
    return posList(response).map(posObject).map(PosBank.fromJson).toList();
  });

  @override
  Future<PosQuote> quote(PosJson body, String date) => _call(() async {
    final response = await workspace.api.post(
      '${workspace.path}/documents/preview',
      body: body,
    );
    return PosQuote.fromJson(posObject(response), date);
  });

  @override
  Future<PosReceipt> post(PosPendingSale sale) => _call(() async {
    final response = await workspace.api.post(
      '${workspace.path}/records',
      body: sale.body,
      idempotencyKey: sale.key,
    );
    return PosReceipt.fromJson(posObject(response));
  }, posting: true);

  @override
  Future<List<PosReceipt>> receipts(int offset) => _call(() async {
    final page = await _records('pos', offset, 50);
    return page.map(posObject).map(PosReceipt.fromJson).toList();
  });

  @override
  Future<PosReceipt> receipt(String id) => _call(() async {
    final response = await workspace.api.get(
      '${workspace.path}/records/${Uri.encodeComponent(id)}',
    );
    return PosReceipt.fromJson(posObject(response));
  });

  Future<ApexPdf> receiptPdf(PosReceipt receipt, int widthMm) => _call(
    () async {
      if (!receipt.posted || !{58, 80}.contains(widthMm)) {
        throw const PosFailure('Choose a posted receipt and a supported roll.');
      }
      final bytes = await workspace.api.download(
        '${workspace.path}/documents/${Uri.encodeComponent(receipt.id)}.pdf',
        query: {'template': 'thermal_$widthMm'},
      );
      return ApexPdf(
        bytes: bytes,
        name: '${receipt.number}-$widthMm-mm',
        rollWidthMm: widthMm,
      );
    },
  );

  Future<PosPendingSale?> _readPending() async {
    final value = await workspace.pending.load(operation);
    return value == null ? null : PosPendingSale.fromJson(value);
  }

  @override
  Future<PosPendingSale?> loadPending() => _storage(_readPending);

  @override
  Future<void> savePending(PosPendingSale sale) => _storage(() async {
    await _requireNoPending();
    await workspace.pending.save(operation, sale.toJson());
  });

  @override
  Future<void> clearPending(PosPendingSale sale) => _storage(() async {
    final prior = await _readPending();
    if (prior == null) return;
    if (prior.key != sale.key || prior.payload != sale.payload) {
      throw StateError('The saved checkout has changed.');
    }
    await workspace.pending.clear(operation);
  });

  @override
  Future<PosRegisterOverview> registerOverview() => _call(() async {
    final response = await workspace.api.get('${workspace.path}/pos-register');
    return PosRegisterOverview.fromJson(posObject(response));
  });

  @override
  Future<void> sendRegisterCommand(PosRegisterCommand command) => _call(
    () async {
      final registerId = Uri.encodeComponent(command.registerId);
      final path = switch (command.action) {
        RegisterOperation.open => '${workspace.path}/pos-register/open',
        RegisterOperation.movement =>
          '${workspace.path}/pos-register/$registerId/movements',
        RegisterOperation.close =>
          '${workspace.path}/pos-register/$registerId/close',
      };
      final response = posObject(
        await workspace.api.post(
          path,
          body: command.body,
          idempotencyKey: command.key,
        ),
      );
      if (command.action == RegisterOperation.movement) {
        final data = posObject(response['data']);
        if (posText(response['id']).isEmpty ||
            response['kind'] != 'pos_register_movement' ||
            data['pos_register_session_id'] != command.registerId ||
            data['direction'] != command.body['direction'] ||
            registerPaise(response['amount']) !=
                registerPaise(command.body['amount'])) {
          throw const FormatException(
            'The server did not confirm the cash movement.',
          );
        }
        return;
      }
      final session = PosRegisterSession.fromJson(response);
      if (command.action == RegisterOperation.close &&
          (session.id != command.registerId ||
              !session.closed ||
              session.counted != registerPaise(command.body['counted_cash']))) {
        throw const FormatException(
          'The server did not confirm the closing count.',
        );
      }
    },
    posting: true,
  );

  Future<PosRegisterCommand?> _readRegisterPending() async {
    final entry = await workspace.pending.load(registerOperation);
    return entry == null ? null : PosRegisterCommand.fromJson(entry);
  }

  @override
  Future<PosRegisterCommand?> loadRegisterPending() =>
      _storage(_readRegisterPending);

  @override
  Future<void> saveRegisterPending(PosRegisterCommand command) =>
      _storage(() async {
        await _requireNoPending();
        await workspace.pending.save(registerOperation, command.toJson());
      });

  @override
  Future<void> clearRegisterPending(PosRegisterCommand command) =>
      _storage(() async {
        final previous = await _readRegisterPending();
        if (previous == null) return;
        if (previous.key != command.key ||
            previous.payload != command.payload ||
            previous.registerId != command.registerId ||
            previous.action != command.action) {
          throw StateError('The saved register action has changed.');
        }
        await workspace.pending.clear(registerOperation);
      });

  @override
  Future<PosQuote> previewReturn(
    String receiptId,
    PosJson body,
    String date,
  ) => _call(() async {
    final result = await workspace.api.post(
      '${workspace.path}/pos/${Uri.encodeComponent(receiptId)}/return/preview',
      body: body,
    );
    return PosQuote.fromJson(posObject(result), date);
  });

  @override
  Future<PosReturnResult> postReturn(
    PosReturnCommand command,
  ) => _call(() async {
    final result = await workspace.api.post(
      '${workspace.path}/pos/${Uri.encodeComponent(command.receiptId)}/return',
      body: command.body,
      idempotencyKey: command.key,
    );
    return PosReturnResult.fromJson(posObject(result), command);
  }, posting: true);

  Future<PosReturnCommand?> _readReturnPending() async {
    final entry = await workspace.pending.load(returnOperation);
    return entry == null ? null : PosReturnCommand.fromJson(entry);
  }

  @override
  Future<PosReturnCommand?> loadReturnPending() => _storage(_readReturnPending);

  @override
  Future<void> saveReturnPending(PosReturnCommand command) =>
      _storage(() async {
        await _requireNoPending();
        await workspace.pending.save(returnOperation, command.toJson());
      });

  @override
  Future<void> clearReturnPending(PosReturnCommand command) =>
      _storage(() async {
        final previous = await _readReturnPending();
        if (previous == null) return;
        if (previous.key != command.key ||
            previous.payload != command.payload ||
            previous.receiptId != command.receiptId) {
          throw StateError('The saved return has changed.');
        }
        await workspace.pending.clear(returnOperation);
      });

  Future<void> _requireNoPending() async {
    if (await _readPending() != null ||
        await _readRegisterPending() != null ||
        await _readReturnPending() != null) {
      throw StateError('A POS action is already awaiting confirmation.');
    }
  }

  Future<T> _storage<T>(Future<T> Function() action) async {
    final store = workspace.pending;
    final previous = _storageOperations[store];
    final done = Completer<void>();
    _storageOperations[store] = done.future;
    try {
      await previous;
      return await action();
    } finally {
      done.complete();
    }
  }
}
