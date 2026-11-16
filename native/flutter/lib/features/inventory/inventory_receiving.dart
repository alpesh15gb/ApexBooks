import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import '../books/books_detail.dart';
import 'inventory_models.dart';
import 'inventory_posting.dart';
import 'inventory_widgets.dart';

class InventoryReceivingPage extends StatefulWidget {
  const InventoryReceivingPage({
    required this.posting,
    required this.order,
    required this.today,
    super.key,
  });

  final InventoryPosting posting;
  final InventoryJson order;
  final String today;

  @override
  State<InventoryReceivingPage> createState() => _InventoryReceivingPageState();
}

class _InventoryReceivingPageState extends State<InventoryReceivingPage> {
  late Future<InventoryJson> _snapshot;
  late String _date;
  String _dueDate = '';
  String _number = '';
  String _notes = '';
  String? _error;
  String? _saved;
  String _savedBillId = '';
  bool _editing = false;
  bool _quoting = false;
  final _quantities = <int, String>{};
  final _overrides = <int, InventoryJson>{};
  ({InventoryJson body, InventoryJson result})? _quote;

  InventoryPosting get _posting => widget.posting;
  WorkspaceContext get _workspace => _posting.workspace;
  String get _id => inventoryText(widget.order['id']);
  String get _path =>
      '${_posting.base}/purchase-orders/${Uri.encodeComponent(_id)}';
  bool get _supported =>
      _workspace.features.contains('purchase_order_receiving');
  bool get _canWrite => _workspace.company.canWrite;
  bool get _pendingHere =>
      _posting.pending?.kind == 'receipt' && _posting.pending?.recordId == _id;

  @override
  void initState() {
    super.initState();
    _date = widget.today;
    _snapshot = _load();
  }

  Future<InventoryJson> _load() async => _supported
      ? inventoryObject(await _workspace.api.get('$_path/receiving'))
      : const {};

  void _edit(VoidCallback change) => setState(() {
    change();
    _quote = null;
    _error = null;
  });

  void _reload() => setState(() {
    _snapshot = _load();
    _error = null;
    _quote = null;
    _editing = false;
    _quantities.clear();
    _overrides.clear();
  });

  InventoryJson _request(InventoryJson snapshot) {
    final selections = <InventoryJson>[];
    for (final line in inventoryRows(snapshot['lines'])) {
      final index = line['line_index'] as int;
      final input = _quantities[index]?.trim() ?? '';
      if (input.isEmpty) continue;
      final quantity = inventoryDecimal(input, 3);
      final remaining = inventoryDecimal(
        inventoryQuantity(line['remaining_quantity']),
        3,
      );
      if (quantity == null || remaining == null || quantity > remaining) {
        throw FormatException(
          'Enter a quantity up to ${inventoryQuantity(line['remaining_quantity'])} for ${line['description']}.',
        );
      }
      if (quantity == BigInt.zero) continue;
      final changes = <String, dynamic>{};
      for (final entry in (_overrides[index] ?? {}).entries) {
        final value = entry.value;
        if (value is String && value.trim().isEmpty || value == null) continue;
        if (const {'rate', 'discount_amount', 'gst_rate'}.contains(entry.key)) {
          final money = inventoryDecimal(inventoryText(value), 2);
          if (money == null ||
              entry.key == 'gst_rate' && money > BigInt.from(10000)) {
            throw FormatException(
              'Review the rate, GST and discount for ${line['description']}.',
            );
          }
        }
        changes[entry.key] = value is String ? value.trim() : value;
      }
      selections.add({'line_index': index, 'quantity': input, ...changes});
    }
    if (selections.isEmpty) {
      throw const FormatException(
        'Enter a received quantity on at least one line.',
      );
    }
    return {
      'source_version': snapshot['source_version'],
      'date': _date,
      if (_number.trim().isNotEmpty) 'number': _number.trim(),
      if (_dueDate.isNotEmpty) 'due_date': _dueDate,
      if (_notes.trim().isNotEmpty) 'notes': _notes.trim(),
      'lines': selections,
    };
  }

  Future<void> _review(InventoryJson snapshot) async {
    setState(() {
      _quoting = true;
      _error = null;
      _quote = null;
    });
    try {
      final body = _request(snapshot);
      final result = inventoryObject(
        await _workspace.api.post('$_path/receipts/preview', body: body),
      );
      if (inventoryText(result['amount']).isEmpty) {
        throw const FormatException('The server did not provide a bill total.');
      }
      if (mounted) setState(() => _quote = (body: body, result: result));
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _quoting = false);
    }
  }

  Future<void> _post() async {
    setState(() => _error = null);
    try {
      final InventoryJson result;
      if (_pendingHere) {
        result = await _posting.retry();
      } else {
        final quote = _quote;
        if (quote == null) return;
        result = await _posting.submit(
          'receipt',
          _id,
          inventoryText(widget.order['number']),
          {...quote.body, 'expected_total': quote.result['amount']},
        );
      }
      if (!mounted) return;
      _reload();
      setState(() {
        _saved = inventorySavedMessage(result, 'receipt');
        _savedBillId = inventoryText(result['id']);
        _number = '';
        _notes = '';
        _dueDate = '';
      });
      await _workspace.refresh();
    } catch (failure) {
      if (!mounted) return;
      if (failure is ApexApiException &&
          requiresInventoryReview(failure, 'receipt') &&
          _posting.pending == null) {
        _reload();
      }
      setState(() => _error = inventoryError(failure));
    }
  }

  Future<void> _pickDate({required bool due}) async {
    final today = DateTime.parse(widget.today);
    final orderDate =
        DateTime.tryParse(inventoryText(widget.order['date'])) ?? today;
    final earliest = due ? DateTime.parse(_date) : orderDate;
    final latest = due ? DateTime(today.year + 20, 12, 31) : today;
    if (earliest.isAfter(latest)) return;
    final current = DateTime.tryParse(due ? _dueDate : _date) ?? earliest;
    final initial = current.isBefore(earliest) || current.isAfter(latest)
        ? earliest
        : current;
    final selected = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: earliest,
      lastDate: latest,
      currentDate: today,
    );
    if (selected != null && mounted) {
      _edit(() {
        final isoDate = selected.toIso8601String().substring(0, 10);
        if (due) {
          _dueDate = isoDate;
        } else {
          _date = isoDate;
          if (_dueDate.isNotEmpty && _dueDate.compareTo(_date) < 0) {
            _dueDate = '';
          }
        }
      });
    }
  }

  void _openBill(String id) {
    if (id.isEmpty) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => Scaffold(
          body: SafeArea(
            child: BooksRecordDetail(
              data: BooksData(_workspace.company.id, _workspace.api.get),
              id: id,
              onBack: () => Navigator.of(context).pop(),
              onOpen: _openBill,
              backLabel: 'Return to receiving',
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _posting,
    builder: (context, _) {
      final order = widget.order;
      final available =
          _canWrite && _posting.loaded && _posting.recoveryError == null;
      final canEdit =
          available && _posting.pending == null && !_posting.busy && !_quoting;
      return PopScope(
        canPop: !_posting.busy,
        child: Scaffold(
          backgroundColor: Apex.paper,
          appBar: AppBar(
            title: const Text('Purchase order'),
            actions: [
              IconButton(
                tooltip: 'Refresh order quantities',
                onPressed: _posting.busy || _quoting ? null : _reload,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          body: FutureBuilder<InventoryJson>(
            future: _snapshot,
            builder: (context, state) {
              final snapshot = state.data ?? const <String, dynamic>{};
              final status = inventoryText(snapshot['status']);
              final lines = inventoryRows(snapshot['lines']);
              final receipts = inventoryRows(snapshot['receipts']);
              final receiving =
                  const {'open', 'partial'}.contains(status) &&
                  state.connectionState == ConnectionState.done;
              final pending = _posting.pending;
              final quote = _quote;
              return SafeArea(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
                        children: [
                          _receivingWidth(
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                _orderSummary(order, status),
                                const SizedBox(height: 16),
                                if (_saved != null)
                                  InventoryNotice(
                                    text: _saved!,
                                    action: _savedBillId.isEmpty
                                        ? null
                                        : TextButton(
                                            onPressed: () =>
                                                _openBill(_savedBillId),
                                            child: const Text(
                                              'View supplier bill',
                                            ),
                                          ),
                                  ),
                                if (_error != null &&
                                    !(_editing &&
                                        receiving &&
                                        pending == null &&
                                        available))
                                  InventoryNotice(text: _error!),
                                if (!_supported)
                                  const InventoryNotice(
                                    text: 'Partial receiving is unavailable on this server.',
                                  ),
                                if (status == 'unavailable')
                                  InventoryNotice(
                                    text: inventoryText(snapshot['reason']),
                                  ),
                                if (pending != null)
                                  InventoryNotice(
                                    text: _pendingHere
                                        ? 'The previous bill is awaiting confirmation.'
                                        : 'Complete the pending inventory request before posting another.',
                                    action: _pendingHere && available
                                        ? TextButton(
                                            onPressed: _posting.busy
                                                ? null
                                                : _post,
                                            child: const Text(
                                              'Retry original bill',
                                            ),
                                          )
                                        : null,
                                  ),
                                if (state.connectionState !=
                                    ConnectionState.done)
                                  const LinearProgressIndicator(),
                                if (state.hasError)
                                  InventoryNotice(
                                    text: inventoryError(state.error!),
                                  ),
                                if (_editing && receiving)
                                  _billDetails(canEdit),
                                if (lines.isNotEmpty)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 8),
                                    child: Text(
                                      'Order lines',
                                      style: Apex.sectionTitle,
                                    ),
                                  ),
                                for (final line in lines)
                                  _line(line, receiving && _editing, canEdit),
                                if (quote != null && pending == null)
                                  _reviewLines(quote.result),
                                if (receipts.isNotEmpty) ...[
                                  const SizedBox(height: 20),
                                  Text(
                                    'Supplier bills',
                                    style: Apex.sectionTitle,
                                  ),
                                  for (final receipt in receipts)
                                    ListTile(
                                      key: ValueKey(
                                        'receiving-bill-${receipt['id']}',
                                      ),
                                      title: Text(
                                        inventoryText(receipt['number']),
                                      ),
                                      subtitle: Text(
                                        '${receipt['date']}${receipt['cancelled'] == true ? ' · Cancelled' : ''}',
                                      ),
                                      trailing: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          _money(
                                            inventoryAmount(receipt['amount']),
                                          ),
                                          const SizedBox(width: 10),
                                          const Icon(Icons.chevron_right),
                                        ],
                                      ),
                                      onTap: () => _openBill(
                                        inventoryText(receipt['id']),
                                      ),
                                    ),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (receiving && pending == null && available)
                      _footer(snapshot, quote?.result, canEdit),
                  ],
                ),
              );
            },
          ),
        ),
      );
    },
  );

  Widget _receivingWidth(Widget child) => Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 920),
      child: SizedBox(width: double.infinity, child: child),
    ),
  );

  Widget _orderSummary(InventoryJson order, String status) {
    final (label, tone) = switch (status) {
      'open' => ('Awaiting delivery', ApexBadgeTone.draft),
      'partial' => ('Partially received', ApexBadgeTone.draft),
      'received' => ('Fully received', ApexBadgeTone.posted),
      'converted' => ('Converted to bill', ApexBadgeTone.converted),
      'unavailable' => ('Full-order billing', ApexBadgeTone.neutral),
      _ => ('', ApexBadgeTone.neutral),
    };
    return ApexPanel(
      padding: const EdgeInsets.all(20),
      child: Padding(
        padding: EdgeInsets.zero,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final wide = constraints.maxWidth >= 540;
            final supplier = Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(inventoryText(order['name']), style: Apex.sectionTitle),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 12,
                  runSpacing: 4,
                  children: [
                    Text(inventoryText(order['number']), style: Apex.strong),
                    Text('Ordered ${order['date']}', style: Apex.note),
                  ],
                ),
              ],
            );
            final totals = Wrap(
              spacing: 20,
              runSpacing: 10,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (label.isNotEmpty) ApexStatusBadge(label, tone: tone),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: wide
                      ? CrossAxisAlignment.end
                      : CrossAxisAlignment.start,
                  children: [
                    const Text('Order total', style: Apex.small),
                    _money(inventoryAmount(order['amount'])),
                  ],
                ),
              ],
            );
            return wide
                ? Row(
                    children: [
                      Expanded(child: supplier),
                      const SizedBox(width: 16),
                      totals,
                    ],
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [supplier, const SizedBox(height: 12), totals],
                  );
          },
        ),
      ),
    );
  }

  Widget _footer(InventoryJson snapshot, InventoryJson? review, bool enabled) {
    final theme = Theme.of(context);
    final button = !_editing
        ? FilledButton.icon(
            key: const ValueKey('receiving-start'),
            onPressed: enabled ? () => _edit(() => _editing = true) : null,
            icon: const Icon(Icons.inventory_2_outlined),
            label: const Text('Receive items'),
          )
        : review == null
        ? FilledButton(
            key: const ValueKey('receiving-review'),
            onPressed: enabled ? () => _review(snapshot) : null,
            child: Text(_quoting ? 'Reviewing bill…' : 'Review supplier bill'),
          )
        : FilledButton.icon(
            key: const ValueKey('receiving-post'),
            onPressed: enabled ? _post : null,
            icon: const Icon(Icons.check),
            label: const Text('Post supplier bill'),
          );
    final total = review == null
        ? null
        : Text(
            'Supplier bill total ${inventoryAmount(review['amount'])}',
            style: Apex.sectionTitle,
          );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(
          top: BorderSide(color: theme.colorScheme.outlineVariant),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
        child: _receivingWidth(
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 540;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_editing && _error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        _error!,
                        style: TextStyle(color: theme.colorScheme.error),
                      ),
                    ),
                  if (wide)
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (total != null) Expanded(child: total),
                        button,
                      ],
                    )
                  else ...[
                    ?total,
                    button,
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _billDetails(bool enabled) {
    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Apex.mintSoft,
        border: Border.all(color: Apex.mintLine),
        borderRadius: BorderRadius.circular(13),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('Supplier bill', style: Apex.sectionTitle),
          const SizedBox(height: 12),
          _receivingFields(
            _dateField(enabled, due: false),
            TextFormField(
              key: const ValueKey('receiving-bill-reference'),
              initialValue: _number,
              enabled: enabled,
              maxLength: 16,
              decoration: const InputDecoration(
                labelText: 'Supplier bill reference (optional)',
                counterText: '',
              ),
              onChanged: (value) => _edit(() => _number = value),
            ),
          ),
          const SizedBox(height: 12),
          _receivingFields(
            _dateField(enabled, due: true),
            TextFormField(
              initialValue: _notes,
              enabled: enabled,
              maxLength: 4000,
              maxLines: 2,
              decoration: const InputDecoration(
                labelText: 'Notes (optional)',
                counterText: '',
              ),
              onChanged: (value) => _edit(() => _notes = value),
            ),
          ),
        ],
      ),
    );
  }

  Widget _dateField(bool enabled, {required bool due}) => Row(
    children: [
      Expanded(
        child: OutlinedButton.icon(
          onPressed: enabled ? () => _pickDate(due: due) : null,
          icon: Icon(
            due ? Icons.event_available_outlined : Icons.event_outlined,
          ),
          label: Text(
            due
                ? (_dueDate.isEmpty ? 'Set due date' : 'Due date $_dueDate')
                : 'Bill date $_date',
          ),
        ),
      ),
      if (due && _dueDate.isNotEmpty)
        IconButton(
          tooltip: 'Clear due date',
          onPressed: enabled ? () => _edit(() => _dueDate = '') : null,
          icon: const Icon(Icons.clear),
        ),
    ],
  );

  Widget _receivingFields(Widget first, Widget second) => LayoutBuilder(
    builder: (context, constraints) => constraints.maxWidth >= 520
        ? Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: first),
              const SizedBox(width: 12),
              Expanded(child: second),
            ],
          )
        : Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [first, const SizedBox(height: 10), second],
          ),
  );

  Widget _line(InventoryJson line, bool editing, bool enabled) {
    final index = line['line_index'] as int;
    final unit = inventoryText(line['unit']);
    final remaining = inventoryQuantity(line['remaining_quantity']);
    final hasBalance =
        (inventoryDecimal(remaining, 3) ?? BigInt.zero) > BigInt.zero;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: ApexPanel(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(inventoryText(line['description']), style: Apex.strong),
            const SizedBox(height: 6),
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 12,
              runSpacing: 6,
              children: [
                ApexStatusBadge(
                  'Remaining $remaining $unit'.trim(),
                  tone: hasBalance
                      ? ApexBadgeTone.draft
                      : ApexBadgeTone.neutral,
                ),
                Text(
                  'Ordered ${inventoryQuantity(line['ordered_quantity'])}',
                  style: Apex.note,
                ),
                Text(
                  'Received ${inventoryQuantity(line['received_quantity'])}',
                  style: Apex.note,
                ),
                Text(
                  'Order rate ${inventoryAmount(line['rate'])}',
                  style: Apex.note,
                ),
              ],
            ),
            if (editing && hasBalance) ...[
              const SizedBox(height: 12),
              _receivingFields(
                TextFormField(
                  key: ValueKey('receiving-quantity-$index'),
                  initialValue: _quantities[index],
                  enabled: enabled,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: InputDecoration(
                    labelText: 'Quantity received for ${line['description']}',
                  ),
                  onChanged: (value) => _edit(() => _quantities[index] = value),
                ),
                _lineField(
                  index,
                  'rate',
                  'Unit price (₹)',
                  inventoryAmount(line['rate']),
                  enabled,
                ),
              ),
              Material(
                type: MaterialType.transparency,
                child: ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: const Text('Discount and tax'),
                  children: [
                    _lineField(
                      index,
                      'discount_amount',
                      'Fixed discount on this bill',
                      'Use the order discount',
                      enabled,
                    ),
                    _lineField(
                      index,
                      'gst_rate',
                      'GST rate (%)',
                      '${line['gst_rate']}%',
                      enabled,
                    ),
                    _lineDropdown(
                      index,
                      'tax_treatment',
                      'Tax treatment',
                      const {
                        'taxable': 'Taxable',
                        'nil_rated': 'Nil rated',
                        'exempt': 'Exempt',
                        'non_gst': 'Non-GST',
                      },
                      enabled,
                    ),
                    _lineDropdown(
                      index,
                      'itc_treatment',
                      'Input tax credit',
                      const {
                        'pending_review': 'Pending review',
                        'ineligible': 'Ineligible',
                      },
                      enabled,
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Supplier rate includes GST'),
                      value:
                          (_overrides[index]?['price_includes_tax'] ??
                              line['price_includes_tax']) ==
                          true,
                      onChanged: enabled
                          ? (value) =>
                                _override(index, 'price_includes_tax', value)
                          : null,
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  void _override(int index, String field, Object? value) =>
      _edit(() => _overrides.putIfAbsent(index, () => {})[field] = value);

  Widget _lineField(
    int index,
    String name,
    String label,
    String hint,
    bool enabled,
  ) => TextFormField(
    key: ValueKey('receiving-$name-$index'),
    initialValue: _overrides[index]?[name] as String?,
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
    enabled: enabled,
    decoration: InputDecoration(labelText: label, hintText: hint),
    onChanged: (value) => _override(index, name, value),
  );

  Widget _lineDropdown(
    int index,
    String name,
    String label,
    Map<String, String> values,
    bool enabled,
  ) => DropdownButtonFormField<String>(
    initialValue: _overrides[index]?[name] as String? ?? '',
    decoration: InputDecoration(labelText: label),
    items: [
      const DropdownMenuItem(value: '', child: Text('Use order value')),
      for (final entry in values.entries)
        DropdownMenuItem(value: entry.key, child: Text(entry.value)),
    ],
    onChanged: enabled ? (value) => _override(index, name, value) : null,
  );

  Widget _reviewLines(InventoryJson result) {
    final data = inventoryObject(result['data']);
    return ApexPanel(
      padding: const EdgeInsets.all(16),
      child: Padding(
        padding: EdgeInsets.zero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Reviewed supplier bill', style: Apex.sectionTitle),
            for (final line in inventoryRows(data['lines']))
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  '${line['description']} · ${inventoryQuantity(line['quantity'])} × ${inventoryAmount(line['rate'])}',
                ),
              ),
          ],
        ),
      ),
    );
  }
}

Widget _money(String text) => Text(
  text,
  maxLines: 1,
  overflow: TextOverflow.ellipsis,
  style: const TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w700,
    color: Apex.ink,
    fontFeatures: [FontFeature.tabularFigures()],
  ),
);
