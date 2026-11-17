import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'inventory_models.dart';
import 'inventory_posting.dart';
import 'inventory_widgets.dart';

/// Quantity rule shared with the web reorder page: greater than zero, up to 3 decimals.
bool reorderQuantityValid(String value) =>
    RegExp(r'^\d+(\.\d{1,3})?$').hasMatch(value) &&
    (double.tryParse(value) ?? 0) > 0;

Future<List<InventoryJson>> inventoryAllRecords(
  WorkspaceContext workspace,
  String kind,
) async {
  const pageSize = 200;
  final path = '/api/companies/${Uri.encodeComponent(workspace.company.id)}/records';
  final records = <String, InventoryJson>{};
  for (var offset = 0; ; offset += pageSize) {
    final page = inventoryRows(
      await workspace.api.get(
        path,
        query: {
          'kind': kind,
          'compact': 'true',
          'limit': '$pageSize',
          'offset': '$offset',
        },
      ),
    );
    final before = records.length;
    for (final row in page) {
      records[inventoryText(row['id'])] = row;
    }
    if (page.length < pageSize || before == records.length) {
      return records.values.toList();
    }
  }
}

/// Review step for the selected low-stock suggestions: choose the supplier and create a
/// purchase order draft. A draft never moves stock or money.
Future<InventoryJson?> showReorderOrderDialog(
  BuildContext context,
  WorkspaceContext workspace,
  List<(InventoryJson, String)> chosen,
) => showDialog<InventoryJson>(
  context: context,
  barrierDismissible: false,
  builder: (_) => _ReorderOrderDialog(workspace: workspace, chosen: chosen),
);

class _ReorderOrderDialog extends StatefulWidget {
  const _ReorderOrderDialog({required this.workspace, required this.chosen});
  final WorkspaceContext workspace;
  final List<(InventoryJson, String)> chosen;

  @override
  State<_ReorderOrderDialog> createState() => _ReorderOrderDialogState();
}

class _ReorderOrderDialogState extends State<_ReorderOrderDialog> {
  late final Future<(List<InventoryJson>, List<InventoryJson>)> _lookups =
      () async {
        final items = await inventoryAllRecords(widget.workspace, 'item');
        final parties = await inventoryAllRecords(widget.workspace, 'party');
        return (items, parties);
      }();
  InventoryJson? _supplier;
  bool _busy = false;
  String? _error;
  String _key = _newKey();

  static String _newKey() {
    final random = Random.secure();
    return 'flutter-reorder-${List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join()}';
  }

  List<InventoryJson> _lines(List<InventoryJson> items) => [
    for (final (row, quantity) in widget.chosen)
      () {
        final item = items
            .where((entry) => entry['id'] == row['item_id'])
            .firstOrNull;
        if (item == null) {
          throw const FormatException(
            'Wait for the item catalogue to finish loading, then review the order again.',
          );
        }
        final data = inventoryObject(item['data']);
        if (data['is_active'] == false) {
          throw const FormatException(
            'An item is now inactive. Refresh the reorder review before continuing.',
          );
        }
        final gst = inventoryText(data['gst_rate']).isEmpty
            ? '0'
            : inventoryText(data['gst_rate']);
        final rate = inventoryText(row['purchase_rate']);
        return <String, dynamic>{
          'item_id': row['item_id'],
          'description': row['name'],
          'unit': row['unit'],
          'quantity': quantity,
          'rate': rate.isEmpty ? '0' : rate,
          'gst_rate': gst,
          'hsn': inventoryText(data['hsn']),
          'tax_treatment': inventoryText(data['tax_treatment']).isNotEmpty
              ? inventoryText(data['tax_treatment'])
              : ((double.tryParse(gst) ?? 0) != 0 ? 'taxable' : 'nil_rated'),
          'discount_percent': '0',
          'price_includes_tax': false,
        };
      }(),
  ];

  Future<void> _create(List<InventoryJson> items) async {
    final supplier = _supplier;
    if (supplier == null || _busy) return;
    final key = _key;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = inventoryObject(supplier['data']);
      final gstin = inventoryText(data['gstin']);
      final result = await widget.workspace.api.post(
        '/api/companies/${Uri.encodeComponent(widget.workspace.company.id)}/records',
        idempotencyKey: key,
        body: {
          'kind': 'purchase_order',
          'name': inventoryText(supplier['name']),
          'date': businessDate(),
          'number': '',
          'amount': '0',
          'data': {
            'party_id': supplier['id'],
            if (gstin.isNotEmpty) 'party_gstin': gstin,
            if (inventoryText(data['address']).isNotEmpty)
              'party_address': inventoryText(data['address']),
            if (inventoryText(data['phone']).isNotEmpty)
              'party_phone': inventoryText(data['phone']),
            'lines': _lines(items),
            'round_total': false,
            'document_discount_percent': '0',
          },
        },
      );
      if (mounted) Navigator.of(context).pop(inventoryObject(result));
    } catch (failure) {
      if (!mounted) return;
      // A definite rejection frees the key; an uncertain one keeps it so a retry is the same request.
      if (failure is ApexApiException && !failure.uncertain) _key = _newKey();
      setState(() {
        _busy = false;
        _error = inventoryError(failure);
      });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Review purchase order'),
    scrollable: true,
    content: SizedBox(
      width: 640,
      child: FutureBuilder<(List<InventoryJson>, List<InventoryJson>)>(
        future: _lookups,
        builder: (context, state) {
          if (state.hasError) {
            return Text(inventoryError(state.error!));
          }
          if (!state.hasData) {
            return const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final (items, parties) = state.data!;
          final suppliers = parties.where((party) {
            final data = inventoryObject(party['data']);
            final type = inventoryText(data['party_type']);
            return data['is_active'] != false &&
                (type.isEmpty || type == 'both' || type == 'supplier');
          }).toList()
            ..sort(
              (a, b) => inventoryText(a['name'])
                  .toLowerCase()
                  .compareTo(inventoryText(b['name']).toLowerCase()),
            );
          String? problem;
          try {
            _lines(items);
          } on FormatException catch (failure) {
            problem = failure.message;
          }
          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Reorder draft only. Choose a supplier and review quantities. Saving this purchase order does not move stock or money.',
                style: Apex.note,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<InventoryJson>(
                initialValue: _supplier,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Supplier'),
                items: [
                  for (final party in suppliers)
                    DropdownMenuItem(
                      value: party,
                      child: Text(
                        inventoryText(party['name']),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: _busy ? null : (value) => setState(() => _supplier = value),
              ),
              const SizedBox(height: 14),
              ApexPanel(
                padding: EdgeInsets.zero,
                child: InventoryDialogTable(
                  headers: const ['Item', 'Quantity', 'Unit'],
                  flex: const [3, 1, 1],
                  rowCount: widget.chosen.length,
                  cell: (row, column) {
                    final (line, quantity) = widget.chosen[row];
                    return switch (column) {
                      0 => Text(
                        inventoryText(line['name']),
                        style: Apex.strong,
                      ),
                      1 => Text(quantity),
                      _ => Text(inventoryText(line['unit'])),
                    };
                  },
                  card: (row) {
                    final (line, quantity) = widget.chosen[row];
                    return Row(
                      children: [
                        Expanded(
                          child: Text(
                            inventoryText(line['name']),
                            style: Apex.strong,
                          ),
                        ),
                        Text('$quantity ${inventoryText(line['unit'])}'.trim()),
                      ],
                    );
                  },
                  breakpoint: 520,
                ),
              ),
              if (problem != null || _error != null) ...[
                const SizedBox(height: 10),
                Text(
                  problem ?? _error!,
                  style: const TextStyle(color: Apex.red),
                ),
              ],
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                spacing: 8,
                children: [
                  TextButton(
                    onPressed: _busy ? null : () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    onPressed: _busy || _supplier == null || problem != null
                        ? null
                        : () => _create(items),
                    child: Text(_busy ? 'Creating…' : 'Create purchase order'),
                  ),
                ],
              ),
            ],
          );
        },
      ),
    ),
  );
}
