import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_widgets.dart';
import 'commerce_commands.dart';
import 'commerce_forms.dart';

typedef CommerceIntent = ({String operation, Json payload});

BigInt orderQuantity(Object? value) =>
    inventoryDecimal(inventoryQuantity(value), 3) ?? BigInt.zero;

BigInt orderAvailable(Json line, String operation) {
  final ordered = orderQuantity(line['quantity']);
  final billed = orderQuantity(line['invoiced']);
  final shipped = orderQuantity(line['shipped']);
  final cancelled = orderQuantity(line['cancelled']);
  final credited = orderQuantity(line['refunded']);
  final remaining = switch (operation) {
    'order.invoice' => ordered - billed - cancelled,
    'order.ship' => ordered - shipped - cancelled,
    'order.refund' => billed - credited,
    _ => BigInt.zero,
  };
  return remaining > BigInt.zero ? remaining ~/ BigInt.from(1000) : BigInt.zero;
}

class CommerceOrderForm extends StatefulWidget {
  const CommerceOrderForm({
    required this.order,
    required this.writable,
    super.key,
  });
  final Json order;
  final bool writable;
  @override
  State<CommerceOrderForm> createState() => _CommerceOrderFormState();
}

class _CommerceOrderFormState extends State<CommerceOrderForm> {
  final _amounts = <String, TextEditingController>{};
  final _carrier = TextEditingController();
  final _tracking = TextEditingController();
  String _operation = 'order.invoice';
  CommerceIntent? _reviewed;
  String? _error;

  Json get _snapshot => inventoryObject(widget.order['snapshot']);
  List<Json> get _lines => inventoryRows(_snapshot['items']);

  @override
  void dispose() {
    for (final input in _amounts.values) {
      input.dispose();
    }
    _carrier.dispose();
    _tracking.dispose();
    super.dispose();
  }

  String _progress(Json item) =>
      '${item['quantity'] ?? 0} / ${item['invoiced'] ?? 0} / ${item['shipped'] ?? 0}'
      '${orderQuantity(item['refunded']) > BigInt.zero ? ' · credited ${item['refunded']}' : ''}';

  Widget? _quantityField(Json item) {
    if (!widget.writable ||
        _operation == 'order.cancel' ||
        orderAvailable(item, _operation) <= BigInt.zero) {
      return null;
    }
    return CommerceField(
      label:
          'Quantity for ${item['name']} (up to ${orderAvailable(item, _operation)})',
      controller: _amounts.putIfAbsent(
        inventoryText(item['id']),
        TextEditingController.new,
      ),
      maxLength: 9,
      type: TextInputType.number,
      onChanged: (_) => _edited(),
    );
  }

  void _edited() => setState(() {
    _reviewed = null;
    _error = null;
  });

  bool get _canCancel =>
      _lines.isNotEmpty &&
      _lines.every(
        (line) =>
            orderQuantity(line['invoiced']) == BigInt.zero &&
            orderQuantity(line['shipped']) == BigInt.zero,
      ) &&
      !const {
        'canceled',
        'cancelled',
        'closed',
        'completed',
      }.contains(widget.order['status']);

  void _review() {
    try {
      final orderId = inventoryText(widget.order['external_id']);
      if (orderId.isEmpty) {
        throw const FormatException(
          'Reload this order before preparing a command.',
        );
      }
      if (_operation == 'order.cancel') {
        if (!_canCancel) {
          throw const FormatException(
            'Only unfulfilled orders can be cancelled here.',
          );
        }
        setState(
          () => _reviewed = (
            operation: _operation,
            payload: {'order_id': orderId},
          ),
        );
        return;
      }
      final items = <String, int>{};
      for (final line in _lines) {
        final id = inventoryText(line['id']);
        final raw = _amounts[id]?.text.trim() ?? '';
        if (raw.isEmpty) continue;
        final quantity = int.tryParse(raw);
        if (!RegExp(r'^\d{1,9}$').hasMatch(raw) ||
            quantity == null ||
            BigInt.from(quantity) > orderAvailable(line, _operation)) {
          throw FormatException(
            'Enter a whole quantity within the available balance for ${line['name']}.',
          );
        }
        if (quantity > 0) items[id] = quantity;
      }
      if (items.isEmpty) {
        throw const FormatException(
          'Enter a quantity for at least one order line.',
        );
      }
      setState(
        () => _reviewed = (
          operation: _operation,
          payload: {
            'order_id': orderId,
            'items': items,
            if (_operation == 'order.ship') 'carrier': _carrier.text.trim(),
            if (_operation == 'order.ship') 'tracking': _tracking.text.trim(),
          },
        ),
      );
    } on FormatException catch (failure) {
      setState(() => _error = failure.message);
    }
  }

  @override
  Widget build(BuildContext context) => CommerceDialog(
    eyebrow: 'BAGISTO ORDER',
    title:
        '${widget.order['number']} · ${inventoryAmount(widget.order['amount'])}',
    error: _error,
    fields: [
      Text(
        '${commerceLabel(widget.order['status'])} · Source ${widget.order['external_id']}',
      ),
      const SizedBox(height: 10),
      for (final shipment in inventoryRows(_snapshot['shipments']))
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('Shipment ${shipment['id']}'),
          subtitle: Text('${shipment['carrier']} · ${shipment['tracking']}'),
        ),
      if (widget.writable)
        DropdownButtonFormField<String>(
          initialValue: _operation,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Order action'),
          items: [
            for (final operation in [
              'order.invoice',
              'order.ship',
              'order.refund',
              if (_canCancel) 'order.cancel',
            ])
              DropdownMenuItem(
                value: operation,
                child: Text(commerceLabel(operation)),
              ),
          ],
          onChanged: (operation) {
            if (operation == null || operation == _operation) return;
            for (final field in _amounts.values) {
              field.clear();
            }
            setState(() {
              _operation = operation;
              _reviewed = null;
              _error = null;
            });
          },
        ),
      if (_lines.isNotEmpty) ...[
        const SizedBox(height: 8),
        ApexPanel(
          padding: EdgeInsets.zero,
          child: InventoryDialogTable(
            headers: const ['Item', 'Ordered / invoiced / shipped', 'Action qty'],
            flex: const [2, 1.3, 2.2],
            breakpoint: 640,
            rowCount: _lines.length,
            cell: (row, column) {
              final item = _lines[row];
              return switch (column) {
                0 => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(inventoryText(item['name']), style: Apex.strong),
                    if (inventoryText(item['sku']).isNotEmpty)
                      Text(inventoryText(item['sku']), style: Apex.note),
                  ],
                ),
                1 => Text(_progress(item)),
                _ => _quantityField(item) ?? const Text('—'),
              };
            },
            card: (row) {
              final item = _lines[row];
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(inventoryText(item['name']), style: Apex.strong),
                  if (inventoryText(item['sku']).isNotEmpty)
                    Text(inventoryText(item['sku']), style: Apex.note),
                  const SizedBox(height: 4),
                  Text(
                    'Ordered / invoiced / shipped ${_progress(item)}',
                    style: Apex.note,
                  ),
                  if (_quantityField(item) case final field?) ...[
                    const SizedBox(height: 10),
                    field,
                  ],
                ],
              );
            },
          ),
        ),
        const SizedBox(height: 8),
      ],
      if (_operation == 'order.ship') ...[
        CommerceField(
          label: 'Carrier (optional)',
          controller: _carrier,
          onChanged: (_) => _edited(),
        ),
        CommerceField(
          label: 'Tracking number (optional)',
          controller: _tracking,
          onChanged: (_) => _edited(),
        ),
      ],
      if (_operation == 'order.refund')
        const Text(
          'A credit note and a cash refund are separate accounting events. Source quantities and payment evidence are validated before posting.',
        ),
      if (_reviewed != null)
        Card(
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(horizontal: 12),
            title: Text(commerceLabel(_reviewed!.operation)),
            subtitle: Text(
              _operation == 'order.cancel'
                  ? 'The store will review whether the order can still be cancelled.'
                  : '${inventoryObject(_reviewed!.payload['items']).values.fold<int>(0, (n, quantity) => n + (quantity as int))} units on order ${widget.order['number']}',
            ),
          ),
        ),
    ],
    primary: widget.writable
        ? FilledButton(
            onPressed: _reviewed == null
                ? _review
                : () => Navigator.pop(context, _reviewed),
            child: Text(
              _reviewed == null ? 'Review command' : 'Queue reviewed command',
            ),
          )
        : const SizedBox.shrink(),
  );
}
