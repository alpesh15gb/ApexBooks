import 'package:flutter/foundation.dart';

import 'pos_controller.dart';
import 'pos_models.dart';
import 'pos_register_models.dart';

abstract interface class PosRegisterGateway {
  Future<PosRegisterOverview> registerOverview();
  Future<void> sendRegisterCommand(PosRegisterCommand command);
  Future<PosRegisterCommand?> loadRegisterPending();
  Future<void> saveRegisterPending(PosRegisterCommand command);
  Future<void> clearRegisterPending(PosRegisterCommand command);
}

class PosRegisterController extends ChangeNotifier {
  PosRegisterController({
    required this.gateway,
    required this.canWrite,
    required this.onChanged,
    this.onFeedback,
  });

  final PosRegisterGateway gateway;
  final bool canWrite;
  final VoidCallback onChanged;
  final VoidCallback? onFeedback;

  PosRegisterOverview? overview;
  PosRegisterCommand? pending;
  bool pendingChecked = false;
  bool busy = false;
  bool refreshing = false;
  String? recoveryError;
  String? loadError;
  String? message;
  int resetVersion = 0;
  bool _disposed = false;
  bool _recovering = false;

  PosRegisterSession? get active => overview?.active;
  bool get blocksNewSale =>
      canWrite && (!pendingChecked || busy || pending != null);
  bool get writable =>
      canWrite &&
      pendingChecked &&
      pending == null &&
      !busy &&
      !refreshing &&
      loadError == null &&
      overview != null;

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  Future<void> recover() async {
    if (_recovering || busy) return;
    _recovering = true;
    pendingChecked = false;
    recoveryError = null;
    _emit();
    try {
      pending = await gateway.loadRegisterPending();
      pendingChecked = true;
    } catch (_) {
      recoveryError = 'Saved register activity could not be checked.';
    } finally {
      _recovering = false;
      _emit();
    }
  }

  Future<void> refresh({bool afterMutation = false}) async {
    if (refreshing || busy && !afterMutation) return;
    refreshing = true;
    loadError = null;
    _emit();
    try {
      overview = await gateway.registerOverview();
    } catch (error) {
      loadError = error is PosFailure
          ? error.message
          : 'Could not load register activity.';
    } finally {
      refreshing = false;
      _emit();
    }
  }

  String? validateOpen(String input) {
    if (parsePosMoney(input) == null) {
      return 'Enter an opening cash amount, including zero.';
    }
    return null;
  }

  String? validateMovement(String amount, String reason) {
    if ((parsePosMoney(amount) ?? 0) <= 0) {
      return 'Enter a cash amount greater than zero.';
    }
    if (reason.trim().isEmpty || reason.trim().length > 200) {
      return 'Enter a reason of up to 200 characters.';
    }
    return null;
  }

  String? validateClose(String amount, String reason, String snapshot) {
    final session = active;
    if (session == null || session.snapshot != snapshot) {
      return 'Register activity changed. Refresh the drawer and count again.';
    }
    final cash = parsePosMoney(amount);
    if (cash == null) return 'Enter the counted cash, including zero.';
    final difference = BigInt.from(cash) - session.expected;
    if (difference != BigInt.zero && reason.trim().isEmpty) {
      return 'Enter a reason for the cash difference.';
    }
    if (reason.trim().length > 200) {
      return 'Use a reason of up to 200 characters.';
    }
    return null;
  }

  Future<void> open(String amount) async {
    if (!writable || active != null || validateOpen(amount) != null) return;
    await _submit(
      PosRegisterCommand.create(
        action: RegisterOperation.open,
        body: {'opening_float': posDecimalText(parsePosMoney(amount)!, 2)},
      ),
    );
  }

  Future<void> move(
    String registerId,
    String direction,
    String amount,
    String reason,
  ) async {
    if (!writable ||
        active?.id != registerId ||
        !{'in', 'out'}.contains(direction) ||
        validateMovement(amount, reason) != null) {
      return;
    }
    await _submit(
      PosRegisterCommand.create(
        action: RegisterOperation.movement,
        registerId: registerId,
        body: {
          'direction': direction,
          'amount': posDecimalText(parsePosMoney(amount)!, 2),
          'reason': reason.trim(),
        },
      ),
    );
  }

  Future<void> close(
    String registerId,
    String amount,
    String reason,
    String snapshot,
  ) async {
    if (!writable ||
        active?.id != registerId ||
        validateClose(amount, reason, snapshot) != null) {
      return;
    }
    await _submit(
      PosRegisterCommand.create(
        action: RegisterOperation.close,
        registerId: registerId,
        body: {
          'counted_cash': posDecimalText(parsePosMoney(amount)!, 2),
          'reason': reason.trim(),
          'snapshot': snapshot,
        },
      ),
    );
  }

  Future<void> retry() async {
    final command = pending;
    if (!canWrite || !pendingChecked || busy || command == null) return;
    await _submit(command);
  }

  Future<void> _submit(PosRegisterCommand command) async {
    busy = true;
    message = null;
    _emit();
    try {
      if (pending == null) {
        try {
          await gateway.saveRegisterPending(command);
        } catch (_) {
          pendingChecked = false;
          recoveryError = 'Could not save the retry details. Check saved register activity before trying again.';
          return;
        }
        pending = command;
      }
      try {
        await gateway.sendRegisterCommand(command);
      } catch (error) {
        if (error is PosFailure && !error.uncertain) {
          if (!await _clear(command)) return;
          message = error.message;
          if (error.status == 409 || error.status == 404) {
            resetVersion++;
            await refresh(afterMutation: true);
            if (!_disposed) onChanged();
          }
        } else {
          message = 'Register confirmation was interrupted. Retry the original action before recording it again.';
        }
        return;
      }
      if (!await _clear(command)) return;
      message = switch (command.action) {
        RegisterOperation.open => 'Register opening recorded.',
        RegisterOperation.movement => 'Cash movement recorded.',
        RegisterOperation.close => 'Register closing count recorded.',
      };
      resetVersion++;
      await refresh(afterMutation: true);
      if (!_disposed) onChanged();
    } finally {
      busy = false;
      _emit();
      if (!_disposed && (message != null || recoveryError != null)) {
        onFeedback?.call();
      }
    }
  }

  Future<bool> _clear(PosRegisterCommand command) async {
    try {
      await gateway.clearRegisterPending(command);
      pending = null;
      return true;
    } catch (_) {
      message = 'Could not clear the saved register action. Retry the original action to finish recovery.';
      return false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
