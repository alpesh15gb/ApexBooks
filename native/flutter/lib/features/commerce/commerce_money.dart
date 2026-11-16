import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import 'commerce_commands.dart';
import 'commerce_forms.dart';
import 'commerce_order.dart';

class CommerceMoneyForm extends StatefulWidget {
  const CommerceMoneyForm({
    required this.workspace,
    required this.orders,
    required this.links,
    super.key,
  });
  final WorkspaceContext workspace;
  final List<Json> orders;
  final List<Json> links;
  @override
  State<CommerceMoneyForm> createState() => _CommerceMoneyFormState();
}

class _CommerceMoneyFormState extends State<CommerceMoneyForm> {
  final _reference = TextEditingController();
  final _amount = TextEditingController();
  final _date = TextEditingController(text: businessDate());
  bool _refund = false;
  bool _confirmed = false;
  bool _checking = false;
  int _revision = 0;
  String? _order;
  String? _target;
  String? _error;
  CommerceIntent? _reviewed;

  List<Json> get _targets => widget.links
      .where(
        (row) =>
            row['entity_type'] == (_refund ? 'credit' : 'invoice') &&
            inventoryText(inventoryObject(row['snapshot'])['order_id']) ==
                _order &&
            inventoryText(row['external_id']).isNotEmpty,
      )
      .toList();

  @override
  void dispose() {
    _reference.dispose();
    _amount.dispose();
    _date.dispose();
    super.dispose();
  }

  void _edit([VoidCallback? change]) => setState(() {
    _revision++;
    change?.call();
    _reviewed = null;
    _error = null;
  });

  Future<void> _review() async {
    if (_checking) return;
    final revision = _revision;
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final source = _reference.text.trim();
      if (source.isEmpty || utf8.encode(source).length > 160 || !_confirmed) {
        throw const FormatException(
          'Confirm the provider movement and enter its exact reference.',
        );
      }
      final issued = _date.text.trim();
      final parsed = DateTime.tryParse(issued);
      if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(issued) ||
          parsed == null ||
          parsed.toIso8601String().substring(0, 10) != issued ||
          issued.compareTo(businessDate()) > 0) {
        throw const FormatException('Use an accounting date through today.');
      }
      final target = _targets
          .where((row) => row['external_id'] == _target)
          .firstOrNull;
      if (_order == null || target == null) {
        throw const FormatException(
          'Choose an order and its accounting source.',
        );
      }
      final document = inventoryObject(target['snapshot']);
      final documentDate = inventoryText(document['date']);
      if (documentDate.isNotEmpty && issued.compareTo(documentDate) < 0) {
        throw const FormatException(
          'The accounting date cannot precede the source document.',
        );
      }
      final value = _amount.text.trim();
      final amount = commercePaymentCents(value);
      if (amount == null || amount <= BigInt.zero) {
        throw const FormatException('Enter a positive amount.');
      }
      final recordId = inventoryText(target['record_id']);
      if (recordId.isEmpty) {
        throw const FormatException(
          'Wait for the accounting source document to post.',
        );
      }
      final workspace = widget.workspace;
      final record = inventoryObject(
        await workspace.api.get(
          '${workspace.path}/records/${Uri.encodeComponent(recordId)}',
        ),
      );
      if (!mounted || revision != _revision) return;
      if (record['id'] != recordId ||
          record['posted'] != true ||
          record['kind'] != (_refund ? 'credit_note' : 'sales_invoice')) {
        throw const FormatException(
          'The accounting source document is not posted.',
        );
      }
      if (issued.compareTo(inventoryText(record['date'])) < 0) {
        throw const FormatException(
          'The accounting date cannot precede the source document.',
        );
      }
      final limit = inventoryDecimal(
        inventoryQuantity(record[_refund ? 'credit_remaining' : 'outstanding']),
        2,
      );
      if (limit == null || amount > limit) {
        throw const FormatException(
          'The amount exceeds the source document’s current available balance.',
        );
      }
      final data = {
        'order_id': _order,
        'date': issued,
        'amount': value,
        if (_refund)
          'credit_id': _target
        else
          'allocations': [
            {'invoice_id': _target, 'amount': value},
          ],
      };
      setState(
        () => _reviewed = (
          operation: _refund ? 'payment.refund' : 'payment.capture',
          payload: {'source_id': source, 'confirmed': true, 'data': data},
        ),
      );
    } catch (failure) {
      if (mounted && revision == _revision) {
        setState(() => _error = inventoryError(failure));
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) => CommerceDialog(
    title: 'Record provider payment or refund',
    error: _error,
    fields: [
      const Text(
        'Use a confirmed gateway or bank movement. This action records the provider evidence in Apex Books.',
      ),
      DropdownButtonFormField<bool>(
        initialValue: _refund,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Money movement'),
        items: const [
          DropdownMenuItem(
            value: false,
            child: Text('Payment against an invoice'),
          ),
          DropdownMenuItem(
            value: true,
            child: Text('Refund against a credit note'),
          ),
        ],
        onChanged: (value) => _edit(() {
          _refund = value ?? false;
          _target = null;
          _confirmed = false;
        }),
      ),
      DropdownButtonFormField<String>(
        initialValue: _order,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Store order'),
        items: [
          for (final row in widget.orders)
            DropdownMenuItem(
              value: inventoryText(row['external_id']),
              child: Text(
                inventoryText(row['number']),
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) => _edit(() {
          _order = value;
          _target = null;
          _confirmed = false;
        }),
      ),
      DropdownButtonFormField<String>(
        key: ValueKey((_order, _refund)),
        initialValue: _target,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: _refund ? 'Source credit note' : 'Source invoice',
        ),
        items: [
          for (final row in _targets)
            DropdownMenuItem(
              value: inventoryText(row['external_id']),
              child: Text(
                '${row['external_id']} · ${inventoryAmount(inventoryObject(row['snapshot'])['amount'])}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) => _edit(() {
          _target = value;
          _confirmed = false;
        }),
      ),
      if (_order != null && _targets.isEmpty)
        const Text('Wait for the source document to arrive in Deliveries.'),
      CommerceField(
        label: 'Bank or provider reference',
        controller: _reference,
        maxLength: 160,
        onChanged: (_) => _edit(() => _confirmed = false),
      ),
      CommerceField(
        label: 'Accounting date (YYYY-MM-DD)',
        controller: _date,
        maxLength: 10,
        onChanged: (_) => _edit(),
      ),
      CommerceField(
        label: 'Confirmed amount (₹)',
        controller: _amount,
        maxLength: 16,
        type: const TextInputType.numberWithOptions(decimal: true),
        onChanged: (_) => _edit(() => _confirmed = false),
      ),
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        value: _confirmed,
        title: Text(
          _refund
              ? 'I confirmed the money was refunded'
              : 'I confirmed the money was received',
        ),
        onChanged: (value) => _edit(() => _confirmed = value == true),
      ),
      if (_reviewed != null)
        Text(
          '${_refund ? 'Recorded refund' : 'Recorded receipt'} · ${inventoryAmount(_amount.text.trim())} · ${_reference.text.trim()}',
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
