import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import 'inventory_models.dart';
import 'inventory_movements.dart';
import 'inventory_posting.dart';
import 'inventory_setup.dart';
import 'inventory_stock_entry.dart';
import 'inventory_widgets.dart';

class InventoryCountPage extends StatefulWidget {
  const InventoryCountPage({
    required this.posting,
    required this.item,
    required this.stock,
    required this.locations,
    this.automobileEnabled = false,
    this.startWith,
    super.key,
  });

  final InventoryPosting posting;
  final InventoryJson item;
  final Object? stock;
  final List<String> locations;
  final bool automobileEnabled;

  /// `opening` opens the opening-stock entry as soon as the page is ready.
  final String? startWith;

  @override
  State<InventoryCountPage> createState() => _InventoryCountPageState();
}

class _InventoryCountPageState extends State<InventoryCountPage> {
  late Future<InventoryJson> _snapshot;
  final _quantity = TextEditingController();
  final _reason = TextEditingController();
  final _cost = TextEditingController();
  String? _error;
  String? _saved;
  bool _reviewed = false;

  InventoryPosting get _posting => widget.posting;
  WorkspaceContext get _workspace => _posting.workspace;
  String get _id => inventoryText(widget.item['id']);
  InventoryJson get _itemData => inventoryObject(widget.item['data']);
  bool get _isTrackedGoods =>
      _itemData['track_stock'] == true &&
      (_itemData['item_type'] ?? 'goods') == 'goods';
  bool get _supported =>
      _workspace.features.contains('stock_counts') && _isTrackedGoods;
  bool get _pendingHere =>
      _posting.pending?.kind != 'receipt' && _posting.pending?.recordId == _id;

  @override
  void initState() {
    super.initState();
    _snapshot = _load();
    final start = widget.startWith;
    if (start != null) {
      _snapshot.then<void>((_) {}, onError: (Object _) {}).then((_) {
        if (!mounted) return;
        final ready =
            _workspace.company.canWrite &&
            _posting.loaded &&
            _posting.recoveryError == null &&
            _posting.pending == null &&
            !_posting.busy &&
            _isTrackedGoods;
        if (ready) _manualEntry(opening: start == 'opening');
      });
    }
  }

  Future<InventoryJson> _load() async => _supported
      ? inventoryObject(
          await _workspace.api.get(
            '${_posting.base}/stock/counts/${Uri.encodeComponent(_id)}',
          ),
        )
      : const {};

  void _reload() => setState(() {
    _snapshot = _load();
    _reviewed = false;
    _quantity.clear();
    _reason.clear();
    _cost.clear();
    _error = null;
  });

  BigInt? _difference(InventoryJson snapshot) {
    final counted = inventoryDecimal(_quantity.text, 3);
    final onHand = inventoryDecimal(inventoryQuantity(snapshot['on_hand']), 3);
    return counted == null || onHand == null ? null : counted - onHand;
  }

  InventoryJson _body(InventoryJson snapshot) {
    final delta = _difference(snapshot);
    final reason = _reason.text.trim();
    if (delta == null) {
      throw const FormatException(
        'Enter a physical quantity with at most three decimal places.',
      );
    }
    if (delta == BigInt.zero) {
      throw const FormatException(
        'Count matches on-hand stock. No adjustment is needed.',
      );
    }
    if (reason.isEmpty) {
      throw const FormatException('Enter a reason for the count difference.');
    }
    final gain = delta > BigInt.zero;
    if (gain &&
        (inventoryDecimal(_cost.text, 2) ?? BigInt.zero) <= BigInt.zero) {
      throw const FormatException(
        'Enter a positive unit cost for the added stock.',
      );
    }
    return {
      'item_id': _id,
      'date': snapshot['date'],
      'stock_snapshot': snapshot['stock_snapshot'],
      'counted_quantity': _quantity.text.trim(),
      'reason': reason,
      if (gain) 'unit_cost': _cost.text.trim(),
    };
  }

  void _edit() => setState(() {
    _reviewed = false;
    _error = null;
  });

  void _review(InventoryJson snapshot) {
    try {
      _body(snapshot);
      setState(() {
        _reviewed = true;
        _error = null;
      });
    } catch (error) {
      setState(() => _error = inventoryError(error));
    }
  }

  Future<void> _post(InventoryJson snapshot) async {
    final kind = _pendingHere ? _posting.pending!.kind : 'count';
    setState(() => _error = null);
    try {
      final result = _pendingHere
          ? await _posting.retry()
          : await _posting.submit(
              'count',
              _id,
              inventoryText(widget.item['name']),
              _body(snapshot),
            );
      if (!mounted) return;
      _reload();
      setState(() => _saved = inventorySavedMessage(result, kind));
      await _workspace.refresh();
    } catch (error) {
      if (!mounted) return;
      if (error is ApexApiException &&
          requiresInventoryReview(error, 'count') &&
          _posting.pending == null) {
        _reload();
      }
      setState(() => _error = inventoryError(error));
    }
  }

  Future<void> _manualEntry({required bool opening}) async {
    final body = await showDialog<InventoryJson>(
      context: context,
      builder: (_) => StockEntryForm(itemId: _id, opening: opening),
    );
    if (!mounted || body == null) return;
    final kind = opening ? 'opening' : 'adjustment';
    setState(() => _error = null);
    try {
      final result = await _posting.submit(
        kind,
        _id,
        inventoryText(widget.item['name']),
        body,
      );
      if (!mounted) return;
      _reload();
      setState(() => _saved = inventorySavedMessage(result, kind));
      await _workspace.refresh();
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    }
  }

  void _openMovements() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) =>
          InventoryMovementsPage(workspace: _workspace, item: widget.item),
    ),
  );

  String _delta(BigInt value) {
    final magnitude = value.abs();
    final units = magnitude ~/ BigInt.from(1000);
    final fraction = (magnitude % BigInt.from(1000)).toString().padLeft(3, '0');
    return inventoryQuantity('$units.$fraction');
  }

  @override
  void dispose() {
    _quantity.dispose();
    _reason.dispose();
    _cost.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _posting,
    builder: (context, _) {
      final data = _itemData;
      final unit = inventoryText(data['unit']);
      final available =
          _workspace.company.canWrite &&
          _posting.loaded &&
          _posting.recoveryError == null;
      final canEdit = available && _posting.pending == null && !_posting.busy;
      return PopScope(
        canPop: !_posting.busy,
        child: Scaffold(
          appBar: AppBar(
            title: const Text('Stock'),
            actions: [
              if (_supported)
                IconButton(
                  tooltip: 'Refresh on-hand quantity',
                  onPressed: _posting.busy ? null : _reload,
                  icon: const Icon(Icons.refresh),
                ),
            ],
          ),
          body: FutureBuilder<InventoryJson>(
            future: _snapshot,
            builder: (context, state) {
              final snapshot = state.data ?? const <String, dynamic>{};
              final onHand = snapshot['on_hand'] ?? widget.stock;
              final delta = _difference(snapshot);
              final gain = delta != null && delta > BigInt.zero;
              final found =
                  snapshot['stock_snapshot'] is String &&
                  state.connectionState == ConnectionState.done;
              final details = [
                inventoryText(data['sku']),
                inventoryText(data['barcode']),
                ...widget.locations,
              ].where((value) => value.isNotEmpty).join(' · ');
              final autoDetails = widget.automobileEnabled
                  ? [
                      if (inventoryText(data['oem_number']).isNotEmpty)
                        'OEM ${data['oem_number']}',
                      inventoryText(data['part_brand']),
                      inventoryText(data['part_grade']),
                    ].where((value) => value.isNotEmpty).join(' · ')
                  : '';
              final fits = widget.automobileEnabled
                  ? inventoryRows(data['vehicle_fitment'])
                        .map(VehicleFitment.fromJson)
                        .toList()
                  : const <VehicleFitment>[];
              return SafeArea(
                child: ListView(
                  padding: EdgeInsets.symmetric(
                    horizontal: MediaQuery.sizeOf(context).width > 912
                        ? (MediaQuery.sizeOf(context).width - 880) / 2
                        : 16,
                    vertical: 20,
                  ),
                  children: [
                    Text(
                      inventoryText(widget.item['name']),
                      style: Apex.registerTitle,
                    ),
                    if (details.isNotEmpty) Text(details, style: Apex.note),
                    if (autoDetails.isNotEmpty) Text(autoDetails),
                    if (fits.isNotEmpty)
                      ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        title: const Text('Fits vehicles'),
                        children: [
                          for (final fit in fits)
                            ListTile(
                              title: Text(fit.label),
                              contentPadding: EdgeInsets.zero,
                            ),
                        ],
                      ),
                    if (data['is_active'] == false) const Text('Archived item'),
                    if (data['track_stock'] != true)
                      const Text('Stock is not tracked for this item.'),
                    if (data['track_stock'] == true)
                      Text(
                        onHand == null
                            ? 'Current stock unavailable'
                            : '${inventoryQuantity(onHand)} $unit on hand',
                        style: Apex.registerTitle.copyWith(fontSize: 26),
                      ),
                    if (_isTrackedGoods &&
                        _workspace.features.contains('stock_movement_history'))
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: _openMovements,
                          icon: const Icon(Icons.history),
                          label: const Text('Stock movements'),
                        ),
                      ),
                    if (_saved != null) InventoryNotice(text: _saved!),
                    if (_error != null) InventoryNotice(text: _error!),
                    if (state.connectionState != ConnectionState.done)
                      const LinearProgressIndicator(),
                    if (state.hasError)
                      InventoryNotice(text: inventoryError(state.error!)),
                    if (_posting.pending != null)
                      InventoryNotice(
                        text: _pendingHere
                            ? 'The previous stock entry is awaiting confirmation.'
                            : 'Complete the pending inventory request before posting another.',
                        action: _pendingHere && available
                            ? TextButton(
                                onPressed: _posting.busy
                                    ? null
                                    : () => _post(snapshot),
                                child: const Text('Retry original entry'),
                              )
                            : null,
                      ),
                    if (found &&
                        _workspace.company.canWrite &&
                        _posting.pending == null) ...[
                      const SizedBox(height: 12),
                      Text('Physical count', style: Apex.sectionTitle),
                      Text('Business date ${snapshot['date']}'),
                      TextField(
                        controller: _quantity,
                        enabled: canEdit,
                        onChanged: (_) => _edit(),
                        keyboardType: const TextInputType.numberWithOptions(
                          decimal: true,
                        ),
                        decoration: const InputDecoration(
                          labelText: 'Counted quantity',
                        ),
                      ),
                      if (gain)
                        TextField(
                          controller: _cost,
                          enabled: canEdit,
                          onChanged: (_) => _edit(),
                          keyboardType: const TextInputType.numberWithOptions(
                            decimal: true,
                          ),
                          decoration: const InputDecoration(
                            labelText: 'Unit cost of added stock (₹)',
                          ),
                        ),
                      TextField(
                        controller: _reason,
                        enabled: canEdit,
                        onChanged: (_) => _edit(),
                        maxLength: 500,
                        decoration: const InputDecoration(
                          labelText: 'Reason for difference',
                        ),
                      ),
                      if (_reviewed && delta != null) ...[
                        Text(
                          '${gain ? 'Increase' : 'Decrease'} by ${_delta(delta)} $unit',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        FilledButton.icon(
                          onPressed: canEdit ? () => _post(snapshot) : null,
                          icon: const Icon(Icons.check),
                          label: const Text('Record stock count'),
                        ),
                      ] else
                        FilledButton(
                          onPressed: canEdit ? () => _review(snapshot) : null,
                          child: const Text('Review adjustment'),
                        ),
                    ],
                    if (_isTrackedGoods &&
                        _workspace.company.canWrite &&
                        _posting.pending == null) ...[
                      const SizedBox(height: 18),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          if (_itemData['is_active'] != false &&
                              (onHand == null ||
                                  inventoryDecimal(
                                        inventoryQuantity(onHand),
                                        3,
                                      ) ==
                                      BigInt.zero))
                            OutlinedButton(
                              onPressed: canEdit
                                  ? () => _manualEntry(opening: true)
                                  : null,
                              child: const Text('Opening stock'),
                            ),
                          OutlinedButton(
                            onPressed: canEdit
                                ? () => _manualEntry(opening: false)
                                : null,
                            child: const Text('Stock adjustment'),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              );
            },
          ),
        ),
      );
    },
  );
}
