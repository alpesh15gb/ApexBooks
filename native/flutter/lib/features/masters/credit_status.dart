import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';

/// Advisory only: the server's canonical credit exposure for one party, debounced like the web
/// app's CreditStatus. Never blocks saving.
class CreditStatus extends StatefulWidget {
  const CreditStatus({
    required this.workspace,
    required this.partyId,
    required this.asOf,
    this.proposedAmount = '0',
    super.key,
  });

  final WorkspaceContext workspace;
  final String partyId;
  final String asOf;
  final String proposedAmount;

  @override
  State<CreditStatus> createState() => _CreditStatusState();
}

class _CreditStatusState extends State<CreditStatus> {
  Json? _status;
  String _error = '';
  Timer? _timer;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _schedule();
  }

  @override
  void didUpdateWidget(covariant CreditStatus oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.partyId != widget.partyId ||
        oldWidget.asOf != widget.asOf ||
        oldWidget.proposedAmount != widget.proposedAmount ||
        oldWidget.workspace != widget.workspace) {
      _schedule();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _generation++;
    super.dispose();
  }

  void _schedule() {
    _timer?.cancel();
    final generation = ++_generation;
    _status = null;
    _error = '';
    if (widget.partyId.isEmpty || widget.asOf.isEmpty) return;
    _timer = Timer(const Duration(milliseconds: 300), () async {
      final workspace = widget.workspace;
      try {
        final result = inventoryObject(
          await workspace.api.get(
            '${workspace.path}/parties/${Uri.encodeComponent(widget.partyId)}/credit-status',
            query: {'as_of': widget.asOf, 'proposed_amount': widget.proposedAmount.isEmpty ? '0' : widget.proposedAmount},
          ),
        );
        if (mounted && generation == _generation) setState(() => _status = result);
      } catch (failure) {
        if (mounted && generation == _generation) setState(() => _error = inventoryError(failure));
      }
    });
  }

  String _money(Object? value) => apexMoney(apexNumber(value) ?? 0);

  @override
  Widget build(BuildContext context) {
    if (widget.partyId.isEmpty || widget.asOf.isEmpty) return const SizedBox.shrink();
    if (_error.isNotEmpty) {
      return _box(
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Credit review unavailable: $_error. This advisory does not block saving; review the party statement before extending credit.',
              style: const TextStyle(fontSize: 13, height: 1.5, color: Apex.muted),
            ),
            const SizedBox(height: 10),
            OutlinedButton(
              onPressed: () => setState(_schedule),
              child: const Text('Retry credit review'),
            ),
          ],
        ),
      );
    }
    final status = _status;
    if (status == null) {
      return Semantics(
        liveRegion: true,
        child: const Text('Reviewing customer credit exposure…', style: Apex.note),
      );
    }
    final exceeded = status['exceeded'] == true;
    final proposed = (apexNumber(widget.proposedAmount) ?? 0) > 0;
    Widget figure(String label, String value) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Apex.muted)),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            fontFamily: Apex.display,
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: exceeded ? Apex.red : Apex.ink,
          ),
        ),
      ],
    );
    return Semantics(
      liveRegion: true,
      container: true,
      label: 'Customer credit review',
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: exceeded ? const Color(0xfffcecea) : Apex.tint,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: exceeded ? const Color(0xffe8b9b5) : Apex.line),
        ),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                exceeded ? 'Credit limit would be exceeded' : 'Customer credit review',
                style: Apex.strong.copyWith(fontSize: 16),
              ),
              const SizedBox(height: 4),
              Text(
                'As of ${inventoryText(status['as_of'])} · advisory only, saving is not blocked',
                style: const TextStyle(fontSize: 13, color: Apex.muted),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 28,
                runSpacing: 12,
                children: [
                  figure('Credit limit', status['credit_limit'] == null ? 'Not set' : _money(status['credit_limit'])),
                  figure('Current net exposure', _money(status['current_exposure'])),
                  if (proposed) figure('With this new sale', _money(status['projected_exposure'])),
                  if (status['remaining_credit'] != null) figure('Remaining credit', _money(status['remaining_credit'])),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                'Receivables ${_money(status['receivable'])} less unused customer credits ${_money(status['customer_credit'])} and advances ${_money(status['customer_advance'])}. Supplier payables are not offset.',
                style: const TextStyle(fontSize: 12, height: 1.5, color: Apex.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _box(Widget child) => DecoratedBox(
    decoration: BoxDecoration(
      color: Apex.tint,
      borderRadius: BorderRadius.circular(10),
      border: Border.all(color: Apex.line),
    ),
    child: Padding(padding: const EdgeInsets.all(14), child: child),
  );
}
