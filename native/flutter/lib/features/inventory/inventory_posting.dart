import 'dart:math';

import 'package:flutter/foundation.dart';

import '../../core/workspace.dart';
import 'inventory_models.dart';

class InventoryPosting extends ChangeNotifier {
  InventoryPosting(this.workspace);

  static const storageKey = 'inventory';
  final WorkspaceContext workspace;
  InventoryOperation? pending;
  String? recoveryError;
  bool loaded = false;
  bool busy = false;
  bool _disposed = false;

  String get base =>
      '/api/companies/${Uri.encodeComponent(workspace.company.id)}';

  Future<void> load() async {
    try {
      final saved = await workspace.pending.load(storageKey);
      pending = saved == null ? null : InventoryOperation.fromJson(saved);
      recoveryError = null;
    } catch (_) {
      recoveryError = 'The saved inventory request could not be opened. Try loading it again before posting.';
    }
    loaded = true;
    _changed();
  }

  Future<InventoryJson> submit(
    String kind,
    String id,
    String name,
    InventoryJson body,
  ) async {
    _requireReady();
    if (pending != null) {
      throw StateError('Confirm the pending inventory request first.');
    }
    final random = Random.secure();
    final key = List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    final operation = InventoryOperation(
      key: 'flutter-inventory-$key',
      kind: kind,
      recordId: id,
      name: name,
      body: body,
    );
    busy = true;
    _changed();
    try {
      await workspace.pending.save(storageKey, operation.toJson());
      pending = operation;
      return await _send(operation, retrying: false);
    } finally {
      busy = false;
      _changed();
    }
  }

  Future<InventoryJson> retry() async {
    _requireReady();
    final operation = pending;
    if (operation == null) {
      throw StateError('There is no pending inventory request.');
    }
    busy = true;
    _changed();
    try {
      return await _send(operation, retrying: true);
    } finally {
      busy = false;
      _changed();
    }
  }

  void _requireReady() {
    if (!workspace.company.canWrite ||
        !loaded ||
        busy ||
        recoveryError != null ||
        _disposed) {
      throw StateError('Inventory posting is currently unavailable.');
    }
  }

  Future<InventoryJson> _send(
    InventoryOperation operation, {
    required bool retrying,
  }) async {
    final id = Uri.encodeComponent(operation.recordId);
    final path = switch (operation.kind) {
      'receipt' => '$base/purchase-orders/$id/receipts',
      'count' => '$base/stock/counts',
      'opening' => '$base/stock/opening',
      'adjustment' => '$base/stock/adjustments',
      _ => throw const FormatException('Invalid inventory posting operation.'),
    };
    final InventoryJson result;
    try {
      final response = await workspace.api.post(
        path,
        body: operation.body,
        idempotencyKey: operation.key,
      );
      result = inventoryObject(response);
      if (inventoryText(result['id']).isEmpty) {
        throw const FormatException(
          'Inventory posting response could not be confirmed.',
        );
      }
    } on ApexApiException catch (error) {
      if ((!retrying && !error.uncertain) ||
          requiresInventoryReview(error, operation.kind)) {
        await workspace.pending.clear(storageKey);
        pending = null;
      }
      rethrow;
    }
    await workspace.pending.clear(storageKey);
    pending = null;
    return result;
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

bool requiresInventoryReview(ApexApiException error, String kind) {
  if (kind == 'receipt') return error.code == 'PO_RECEIPT_REVIEW_REQUIRED';
  // The current stock count contract reports stale snapshots after checking
  // for a previous committed key. Other conflicts may still be unresolved.
  return error.status == 409 &&
      const {
        'The business date changed. Refresh on-hand stock and count again',
        'Stock moved after this count started. Refresh on-hand stock and count again',
      }.contains(error.message);
}

String inventoryError(Object error) => switch (error) {
  ApexApiException value => value.message,
  FormatException value => value.message,
  StateError value => value.message,
  _ => 'Could not complete the inventory request. Check the connection and try again.',
};
