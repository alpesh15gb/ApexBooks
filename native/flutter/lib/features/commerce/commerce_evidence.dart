import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../banking/bank_data.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import 'commerce_commands.dart';
import 'commerce_forms.dart';
import 'commerce_order.dart';

enum CommerceEvidenceKind {
  advance('Record customer advance', 'payment.capture'),
  advanceRefund('Record advance refund', 'payment.refund'),
  payout('Record gateway payout', 'settlement.record'),
  physical('Record goods received', 'return.receive');

  const CommerceEvidenceKind(this.label, this.operation);
  final String label;
  final String operation;
}

Json payoutData({
  required String date,
  required String bank,
  required List<Json> captures,
  required List<Json> refunds,
  required String net,
  required String fee,
}) {
  BigInt sum(List<Json> sources) =>
      sources.fold<BigInt>(BigInt.zero, (total, row) {
        final amount = inventoryDecimal(
          inventoryQuantity(inventoryObject(row['snapshot'])['amount']),
          2,
        );
        if (amount == null || amount <= BigInt.zero) {
          throw const FormatException(
            'A selected provider movement has no valid recorded amount.',
          );
        }
        return total + amount;
      });
  final grossCents = sum(captures);
  final refundCents = sum(refunds);
  final netCents = commercePaymentCents(net.trim());
  final feeCents = commercePaymentCents(fee.trim().isEmpty ? '0' : fee.trim());
  if (bank.isEmpty ||
      captures.isEmpty ||
      netCents == null ||
      feeCents == null ||
      grossCents > commerceMoneyLimit ||
      netCents <= BigInt.zero ||
      grossCents != netCents + feeCents + refundCents) {
    throw const FormatException(
      'Choose the receiving bank and captures. Captures minus refunds and fees must equal the bank deposit.',
    );
  }
  return {
    'date': date,
    'bank_account_id': bank,
    'gross': decimalMoney(grossCents),
    'net': decimalMoney(netCents),
    'fee': decimalMoney(feeCents),
    'capture_ids': captures.map((row) => row['external_id']).toList(),
    'refund_ids': refunds.map((row) => row['external_id']).toList(),
  };
}

class CommerceEvidenceForm extends StatefulWidget {
  const CommerceEvidenceForm({
    required this.workspace,
    required this.kind,
    required this.orders,
    required this.links,
    required this.stock,
    required this.banks,
    required this.gatewayId,
    super.key,
  });
  final WorkspaceContext workspace;
  final CommerceEvidenceKind kind;
  final List<Json> orders;
  final List<Json> links;
  final List<Json> stock;
  final List<Json> banks;
  final String gatewayId;

  @override
  State<CommerceEvidenceForm> createState() => _CommerceEvidenceFormState();
}

class _CommerceEvidenceFormState extends State<CommerceEvidenceForm> {
  final _source = TextEditingController();
  final _date = TextEditingController(text: businessDate());
  final _amount = TextEditingController();
  final _fee = TextEditingController(text: '0');
  final _gst = TextEditingController(text: '0');
  late final _state = TextEditingController(
    text: widget.workspace.company.stateCode,
  );
  final _quantities = <String, TextEditingController>{};
  final _captures = <String>{};
  final _refunds = <String>{};
  String _supply = 'goods';
  String? _order;
  String? _target;
  String? _bank;
  String? _error;
  bool _confirmed = false;
  bool _checking = false;
  int _changeCount = 0;
  CommerceIntent? _reviewed;

  bool get _payout => widget.kind == CommerceEvidenceKind.payout;
  bool get _physical => widget.kind == CommerceEvidenceKind.physical;
  bool get _advance => widget.kind == CommerceEvidenceKind.advance;
  bool get _taxedService =>
      _supply == 'services' && widget.workspace.company.taxMode == 'regular';

  List<Json> get _targets => widget.links.where((row) {
    if (inventoryText(row['external_id']).isEmpty ||
        inventoryText(row['record_id']).isEmpty) {
      return false;
    }
    final source = inventoryObject(row['snapshot']);
    if (inventoryText(source['order_id']) != _order) return false;
    if (_physical) return row['entity_type'] == 'credit';
    return row['entity_type'] == 'capture' &&
        inventoryObject(source['_result'])['advance'] == true;
  }).toList();

  Json? get _selected =>
      _targets.where((row) => row['external_id'] == _target).firstOrNull;

  List<Json> get _credited {
    final linked = {
      for (final item in widget.stock)
        if (item['track_stock'] == true)
          inventoryText(item['external_id']): item,
    };
    final totals = <String, ({String product, BigInt quantity})>{};
    for (final line in inventoryRows(
      inventoryObject(_selected?['snapshot'])['lines'],
    )) {
      final product = inventoryText(line['product_id']);
      final item = linked[product];
      final units = inventoryDecimal(inventoryQuantity(line['quantity']), 3);
      if (item == null || units == null || units <= BigInt.zero) continue;
      final itemId = inventoryText(item['item_id']);
      final key = itemId.isEmpty ? product : itemId;
      final existing = totals[key];
      totals[key] = (
        product: existing?.product ?? product,
        quantity: (existing?.quantity ?? BigInt.zero) + units,
      );
    }
    final scale = BigInt.from(1000);
    return [
      for (final total in totals.values)
        {
          'product_id': total.product,
          'quantity': inventoryQuantity(
            '${total.quantity ~/ scale}.${(total.quantity % scale).toString().padLeft(3, '0')}',
          ),
        },
    ];
  }

  List<Json> _unsettled(String type) => widget.links
      .where(
        (row) =>
            row['entity_type'] == type &&
            inventoryText(row['external_id']).isNotEmpty &&
            inventoryText(inventoryObject(row['snapshot'])['_settled']).isEmpty,
      )
      .toList();

  void _edit([VoidCallback? change]) => setState(() {
    _changeCount++;
    change?.call();
    _reviewed = null;
    _error = null;
    _confirmed = false;
  });

  void _clearTarget() {
    _target = null;
    for (final field in _quantities.values) {
      field.clear();
    }
  }

  @override
  void dispose() {
    for (final input in [
      _source,
      _date,
      _amount,
      _fee,
      _gst,
      _state,
      ..._quantities.values,
    ]) {
      input.dispose();
    }
    super.dispose();
  }

  Future<Json> _confirmedRecord(Json link) async {
    final id = Uri.encodeComponent(inventoryText(link['record_id']));
    final record = inventoryObject(
      await widget.workspace.api.get('${widget.workspace.path}/records/$id'),
    );
    if (record['id'] != link['record_id'] || record['posted'] != true) {
      throw const FormatException(
        'The original accounting record has not posted.',
      );
    }
    return record;
  }

  Future<void> _review() async {
    if (_checking) return;
    final revision = _changeCount;
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final source = _source.text.trim();
      if (!_confirmed || source.isEmpty || utf8.encode(source).length > 160) {
        throw const FormatException(
          'Confirm the movement and enter its exact source reference.',
        );
      }
      final date = validBankDate(_date.text);
      if (date == null || date.compareTo(businessDate()) > 0) {
        throw const FormatException('Use an accounting date through today.');
      }
      final data = await _body(date);
      if (!mounted || revision != _changeCount) return;
      setState(
        () => _reviewed = (
          operation: widget.kind.operation,
          payload: {'source_id': source, 'confirmed': true, 'data': data},
        ),
      );
    } catch (failure) {
      if (mounted && revision == _changeCount) {
        setState(() => _error = inventoryError(failure));
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<Json> _body(String date) async {
    if (_payout) {
      if (_bank == widget.gatewayId) {
        throw const FormatException('Choose a different destination bank.');
      }
      return payoutData(
        date: date,
        bank: _bank ?? '',
        net: _amount.text,
        fee: _fee.text,
        captures: _unsettled('capture')
            .where((row) => _captures.contains(row['external_id']))
            .toList(),
        refunds: _unsettled('refund')
            .where((row) => _refunds.contains(row['external_id']))
            .toList(),
      );
    }
    final order = _order;
    if (order == null) {
      throw const FormatException('Choose the original store order.');
    }
    final data = <String, dynamic>{'order_id': order, 'date': date};
    final amountText = _amount.text.trim();
    final amount = commercePaymentCents(amountText);
    if (!_physical && (amount == null || amount <= BigInt.zero)) {
      throw const FormatException('Enter a positive confirmed amount.');
    }
    if (_advance) {
      data.addAll({'amount': amountText, 'advance_supply': _supply});
      if (_taxedService) {
        final rate = inventoryDecimal(_gst.text, 2);
        final state = _state.text.trim();
        final stateNumber = int.tryParse(state);
        if (rate == null ||
            rate > BigInt.from(10000) ||
            widget.workspace.company.stateCode.isEmpty ||
            stateNumber == null ||
            state.length != 2 ||
            !(stateNumber >= 1 && stateNumber <= 38 || stateNumber == 97)) {
          throw const FormatException(
            'Enter the service GST rate and a valid two-digit place of supply.',
          );
        }
        data.addAll({
          'advance_gst_rate': _gst.text.trim(),
          'place_of_supply': state,
        });
      }
      return data;
    }
    final link = _selected;
    if (link == null) {
      throw const FormatException('Choose the original accounting source.');
    }
    final record = await _confirmedRecord(link);
    if (date.compareTo(inventoryText(record['date'])) < 0) {
      throw const FormatException(
        'The accounting date cannot precede the source document.',
      );
    }
    if (_physical) {
      if (record['kind'] != 'credit_note' ||
          inventoryObject(record['data'])['return_stock'] != false) {
        throw const FormatException(
          'Choose a credit note that did not already record stock.',
        );
      }
      final lines = <Json>[];
      final seen = <String>{};
      for (final line in _credited) {
        final id = inventoryText(line['product_id']);
        final raw = _quantities[id]?.text.trim() ?? '';
        if (raw.isEmpty || !seen.add(id)) continue;
        final quantity = inventoryDecimal(raw, 3);
        final cap = inventoryDecimal(inventoryQuantity(line['quantity']), 3);
        if (quantity == null || cap == null || quantity > cap) {
          throw const FormatException(
            'Enter a quantity within the credited stock balance.',
          );
        }
        if (quantity > BigInt.zero) {
          lines.add({'product_id': id, 'quantity': raw});
        }
      }
      if (lines.isEmpty) {
        throw const FormatException(
          'Enter the quantities physically received.',
        );
      }
      return {...data, 'credit_id': link['external_id'], 'lines': lines};
    }
    final available = inventoryDecimal(
      inventoryQuantity(record['advance_remaining']),
      2,
    );
    if (inventoryObject(record['data'])['is_advance'] != true ||
        available == null ||
        amount! > available) {
      throw const FormatException(
        'The refund exceeds the remaining customer advance.',
      );
    }
    return {...data, 'capture_id': link['external_id'], 'amount': amountText};
  }

  Widget _choice(
    String label,
    String? selected,
    List<DropdownMenuItem<String>> items,
    ValueChanged<String?> change, {
    Key? key,
  }) => DropdownButtonFormField<String>(
    key: key,
    initialValue: selected,
    isExpanded: true,
    items: items,
    onChanged: change,
    decoration: InputDecoration(labelText: label),
  );

  List<Widget> _sourceFields() => [
    if (!_payout)
      _choice(
        'Store order',
        _order,
        [
          for (final row in widget.orders)
            DropdownMenuItem(
              value: inventoryText(row['external_id']),
              child: Text(
                inventoryText(row['number']),
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        (value) => _edit(() {
          _order = value;
          _clearTarget();
        }),
      ),
    if (!_payout && !_advance)
      _choice(
        _physical ? 'Source credit note' : 'Source advance',
        _target,
        [
          for (final row in _targets)
            DropdownMenuItem(
              value: inventoryText(row['external_id']),
              child: Text(
                '${row['external_id']} · ${inventoryAmount(inventoryObject(row['snapshot'])['amount'])}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        (value) => _edit(() {
          _clearTarget();
          _target = value;
        }),
        key: ValueKey(_order),
      ),
    if (_advance) ...[
      _choice('Advance supply', _supply, const [
        DropdownMenuItem(value: 'goods', child: Text('Goods')),
        DropdownMenuItem(value: 'services', child: Text('Services')),
      ], (value) => _edit(() => _supply = value ?? 'goods')),
      if (_taxedService) ...[
        CommerceField(
          label: 'Advance GST rate (%)',
          controller: _gst,
          type: _decimal,
          maxLength: 6,
          onChanged: (_) => _edit(),
        ),
        CommerceField(
          label: 'Place of supply state code',
          controller: _state,
          maxLength: 2,
          onChanged: (_) => _edit(),
        ),
      ],
      const Text(
        'Available advances are applied to matching invoices as they post.',
      ),
    ],
    if (_physical)
      for (final line in _credited)
        CommerceField(
          label:
              'Product ${line['product_id']} · Credited ${inventoryQuantity(line['quantity'])}',
          controller: _quantities.putIfAbsent(
            inventoryText(line['product_id']),
            TextEditingController.new,
          ),
          maxLength: 16,
          type: _decimal,
          onChanged: (_) => _edit(),
        ),
    if (_physical && _target != null && _credited.isEmpty)
      const Text('No credited items are mapped to tracked stock.'),
  ];

  static const _decimal = TextInputType.numberWithOptions(decimal: true);

  List<Widget> _payoutFields() => [
    _choice('Destination bank account', _bank, [
      for (final bank in widget.banks)
        if (bank['id'] != widget.gatewayId)
          DropdownMenuItem(
            value: inventoryText(bank['id']),
            child: Text(
              inventoryText(bank['name']),
              overflow: TextOverflow.ellipsis,
            ),
          ),
    ], (value) => _edit(() => _bank = value)),
    const Text('Captures in this payout'),
    ..._unsettled('capture').map((row) => _included(row, _captures)),
    const Text('Refunds deducted by the provider'),
    ..._unsettled('refund').map((row) => _included(row, _refunds)),
    CommerceField(
      label: 'Provider fee excluding GST (₹)',
      controller: _fee,
      maxLength: 16,
      type: _decimal,
      onChanged: (_) => _edit(),
    ),
  ];

  Widget _included(Json row, Set<String> selected) {
    final id = inventoryText(row['external_id']);
    return CheckboxListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      value: selected.contains(id),
      title: Text(
        '$id · ${inventoryAmount(inventoryObject(row['snapshot'])['amount'])}',
      ),
      onChanged: (value) => _edit(() {
        if (value == true) {
          selected.add(id);
        } else {
          selected.remove(id);
        }
      }),
    );
  }

  String get _confirmation => switch (widget.kind) {
    CommerceEvidenceKind.advance => 'I confirmed the advance was received',
    CommerceEvidenceKind.advanceRefund =>
      'I confirmed the advance was refunded',
    CommerceEvidenceKind.payout =>
      'I confirmed the payout reached the receiving bank',
    CommerceEvidenceKind.physical =>
      'I confirmed these goods were physically received',
  };

  @override
  Widget build(BuildContext context) => CommerceDialog(
    title: widget.kind.label,
    error: _error,
    fields: [
      ..._sourceFields(),
      if (_payout) ..._payoutFields(),
      CommerceField(
        label: _physical ? 'Receiving reference' : 'Bank or provider reference',
        controller: _source,
        maxLength: 160,
        onChanged: (_) => _edit(),
      ),
      CommerceField(
        label: 'Accounting date (YYYY-MM-DD)',
        controller: _date,
        maxLength: 10,
        onChanged: (_) => _edit(),
      ),
      if (!_physical)
        CommerceField(
          label: _payout ? 'Bank deposit (₹)' : 'Confirmed amount (₹)',
          controller: _amount,
          maxLength: 16,
          type: _decimal,
          onChanged: (_) => _edit(),
        ),
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(_confirmation),
        value: _confirmed,
        onChanged: (value) => setState(() {
          _changeCount++;
          _confirmed = value == true;
          _reviewed = null;
          _error = null;
        }),
      ),
      if (_reviewed != null)
        Text(
          '${widget.kind.label} · ${_source.text.trim()}${_physical ? '' : ' · ${inventoryAmount(_amount.text.trim())}'}',
        ),
    ],
    primary: FilledButton(
      onPressed: _checking
          ? null
          : _reviewed == null
          ? _review
          : () => Navigator.pop(context, _reviewed),
      child: Text(
        _checking
            ? 'Checking source…'
            : _reviewed == null
            ? 'Review evidence'
            : 'Queue reviewed evidence',
      ),
    ),
  );
}
