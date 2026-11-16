import 'package:material_ui/material_ui.dart';

import '../../ui/apex_widgets.dart';
import 'pos_models.dart';
import 'pos_return_controller.dart';
import 'pos_return_models.dart';
import 'pos_widgets.dart';

class PosReturnPanel extends StatelessWidget {
  const PosReturnPanel({
    required this.returns,
    required this.banks,
    required this.back,
    required this.otherActionPending,
    super.key,
  });

  final PosReturnController returns;
  final List<PosBank> banks;
  final VoidCallback back;
  final bool otherActionPending;

  @override
  Widget build(BuildContext context) {
    final source = returns.source;
    final result = returns.completed;
    final quote = returns.quote;
    return ApexPanel(
      borderColor: PosColors.rule,
      padding: EdgeInsets.all(
        MediaQuery.sizeOf(context).width >= 700 ? 22 : 14,
      ),
      child: Material(
        type: MaterialType.transparency,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: returns.posting ? null : back,
                icon: const Icon(Icons.arrow_back),
                label: const Text('Back to receipt'),
              ),
            ),
            PosPanelHeading(
              source == null ? 'Receipt return' : 'Return ${source.number}',
            ),
            const SizedBox(height: 9),
            if (returns.loadingSource || returns.posting)
              const LinearProgressIndicator(),
            if (otherActionPending && returns.pending == null)
              _note(
                'Resolve the saved checkout or register action before posting another return.',
              ),
            if (returns.storageError case final error?) ...[
              _note(error),
              OutlinedButton(
                onPressed: returns.recover,
                child: const Text('Check saved returns'),
              ),
            ],
            if (returns.error case final error?) _note(error),
            if (returns.pending != null) ...[
              _note(
                'The original return is awaiting confirmation. Retry it before issuing another refund.',
              ),
              FilledButton.icon(
                onPressed: returns.canRetry ? returns.submit : null,
                icon: const Icon(Icons.replay),
                label: const Text('Retry original return'),
              ),
            ] else if (result != null) ...[
              _note(
                result.active ? 'Return posted' : 'Return previously recorded',
              ),
              Text(
                'Credit note ${result.creditNumber} · ${posMoneyText(result.amount!)}',
              ),
              if (result.refundNumber.isNotEmpty)
                Text('Refund ${result.refundNumber}'),
            ] else if (source != null) ...[
              Text(source.customer),
              const SizedBox(height: 12),
              if (!returns.lines.any((line) => (line.quantity ?? 0) > 0))
                _note(
                  'No receipt lines have a confirmed quantity available to return.',
                ),
              for (final line in returns.lines) _quantity(line),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Return resellable items to stock'),
                value: returns.returnStock,
                onChanged: returns.editable
                    ? (value) => returns.changeOptions(returnStock: value)
                    : null,
              ),
              TextFormField(
                key: ValueKey('reason-${source.id}'),
                initialValue: returns.reason,
                enabled: returns.editable,
                maxLength: 200,
                decoration: const InputDecoration(
                  labelText: 'Return reason (optional)',
                ),
                onChanged: (value) => returns.changeOptions(reason: value),
              ),
              DropdownButtonFormField<PosReturnSettlement>(
                initialValue: returns.settlement,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Settlement'),
                onChanged: returns.editable
                    ? (value) => returns.changeOptions(settlement: value)
                    : null,
                items: const [
                  DropdownMenuItem(
                    value: PosReturnSettlement.credit,
                    child: Text('Keep as customer credit'),
                  ),
                  DropdownMenuItem(
                    value: PosReturnSettlement.cash,
                    child: Text('Cash refund'),
                  ),
                  DropdownMenuItem(
                    value: PosReturnSettlement.bank,
                    child: Text('Bank / UPI / card refund'),
                  ),
                ],
              ),
              if (returns.settlement == PosReturnSettlement.bank) ...[
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  initialValue: banks.any((bank) => bank.id == returns.bankId)
                      ? returns.bankId
                      : null,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Refund bank account',
                  ),
                  onChanged: returns.editable
                      ? (bank) => returns.changeOptions(bankId: bank)
                      : null,
                  items: [
                    for (final bank in banks)
                      DropdownMenuItem(value: bank.id, child: Text(bank.label)),
                  ],
                ),
              ],
              const SizedBox(height: 12),
              if (returns.quoteError case final error?) _note(error),
              if (returns.quoting) _note('Checking the return total…'),
              if (quote != null) ...[
                Semantics(
                  liveRegion: true,
                  child: Text(
                    'Return total ${posMoneyText(quote.paise)}',
                    style: const TextStyle(
                      fontFamily: 'DM Sans Display',
                      fontSize: 24,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -.6,
                      color: PosColors.totalText,
                    ),
                  ),
                ),
                if (returns.settlement != PosReturnSettlement.credit)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    value: returns.confirmed,
                    title: Text(
                      returns.settlement == PosReturnSettlement.cash
                          ? 'I handed this cash refund to the customer.'
                          : 'I confirmed this refund in the bank, UPI or card terminal.',
                    ),
                    onChanged: returns.editable && !otherActionPending
                        ? (value) => returns.confirm(value == true)
                        : null,
                  ),
              ],
              const SizedBox(height: 10),
              FilledButton(
                key: const ValueKey('pos-post-return'),
                onPressed: returns.ready && !otherActionPending
                    ? returns.submit
                    : null,
                child: const Text('Post return'),
              ),
            ] else if (!returns.loadingSource && returns.receiptId.isNotEmpty)
              OutlinedButton(
                onPressed: returns.reload,
                child: const Text('Reload receipt'),
              ),
          ],
        ),
      ),
    );
  }

  Widget _quantity(PosReturnLine line) {
    final available = line.quantity;
    final unit = line.unit.isEmpty ? 'units' : line.unit;
    final label =
        'Return quantity for ${line.description} (line ${line.index + 1})';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: ValueKey(line.index),
        initialValue: returns.quantities[line.index],
        decoration: InputDecoration(
          labelText: label,
          helperText: available == null
              ? (line.reason.isEmpty
                    ? 'Return quantity needs review'
                    : line.reason)
              : 'Available to return · ${line.available} $unit',
          helperMaxLines: 2,
        ),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        enabled: returns.editable && (available ?? 0) > 0,
        onChanged: (value) => returns.changeQuantity(line.index, value),
      ),
    );
  }

  Widget _note(String message) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Semantics(liveRegion: true, child: Text(message)),
  );
}
