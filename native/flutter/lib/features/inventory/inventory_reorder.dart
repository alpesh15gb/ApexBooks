import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'inventory_models.dart';
import 'inventory_widgets.dart';
import 'inventory_posting.dart';

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

  Future<InventoryJson> _load() async => inventoryObject(
    await widget.workspace.api.get('${widget.workspace.path}/reports/reorder'),
  );

  void _refresh() {
    final report = _load();
    setState(() {
      _report = report;
    });
  }

  @override
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
          return ApexPage(
            maxWidth: 1080,
            children: [
              const ApexRegisterHeading(
                'Low stock & reorder',
                subtitle: 'Suggested quantities are a starting point for reviewing a purchase order.',
              ),
              const SizedBox(height: 18),
              ApexRegisterPanel(
                title: rows.length == 1
                    ? '1 item at or below its threshold'
                    : '${rows.length} items at or below their thresholds',
                subtitle: 'As of ${data['as_of']}',
                child: rows.isEmpty
                    ? const ApexEmptyState(
                        icon: Icons.inventory_2_outlined,
                        title: 'No low-stock items for this date',
                        note: 'Enable a threshold on a tracked item to include it.',
                      )
                    : Column(
                        children: [
                          for (final (index, row) in rows.indexed) ...[
                            if (index > 0)
                              const Divider(height: 1, color: Apex.lineSoft),
                            _row(row),
                          ],
                        ],
                      ),
              ),
            ],
          );
        },
      ),
    ),
  );

  Widget _row(InventoryJson row) {
    final unit = inventoryText(row['unit']);
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
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
        child: Row(
          children: [
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
