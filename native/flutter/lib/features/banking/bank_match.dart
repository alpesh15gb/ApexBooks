import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import 'bank_data.dart';
import 'bank_forms.dart';

typedef MatchCandidate = ({Json record, BigInt available});

class BankMatchDialog extends StatefulWidget {
  const BankMatchDialog({
    required this.workspace,
    required this.bank,
    required this.line,
    this.asOf,
    super.key,
  });
  final WorkspaceContext workspace;
  final String bank;
  final Json line;

  /// Reconcile-through date; later entries are not offered, as in the web app.
  final String? asOf;
  @override
  State<BankMatchDialog> createState() => _BankMatchDialogState();
}

class _BankMatchDialogState extends State<BankMatchDialog> {
  final _amount = TextEditingController();
  late final Future<List<MatchCandidate>> _choices = _load();
  MatchCandidate? _selected;
  String _search = '';
  String? _error;

  BigInt get _remaining =>
      signedMoney(inventoryText(widget.line['remaining_amount'])) ??
      BigInt.zero;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<List<MatchCandidate>> _load() async {
    final workspace = widget.workspace;
    final bank = widget.bank;
    final statementAmount =
        signedMoney(inventoryText(widget.line['amount'])) ?? BigInt.zero;
    final used = <String, BigInt>{};
    final exact = <String>{};
    final onThisLine = <String>{};
    final rows = inventoryRows(
      await workspace.api.get(
        '${workspace.path}/bank-statement',
        query: {'bank_account_id': bank},
      ),
    );
    for (final line in rows) {
      if (line['matched_record_id'] is String) {
        exact.add(line['matched_record_id'] as String);
      }
      for (final allocation in inventoryRows(line['allocations'])) {
        final id = inventoryText(allocation['record_id']);
        if (line['id'] == widget.line['id']) onThisLine.add(id);
        used[id] =
            (used[id] ?? BigInt.zero) +
            (signedMoney(inventoryText(allocation['amount'])) ?? BigInt.zero);
      }
    }

    const pageSize = 200;
    final candidates = <MatchCandidate>[];
    final seen = <String>{};
    for (var offset = 0; ; offset += pageSize) {
      final page = inventoryRows(
        await workspace.api.get(
          '${workspace.path}/records',
          query: {'compact': 'true', 'limit': '$pageSize', 'offset': '$offset'},
        ),
      );
      final previous = seen.length;
      for (final record in page) {
        final id = inventoryText(record['id']);
        if (!seen.add(id) || exact.contains(id) || onThisLine.contains(id)) {
          continue;
        }
        final asOf = widget.asOf;
        if (asOf != null &&
            inventoryText(record['date']).compareTo(asOf) > 0) {
          continue;
        }
        final movement = bankMovement(record, bank);
        if (movement == null ||
            movement.isNegative != statementAmount.isNegative) {
          continue;
        }
        final available = movement.abs() - (used[id] ?? BigInt.zero);
        if (available > BigInt.zero) {
          candidates.add((record: record, available: available));
        }
      }
      if (page.length < pageSize || seen.length == previous) break;
    }
    candidates.sort((a, b) {
      final x = a.available == _remaining ? 0 : 1;
      final y = b.available == _remaining ? 0 : 1;
      if (x != y) return x.compareTo(y);
      final date = inventoryText(widget.line['date']);
      final first = inventoryText(a.record['date']);
      final second = inventoryText(b.record['date']);
      if (first == date) return second == date ? 0 : -1;
      if (second == date) return 1;
      return second.compareTo(first);
    });
    return candidates;
  }

  void _choose(MatchCandidate candidate) => setState(() {
    _selected = candidate;
    final cap = candidate.available < _remaining
        ? candidate.available
        : _remaining;
    _amount.text = decimalMoney(cap);
    _error = null;
  });

  void _confirm() {
    final candidate = _selected;
    final amount = signedMoney(_amount.text);
    if (candidate == null) return;
    if (amount == null ||
        amount <= BigInt.zero ||
        amount > candidate.available ||
        amount > _remaining) {
      setState(
        () => _error = 'Enter an amount within both remaining balances.',
      );
      return;
    }
    Navigator.pop(context, {
      'record_id': candidate.record['id'],
      'amount': decimalMoney(amount),
    });
  }

  @override
  Widget build(BuildContext context) => BankFormDialog(
    title: 'Match bank transaction',
    error: _error,
    fields: [
      Text(
        '${widget.line['description']} · ${inventoryAmount(widget.line['remaining_amount'])} remaining',
      ),
      TextField(
        decoration: const InputDecoration(
          labelText: 'Search reference, date or name',
          prefixIcon: Icon(Icons.search),
        ),
        onChanged: (value) =>
            setState(() => _search = value.trim().toLowerCase()),
      ),
      FutureBuilder<List<MatchCandidate>>(
        future: _choices,
        builder: (context, state) {
          if (state.connectionState != ConnectionState.done) {
            return const LinearProgressIndicator();
          }
          if (state.hasError) return Text(inventoryError(state.error!));
          final choices = (state.data ?? const <MatchCandidate>[])
              .where(
                (candidate) =>
                    '${candidate.record['number']} ${candidate.record['name']} ${candidate.record['date']}'
                        .toLowerCase()
                        .contains(_search),
              )
              .take(40)
              .toList();
          if (choices.isEmpty) {
            return const Text('No eligible transactions match.');
          }
          return Column(
            children: [
              for (final candidate in choices)
                ListTile(
                  leading: Icon(
                    _selected?.record['id'] == candidate.record['id']
                        ? Icons.check_circle
                        : Icons.circle_outlined,
                  ),
                  title: Text(inventoryText(candidate.record['name'])),
                  subtitle: Text(
                    '${candidate.record['number']} · ${candidate.record['date']}',
                  ),
                  trailing: Text(
                    inventoryAmount(decimalMoney(candidate.available)),
                  ),
                  onTap: () => _choose(candidate),
                ),
            ],
          );
        },
      ),
      if (_selected != null)
        BankField(
          label: 'Amount to match (₹)',
          controller: _amount,
          maxLength: 16,
          keyboard: const TextInputType.numberWithOptions(decimal: true),
        ),
    ],
    primary: FilledButton(
      onPressed: _selected == null ? null : _confirm,
      child: const Text('Match amount'),
    ),
  );
}
