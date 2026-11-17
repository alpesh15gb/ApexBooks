import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../books/books_data.dart';
import '../books/books_detail.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'inventory_models.dart';
import 'inventory_rules.dart';
import 'inventory_widgets.dart';
import 'inventory_posting.dart';

class InventoryMovementsPage extends StatefulWidget {
  const InventoryMovementsPage({
    required this.workspace,
    required this.item,
    super.key,
  });
  final WorkspaceContext workspace;
  final InventoryJson item;

  @override
  State<InventoryMovementsPage> createState() => _InventoryMovementsPageState();
}

class _InventoryMovementsPageState extends State<InventoryMovementsPage> {
  late String _to = businessDate();
  late String _from = DateTime.parse(_to)
      .subtract(const Duration(days: 89))
      .toIso8601String()
      .substring(0, 10);
  final _rows = <String, InventoryJson>{};
  InventoryJson? _next;
  String? _error;
  bool _loading = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({required bool reset}) async {
    if (!reset && (_next == null || _loading)) return;
    final next = reset ? null : _next;
    final range = {
      'from_date': _from,
      'to_date': _to,
      'limit': '50',
      if (next != null) 'before_date': inventoryText(next['date']),
      if (next != null) 'before_id': inventoryText(next['id']),
    };
    final generation = ++_generation;
    setState(() {
      if (reset) {
        _rows.clear();
        _next = null;
      }
      _loading = true;
      _error = null;
    });
    try {
      final id = Uri.encodeComponent(inventoryText(widget.item['id']));
      final data = inventoryObject(
        await widget.workspace.api.get(
          '${widget.workspace.path}/reports/stock/$id/movements',
          query: range,
        ),
      );
      if (!mounted || generation != _generation) return;
      final cursor = inventoryObject(data['next']);
      setState(() {
        for (final row in inventoryRows(data['rows'])) {
          _rows[inventoryText(row['id'])] = row;
        }
        _next =
            cursor['date'] is String &&
                cursor['id'] is String &&
                (cursor['date'] != next?['date'] || cursor['id'] != next?['id'])
            ? cursor
            : null;
      });
    } catch (failure) {
      if (mounted && generation == _generation) {
        setState(() => _error = inventoryError(failure));
      }
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _pick(bool start) async {
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.parse(start ? _from : _to),
      firstDate: start ? DateTime(1900) : DateTime.parse(_from),
      lastDate: DateTime.parse(start ? _to : businessDate()),
    );
    if (date == null || !mounted) return;
    final iso = date.toIso8601String().substring(0, 10);
    if (start) {
      _from = iso;
    } else {
      _to = iso;
    }
    await _load(reset: true);
  }

  void _open(String id) {
    if (id.isEmpty) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => Scaffold(
          body: SafeArea(
            child: BooksRecordDetail(
              data: BooksData(
                widget.workspace.company.id,
                widget.workspace.api.get,
              ),
              id: id,
              onBack: () => Navigator.of(context).pop(),
              onOpen: _open,
              backLabel: 'Return to stock movements',
            ),
          ),
        ),
      ),
    );
  }

  String _kind(Object? kind) => switch (kind) {
    'stock_opening' => 'Opening stock',
    'stock_adjustment' => 'Stock adjustment',
    'purchase_bill' => 'Purchase bill',
    'debit_note' => 'Purchase return',
    'sales_invoice' => 'Sales invoice',
    'credit_note' => 'Sales return',
    'stock_return' => 'Stock return',
    'pos' => 'POS receipt',
    _ => inventoryText(kind).replaceAll('_', ' '),
  };

  @override
  Widget build(BuildContext context) {
    final rows = _rows.values.toList();
    return Scaffold(
      backgroundColor: Apex.paper,
      appBar: AppBar(title: const Text('Stock movements')),
      body: SafeArea(
        child: ApexPage(
          maxWidth: 960,
          children: [
            ApexRegisterHeading(
              inventoryText(widget.item['name']),
              subtitle: 'Quantity change and cost change, newest first',
              actions: [
                OutlinedButton(
                  onPressed: () => _pick(true),
                  child: Text('From $_from'),
                ),
                OutlinedButton(
                  onPressed: () => _pick(false),
                  child: Text('Through $_to'),
                ),
                IconButton(
                  onPressed: _loading ? null : () => _load(reset: true),
                  tooltip: 'Refresh movements',
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 18),
            if (_loading) const LinearProgressIndicator(),
            if (_error != null) InventoryNotice(text: _error!),
            ApexPanel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (!_loading && _error == null && rows.isEmpty)
                    const ApexEmptyState(
                      icon: Icons.history,
                      title: 'No movements during this period.',
                    ),
                  for (final (index, row) in rows.indexed) ...[
                    if (index > 0)
                      const Divider(height: 1, color: Apex.lineSoft),
                    _movement(row),
                  ],
                ],
              ),
            ),
            if (_next != null)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton(
                    onPressed: _loading ? null : () => _load(reset: false),
                    child: const Text('Load older movements'),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _movement(InventoryJson row) {
    final quantity = inventoryMovementQuantity(
      row['quantity'],
      inventoryObject(widget.item['data'])['unit'],
    );
    final negative = quantity.startsWith('-');
    return InkWell(
      onTap: () => _open(inventoryText(row['record_id'])),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${_kind(row['kind'])}${inventoryText(row['number']).isEmpty ? '' : ' · ${inventoryText(row['number'])}'}',
                    style: Apex.strong,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${row['date']} · Cost change ${inventoryMovementCost(row['cost_value'])}',
                    style: Apex.note,
                  ),
                ],
              ),
            ),
            Text(
              quantity,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: negative ? Apex.red : Apex.greenText,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
