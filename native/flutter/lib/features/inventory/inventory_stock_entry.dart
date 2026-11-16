import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import 'inventory_models.dart';
import 'inventory_widgets.dart';

class StockEntryForm extends StatefulWidget {
  const StockEntryForm({
    required this.itemId,
    required this.opening,
    super.key,
  });
  final String itemId;
  final bool opening;

  @override
  State<StockEntryForm> createState() => _StockEntryFormState();
}

class _StockEntryFormState extends State<StockEntryForm> {
  final _date = TextEditingController(text: businessDate());
  final _quantity = TextEditingController();
  final _cost = TextEditingController();
  final _reason = TextEditingController();
  String _direction = 'increase';
  String? _error;
  InventoryJson? _reviewed;

  bool get _gain => widget.opening || _direction == 'increase';

  @override
  void dispose() {
    _date.dispose();
    _quantity.dispose();
    _cost.dispose();
    _reason.dispose();
    super.dispose();
  }

  void _edit() => setState(() {
    _reviewed = null;
    _error = null;
  });

  void _review() {
    final date = _date.text.trim();
    final parsed = DateTime.tryParse(date);
    final quantity = inventoryDecimal(_quantity.text, 3);
    final cost = inventoryDecimal(_cost.text, 2);
    if (parsed == null ||
        parsed.toIso8601String().substring(0, 10) != date ||
        date.compareTo(businessDate()) > 0 ||
        quantity == null ||
        quantity <= BigInt.zero) {
      setState(
        () => _error =
            'Enter a valid date through today and a positive quantity.',
      );
      return;
    }
    if (_gain && (cost == null || cost <= BigInt.zero)) {
      setState(() => _error = 'Enter a positive unit cost.');
      return;
    }
    if (!widget.opening && _reason.text.trim().isEmpty) {
      setState(() => _error = 'Enter a reason for the stock adjustment.');
      return;
    }
    setState(
      () => _reviewed = {
        'item_id': widget.itemId,
        'date': date,
        'quantity': _quantity.text.trim(),
        if (_gain) 'unit_cost': _cost.text.trim(),
        if (!widget.opening) 'reason': _reason.text.trim(),
        if (!widget.opening) 'direction': _direction,
      },
    );
  }

  Widget _field(
    String label,
    TextEditingController controller,
    int limit, [
    TextInputType? keyboard,
  ]) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: TextField(
      controller: controller,
      onChanged: (_) => _edit(),
      maxLength: limit,
      keyboardType: keyboard,
      decoration: InputDecoration(labelText: label, counterText: ''),
    ),
  );

  static const _decimal = TextInputType.numberWithOptions(decimal: true);

  @override
  @override
  Widget build(BuildContext context) => InventoryModal(
    title: widget.opening ? 'Opening stock' : 'Stock adjustment',
    subtitle: widget.opening
        ? 'Introduce stock already owned when you begin these books.'
        : 'Record a stock increase or loss with its reason.',
    actions: [
      OutlinedButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _reviewed == null
            ? _review
            : () => Navigator.pop(context, _reviewed),
        child: Text(
          _reviewed == null ? 'Review stock entry' : 'Post stock entry',
        ),
      ),
    ],
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!widget.opening)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: DropdownButtonFormField<String>(
              initialValue: _direction,
              decoration: const InputDecoration(labelText: 'Change'),
              items: const [
                DropdownMenuItem(
                  value: 'increase',
                  child: Text('Increase stock'),
                ),
                DropdownMenuItem(
                  value: 'decrease',
                  child: Text('Decrease stock'),
                ),
              ],
              onChanged: (value) {
                if (value != null) {
                  _direction = value;
                  _edit();
                }
              },
            ),
          ),
        _field('Date (YYYY-MM-DD)', _date, 10),
        _field('Quantity', _quantity, 16, _decimal),
        if (_gain) _field('Unit cost (₹)', _cost, 16, _decimal),
        if (!widget.opening) _field('Reason', _reason, 500),
        if (_reviewed != null)
          InventoryNotice(
            text:
                '${widget.opening
                    ? 'Opening quantity'
                    : _gain
                    ? 'Increase by'
                    : 'Decrease by'} ${_reviewed!['quantity']}',
          ),
        if (_error != null)
          Text(_error!, style: const TextStyle(color: Apex.red, fontSize: 13)),
      ],
    ),
  );
}
