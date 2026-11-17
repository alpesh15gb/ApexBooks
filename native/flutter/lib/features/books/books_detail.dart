import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'register_query.dart' show registerSettlement;
import 'books_entry_draft.dart' show BooksTextFallback, booksDecimal, booksParsePaise;

class BooksRecordDetail extends StatefulWidget {
  const BooksRecordDetail({
    required this.data,
    required this.id,
    required this.onBack,
    required this.onOpen,
    required this.backLabel,
    this.actions,
    super.key,
  });

  final BooksData data;
  final String id;
  final VoidCallback onBack;
  final ValueChanged<String> onOpen;
  final String backLabel;
  final Widget Function(BooksRecord record)? actions;

  @override
  State<BooksRecordDetail> createState() => _BooksRecordDetailState();
}

class _BooksRecordDetailState extends State<BooksRecordDetail> {
  late Future<BooksRecord> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.data.record(widget.id);
  }

  void _retry() => setState(() => _future = widget.data.record(widget.id));

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1200),
        child: FutureBuilder<BooksRecord>(
          future: _future,
          builder: (context, snapshot) {
            final row = snapshot.data;
            return LayoutBuilder(
              builder: (context, constraints) {
                final wide =
                    constraints.maxWidth >=
                    MediaQuery.textScalerOf(context).scale(820);
                return ListView(
                  padding: EdgeInsets.all(wide ? 24 : 16),
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: widget.onBack,
                        icon: const Icon(Icons.arrow_back),
                        label: Text(widget.backLabel),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (snapshot.connectionState != ConnectionState.done)
                      const LinearProgressIndicator(
                        semanticsLabel: 'Loading transaction details',
                      )
                    else if (row == null)
                      ListTile(
                        title: const Text('Could not load this transaction.'),
                        trailing: TextButton(
                          onPressed: _retry,
                          child: const Text('Retry'),
                        ),
                      )
                    else if (row.kind == 'item')
                      _itemContent(context, row)
                    else
                      ..._content(context, row, wide: wide),
                  ],
                );
              },
            );
          },
        ),
      ),
    );
  }

  /// Stored amounts, like the web's "Document totals" section. Nothing is estimated.
  Widget _documentTotals(BooksRecord row) {
    final data = row.data;
    bool known(String key) => booksParsePaise(data[key]) != null;
    final ready = const ['taxable', 'cgst', 'sgst', 'igst', 'round_off'].every(known);
    if (!ready) {
      return const ApexPanel(
        child: Padding(
          padding: EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 6,
            children: [
              Text('Document totals', style: Apex.panelTitle),
              Text(
                'Stored subtotal and tax breakdown are unavailable for this record. The document total above is retained; no tax breakdown has been estimated.',
                style: Apex.note,
              ),
            ],
          ),
        ),
      );
    }
    bool nonZero(String key) =>
        (booksParsePaise(data[key]) ?? BigInt.zero) != BigInt.zero;
    final rows = <(String, Object?)>[
      ('Subtotal after discounts', data['taxable']),
      for (final key in ['cgst', 'sgst', 'igst'])
        if (nonZero(key))
          (key == 'sgst' ? 'SGST / UTGST' : key.toUpperCase(), data[key]),
      if (known('supplier_tax') && nonZero('supplier_tax'))
        ('Supplier tax (unclassified)', data['supplier_tax']),
      if (nonZero('round_off')) ('Round off', data['round_off']),
      ('Document total', row.json['amount']),
    ];
    return ApexPanel(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 8,
          children: [
            const Text('Document totals', style: Apex.panelTitle),
            for (final (label, value) in rows)
              Row(
                children: [
                  Expanded(child: Text(label, style: Apex.note)),
                  Text(booksMoney(value), style: Apex.strong),
                ],
              ),
            const Text(
              'Stored document amounts. Line and document discounts shown above are already included in the subtotal. These figures do not establish GST eligibility or filing status.',
              style: Apex.note,
            ),
          ],
        ),
      ),
    );
  }

  Widget _itemContent(BuildContext context, BooksRecord row) {
    final theme = Theme.of(context);
    final item = row.data;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(row.party, style: theme.textTheme.headlineSmall),
        Chip(
          label: Text(
            item['is_active'] == false ? 'Archived item' : 'Active item',
          ),
        ),
        Card(
          child: Column(
            children: [
              for (final (label, value) in [
                ('SKU', booksText(item['sku'])),
                ('Barcode', booksText(item['barcode'])),
                ('HSN/SAC', booksText(item['hsn'])),
                ('Unit', booksText(item['unit'])),
                ('Sale rate', _moneyIfPresent(item['sale_rate'])),
                ('Purchase rate', _moneyIfPresent(item['purchase_rate'])),
              ])
                if (value.isNotEmpty)
                  ListTile(title: Text(label), subtitle: Text(value)),
            ],
          ),
        ),
      ],
    );
  }

  List<Widget> _content(
    BuildContext context,
    BooksRecord row, {
    required bool wide,
  }) {
    final data = row.data;
    final lines = data['lines'] == null
        ? const <BooksJson>[]
        : booksRows(data['lines']);
    final trail = row.json['document_trail'] == null
        ? const <BooksJson>[]
        : booksRows(row.json['document_trail']);
    final allocations = row.json['allocations'] == null
        ? const <BooksJson>[]
        : booksRows(row.json['allocations']);
    final noTax = [
      data['cgst'],
      data['sgst'],
      data['igst'],
    ].every((value) => (booksParsePaise(value) ?? BigInt.zero) == BigInt.zero);
    final fields = <(String, String)>[
      ('Date', row.date),
      ('Due date', booksText(data['due_date'])),
      ('Reference', booksText(data['reference'])),
      ('Advance remaining', _moneyIfPresent(row.json['advance_remaining'])),
      ('Credit remaining', _moneyIfPresent(row.json['credit_remaining'])),
      // Like the web app, a document without GST (or a receipt) does not show empty tax boxes.
      if (!noTax || lines.isNotEmpty)
        ('Taxable', _moneyIfPresent(data['taxable'])),
      if (!noTax) ...[
        ('CGST', _moneyIfPresent(data['cgst'])),
        ('SGST', _moneyIfPresent(data['sgst'])),
        ('IGST', _moneyIfPresent(data['igst'])),
      ],
      ('Bank amount', _moneyIfPresent(data['bank_amount'])),
      ('Cash amount', _moneyIfPresent(data['cash_amount'])),
      ('Cash tendered', _moneyIfPresent(data['tender_amount'])),
      ('Change', _moneyIfPresent(data['change_amount'])),
    ];
    final notes = booksText(data['notes']);
    final identity = Column(
      spacing: 8,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (row.number.isNotEmpty)
              Text(
                booksKindLabel(row.kind),
                style: Apex.eyebrow.copyWith(color: Apex.greenText),
              ),
            _Status(status: row.status),
            if (registerSettlement(row) case final settlement
                when settlement.isNotEmpty)
              Text(settlement, style: Apex.small),
          ],
        ),
        Semantics(
          header: true,
          child: Text(row.label, style: Apex.registerTitle),
        ),
        if (row.party.isNotEmpty) Text(row.party, style: Apex.panelTitle),
        Wrap(
          spacing: 20,
          runSpacing: 6,
          children: [
            for (final (label, value) in fields.take(3))
              if (value.isNotEmpty) _Fact(label: label, value: value),
          ],
        ),
      ],
    );
    final amounts = Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Apex.tint,
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
      child: Wrap(
        spacing: 24,
        runSpacing: 10,
        children: [
          _Fact(
            label: 'Total',
            value: booksMoney(row.json['amount']),
            prominent: true,
          ),
          if (_moneyIfPresent(row.json['outstanding']) case final balance
              when balance.isNotEmpty)
            _Fact(
              label: 'Current outstanding',
              value: balance,
              prominent: true,
            ),
        ],
      ),
    );
    return [
      ApexPanel(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: 14,
            children: [
              if (wide)
                Row(
                  spacing: 24,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 3, child: identity),
                    Expanded(flex: 2, child: amounts),
                  ],
                )
              else ...[
                identity,
                amounts,
              ],
              if (fields.skip(3).any((field) => field.$2.isNotEmpty))
                Wrap(
                  spacing: 24,
                  runSpacing: 10,
                  children: [
                    for (final (label, value) in fields.skip(3))
                      if (value.isNotEmpty) _Fact(label: label, value: value),
                  ],
                ),
            ],
          ),
        ),
      ),
      if (row.json['cancelled'] == true)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Apex.tint,
              border: Border.all(color: Apex.line),
              borderRadius: BorderRadius.circular(Apex.radiusPanel),
            ),
            child: Text(
              'Cancelled. ${booksText(data['cancelled'] is Map ? (data['cancelled'] as Map)['reason'] : null).ifEmpty('No reason recorded')}. The number ${row.number} stays in your records; its ledger, stock and balance effects were reversed.',
            ),
          ),
        ),
      if (widget.actions case final actions?)
        Padding(padding: const EdgeInsets.only(top: 8), child: actions(row)),
      if (lines.isNotEmpty) ...[
        const SizedBox(height: 16),
        ApexPanel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.all(14),
                child: Semantics(
                  header: true,
                  child: Row(
                    children: [
                      const Expanded(
                        child: Text('Items & services', style: Apex.panelTitle),
                      ),
                      Text(
                        '${lines.length} line${lines.length == 1 ? '' : 's'}',
                        style: Apex.note,
                      ),
                    ],
                  ),
                ),
              ),
              if (wide)
                ColoredBox(
                  color: Apex.tableHead,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 10,
                    ),
                    child: _LineColumns(
                      textStyle: Apex.tableHeader,
                      description: const Text('Description'),
                      quantity: 'Quantity',
                      rate: 'Unit rate',
                      amount: 'Amount',
                    ),
                  ),
                ),
              for (final (index, line) in lines.indexed) ...[
                if (index > 0 || !wide) const Divider(height: 1),
                _Line(line: line, wide: wide),
              ],
            ],
          ),
        ),
      ],
      if (lines.isNotEmpty) ...[
        const SizedBox(height: 16),
        _documentTotals(row),
      ],
      if (row.kind == 'purchase_bill' &&
          booksText(data['purchase_order_id']).isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('Purchase order', style: Apex.panelTitle),
        const SizedBox(height: 6),
        const Text(
          'This bill records goods received against a purchase order.',
          style: Apex.note,
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: () => widget.onOpen(booksText(data['purchase_order_id'])),
            icon: const Icon(Icons.arrow_forward, size: 16),
            label: const Text('View source order'),
          ),
        ),
      ],
      const SizedBox(height: 16),
      const Text('Payment & document trail', style: Apex.panelTitle),
      const SizedBox(height: 6),
      for (final entry in trail) _TrailLink(entry: entry, onOpen: widget.onOpen),
      if (trail.isEmpty && allocations.isEmpty)
        const Text(
          'No linked payment or conversion appears in this record.',
          style: Apex.note,
        ),
      const SizedBox(height: 6),
      const Text(
        'Recording a payment, settling an invoice and matching a bank statement are separate steps. Downloading or printing never posts another transaction.',
        style: Apex.note,
      ),
      if (notes.isNotEmpty) ...[
        const SizedBox(height: 16),
        const Text('Notes', style: Apex.panelTitle),
        const SizedBox(height: 6),
        Text(notes, style: Apex.lead.copyWith(color: Apex.inkSoft)),
      ],
      const SizedBox(height: 20),
      Container(
        padding: const EdgeInsets.only(top: 12),
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: Apex.line)),
        ),
        child: Row(
          children: [
            const Icon(Icons.check_circle_outline, size: 16, color: Apex.greenText),
            const SizedBox(width: 6),
            const Expanded(
              child: Text('Your original record stays in history', style: Apex.note),
            ),
            OutlinedButton(
              onPressed: widget.onBack,
              child: const Text('Back to register'),
            ),
          ],
        ),
      ),
      if (allocations.isNotEmpty && trail.isEmpty) ...[
        const SizedBox(height: 16),
        const Text('Payment allocations', style: Apex.panelTitle),
        const SizedBox(height: 6),
        for (final allocation in allocations)
          ListTile(
            title: Text(booksMoney(allocation['amount'])),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => widget.onOpen(booksText(allocation['document_id'])),
          ),
      ],
    ];
  }
}

String _moneyIfPresent(Object? value) =>
    booksText(value).isEmpty ? '' : booksMoney(value);

class _Fact extends StatelessWidget {
  const _Fact({
    required this.label,
    required this.value,
    this.prominent = false,
  });

  final String label;
  final String value;
  final bool prominent;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      spacing: 3,
      children: [
        Text(label, style: Apex.note.copyWith(height: 1.3)),
        Text(
          value,
          style: prominent
              ? Apex.money.copyWith(fontSize: 24)
              : const TextStyle(fontSize: 14, color: Apex.ink),
        ),
      ],
    );
  }
}

class _Status extends StatelessWidget {
  const _Status({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) => ApexStatusBadge(
    status,
    tone: switch (status) {
      'Posted' => ApexBadgeTone.posted,
      'Cancelled' => ApexBadgeTone.cancelled,
      'Converted' => ApexBadgeTone.converted,
      'Draft' || 'Open draft' => ApexBadgeTone.draft,
      _ => ApexBadgeTone.neutral,
    },
  );
}

class _LineColumns extends StatelessWidget {
  const _LineColumns({
    required this.description,
    required this.quantity,
    required this.rate,
    required this.amount,
    this.textStyle,
  });

  final Widget description;
  final String quantity;
  final String rate;
  final String amount;
  final TextStyle? textStyle;

  @override
  Widget build(BuildContext context) => Row(
    spacing: 10,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Expanded(flex: 5, child: description),
      for (final value in [quantity, rate, amount])
        Expanded(
          flex: 2,
          child: Text(
            value.isEmpty ? '—' : value,
            textAlign: TextAlign.end,
            style: textStyle,
          ),
        ),
    ],
  );
}

class _Line extends StatelessWidget {
  const _Line({required this.line, required this.wide});
  final BooksJson line;
  final bool wide;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final quantity = [
      booksText(line['quantity']),
      booksText(line['unit']),
    ].where((value) => value.isNotEmpty).join(' ');
    final rate = _moneyIfPresent(line['rate']);
    final taxable = booksParsePaise(line['taxable']);
    final tax = booksParsePaise(line['tax']);
    final amount = taxable == null || tax == null
        ? ''
        : booksMoney(booksDecimal(taxable + tax));
    final details = <String>[
      if (!wide) ...[
        if (quantity.isNotEmpty) quantity,
        if (rate.isNotEmpty) '$rate per unit',
      ],
      if (booksText(line['taxable']).isNotEmpty &&
          (!wide || tax != BigInt.zero))
        '${booksMoney(line['taxable'])} taxable',
      if (tax != null && tax != BigInt.zero) '${booksMoney(line['tax'])} tax',
      if (booksText(line['hsn']).isNotEmpty)
        'HSN/SAC ${booksText(line['hsn'])}',
    ];
    final description = booksText(line['description']);
    final name = booksText(line['name']);
    final lineSummary = Column(
      spacing: 3,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          name.isNotEmpty
              ? name
              : description.isNotEmpty
              ? description
              : 'Line item',
          style: Apex.strong,
        ),
        for (final info in [
          if (description.isNotEmpty && name != description && name.isNotEmpty)
            description,
          if (details.isNotEmpty) details.join(' · '),
        ])
          Text(info, style: Apex.note.copyWith(height: 1.4)),
      ],
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: wide
          ? _LineColumns(
              description: lineSummary,
              quantity: quantity,
              rate: rate,
              amount: amount,
              textStyle: theme.textTheme.bodyMedium,
            )
          : Column(
              spacing: 6,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                lineSummary,
                if (amount.isNotEmpty)
                  Text('Amount  $amount', style: Apex.strong),
              ],
            ),
    );
  }
}

class _TrailLink extends StatelessWidget {
  const _TrailLink({required this.entry, required this.onOpen});
  final BooksJson entry;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    final id = booksText(entry['id']);
    final number = booksText(entry['number']);
    final kind = booksKindLabel(booksText(entry['kind']));
    final relations = entry['relations'];
    final labels = [
      if (relations is List)
        ...relations.map(booksText).where((value) => value.isNotEmpty),
      if (entry['cancelled'] == true) 'Cancelled',
      if (entry['allocated_amount'] != null)
        '${booksMoney(entry['allocated_amount'])} allocated',
      if (entry['historical_allocated_amount'] != null)
        '${booksMoney(entry['historical_allocated_amount'])} formerly allocated',
    ];
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
        side: const BorderSide(color: Apex.line),
      ),
      child: ListTile(
        leading: const ApexIconTile(Icons.description_outlined),
        title: Text(number.isNotEmpty ? number : kind),
        subtitle: Text(
          [
            kind,
            booksText(entry['date']),
            ...labels,
          ].where((value) => value.isNotEmpty).join(' · '),
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: id.isEmpty ? null : () => onOpen(id),
      ),
    );
  }
}
