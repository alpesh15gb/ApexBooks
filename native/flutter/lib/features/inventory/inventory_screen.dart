import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'inventory_count.dart';
import 'inventory_models.dart';
import 'inventory_posting.dart';
import 'inventory_receiving.dart';
import 'inventory_reorder.dart';
import 'inventory_setup.dart';
import 'inventory_widgets.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({
    required this.workspace,
    this.active = true,
    this.revision = 0,
    super.key,
  });

  final WorkspaceContext workspace;
  final bool active;
  final int revision;

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  static const _unassigned = ':unassigned';
  static const _tableWidth = 720.0;
  final _itemSearch = TextEditingController();
  final _orderSearch = TextEditingController();
  late InventoryPosting _posting;
  late Future<List<InventoryJson>> _items;
  late Future<List<InventoryJson>> _orders;
  late Future<InventoryJson> _stock;
  late Future<InventorySetup> _setup;
  String _shelf = '';
  String _orderFilter = '';
  bool _showArchived = false;
  int _tab = 0;

  WorkspaceContext get _workspace => widget.workspace;

  @override
  void initState() {
    super.initState();
    _startCompany();
  }

  @override
  void didUpdateWidget(covariant InventoryScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workspace.company.id != _workspace.company.id ||
        oldWidget.workspace.company.canWrite != _workspace.company.canWrite) {
      _posting.dispose();
      _itemSearch.clear();
      _orderSearch.clear();
      _showArchived = false;
      _shelf = '';
      _orderFilter = '';
      _startCompany();
    } else if (widget.active &&
        (!oldWidget.active || oldWidget.revision != widget.revision)) {
      _reload();
    }
  }

  void _startCompany() {
    _posting = InventoryPosting(_workspace);
    _posting.load();
    _reload();
  }

  void _reload() {
    _items = _records('item');
    _orders = _records('purchase_order');
    _stock = _readStock();
    _setup = InventorySetup.load(_workspace);
    for (final future in [_items, _orders, _stock, _setup]) {
      future.then<void>((_) {}, onError: (Object _) {});
    }
  }

  Future<List<InventoryJson>> _records(String kind) async {
    const pageSize = 200;
    final path = '${_posting.base}/records';
    final api = _workspace.api;
    final records = <String, InventoryJson>{};
    for (var offset = 0; ; offset += pageSize) {
      final result = await api.get(
        path,
        query: {
          'kind': kind,
          'compact': 'true',
          'limit': '$pageSize',
          'offset': '$offset',
        },
      );
      final page = inventoryRows(result);
      final previousLength = records.length;
      for (final row in page) {
        records[inventoryText(row['id'])] = row;
      }
      if (page.length < pageSize || previousLength == records.length) {
        return records.values.toList();
      }
    }
  }

  Future<InventoryJson> _readStock() async {
    if (_workspace.features.contains('pos_stock_summary')) {
      return inventoryObject(
        await _workspace.api.get('${_posting.base}/pos/stock'),
      );
    }
    final date = businessDate();
    final report = inventoryObject(
      await _workspace.api.get(
        '${_posting.base}/reports/stock',
        query: {'from_date': date, 'to_date': date},
      ),
    );
    return {'date': report['to_date'] ?? date, 'rows': report['rows']};
  }

  Future<void> _refresh() async {
    setState(_reload);
    await Future.wait<Object>([_items, _orders, _stock, _setup])
        .then<void>((_) {}, onError: (Object _) {});
  }

  Future<void> _openItem(
    InventoryJson item,
    Object? stock,
    InventorySetup setup, {
    String? startWith,
  }) async {
    final data = inventoryObject(item['data']);
    final existing = data['location_ids'];
    final names = setup.shelfLabels;
    final locations = existing is List
        ? existing.map((id) => names[id]).whereType<String>().toList()
        : <String>[];
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => InventoryCountPage(
          posting: _posting,
          item: item,
          stock: stock,
          locations: locations,
          automobileEnabled: setup.automobileEnabled,
          startWith: startWith,
        ),
      ),
    );
    if (mounted) await _refresh();
  }

  Future<void> _openOrder(InventoryJson order, String? serverDate) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => InventoryReceivingPage(
          posting: _posting,
          order: order,
          today: serverDate ?? businessDate(),
        ),
      ),
    );
    if (mounted) await _refresh();
  }

  /// The web header's "Opening stock" and "Count or adjust stock" start with a
  /// choice of tracked item; the entry itself is the item's own workflow.
  Future<void> _chooseItem({String? startWith}) async {
    final workspace = _workspace;
    try {
      final items = await _items;
      final setup = await _setup.catchError(
        (Object _) => const InventorySetup(),
      );
      final stock = await _stock.then<InventoryJson>(
        (value) => value,
        onError: (Object _) => const <String, dynamic>{},
      );
      if (!mounted || workspace != _workspace) return;
      final eligible = items.where((item) {
        final data = inventoryObject(item['data']);
        return data['track_stock'] == true &&
            (data['item_type'] ?? 'goods') == 'goods' &&
            (startWith != 'opening' || data['is_active'] != false);
      }).toList()..sort(_byName);
      final chosen = await showDialog<InventoryJson>(
        context: context,
        builder: (_) => _ItemPickerDialog(
          title: startWith == 'opening'
              ? 'Opening stock'
              : 'Count or adjust stock',
          subtitle: startWith == 'opening'
              ? 'Introduce stock already owned when you begin these books.'
              : 'Choose the tracked item to count or adjust.',
          items: eligible,
        ),
      );
      if (chosen == null || !mounted || workspace != _workspace) return;
      final quantities = {
        for (final row in inventoryRows(stock['rows']))
          inventoryText(row['item_id']): row['closing_quantity'],
      };
      await _openItem(
        chosen,
        quantities[inventoryText(chosen['id'])],
        setup,
        startWith: startWith,
      );
    } catch (failure) {
      if (mounted && workspace == _workspace) {
        showInventoryMessage(context, inventoryError(failure));
      }
    }
  }

  int _byName(InventoryJson a, InventoryJson b) =>
      inventoryText(a['name'])
          .toLowerCase()
          .compareTo(inventoryText(b['name']).toLowerCase());

  void _openLowStock() {
    final workspace = _workspace;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => InventoryReorderPage(
          workspace: workspace,
          openItem: (row) async {
            try {
              final id = row['item_id'];
              final items = await _items;
              final setup = await _setup.catchError(
                (Object _) => const InventorySetup(),
              );
              if (!mounted || workspace != _workspace) return;
              final item = items
                  .where((entry) => entry['id'] == id)
                  .firstOrNull;
              if (item == null) {
                showInventoryMessage(
                  context,
                  'This item is no longer in the catalogue.',
                );
                return;
              }
              await _openItem(item, row['on_hand'], setup);
            } catch (failure) {
              if (mounted && workspace == _workspace) {
                showInventoryMessage(context, inventoryError(failure));
              }
            }
          },
        ),
      ),
    );
  }

  Future<void> _retry() async {
    final kind = _posting.pending?.kind;
    try {
      final result = await _posting.retry();
      if (!mounted) return;
      showInventoryMessage(
        context,
        inventorySavedMessage(result, kind ?? 'count'),
      );
      await _workspace.refresh();
      if (mounted) await _refresh();
    } catch (error) {
      if (mounted) showInventoryMessage(context, inventoryError(error));
    }
  }

  @override
  void dispose() {
    _itemSearch.dispose();
    _orderSearch.dispose();
    _posting.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _posting,
    builder: (context, _) {
      final pending = _posting.pending;
      final canWrite = _workspace.company.canWrite;
      return FutureBuilder<InventoryJson>(
        future: _stock,
        builder: (context, stockState) {
          final stock = {
            for (final row in inventoryRows(stockState.data?['rows']))
              inventoryText(row['item_id']): row['closing_quantity'],
          };
          final date = stockState.data?['date'];
          final stockDate = date is String ? date : null;
          return FutureBuilder<List<InventoryJson>>(
            future: _items,
            builder: (context, itemState) => FutureBuilder<InventorySetup>(
              future: _setup,
              builder: (context, setupState) => FutureBuilder<List<InventoryJson>>(
                future: _orders,
                builder: (context, orderState) {
                  final setup = setupState.data ?? const InventorySetup();
                  return ApexPage(
                    children: [
                      _heading(canWrite),
                      if (pending != null)
                        InventoryNotice(
                          text:
                              '${pending.name}: ${inventoryOperationName(pending.kind)} is awaiting confirmation.',
                          action: canWrite
                              ? TextButton(
                                  onPressed: _posting.busy ? null : _retry,
                                  child: const Text('Retry original'),
                                )
                              : null,
                        ),
                      if (_posting.recoveryError != null)
                        InventoryNotice(
                          text: _posting.recoveryError!,
                          action: TextButton(
                            onPressed: _posting.load,
                            child: const Text('Try again'),
                          ),
                        ),
                      const SizedBox(height: 18),
                      _stats(itemState.data, stock, orderState.data),
                      const SizedBox(height: 18),
                      if (stockState.hasError)
                        const InventoryNotice(
                          text: 'Current stock could not be loaded. Refresh to try again.',
                        ),
                      _tab == 0
                          ? _itemPanel(
                              itemState,
                              setup,
                              stock,
                              stockDate,
                              orderState.data?.length ?? 0,
                            )
                          : _orderPanel(
                              orderState,
                              stockDate,
                              itemState.data?.length ?? 0,
                            ),
                    ],
                  );
                },
              ),
            ),
          );
        },
      );
    },
  );

  Widget _heading(bool canWrite) {
    final actions = <Widget>[
      if (_workspace.features.contains('low_stock_reorder'))
        OutlinedButton(
          onPressed: _openLowStock,
          child: const Text('Low stock & reorder'),
        ),
      if (canWrite && _workspace.features.contains('stock_counts')) ...[
        OutlinedButton(
          onPressed: _posting.busy
              ? null
              : () => _chooseItem(startWith: 'opening'),
          child: const Text('Opening stock'),
        ),
        OutlinedButton(
          onPressed: _posting.busy ? null : _chooseItem,
          child: const Text('Count or adjust stock'),
        ),
      ],
      IconButton(
        onPressed: _refresh,
        tooltip: 'Refresh stock',
        icon: const Icon(Icons.refresh_rounded, size: 20),
      ),
    ];
    const title = 'Stock';
    const subtitle =
        'On-hand quantities, shelf locations and purchase receiving';
    return LayoutBuilder(
      builder: (context, limits) => limits.maxWidth >= 1100
          ? ApexRegisterHeading(title, subtitle: subtitle, actions: actions)
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const ApexRegisterHeading(title, subtitle: subtitle),
                const SizedBox(height: 14),
                Wrap(spacing: 8, runSpacing: 8, children: actions),
              ],
            ),
    );
  }

  Widget _stats(
    List<InventoryJson>? items,
    Map<String, Object?> stock,
    List<InventoryJson>? orders,
  ) {
    var tracked = 0;
    var low = 0;
    for (final item in items ?? const <InventoryJson>[]) {
      final data = inventoryObject(item['data']);
      if (data['track_stock'] != true || data['is_active'] == false) continue;
      tracked++;
      final threshold = num.tryParse(
        inventoryText(data['low_stock_threshold']),
      );
      final onHand = num.tryParse(
        inventoryText(stock[inventoryText(item['id'])]),
      );
      if (threshold != null && onHand != null && onHand <= threshold) low++;
    }
    final open = (orders ?? const <InventoryJson>[])
        .where((order) => _orderStatus(order).$1 != 'Cancelled')
        .where((order) => _orderStatus(order).$1 != 'Converted')
        .length;
    final loaded = items != null;
    return ApexStatGrid([
      ApexStatCard(
        label: 'Items tracked',
        value: loaded ? '$tracked' : '—',
        icon: Icons.inventory_2_outlined,
      ),
      ApexStatCard(
        label: 'Low stock',
        value: loaded ? '$low' : '—',
        icon: Icons.warning_amber_rounded,
      ),
      ApexStatCard(
        label: 'Orders to receive',
        value: orders == null ? '—' : '$open',
        icon: Icons.local_shipping_outlined,
      ),
    ]);
  }

  Widget _tabs(int itemCount, int orderCount) => ApexFilterTabs<int>(
    label: 'Stock view',
    selected: _tab,
    onSelected: (value) => setState(() => _tab = value),
    tabs: [(0, 'Items', itemCount), (1, 'Purchase orders', orderCount)],
  );

  Widget _itemPanel(
    AsyncSnapshot<List<InventoryJson>> state,
    InventorySetup setup,
    Map<String, Object?> stock,
    String? date,
    int orders,
  ) {
    final locations = setup.shelfLabels;
    final shelf = _shelf == _unassigned || locations.containsKey(_shelf)
        ? _shelf
        : '';
    bool visible(InventoryJson data) {
      if (!_showArchived && data['is_active'] == false) return false;
      if (shelf.isEmpty) return true;
      final ids = data['location_ids'];
      if (shelf == _unassigned) return ids is! List || ids.isEmpty;
      return ids is List && ids.contains(shelf);
    }

    final all = state.data ?? const <InventoryJson>[];
    final rows =
        all
            .where(
              (item) =>
                  visible(inventoryObject(item['data'])) &&
                  itemMatches(
                    item,
                    _itemSearch.text,
                    locations,
                    automobileEnabled: setup.automobileEnabled,
                  ),
            )
            .toList()
          ..sort(_byName);
    final loading = state.connectionState != ConnectionState.done;
    final orderCount = orders;

    final search = KeyedSubtree(
      key: const ValueKey('inventory-item-search'),
      child: InventorySearchField(
        controller: _itemSearch,
        width: null,
        hint: setup.automobileEnabled
            ? 'Search items, barcode or vehicle'
            : 'Search items or barcode',
        onChanged: (_) => setState(() {}),
        onSubmitted: (query) {
          final needle = query.trim().toLowerCase();
          if (needle.isEmpty) return;
          final matches = all.where((item) {
            final data = inventoryObject(item['data']);
            return visible(data) &&
                inventoryText(data['barcode']).toLowerCase() == needle;
          }).toList();
          if (matches.length == 1) {
            _openItem(
              matches.single,
              stock[inventoryText(matches.single['id'])],
              setup,
            );
          }
          if (matches.length > 1) {
            showInventoryMessage(
              context,
              'More than one item uses that barcode. Choose an item from the list.',
            );
          }
        },
      ),
    );
    final filters = Wrap(
      spacing: 14,
      runSpacing: 10,
      crossAxisAlignment: WrapCrossAlignment.end,
      children: [
        if (setup.shelves.isNotEmpty)
          KeyedSubtree(
            key: ValueKey(('inventory-shelf-filter', shelf)),
            child: ApexFilterSelect<String>(
              label: 'Location',
              value: shelf,
              width: 220,
              items: [
                ('', 'All shelves'),
                (_unassigned, 'Unassigned shelf'),
                for (final option in setup.shelves) (option.id, option.label),
              ],
              onChanged: (value) => setState(() => _shelf = value),
            ),
          ),
        FilterChip(
          label: const Text('Include archived'),
          selected: _showArchived,
          onSelected: (value) => setState(() => _showArchived = value),
        ),
      ],
    );
    final emptyText = state.hasError
        ? inventoryError(state.error!)
        : loading
        ? 'Loading items…'
        : _itemSearch.text.trim().isEmpty && shelf.isEmpty
        ? 'There are no items to display.'
        : 'No items match the search.';
    return ApexRegisterPanel(
      title: 'Stock register',
      subtitle:
          '${rows.length} ${rows.length == 1 ? 'item' : 'items'} in this view'
          '${date == null ? '' : ' · Stock as of $date'}',
      search: _searchBox(search),
      filters: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _tabs(all.length, orderCount),
          const SizedBox(height: 10),
          filters,
          if (shelf.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text(
              'Stock quantities cover the full company',
              style: Apex.small,
            ),
          ],
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (loading) const LinearProgressIndicator(minHeight: 2),
          if (rows.isEmpty)
            ApexEmptyState(icon: Icons.inventory_2_outlined, title: emptyText)
          else
            LayoutBuilder(
              builder: (context, limits) {
                final table = limits.maxWidth >= _tableWidth;
                return ApexTable(
                  key: ValueKey(
                    table ? 'inventory-item-table' : 'inventory-item-cards',
                  ),
                  columns: const [
                    ApexColumn('Item', flex: 3.2),
                    ApexColumn('SKU / barcode', flex: 2),
                    ApexColumn('Shelf locations', flex: 2.4),
                    ApexColumn('On hand', flex: 1.8, alignEnd: true),
                    ApexColumn('Actions', flex: 1.2, alignEnd: true),
                  ],
                  rowCount: rows.length,
                  onRowTap: (row) => _openItem(
                    rows[row],
                    stock[inventoryText(rows[row]['id'])],
                    setup,
                  ),
                  cell: (row, column) =>
                      _itemCell(rows[row], column, stock, setup),
                  card: (row) => _itemCard(rows[row], stock, setup),
                );
              },
            ),
        ],
      ),
    );
  }

  Widget _searchBox(Widget field) => LayoutBuilder(
    builder: (context, limits) => SizedBox(
      width: limits.maxWidth < 400 ? double.infinity : 320,
      child: field,
    ),
  );

  ({
    String balance,
    bool known,
    String codes,
    String oem,
    List<String> places,
    bool archived,
    bool tracked,
  })
  _itemFacts(
    InventoryJson item,
    Map<String, Object?> stock,
    InventorySetup setup,
  ) {
    final data = inventoryObject(item['data']);
    final units = inventoryText(data['unit']);
    final tracked = data['track_stock'] == true;
    final quantity = stock[inventoryText(item['id'])];
    final known = tracked && quantity != null;
    final balance = known
        ? '${inventoryQuantity(quantity)}${units.isEmpty ? '' : ' $units'}'
        : tracked
        ? 'Stock unavailable'
        : 'Untracked';
    final ids = data['location_ids'];
    return (
      balance: balance,
      known: known,
      codes: [
        inventoryText(data['sku']),
        inventoryText(data['barcode']),
      ].where((value) => value.isNotEmpty).join(' · '),
      oem: setup.automobileEnabled ? inventoryText(data['oem_number']) : '',
      places: [
        if (ids is List)
          for (final id in ids) setup.shelfLabels[id] ?? 'Unknown shelf',
      ],
      archived: data['is_active'] == false,
      tracked: tracked,
    );
  }

  Widget _itemCell(
    InventoryJson item,
    int column,
    Map<String, Object?> stock,
    InventorySetup setup,
  ) {
    final facts = _itemFacts(item, stock, setup);
    final id = inventoryText(item['id']);
    switch (column) {
      case 0:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              inventoryText(item['name']),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Apex.strong,
            ),
            if (facts.archived || facts.oem.isNotEmpty)
              Text(
                facts.archived ? 'Archived' : 'OEM ${facts.oem}',
                style: Apex.small,
              ),
          ],
        );
      case 1:
        return Text(
          facts.codes.isEmpty ? '—' : facts.codes,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: Apex.note,
        );
      case 2:
        return Text(
          facts.places.isEmpty ? 'Unassigned' : facts.places.join(' · '),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: Apex.note,
        );
      case 3:
        return KeyedSubtree(
          key: ValueKey('inventory-item-row-$id'),
          child: Text(
            facts.balance,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 13,
              fontWeight: facts.known ? FontWeight.w700 : FontWeight.w400,
              color: facts.known ? Apex.ink : Apex.muted,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        );
      default:
        return ApexLink(
          'Count',
          onTap: () => _openItem(item, stock[id], setup),
        );
    }
  }

  Widget _itemCard(
    InventoryJson item,
    Map<String, Object?> stock,
    InventorySetup setup,
  ) {
    final facts = _itemFacts(item, stock, setup);
    final details = [
      facts.codes,
      facts.oem,
      ...facts.places,
      if (facts.archived) 'Archived',
    ].where((value) => value.isNotEmpty).join(' · ');
    return Row(
      key: ValueKey('inventory-item-row-${item['id']}'),
      children: [
        ApexIconTile(
          facts.tracked ? Icons.inventory_2_outlined : Icons.sell_outlined,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                inventoryText(item['name']),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Apex.strong,
              ),
              if (details.isNotEmpty)
                Text(
                  details,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Apex.small,
                ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Text(
          facts.balance,
          style: TextStyle(
            fontSize: 13,
            fontWeight: facts.known ? FontWeight.w700 : FontWeight.w400,
            color: facts.known ? Apex.ink : Apex.muted,
          ),
        ),
      ],
    );
  }

  (String, ApexBadgeTone) _orderStatus(InventoryJson row) {
    final data = inventoryObject(row['data']);
    if (row['cancelled'] == true) return ('Cancelled', ApexBadgeTone.cancelled);
    if (inventoryText(row['converted_to']).isNotEmpty) {
      return ('Converted', ApexBadgeTone.converted);
    }
    if (data['purchase_order_receiving_started'] == true) {
      return ('Receiving started', ApexBadgeTone.posted);
    }
    return ('Open order', ApexBadgeTone.draft);
  }

  Widget _orderPanel(
    AsyncSnapshot<List<InventoryJson>> state,
    String? date,
    int itemTotal,
  ) {
    final query = _orderSearch.text.trim().toLowerCase();
    final all = state.data ?? const <InventoryJson>[];
    final rows = all
        .where(
          (order) =>
              '${order['number']} ${order['name']}'.toLowerCase().contains(
                query,
              ) &&
              (_orderFilter.isEmpty || _orderStatus(order).$1 == _orderFilter),
        )
        .toList();
    final loading = state.connectionState != ConnectionState.done;
    final search = KeyedSubtree(
      key: const ValueKey('inventory-order-search'),
      child: InventorySearchField(
        controller: _orderSearch,
        width: null,
        hint: 'Search purchase orders',
        onChanged: (_) => setState(() {}),
      ),
    );
    return ApexRegisterPanel(
      title: 'Orders to receive',
      subtitle:
          '${rows.length} ${rows.length == 1 ? 'order' : 'orders'} in this view',
      search: _searchBox(search),
      filters: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _tabs(itemTotal, all.length),
          const SizedBox(height: 10),
          KeyedSubtree(
            key: const ValueKey('inventory-order-status-filter'),
            child: ApexFilterSelect<String>(
              label: 'Order status',
              value: _orderFilter,
              width: 230,
              items: const [
                ('', 'All orders'),
                ('Open order', 'Open orders'),
                ('Receiving started', 'Receiving started'),
                ('Converted', 'Converted'),
                ('Cancelled', 'Cancelled'),
              ],
              onChanged: (value) => setState(() => _orderFilter = value),
            ),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (loading) const LinearProgressIndicator(minHeight: 2),
          if (rows.isEmpty)
            ApexEmptyState(
              icon: Icons.local_shipping_outlined,
              title: state.hasError
                  ? inventoryError(state.error!)
                  : loading
                  ? 'Loading purchase orders…'
                  : 'No purchase orders match the search.',
            )
          else
            LayoutBuilder(
              builder: (context, limits) {
                final table = limits.maxWidth >= _tableWidth;
                return ApexTable(
                  key: ValueKey(
                    table ? 'inventory-order-table' : 'inventory-order-cards',
                  ),
                  columns: const [
                    ApexColumn('Order', flex: 2.6),
                    ApexColumn('Supplier', flex: 2.9),
                    ApexColumn('Date', flex: 1.6),
                    ApexColumn('Receiving', flex: 1.9),
                    ApexColumn('Order total', flex: 1.6, alignEnd: true),
                  ],
                  rowCount: rows.length,
                  onRowTap: (row) => _openOrder(rows[row], date),
                  cell: (row, column) => _orderCell(rows[row], column),
                  card: (row) => _orderCard(rows[row]),
                );
              },
            ),
        ],
      ),
    );
  }

  Widget _orderCell(InventoryJson order, int column) {
    final (label, tone) = _orderStatus(order);
    switch (column) {
      case 0:
        return Text(
          inventoryText(order['number']).isEmpty
              ? '—'
              : inventoryText(order['number']),
          key: ValueKey('inventory-order-row-${order['id']}'),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: Apex.strong,
        );
      case 1:
        return Text(
          inventoryText(order['name']),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 13, color: Apex.ink),
        );
      case 2:
        return Text(inventoryText(order['date']), style: Apex.note);
      case 3:
        return ApexStatusBadge(label, tone: tone);
      default:
        return Text(
          inventoryAmount(order['amount']),
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: Apex.ink,
            fontFeatures: [FontFeature.tabularFigures()],
          ),
        );
    }
  }

  Widget _orderCard(InventoryJson order) {
    final (label, tone) = _orderStatus(order);
    return Row(
      key: ValueKey('inventory-order-row-${order['id']}'),
      children: [
        const ApexIconTile(Icons.local_shipping_outlined),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                inventoryText(order['name']),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Apex.strong,
              ),
              Text(
                '${inventoryText(order['number'])} · ${inventoryText(order['date'])}',
                style: Apex.small,
              ),
              const SizedBox(height: 6),
              Align(
                alignment: Alignment.centerLeft,
                child: ApexStatusBadge(label, tone: tone),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Text(
          inventoryAmount(order['amount']),
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
        ),
      ],
    );
  }
}

/// Chooser shown before an opening-stock or count entry, as in the web modal.
class _ItemPickerDialog extends StatefulWidget {
  const _ItemPickerDialog({
    required this.title,
    required this.subtitle,
    required this.items,
  });

  final String title;
  final String subtitle;
  final List<InventoryJson> items;

  @override
  State<_ItemPickerDialog> createState() => _ItemPickerDialogState();
}

class _ItemPickerDialogState extends State<_ItemPickerDialog> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final query = _search.text.trim().toLowerCase();
    final shown = widget.items.where((item) {
      final data = inventoryObject(item['data']);
      return '${item['name']} ${data['sku'] ?? ''} ${data['barcode'] ?? ''}'
          .toLowerCase()
          .contains(query);
    }).toList();
    return InventoryModal(
      title: widget.title,
      subtitle: widget.subtitle,
      actions: [
        OutlinedButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
      ],
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InventorySearchField(
            controller: _search,
            width: null,
            hint: 'Search tracked items',
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 10),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 320),
            child: shown.isEmpty
                ? const InventoryEmpty(text: 'No tracked items found.')
                : ListView.separated(
                    shrinkWrap: true,
                    itemCount: shown.length,
                    separatorBuilder: (context, _) =>
                        const Divider(height: 1, color: Apex.lineSoft),
                    itemBuilder: (context, index) {
                      final item = shown[index];
                      final unit = inventoryText(
                        inventoryObject(item['data'])['unit'],
                      );
                      return ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        title: Text(inventoryText(item['name'])),
                        subtitle: unit.isEmpty ? null : Text(unit),
                        onTap: () => Navigator.pop(context, item),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
