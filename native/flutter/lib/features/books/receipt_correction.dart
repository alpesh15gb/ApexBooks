import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import 'books_data.dart';

const receiptCorrectionsFeature = 'receipt_allocation_corrections';

bool canCorrectReceipt(WorkspaceContext workspace, BooksRecord row) =>
    workspace.company.canWrite &&
    workspace.features.contains(receiptCorrectionsFeature) &&
    (row.kind == 'payment_in' ||
        row.kind == 'advance_application' &&
            row.data['payment_kind'] == 'payment_in') &&
    (row.json['posted'] == true ||
        row.data.containsKey('receipt_correction_superseded'));

class ReceiptCorrectionDialog extends StatefulWidget {
  const ReceiptCorrectionDialog({
    required this.workspace,
    required this.record,
    super.key,
  });

  final WorkspaceContext workspace;
  final BooksRecord record;

  @override
  State<ReceiptCorrectionDialog> createState() =>
      _ReceiptCorrectionDialogState();
}

class _ReceiptCorrectionDialogState extends State<ReceiptCorrectionDialog> {
  final _form = GlobalKey<FormState>();
  final _reason = TextEditingController();
  final _plans = <String, BooksJson>{};
  BooksJson? _data;
  BooksJson? _preview;
  BooksJson? _pending;
  String? _addCredit;
  String? _error;
  bool _busy = true;

  String get _path =>
      '${widget.workspace.path}/records/${Uri.encodeComponent(widget.record.id)}/receipt-correction';
  String get _storageKey => 'receipt-correction:${widget.record.id}';
  List<BooksJson> get _credits => booksRows(_data?['credits'] ?? []);
  List<BooksJson> get _invoices => booksRows(_data?['invoices'] ?? []);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  BooksJson _plan(String id, {bool anchor = false}) => {
    'credit_id': id,
    'replace': <String>[],
    'unlink': <String>[
      if (anchor && widget.record.kind == 'advance_application')
        widget.record.id,
    ],
    'allocations': <BooksJson>[],
    'apply': <BooksJson>[],
  };

  Future<void> _load() async {
    try {
      final pending = await widget.workspace.pending.load(_storageKey);
      if (!mounted) return;
      if (pending != null) {
        setState(() => _pending = pending);
      } else {
        final data = await widget.workspace.api.get(_path) as BooksJson;
        if (!mounted) return;
        setState(() {
          _data = data;
          final id = booksText(data['anchor_credit_id']);
          _plans[id] = _plan(id, anchor: true);
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  BooksJson _payload() => {
    'reason': _reason.text.trim(),
    'credits': [
      for (final plan in _plans.values)
        {
          ...plan,
          'allocations': [
            for (final allocation in booksRows(plan['allocations']))
              {
                'purpose': allocation['purpose'],
                'amount': allocation['amount'],
                if (allocation['purpose'] == 'invoice')
                  'document_id': allocation['document_id'],
                if (allocation['purpose'] != 'invoice')
                  'notes': booksText(allocation['notes']),
                if (allocation['purpose'] == 'services') ...{
                  'gst_rate': allocation['gst_rate'],
                  'place_of_supply': allocation['place_of_supply'],
                },
              },
          ],
        },
    ],
  };

  Future<void> _review() async {
    if (_busy || _form.currentState?.validate() != true) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final request = _payload();
      final preview = await widget.workspace.api.post(
        '$_path/preview',
        body: request,
      ) as BooksJson;
      if (mounted) setState(() => _preview = {...preview, 'payload': request});
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _post() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final workspace = widget.workspace;
    try {
      var operation = _pending;
      if (operation == null) {
        final random = Random.secure();
        final key = List.generate(
          16,
          (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
        ).join();
        operation = {
          'key': 'flutter-receipt-$key',
          'body': {
            ...(_preview!['payload'] as BooksJson),
            'snapshot': _preview!['snapshot'],
          },
        };
        await workspace.pending.save(_storageKey, operation);
        _pending = operation;
      }
      final response = await workspace.api.post(
        '$_path/post',
        body: operation['body'] as BooksJson,
        idempotencyKey: operation['key'] as String,
      ) as BooksJson;
      if (booksText(response['id']).isEmpty) {
        throw const FormatException('Posting could not be confirmed.');
      }
      await workspace.pending.clear(_storageKey);
      if (mounted) Navigator.of(context).pop(true);
    } on ApexApiException catch (error) {
      // The server checks for a committed key before reporting a stale or invalid plan.
      if (_pending != null && (error.status == 409 || error.status == 422)) {
        await workspace.pending.clear(_storageKey);
        _pending = null;
      }
      if (mounted) setState(() => _error = error.toString());
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _creditLabel(BooksJson credit) => [
    credit['date'],
    credit['bank'],
    if (booksText(credit['utr']).isNotEmpty) 'UTR ${credit['utr']}',
    booksMoney(credit['amount']),
    credit['description'],
  ].map(booksText).where((text) => text.isNotEmpty).join(' · ');

  Widget _select(
    String label,
    String? value,
    List<(String, String)> options,
    ValueChanged<String?> changed, {
    bool required = true,
  }) => DropdownButtonFormField<String>(
    decoration: InputDecoration(labelText: label),
    isExpanded: true,
    initialValue: options.any((option) => option.$1 == value) ? value : null,
    items: [
      for (final (key, text) in options)
        DropdownMenuItem(
          value: key,
          child: Text(text, overflow: TextOverflow.ellipsis),
        ),
    ],
    validator: required
        ? (choice) => choice == null ? 'Choose an option' : null
        : null,
    onChanged: _busy ? null : changed,
  );

  Widget _field(
    String label,
    BooksJson row,
    String key, {
    bool required = true,
    bool amount = false,
  }) => TextFormField(
    decoration: InputDecoration(labelText: label),
    initialValue: booksText(row[key]),
    enabled: !_busy,
    keyboardType: amount
        ? const TextInputType.numberWithOptions(decimal: true)
        : TextInputType.text,
    validator: required
        ? (text) => (text ?? '').trim().isEmpty ? 'Enter $label' : null
        : null,
    onChanged: (text) => row[key] = text.trim(),
  );

  Widget _receipt(BooksJson receipt) {
    final purpose = switch (receipt['purpose']) {
      'invoice' => 'Invoice payment',
      'goods' => 'Goods advance',
      'services' => 'Service advance',
      'unallocated' => 'Unallocated customer receipt',
      _ => 'Advance',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$purpose · ${booksMoney(receipt['amount'])}'),
        if (booksText(receipt['notes']).isNotEmpty)
          Text(booksText(receipt['notes'])),
        if (receipt['advance_available'] != null)
          Text('Advance available ${booksMoney(receipt['advance_available'])}'),
        for (final link in booksRows(receipt['direct']))
          Text('${link['invoice']} · ${booksMoney(link['amount'])}'),
        for (final link in booksRows(receipt['settlements']))
          Text(
            '${link['number']} · ${booksMoney(link['amount'])} · ${booksRows(link['allocations']).map((row) => row['invoice']).join(', ')}',
          ),
      ],
    );
  }

  void _toggle(List<String> values, String id, bool? checked) => setState(() {
    if (checked == true) {
      values.add(id);
    } else {
      values.remove(id);
    }
  });

  List<(String, String)> _targets({bool advance = false}) => [
    for (final row in _invoices)
      if (!advance || row['kind'] == 'sales_invoice')
        (
          booksText(row['id']),
          '${row['number']} · ${booksMoney(row['outstanding'])} outstanding',
        ),
  ];

  Widget _credit(BooksJson credit) {
    final id = booksText(credit['id']);
    final plan = _plans[id]!;
    final replace = plan['replace'] as List<String>;
    final unlink = plan['unlink'] as List<String>;
    final receipts = booksRows(credit['receipts']);
    final allocations = plan['allocations'] as List<BooksJson>;
    final applications = plan['apply'] as List<BooksJson>;
    final advances = [
      for (final row in receipts)
        if (row['advance_available'] != null && !replace.contains(row['id']))
          (
            booksText(row['id']),
            '${row['number']} · ${booksMoney(row['advance_available'])} available',
          ),
    ];
    return Card(
      key: ValueKey(id),
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 8,
          children: [
            Text(
              _creditLabel(credit),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              'Booked ${booksMoney(credit['booked'])} · Currently unallocated ${booksMoney(credit['unallocated'])}',
            ),
            for (final row in receipts) ...[
              _receipt(row),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('Reclassify ${row['number']}'),
                value: replace.contains(row['id']),
                onChanged: _busy
                    ? null
                    : (value) => _toggle(replace, booksText(row['id']), value),
              ),
              for (final settlement in booksRows(row['settlements']))
                if (settlement['kind'] == 'advance_application')
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text('Unlink ${settlement['number']}'),
                    value: unlink.contains(settlement['id']),
                    onChanged: _busy
                        ? null
                        : (value) => _toggle(
                            unlink,
                            booksText(settlement['id']),
                            value,
                          ),
                  ),
            ],
            for (final row in allocations)
              Column(
                key: ObjectKey(row),
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _select('Purpose', row['purpose'] as String?, const [
                    ('invoice', 'Invoice payment'),
                    ('goods', 'Goods advance'),
                    ('services', 'Service advance'),
                  ], (value) => setState(() => row['purpose'] = value)),
                  _field('Allocation amount', row, 'amount', amount: true),
                  if (row['purpose'] == 'invoice')
                    _select(
                      'Invoice',
                      row['document_id'] as String?,
                      _targets(),
                      (value) => row['document_id'] = value,
                    )
                  else
                    _field(
                      'Advance description',
                      row,
                      'notes',
                      required: false,
                    ),
                  if (row['purpose'] == 'services') ...[
                    _field('GST rate (%)', row, 'gst_rate', amount: true),
                    _field('Place of supply code', row, 'place_of_supply'),
                  ],
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => allocations.remove(row)),
                    child: const Text('Remove allocation'),
                  ),
                ],
              ),
            for (final row in applications)
              Column(
                key: ObjectKey(row),
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _select(
                    'Existing advance',
                    row['source_id'] as String?,
                    advances,
                    (value) => row['source_id'] = value,
                  ),
                  _select(
                    'Apply to invoice',
                    row['document_id'] as String?,
                    _targets(advance: true),
                    (value) => row['document_id'] = value,
                  ),
                  _field('Application date (YYYY-MM-DD)', row, 'date'),
                  _field('Application amount', row, 'amount', amount: true),
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => applications.remove(row)),
                    child: const Text('Remove application'),
                  ),
                ],
              ),
            const Text(
              'Any remaining balance will be held as an unallocated receipt.',
            ),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _busy
                      ? null
                      : () => setState(
                          () => allocations.add({
                            'purpose': 'invoice',
                            'place_of_supply':
                                widget.workspace.company.stateCode,
                          }),
                        ),
                  child: const Text('Add allocation'),
                ),
                if (advances.isNotEmpty)
                  OutlinedButton(
                    onPressed: _busy
                        ? null
                        : () => setState(
                            () => applications.add({'date': businessDate()}),
                          ),
                    child: const Text('Apply existing advance'),
                  ),
                if (id != _data?['anchor_credit_id'])
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() => _plans.remove(id)),
                    child: const Text('Remove credit'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _reviewResults(BooksJson preview) => [
    for (final (label, key) in const [
      ('Before', 'before'),
      ('Proposed', 'after'),
    ]) ...[
      Text(label, style: Theme.of(context).textTheme.titleMedium),
      for (final credit in booksRows(preview[key])) ...[
        Text(_creditLabel(credit)),
        Text(
          'Booked ${booksMoney(credit['booked'])} · Unallocated ${booksMoney(credit['unallocated'])}',
        ),
        for (final receipt in booksRows(credit['receipts'])) _receipt(receipt),
        const Divider(),
      ],
    ],
    for (final (label, key) in const [
      ('Outstanding before', 'invoices_before'),
      ('Outstanding after', 'invoices_after'),
    ])
      for (final invoice in booksRows(preview[key]))
        Text(
          "${invoice['number']} · $label ${booksMoney(invoice['outstanding'])}",
        ),
  ];

  @override
  Widget build(BuildContext context) {
    final preview = _preview;
    final candidates = [
      for (final credit in _credits)
        if (!_plans.containsKey(credit['id']))
          (booksText(credit['id']), _creditLabel(credit)),
    ];
    return PopScope(
      canPop: !_busy,
      child: AlertDialog(
        scrollable: true,
        title: const Text('Correct allocation'),
        content: SizedBox(
          width: 720,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: 8,
            children: [
              if (_busy) const LinearProgressIndicator(),
              if (_error != null)
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              if (_pending != null)
                const Text(
                  'The previous posting response could not be confirmed. Retry the same correction.',
                ),
              if (preview != null) ..._reviewResults(preview),
              if (preview == null && _pending == null && _data != null)
                Form(
                  key: _form,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    spacing: 8,
                    children: [
                      for (final credit in _credits)
                        if (_plans.containsKey(credit['id'])) _credit(credit),
                      if (candidates.isNotEmpty) ...[
                        _select(
                          'Another bank credit or receipt',
                          _addCredit,
                          candidates,
                          (value) => setState(() => _addCredit = value),
                          required: false,
                        ),
                        OutlinedButton(
                          onPressed: _busy || _addCredit == null
                              ? null
                              : () => setState(() {
                                  _plans[_addCredit!] = _plan(_addCredit!);
                                  _addCredit = null;
                                }),
                          child: const Text('Add credit'),
                        ),
                      ],
                      TextFormField(
                        controller: _reason,
                        enabled: !_busy,
                        maxLength: 200,
                        decoration: const InputDecoration(
                          labelText: 'Correction reason',
                        ),
                        validator: (value) => (value ?? '').trim().length < 3
                            ? 'Enter a correction reason'
                            : null,
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _busy ? null : () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
          if (preview != null && _pending == null)
            TextButton(
              onPressed: _busy
                  ? null
                  : () => setState(() {
                      _preview = null;
                      _error = null;
                    }),
              child: const Text('Edit correction'),
            ),
          if (preview != null || _pending != null)
            FilledButton(
              onPressed: _busy ? null : _post,
              child: Text(
                _pending != null ? 'Retry correction' : 'Post correction',
              ),
            )
          else if (_data != null)
            FilledButton(
              onPressed: _busy ? null : _review,
              child: const Text('Preview correction'),
            ),
        ],
      ),
    );
  }
}
