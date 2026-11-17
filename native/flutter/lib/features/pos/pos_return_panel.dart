import 'package:material_ui/material_ui.dart';

import '../../ui/apex_widgets.dart';
import 'pos_models.dart';
import 'pos_return_controller.dart';
import 'pos_return_models.dart';
import 'pos_widgets.dart';

typedef PosDocumentDownload = Future<void> Function(String id, String number);

/// Return flow, worded like the web `PosReturn` dialog but shown inline.
class PosReturnPanel extends StatelessWidget {
  const PosReturnPanel({
    required this.returns,
    required this.banks,
    required this.back,
    required this.otherActionPending,
    this.download,
    super.key,
  });

  final PosReturnController returns;
  final List<PosBank> banks;
  final VoidCallback back;
  final bool otherActionPending;
  final PosDocumentDownload? download;

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
            if (source != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  source.customer,
                  style: const TextStyle(fontSize: 13, color: PosColors.muted),
                ),
              ),
            const SizedBox(height: 9),
            if (returns.loadingSource || returns.posting)
              const LinearProgressIndicator(),
            if (returns.loadingSource && source == null)
              _note('Checking quantities still eligible for return…'),
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
            if (returns.error case final error?) _note(error, error: true),
            if (returns.pending != null) ...[
              PosInfoBox(
                'The previous return response was not confirmed. Retry the original request before sending another refund.',
              ),
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: returns.canRetry ? returns.submit : null,
                icon: const Icon(Icons.replay),
                label: Text(returns.posting ? 'Posting return…' : 'Retry return'),
              ),
            ] else if (result != null)
              _result(result)
            else if (source != null) ...[
              PosFieldset(
                legend: 'Return items',
                children: [
                  for (final line in returns.lines) _quantity(line),
                  if (!returns.lines.any((line) => (line.quantity ?? 0) > 0))
                    const Text(
                      'No items have a confirmed returnable quantity.',
                    ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    controlAffinity: ListTileControlAffinity.leading,
                    title: const Text('Return resellable items to inventory'),
                    value: returns.returnStock,
                    onChanged: returns.editable
                        ? (value) =>
                              returns.changeOptions(returnStock: value == true)
                        : null,
                  ),
                  TextFormField(
                    key: ValueKey('reason-${source.id}'),
                    initialValue: returns.reason,
                    enabled: returns.editable,
                    maxLength: 200,
                    decoration: const InputDecoration(
                      labelText: 'Reason',
                      counterText: '',
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
                  if (returns.settlement == PosReturnSettlement.bank)
                    DropdownButtonFormField<String>(
                      initialValue: banks.any((bank) => bank.id == returns.bankId)
                          ? returns.bankId
                          : null,
                      isExpanded: true,
                      hint: const Text('Choose a bank account'),
                      decoration: const InputDecoration(
                        labelText: 'Refund bank account',
                      ),
                      onChanged: returns.editable
                          ? (bank) => returns.changeOptions(bankId: bank)
                          : null,
                      items: [
                        for (final bank in banks)
                          DropdownMenuItem(
                            value: bank.id,
                            child: Text(bank.label),
                          ),
                      ],
                    ),
                  if (returns.quoteError case final error?)
                    _note(error, error: true),
                  if (returns.quoting) _note('Checking return total…'),
                  if (quote != null)
                    PosInfoBox(
                      'Return total ${posMoneyText(quote.paise)}',
                    ),
                  if (quote != null && returns.settlement != PosReturnSettlement.credit)
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      value: returns.confirmed,
                      title: Text(
                        returns.settlement == PosReturnSettlement.cash
                            ? 'I am recording the cash paid out for this return.'
                            : 'I confirmed this refund in the bank, UPI or card terminal.',
                      ),
                      onChanged: returns.editable && !otherActionPending
                          ? (value) => returns.confirm(value == true)
                          : null,
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                alignment: WrapAlignment.end,
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton(
                    onPressed: returns.posting ? null : back,
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    key: const ValueKey('pos-post-return'),
                    onPressed: returns.ready && !otherActionPending
                        ? returns.submit
                        : null,
                    child: Text(
                      returns.posting ? 'Posting return…' : 'Post return',
                    ),
                  ),
                ],
              ),
            ] else if (!returns.loadingSource && returns.receiptId.isNotEmpty)
              OutlinedButton(
                onPressed: returns.reload,
                child: const Text('Retry loading receipt'),
              ),
          ],
        ),
      ),
    );
  }

  Widget _result(PosReturnResult result) {
    final credit = result.credit;
    final refund = result.refund;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: PosColors.successFill,
        border: Border.all(color: PosColors.successBorder),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 10,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.check_circle_outline,
                  size: 23,
                  color: PosColors.successText,
                ),
                const SizedBox(width: 11),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        result.active ? 'Return posted' : 'Return was cancelled',
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: PosColors.successText,
                        ),
                      ),
                      Text(
                        '${result.creditNumber}${refund != null ? ' · Refund ${result.refundNumber}${refund['posted'] == false ? ' · Cancelled' : ''}' : credit['posted'] != false ? ' · Retained as customer credit' : ''}',
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(0xff426454),
                        ),
                      ),
                      Text(
                        'Credit note ${result.creditNumber} · ${posMoneyText(result.amount!)}',
                        style: const TextStyle(
                          fontSize: 13,
                          color: Color(0xff426454),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (download != null)
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton(
                    onPressed: () =>
                        download!(posText(credit['id']), result.creditNumber),
                    child: const Text('Download credit note'),
                  ),
                  if (refund != null)
                    OutlinedButton(
                      onPressed: () =>
                          download!(posText(refund['id']), result.refundNumber),
                      child: const Text('Download refund voucher'),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _quantity(PosReturnLine line) {
    final available = line.quantity;
    final unit = line.unit.isEmpty ? 'units' : line.unit;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(
            '${line.description} · ${available == null ? 'Quantity needs review' : '${line.available} $unit remaining'}',
            style: const TextStyle(fontSize: 14, color: PosColors.ink),
          ),
        ),
        Semantics(
          label:
              'Return quantity for ${line.description} (line ${line.index + 1})',
          textField: true,
          child: TextFormField(
            key: ValueKey(line.index),
            initialValue: returns.quantities[line.index],
            decoration: InputDecoration(
              hintText: 'Quantity to return',
              helperText: line.reason.isEmpty ? null : line.reason,
              helperMaxLines: 2,
            ),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            enabled: returns.editable && (available ?? 0) > 0,
            onChanged: (value) => returns.changeQuantity(line.index, value),
          ),
        ),
      ],
    );
  }

  Widget _note(String message, {bool error = false}) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Semantics(
      liveRegion: true,
      child: Text(
        message,
        style: error
            ? const TextStyle(color: Color(0xff9b2d1a), fontSize: 14)
            : null,
      ),
    ),
  );
}
