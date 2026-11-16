import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../inventory/inventory_count.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import '../inventory/inventory_reorder.dart';
import '../inventory/inventory_setup.dart';
import 'item_setup_fields.dart';
import 'master_editor.dart';
import 'master_import.dart';
import 'party_statement.dart';

class MastersScreen extends StatefulWidget {
  const MastersScreen({
    required this.workspace,
    this.active = true,
    this.revision = 0,
    this.group,
    super.key,
  });
  final WorkspaceContext workspace;
  final bool active;
  final int revision;

  /// Page chosen in the navigation: customer or supplier open Parties, item opens Items.
  /// Null keeps the current page.
  final MasterGroup? group;

  @override
  State<MastersScreen> createState() => _MastersScreenState();
}

class _MastersScreenState extends State<MastersScreen> {
  static const _operation = 'master-create';
  static const _pageSize = 50;
  late Future<List<Json>> _rows;
  final _searchController = TextEditingController();
  MasterGroup _group = MasterGroup.customer;
  String _search = '';
  String _status = 'all';
  int _page = 1;
  bool _busy = false;
  bool _ready = false;
  Json? _pending;
  String? _error;
  Json? _balances;
  Future<InventorySetup>? _setup;
  InventoryPosting? _posting;

  WorkspaceContext get _workspace => widget.workspace;
  String get _base => _workspace.path;
  bool get _items => _group == MasterGroup.item;

  @override
  void initState() {
    super.initState();
    if (widget.group case final group?) _group = group;
    _rows = _fetch();
    _loadSide();
    _loadPending();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _posting?.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant MastersScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.group != oldWidget.group && widget.group != null && widget.group != _group) {
      final wasItems = _items;
      _group = widget.group!;
      _search = '';
      _searchController.clear();
      _status = 'all';
      _page = 1;
      // Items and parties come from different lists.
      if (wasItems != _items) {
        _rows = _fetch();
        _loadSide();
      }
    }
    if (oldWidget.workspace.company.id != _workspace.company.id) {
      _pending = null;
      _ready = false;
      _busy = false;
      _error = null;
      _posting?.dispose();
      _posting = null;
      _loadPending();
      _rows = _fetch();
      _loadSide();
    } else if (widget.active && (!oldWidget.active || widget.revision != oldWidget.revision)) {
      _rows = _fetch();
      _loadSide();
    }
  }

  /// Party balances (Parties) or shelf names (Items), loaded beside the list.
  void _loadSide() {
    final workspace = _workspace;
    _balances = null;
    _setup = null;
    if (_items) {
      final setup = InventorySetup.load(workspace);
      setup.then<void>((_) {}, onError: (Object _) {});
      _setup = setup;
      return;
    }
    if (!workspace.features.contains('party_balances')) return;
    () async {
      try {
        final result = inventoryObject(await workspace.api.get('${workspace.path}/parties/balances'));
        final byId = {
          for (final row in inventoryRows(result['rows'])) inventoryText(row['party_id']): apexNumber(row['net']) ?? 0,
        };
        if (mounted && workspace == _workspace && !_items) {
          setState(() => _balances = {...result, 'by_id': byId});
        }
      } catch (_) {
        if (mounted && workspace == _workspace) setState(() => _balances = null);
      }
    }();
  }

  Future<void> _loadPending() async {
    final workspace = _workspace;
    try {
      final pending = await workspace.pending.load(_operation);
      if (!mounted || workspace != _workspace) return;
      if (pending != null && (pending['key'] is! String || pending['body'] is! Map)) {
        throw const FormatException('Saved master request could not be read.');
      }
      setState(() {
        _ready = true;
        _pending = pending;
        _error = null;
      });
    } catch (_) {
      if (mounted && workspace == _workspace) {
        setState(() => _error = 'The previous master request could not be recovered. Try loading it again.');
      }
    }
  }

  Future<List<Json>> _fetch() async {
    final kind = _items ? 'item' : 'party';
    final base = _base;
    final api = _workspace.api;
    const pageSize = 200;
    final rows = <String, Json>{};
    for (var offset = 0; ; offset += pageSize) {
      final page = inventoryRows(
        await api.get(
          '$base/records',
          query: {'kind': kind, 'compact': 'true', 'limit': '$pageSize', 'offset': '$offset'},
        ),
      );
      final previous = rows.length;
      rows.addEntries(page.map((row) => MapEntry(inventoryText(row['id']), row)));
      if (page.length < pageSize || previous == rows.length) {
        return rows.values.toList();
      }
    }
  }

  void _reload() {
    final rows = _fetch();
    setState(() {
      _rows = rows;
    });
    _loadSide();
  }

  Future<void> _storeMaster(WorkspaceContext workspace, MasterGroup group, String? id, Json fields) async {
    if (_busy || !_ready || _pending != null || !_workspace.company.canWrite) {
      throw StateError('Resolve the previous master request first.');
    }
    if (!mounted || _workspace != workspace) {
      throw StateError('The company changed. Reopen this master.');
    }
    setState(() => _busy = true);
    try {
      if (id != null) {
        await workspace.api.put('${workspace.path}/masters/${Uri.encodeComponent(id)}', body: fields);
      } else {
        final rng = Random.secure();
        final key = List.generate(20, (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
        final body = {
          'kind': group == MasterGroup.item ? 'item' : 'party',
          'date': businessDate(),
          'name': fields['name'],
          'data': Map.of(fields)..remove('name'),
        };
        final command = {'key': 'flutter-master-$key', 'body': body};
        await workspace.pending.save(_operation, command);
        _pending = command;
        await _sendCreate(workspace, command, retrying: false);
      }
      if (mounted && workspace == _workspace) _reload();
      await workspace.refresh();
    } finally {
      if (mounted && workspace == _workspace) setState(() => _busy = false);
    }
  }

  Future<void> _sendCreate(WorkspaceContext workspace, Json command, {required bool retrying}) async {
    try {
      final result = inventoryObject(
        await workspace.api.post(
          '${workspace.path}/records',
          body: inventoryObject(command['body']),
          idempotencyKey: command['key'] as String,
        ),
      );
      if (inventoryText(result['id']).isEmpty) {
        throw const FormatException('The saved master could not be confirmed.');
      }
    } on ApexApiException catch (error) {
      if (!retrying && !error.uncertain) {
        await workspace.pending.clear(_operation);
        if (workspace == _workspace) _pending = null;
      }
      rethrow;
    }
    await workspace.pending.clear(_operation);
    if (workspace == _workspace) _pending = null;
  }

  Future<void> _retry() async {
    final workspace = _workspace;
    final pending = _pending;
    if (_busy || pending == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _sendCreate(workspace, pending, retrying: true);
      await workspace.refresh();
      if (mounted && workspace == _workspace) _reload();
    } catch (failure) {
      if (mounted && workspace == _workspace) {
        setState(() => _error = inventoryError(failure));
      }
    } finally {
      if (mounted && workspace == _workspace) setState(() => _busy = false);
    }
  }

  void _open([Json? record]) {
    final workspace = _workspace;
    final group = _items ? MasterGroup.item : MasterGroup.customer;
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => MasterEditorPage(
        group: group,
        workspace: workspace,
        record: record,
        onSave: (id, fields) => _storeMaster(workspace, group, id, fields),
        canWrite: _workspace.company.canWrite && _ready && _pending == null,
        canArchive: _workspace.features.contains('master_lifecycle'),
      ),
    );
  }

  void _openStatement(Json record) {
    final workspace = _workspace;
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => PartyStatementPage(workspace: workspace, party: record)),
    );
  }

  Future<void> _openImport() async {
    final workspace = _workspace;
    final kind = _items ? 'item' : 'party';
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => MasterImportPage(workspace: workspace, initialKind: kind)),
    );
    if (mounted && workspace == _workspace) _reload();
  }

  // ---- Stock actions on the Items page (the same screens the Stock page uses). ----

  Future<InventoryPosting> _stockPosting() async {
    final posting = _posting ??= InventoryPosting(_workspace);
    if (!posting.loaded) await posting.load();
    return posting;
  }

  Future<InventorySetup> _loadedSetup() async {
    try {
      return await (_setup ?? InventorySetup.load(_workspace));
    } catch (_) {
      return const InventorySetup();
    }
  }

  Future<void> _countItem(Json item, Object? stock) async {
    final workspace = _workspace;
    final posting = await _stockPosting();
    final setup = await _loadedSetup();
    if (!mounted || workspace != _workspace) return;
    final ids = inventoryObject(item['data'])['location_ids'];
    final names = setup.shelfLabels;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => InventoryCountPage(
          posting: posting,
          item: item,
          stock: stock,
          locations: ids is List ? ids.map((id) => names[id]).whereType<String>().toList() : <String>[],
          automobileEnabled: setup.automobileEnabled,
        ),
      ),
    );
    if (mounted && workspace == _workspace) _reload();
  }

  bool _tracked(Json row) => inventoryObject(row['data'])['track_stock'] == true;

  Future<void> _pickStockItem(List<Json> rows) async {
    final choices = rows.where(_tracked).toList();
    final picked = await showDialog<Json>(
      context: context,
      builder: (context) => _StockItemDialog(items: choices),
    );
    if (picked != null && mounted) await _countItem(picked, null);
  }

  void _openLowStock(List<Json> rows) {
    final workspace = _workspace;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => InventoryReorderPage(
          workspace: workspace,
          openItem: (row) async {
            final item = rows.where((entry) => entry['id'] == row['item_id']).firstOrNull;
            if (item == null) {
              ScaffoldMessenger.of(
                context,
              ).showSnackBar(const SnackBar(content: Text('This item is no longer in the catalogue.')));
              return;
            }
            await _countItem(item, row['on_hand']);
          },
        ),
      ),
    );
  }

  // ---- Filtering ----

  static int _newestFirst(Json a, Json b) {
    final dataA = inventoryObject(a['data']);
    final dataB = inventoryObject(b['data']);
    final byDate = inventoryText(b['date']).compareTo(inventoryText(a['date']));
    if (byDate != 0) return byDate;
    final byCreated = inventoryText(dataB['created_at']).compareTo(inventoryText(dataA['created_at']));
    if (byCreated != 0) return byCreated;
    return inventoryText(b['id']).compareTo(inventoryText(a['id']));
  }

  bool get _lifecycle => _workspace.features.contains('master_lifecycle');
  String get _activeStatus => _lifecycle ? _status : 'all';
  bool get _hasFilters => _search.isNotEmpty || _activeStatus != 'all';

  List<Json> _filter(List<Json> all, InventorySetup? setup) {
    return all.where((row) {
      final data = inventoryObject(row['data']);
      final active = data['is_active'] != false;
      if (_activeStatus == 'active' && !active) return false;
      if (_activeStatus == 'inactive' && active) return false;
      if (_search.isEmpty) return true;
      if (_items) {
        return itemMatches(
          row,
          _search,
          setup?.shelfLabels ?? const {},
          automobileEnabled: setup?.automobileEnabled ?? false,
        );
      }
      final text = [
        row['name'],
        row['number'],
        data['phone'],
        data['email'],
        data['gstin'],
      ].whereType<Object>().join(' ').toLowerCase();
      return text.contains(_search);
    }).toList()..sort(_newestFirst);
  }

  void _resetFilters() {
    setState(() {
      _search = '';
      _searchController.clear();
      _status = 'all';
      _page = 1;
    });
  }

  // ---- Presentation ----

  Widget _notice(String text, {String? action, VoidCallback? onTap}) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: ApexPanel(
      radius: Apex.radiusControl,
      color: const Color(0xfffbf2e2),
      borderColor: const Color(0xffefd9a8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13, color: Color(0xff7a5014)))),
          if (action != null) TextButton(onPressed: onTap, child: Text(action)),
        ],
      ),
    ),
  );

  List<Widget> _headingActions(List<Json> rows, bool canWrite, bool stockReady) {
    final features = _workspace.features;
    final importButton = OutlinedButton.icon(
      onPressed: _busy ? null : _openImport,
      icon: const Icon(Icons.upload_file, size: 17),
      label: const Text('Import CSV'),
    );
    if (!_items) {
      return [
        if (_workspace.company.canWrite) importButton,
        FilledButton.icon(
          onPressed: canWrite ? () => _open() : null,
          icon: const Icon(Icons.add, size: 17),
          label: const Text('Add party'),
        ),
      ];
    }
    final canStock = _workspace.company.canWrite && stockReady && rows.any(_tracked);
    return [
      Tooltip(
        message: features.contains('low_stock_reorder') ? '' : 'Connected API upgrade required',
        child: OutlinedButton(
          onPressed: features.contains('low_stock_reorder') && stockReady ? () => _openLowStock(rows) : null,
          child: const Text('Low stock & reorder'),
        ),
      ),
      OutlinedButton.icon(
        onPressed: canStock ? () => _pickStockItem(rows) : null,
        icon: const Icon(Icons.add, size: 17),
        label: const Text('Opening stock'),
      ),
      OutlinedButton.icon(
        onPressed: canStock ? () => _pickStockItem(rows) : null,
        icon: const Icon(Icons.add, size: 17),
        label: Text(features.contains('stock_counts') ? 'Count or adjust stock' : 'Adjust stock'),
      ),
      if (_workspace.company.canWrite) importButton,
      FilledButton.icon(
        onPressed: canWrite ? () => _open() : null,
        icon: const Icon(Icons.add, size: 17),
        label: const Text('Add item'),
      ),
    ];
  }

  Widget _balanceStrip() {
    final balances = _balances;
    if (balances == null) return const SizedBox.shrink();
    final totals = inventoryObject(balances['totals']);
    Widget figure(String label, Object? value, Color color) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Apex.muted)),
        Text(
          apexMoney(apexNumber(value) ?? 0),
          style: TextStyle(fontFamily: Apex.display, fontSize: 18, fontWeight: FontWeight.w700, color: color),
        ),
      ],
    );
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Color(0xffeaf6ee),
        border: Border(bottom: BorderSide(color: Apex.line)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
        child: Wrap(
          spacing: 24,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            figure("You'll get", totals['to_receive'], Apex.green),
            figure("You'll pay", totals['to_pay'], Apex.red),
            Text(
              'Closing balances as of ${inventoryText(balances['as_of'])}',
              style: const TextStyle(fontSize: 12, color: Apex.muted),
            ),
          ],
        ),
      ),
    );
  }

  String _cap(String value) => value.isEmpty ? value : value[0].toUpperCase() + value.substring(1);

  String _details(Json row) {
    final data = inventoryObject(row['data']);
    if (!_items) {
      final text = [
        data['gstin'],
        data['phone'],
        data['email'],
      ].map(inventoryText).where((value) => value.isNotEmpty).join(' · ');
      return text.isEmpty ? '—' : text;
    }
    final rate = inventoryText(data['sale_rate']);
    final gst = inventoryText(data['gst_rate']);
    final unit = inventoryText(data['unit']);
    final text = [
      if (inventoryText(data['hsn']).isNotEmpty) 'HSN ${data['hsn']}',
      if (rate.isNotEmpty && rate != '0') '${apexMoney(apexNumber(rate) ?? 0)}${unit.isEmpty ? '' : ' / $unit'}',
      if (gst.isNotEmpty) 'GST $gst%',
    ].join(' · ');
    return text.isEmpty ? '—' : text;
  }

  String _sub(Json row) {
    final data = inventoryObject(row['data']);
    final number = inventoryText(row['number']);
    if (number.isNotEmpty) return number;
    if (!_items) {
      final gstin = inventoryText(data['gstin']);
      return gstin.isEmpty ? 'Party' : gstin;
    }
    final hsn = inventoryText(data['hsn']);
    return hsn.isEmpty ? 'Item' : 'HSN / SAC $hsn';
  }

  String _type(Json row) {
    final data = inventoryObject(row['data']);
    if (_items) {
      final type = inventoryText(data['item_type']);
      return _cap(type.isEmpty ? 'item' : type);
    }
    final type = inventoryText(data['party_type']);
    return _cap(type.isEmpty ? 'both' : type);
  }

  Widget _nameCell(Json row) {
    final data = inventoryObject(row['data']);
    final archived = data['is_active'] == false;
    final name = inventoryText(row['name']).isEmpty ? 'Untitled' : inventoryText(row['name']);
    return Row(
      children: [
        ApexIconTile(
          _items ? Icons.inventory_2_outlined : Icons.people_outline_rounded,
          background: const Color(0xfff0f2f5),
          foreground: Apex.muted,
          size: 38,
          iconSize: 17,
          radius: 10,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _items
                  ? Text(name, style: Apex.strong.copyWith(fontSize: 14))
                  : ApexLink(name, strong: true, onTap: () => _openStatement(row)),
              if (archived)
                const Padding(
                  padding: EdgeInsets.only(top: 3),
                  child: ApexStatusBadge('Archived · history retained'),
                ),
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(_sub(row), style: Apex.small.copyWith(fontSize: 12)),
              ),
            ],
          ),
        ),
      ],
    );
  }

  List<Widget> _itemMeta(Json row, InventorySetup? setup) {
    if (setup == null) return const [];
    final data = inventoryObject(row['data']);
    final ids = data['location_ids'];
    final places = [
      if (ids is List)
        for (final id in ids) ?setup.shelves.where((shelf) => shelf.id == id).firstOrNull?.name,
    ];
    final oem = inventoryText(data['oem_number']).trim();
    final grade = itemGradeLabels[inventoryText(data['part_grade'])];
    final part = [
      if (oem.isNotEmpty) 'Part $oem',
      inventoryText(data['part_brand']).trim(),
      ?grade,
    ].where((value) => value.isNotEmpty).join(' · ');
    final fits = [
      for (final fit in inventoryRows(data['vehicle_fitment']).map(VehicleFitment.fromJson))
        if (_fitText(fit).isNotEmpty) _fitText(fit),
    ];
    const style = TextStyle(fontSize: 12, color: Apex.muted);
    return [
      if (places.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.place_outlined, size: 12, color: Apex.greenText),
              const SizedBox(width: 3),
              Flexible(child: Text(places.join(' · '), style: style.copyWith(color: Apex.greenText))),
            ],
          ),
        ),
      if (part.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 3), child: Text(part, style: style)),
      if (fits.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 3),
          child: Text(
            'Fits ${fits.take(2).join(', ')}${fits.length > 2 ? ' +${fits.length - 2} more' : ''}',
            style: style,
          ),
        ),
    ];
  }

  /// Vehicle label as the web app writes it: "Tata Nexon 2020–2025".
  String _fitText(VehicleFitment fit) {
    final years = fit.from != null && fit.to != null
        ? (fit.from == fit.to ? '${fit.from}' : '${fit.from}–${fit.to}')
        : fit.from != null
        ? '${fit.from} onwards'
        : fit.to != null
        ? 'up to ${fit.to}'
        : '';
    return [fit.make, fit.model, years].where((value) => value.trim().isNotEmpty).join(' ');
  }

  (String, String, Color) _balanceFor(Json row) {
    final net = (_balances?['by_id'] as Map?)?[inventoryText(row['id'])];
    final num value = net is num ? net : 0;
    if (value > 0) return (apexMoney(value.abs()), "You'll get", Apex.green);
    if (value < 0) return (apexMoney(value.abs()), "You'll pay", Apex.red);
    return (apexMoney(0), 'Settled', Apex.ink);
  }

  Widget _balanceCell(Json row, {bool end = true}) {
    final (amount, label, color) = _balanceFor(row);
    return Column(
      crossAxisAlignment: end ? CrossAxisAlignment.end : CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(amount, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: color)),
        Text(label, style: Apex.small.copyWith(fontSize: 12)),
      ],
    );
  }

  Widget _actionCell(Json row) => ApexLink(_workspace.company.canWrite ? 'Edit' : 'View', onTap: () => _open(row));

  Widget _table(List<Json> rows, InventorySetup? setup) {
    final showBalance = !_items && _balances != null;
    final columns = [
      const ApexColumn('Name', flex: 3.2),
      const ApexColumn('Details', flex: 2.6),
      const ApexColumn('Type', flex: 1.5),
      if (showBalance) const ApexColumn('Balance', flex: 1.6, alignEnd: true),
      const ApexColumn('Actions', width: 110, alignEnd: true),
    ];
    return ApexTable(
      columns: columns,
      rowCount: rows.length,
      onRowTap: (index) => _items ? _open(rows[index]) : _openStatement(rows[index]),
      cell: (index, column) {
        final row = rows[index];
        switch (columns[column].title) {
          case 'Name':
            return _nameCell(row);
          case 'Details':
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_details(row), style: const TextStyle(fontSize: 13, color: Apex.muted)),
                if (_items) ..._itemMeta(row, setup),
              ],
            );
          case 'Type':
            return ApexStatusBadge(_type(row), tone: ApexBadgeTone.posted);
          case 'Balance':
            return _balanceCell(row);
          default:
            return _actionCell(row);
        }
      },
      card: (index) {
        final row = rows[index];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: _nameCell(row)),
                const SizedBox(width: 8),
                ApexStatusBadge(_type(row), tone: ApexBadgeTone.posted),
              ],
            ),
            const SizedBox(height: 10),
            Text(_details(row), style: const TextStyle(fontSize: 13, color: Apex.muted)),
            if (_items) ..._itemMeta(row, setup),
            const SizedBox(height: 10),
            Row(children: [if (showBalance) _balanceCell(row, end: false), const Spacer(), _actionCell(row)]),
          ],
        );
      },
    );
  }

  Widget _pagination(int total, int pages, int current) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
    child: Wrap(
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: 12,
      runSpacing: 8,
      children: [
        Text(
          '${(current - 1) * _pageSize + 1}–${min(current * _pageSize, total)} of $total',
          style: const TextStyle(fontSize: 12, color: Apex.muted),
        ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            OutlinedButton(
              onPressed: current > 1 ? () => setState(() => _page = current - 1) : null,
              child: const Text('Previous'),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text('Page $current of $pages', style: const TextStyle(fontSize: 12, color: Apex.muted)),
            ),
            OutlinedButton(
              onPressed: current < pages ? () => setState(() => _page = current + 1) : null,
              child: const Text('Next'),
            ),
          ],
        ),
      ],
    ),
  );

  Widget _panel(List<Json> all, InventorySetup? setup) {
    final rows = _filter(all, setup);
    final pages = max(1, (rows.length / _pageSize).ceil());
    final current = min(_page, pages);
    final visible = rows.skip((current - 1) * _pageSize).take(_pageSize).toList();
    final canWrite = _workspace.company.canWrite && _ready && !_busy && _pending == null;
    final noun = _items ? 'item' : 'party';
    return ApexRegisterPanel(
      title: _items ? 'Catalogue' : 'Directory',
      subtitle: '${rows.length} ${rows.length == 1 ? 'record' : 'records'} in this view',
      search: ApexSearchField(
        controller: _searchController,
        hint: _items ? 'Search item or reference' : 'Search party or reference',
        width: MediaQuery.sizeOf(context).width < 700 ? null : 300,
        onChanged: (value) => setState(() {
          _search = value.trim().toLowerCase();
          _page = 1;
        }),
      ),
      filters: _lifecycle
          ? Wrap(
              spacing: 14,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.end,
              children: [
                ApexFilterSelect<String>(
                  label: 'Status',
                  value: _status,
                  items: const [('all', 'All entries'), ('active', 'Active'), ('inactive', 'Archived')],
                  onChanged: (value) => setState(() {
                    _status = value;
                    _page = 1;
                  }),
                ),
                if (_hasFilters) TextButton(onPressed: _resetFilters, child: const Text('Reset filters')),
              ],
            )
          : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!_items) _balanceStrip(),
          if (rows.isEmpty)
            ApexEmptyState(
              icon: Icons.description_outlined,
              title: _hasFilters
                  ? 'No matching records'
                  : _items
                  ? 'Build your item catalogue'
                  : 'Your party list starts here',
              note: _hasFilters
                  ? 'Change the search or filters to find your records.'
                  : _workspace.company.canWrite
                  ? _items
                        ? 'Add products or services with prices, tax defaults and optional stock tracking.'
                        : 'Add a customer or supplier so you can reuse their details on every document.'
                  : 'There are no records here yet. Your company owner can add them.',
              action: _hasFilters
                  ? OutlinedButton(onPressed: _resetFilters, child: const Text('Clear filters'))
                  : _workspace.company.canWrite
                  ? FilledButton.icon(
                      onPressed: canWrite ? () => _open() : null,
                      icon: const Icon(Icons.add, size: 15),
                      label: Text('Add $noun'),
                    )
                  : null,
            )
          else
            _table(visible, setup),
          if (pages > 1) _pagination(rows.length, pages, current),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final canWrite = _workspace.company.canWrite && _ready && !_busy && _pending == null;
    return FutureBuilder<List<Json>>(
      future: _rows,
      builder: (context, state) {
        final loaded = state.connectionState == ConnectionState.done && state.hasData;
        final all = state.data ?? const <Json>[];
        return ApexPage(
          children: [
            if (_pending != null)
              _notice(
                'The previous master could not be confirmed.',
                action: 'Retry original',
                onTap: _busy || !_workspace.company.canWrite ? null : _retry,
              ),
            if (_error != null) _notice(_error!, action: !_ready ? 'Try again' : null, onTap: _loadPending),
            ApexRegisterHeading(
              _items ? 'Items' : 'Parties',
              subtitle: _items ? 'Products, services, and stock' : 'Customers and suppliers',
              actions: _headingActions(all, canWrite, loaded),
            ),
            const SizedBox(height: 18),
            if (state.hasError)
              ApexPanel(
                radius: Apex.radiusPanel,
                child: ApexEmptyState(
                  icon: Icons.error_outline,
                  title: 'Records could not be loaded',
                  note: inventoryError(state.error!),
                  action: OutlinedButton(onPressed: _reload, child: const Text('Try again')),
                ),
              )
            else if (!loaded)
              const ApexPanel(
                radius: Apex.radiusPanel,
                padding: EdgeInsets.symmetric(vertical: 46),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_items)
              FutureBuilder<InventorySetup>(future: _setup, builder: (context, setup) => _panel(all, setup.data))
            else
              _panel(all, null),
          ],
        );
      },
    );
  }
}

class _StockItemDialog extends StatefulWidget {
  const _StockItemDialog({required this.items});
  final List<Json> items;

  @override
  State<_StockItemDialog> createState() => _StockItemDialogState();
}

class _StockItemDialogState extends State<_StockItemDialog> {
  String _search = '';

  @override
  Widget build(BuildContext context) {
    final rows = widget.items.where((row) => inventoryText(row['name']).toLowerCase().contains(_search)).toList();
    return AlertDialog(
      title: const Text('Choose a tracked item'),
      content: SizedBox(
        width: 420,
        height: 320,
        child: Column(
          children: [
            TextField(
              onChanged: (value) => setState(() => _search = value.trim().toLowerCase()),
              decoration: const InputDecoration(labelText: 'Find an item', prefixIcon: Icon(Icons.search)),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: rows.isEmpty
                  ? const Center(child: Text('No stock-tracked items match.'))
                  : ListView.builder(
                      itemCount: rows.length,
                      itemBuilder: (context, index) {
                        final row = rows[index];
                        return ListTile(
                          title: Text(inventoryText(row['name'])),
                          subtitle: Text(inventoryText(inventoryObject(row['data'])['unit'])),
                          onTap: () => Navigator.pop(context, row),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel'))],
    );
  }
}
