import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';

const commerceLabels = {
  'catalogue.scan': 'Read store catalogue',
  'catalogue.publish': 'Publish accounting prices and stock',
  'history.scan': 'Scan store order history',
  'stock.project': 'Refresh sellable stock',
  'reconcile.snapshot': 'Reconcile store balances and stock',
  'order.invoice': 'Create invoice',
  'order.ship': 'Create shipment',
  'order.cancel': 'Cancel unfulfilled order',
  'order.refund': 'Create credit / refund',
  'payment.capture': 'Record confirmed store payment',
  'payment.refund': 'Record confirmed store refund',
  'settlement.record': 'Record gateway payout',
  'return.receive': 'Record physical return',
};

String commerceRoot(WorkspaceContext workspace) =>
    '${workspace.path}/commerce/connections';

final commerceMoneyLimit = BigInt.from(99999999999999);

BigInt? commercePaymentCents(String amount) {
  final cents = inventoryDecimal(amount, 2);
  return cents != null && cents <= commerceMoneyLimit ? cents : null;
}

String commercePath(WorkspaceContext workspace, String connection) =>
    '${commerceRoot(workspace)}/${Uri.encodeComponent(connection)}';

String commerceLabel(Object? value) {
  final text = inventoryText(value);
  final label =
      commerceLabels[text] ?? text.replaceAll(RegExp(r'[._]'), ' ').trim();
  return label.isEmpty ? '—' : '${label[0].toUpperCase()}${label.substring(1)}';
}

class CommerceCommand {
  CommerceCommand({
    required this.connection,
    required this.id,
    required this.operation,
    required Json payload,
  }) : _serialized = jsonEncode(payload);
  final String connection;
  final String id;
  final String operation;
  final String _serialized;
  Json get body => {
    'command_id': id,
    'operation': operation,
    'payload': jsonDecode(_serialized),
  };
  Json get stored => {'connection': connection, 'body': body};

  factory CommerceCommand.restore(Json data) {
    final body = inventoryObject(data['body']);
    final connection = inventoryText(data['connection']);
    final id = inventoryText(body['command_id']);
    final operation = inventoryText(body['operation']);
    if (connection.isEmpty ||
        id.isEmpty ||
        id.length > 100 ||
        !commerceLabels.containsKey(operation) ||
        body['payload'] is! Map) {
      throw const FormatException('The saved store command was not readable.');
    }
    return CommerceCommand(
      connection: connection,
      id: id,
      operation: operation,
      payload: inventoryObject(body['payload']),
    );
  }
}

class CommerceCommandQueue extends ChangeNotifier {
  CommerceCommandQueue(this.workspace);
  static const storageKey = 'commerce-command';
  final WorkspaceContext workspace;
  CommerceCommand? pending;
  bool busy = false;
  bool ready = false;
  bool _disposed = false;
  String? recoveryError;

  Future<void> load() async {
    try {
      final saved = await workspace.pending.load(storageKey);
      pending = saved == null ? null : CommerceCommand.restore(saved);
      recoveryError = null;
    } catch (_) {
      recoveryError =
          'The saved store command could not be opened. Try loading it again.';
    }
    ready = true;
    _notify();
  }

  bool get canSubmit =>
      ready &&
      !busy &&
      recoveryError == null &&
      pending == null &&
      workspace.company.canWrite;

  Future<Json> submit(String connection, String operation, Json payload) async {
    if (!canSubmit || _disposed || !commerceLabels.containsKey(operation)) {
      throw StateError('Resolve the original store command first.');
    }
    final random = Random.secure();
    final id = List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    final command = CommerceCommand(
      connection: connection,
      id: 'flutter-commerce-$id',
      operation: operation,
      payload: payload,
    );
    busy = true;
    _notify();
    try {
      await workspace.pending.save(storageKey, command.stored);
      pending = command;
      return await _send(command, retry: false);
    } finally {
      busy = false;
      _notify();
    }
  }

  Future<Json> retry(String connection) async {
    final command = pending;
    if (command == null ||
        command.connection != connection ||
        busy ||
        !workspace.company.canWrite ||
        _disposed) {
      throw StateError('Open the connection for the original store command.');
    }
    busy = true;
    _notify();
    try {
      return await _send(command, retry: true);
    } finally {
      busy = false;
      _notify();
    }
  }

  Future<Json> _send(CommerceCommand command, {required bool retry}) async {
    final Json result;
    try {
      result = inventoryObject(
        await workspace.api.post(
          '${commercePath(workspace, command.connection)}/commands',
          body: command.body,
        ),
      );
      if (result['command_id'] != command.id ||
          result['connection_id'] != command.connection ||
          result['operation'] != command.operation) {
        throw const FormatException(
          'The store command was not confirmed. Retry its original request.',
        );
      }
    } on ApexApiException catch (failure) {
      if (!retry && !failure.uncertain && failure.status != 409) {
        await workspace.pending.clear(storageKey);
        pending = null;
      }
      rethrow;
    }
    await workspace.pending.clear(storageKey);
    pending = null;
    return result;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
