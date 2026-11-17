import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'inventory_models.dart';
import 'inventory_widgets.dart';
import 'inventory_posting.dart';
import 'inventory_reorder_order.dart';

class InventoryReorderPage extends StatefulWidget {
  const InventoryReorderPage({
    required this.workspace,
    required this.openItem,
    super.key,
  });
  final WorkspaceContext workspace;
  final Future<void> Function(InventoryJson) openItem;

  @override
  State<InventoryReorderPage> createState() => _InventoryReorderPageState();
}

class _InventoryReorderPageState extends State<InventoryReorderPage> {
  late Future<InventoryJson> _report = _load();
  final _search = TextEditingController();
  final _selection = <String, String>{};
  String? _created;
  bool _creating = false;

  bool get _canWrite => widget.workspace.company.canWrite;

  Future<InventoryJson> _load() async => inventoryObject(
    await widget.workspace.api.get(
      '${widget.workspace.path}/reports/reorder',
      query: {'as_of': businessDate()},
    ),
  );

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _refresh() {
    final report = _load();
    setState(() {
      _report = report;
      _selection.clear();
    });
  }

  Future<void> _createOrder(List<InventoryJson> rows) async {
    if (_creating) return;
    setState(() => _creating = true);
    final chosen = [
      for (final row in rows)
        if (_selection.containsKey(inventoryText(row['item_id'])))
          (row, _selection[inventoryText(row['item_id'])]!),
    ];
    final created = await showReorderOrderDialog(
      context,
      widget.workspace,
      chosen,
    );
    if (!mounted) return;
    setState(() {
      _creating = false;
      if (created != null) {
        final number = inventoryText(created['number']);
        _created = number.isEmpty ? 'draft' : number;
        _selection.clear();
      }
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Apex.paper,
    appBar: AppBar(
      title: const Text('Stock'),
      actions: [
        IconButton(
          onPressed: _refresh,
          tooltip: 'Refresh low stock',
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: SafeArea(
      child: FutureBuilder<InventoryJson>(
        future: _report,
        builder: (context, state) {
          if (state.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (state.hasError) {
            return ApexPage(
              maxWidth: 1080,
              children: [InventoryNotice(text: inventoryError(state.error!))],
            );
          }
          final data = state.data ?? const {};
          final rows = inventoryRows(data['rows']);
          final query = _search.text.trim().toLowerCase();
          final visible = rows
              .where(
                (row) =>
                    inventoryText(row['name']).toLowerCase().contains(query),
              )
              .take(100)
              .toList();
          final selected = rows
              .where(
                (row) => _selection.containsKey(inventoryText(row['item_id'])),
              )
              .toList();
          final valid =
              selected.isNotEmpty &&
              selected.length <= 100 &&
              selected.every(
                (row) => reorderQuantityValid(
                  _selection[inventoryText(row['item_id'])] ?? '',
                ),
              );
          return ApexPage(
            maxWidth: 1080,
            children: [
              const Text(
                'INVENTORY PLANNING',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: .8,
                  color: Apex.greenText,
                ),
              ),
              const SizedBox(height: 6),
              const ApexRegisterHeading(
                'Low stock & reorder',
                subtitle:
                    'Review stock at or below your saved threshold. Nothing is ordered or posted until you review and save a purchase order.',
              ),
              const SizedBox(height: 18),
              if (_created case final number?)
                InventoryNotice(
                  text:
                      'Purchase order $number created. Review this order before placing another. Stock is unchanged until goods are received and recorded; the low-stock recommendation remains visible.',
                ),
              ApexRegisterPanel(
                title: rows.length == 1
                    ? '1 item at or below its threshold'
                    : '${rows.length} items at or below their thresholds',
                subtitle: 'As of ${data['as_of']}',
                child: rows.isEmpty
                    ? ApexEmptyState(
                        icon: Icons.inventory_2_outlined,
                        title: 'No low-stock items for this date',
                        note:
                            'Enable a threshold on a tracked item to include it. A blank threshold disables alerts; zero is a valid threshold.',
                        action: OutlinedButton(
                          onPressed: () => Navigator.of(context).maybePop(),
                          child: const Text('Manage item thresholds'),
                        ),
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(22, 4, 22, 8),
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: ApexSearchField(
                                controller: _search,
                                hint: 'Search recommendations',
                                onChanged: (_) => setState(() {}),
                              ),
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.fromLTRB(22, 0, 22, 8),
                            child: Text(
                              'Showing ${visible.length} of ${rows.length} recommendations. Select at most 100 items per purchase order.',
                              style: Apex.note,
                            ),
                          ),
                          for (final (index, row) in visible.indexed) ...[
                            if (index > 0)
                              const Divider(height: 1, color: Apex.lineSoft),
                            _row(row),
                          ],
                        ],
                      ),
              ),
              if (_canWrite && rows.isNotEmpty) ...[
                const SizedBox(height: 14),
                Wrap(
                  spacing: 14,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  alignment: WrapAlignment.end,
                  children: [
                    Text(
                      '${selected.length} selected · Draft only, no stock or payment movement',
                      style: Apex.note,
                    ),
                    FilledButton.icon(
                      onPressed: valid && !_creating
                          ? () => _createOrder(rows)
                          : null,
                      icon: const Icon(Icons.arrow_forward, size: 16),
                      iconAlignment: IconAlignment.end,
                      label: const Text('Create purchase order'),
                    ),
                  ],
                ),
              ],
              if (!_canWrite)
                const InventoryNotice(
                  text:
                      'Read-only access. An owner or editor can change thresholds and prepare a purchase order.',
                ),
            ],
          );
        },
      ),
    ),
  );

  Widget _row(InventoryJson row) {
    final unit = inventoryText(row['unit']);
    final id = inventoryText(row['item_id']);
    final picked = _selection.containsKey(id);
    final warning = switch (row['valuation_status']) {
      'negative' => 'Negative inventory',
      'unvalued' => 'Stock valuation requires review',
      _ => '',
    };
    return InkWell(
      onTap: () async {
        await widget.openItem(row);
        if (mounted) _refresh();
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Row(
          children: [
            if (_canWrite)
              Checkbox(
                value: picked,
                semanticLabel: 'Select ${row['name']}',
                onChanged: (value) => setState(() {
                  if (value == true) {
                    final suggested = inventoryText(row['suggested_quantity']);
                    _selection[id] = (double.tryParse(suggested) ?? 0) > 0
                        ? suggested
                        : '';
                  } else {
                    _selection.remove(id);
                  }
                }),
              )
            else
              const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(inventoryText(row['name']), style: Apex.strong),
                  const SizedBox(height: 3),
                  Text(
                    'On hand ${inventoryQuantity(row['on_hand'])} · Threshold ${inventoryQuantity(row['low_stock_threshold'])}',
                    style: Apex.note,
                  ),
                  if (warning.isNotEmpty)
                    Text(
                      warning,
                      style: const TextStyle(fontSize: 12, color: Apex.red),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            if (_canWrite && picked) ...[
              SizedBox(
                width: 110,
                child: TextFormField(
                  key: ValueKey('reorder-quantity-$id'),
                  initialValue: _selection[id],
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: InputDecoration(
                    isDense: true,
                    labelText: 'Order quantity',
                    errorText: reorderQuantityValid(_selection[id] ?? '')
                        ? null
                        : 'Invalid',
                  ),
                  onChanged: (value) => setState(() => _selection[id] = value),
                ),
              ),
              const SizedBox(width: 12),
            ],
            ApexStatusBadge(
              'Suggest ${inventoryQuantity(row['suggested_quantity'])} $unit'
                  .trim(),
              tone: ApexBadgeTone.draft,
            ),
          ],
        ),
      ),
    );
  }
}
