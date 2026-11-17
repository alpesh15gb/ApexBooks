import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import '../books/books_detail.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import '../inventory/inventory_reorder_order.dart';
import 'commerce_commands.dart';
import 'commerce_evidence.dart';
import 'commerce_forms.dart';
import 'commerce_money.dart';
import 'commerce_order.dart';
import 'commerce_widgets.dart';

enum _Panel {
  overview('Overview'),
  catalogue('Catalogue'),
  orders('Orders'),
  payments('Payments'),
  deliveries('Deliveries'),
  reconciliation('Reconciliation');

  const _Panel(this.label);
  final String label;
}

class CommerceScreen extends StatefulWidget {
  const CommerceScreen({required this.workspace, this.onBack, super.key});
  final WorkspaceContext workspace;
  final VoidCallback? onBack;
  @override
  State<CommerceScreen> createState() => _CommerceScreenState();
}

class _CommerceScreenState extends State<CommerceScreen> {
  List<Json> _connections = const [];
  Json? _data;
  Json? _setupUnconfirmed;
  String _selected = '';
  _Panel _panel = _Panel.overview;
  bool _loading = false;
  bool _busy = false;
  bool _setupDialogOpen = false;
  int _generation = 0;
  String? _notice;
  String? _error;
  late CommerceCommandQueue _queue;
  Map<String, String> _partyNames = const {};
  WorkspaceContext? _partiesFor;

  WorkspaceContext get _workspace => widget.workspace;
  bool get _owner => _workspace.company.role == 'owner';
  bool get _available => !_busy && !_queue.busy && !_loading;
  Json get _connection => inventoryObject(_data?['connection']);
  bool get _active =>
      _connection['id'] == _selected && _connection['status'] == 'active';
  bool get _canCommand => _available && _active && _queue.canSubmit;
  String get _path => commercePath(_workspace, _selected);
  List<Json> _rows(String kind) => inventoryRows(_data?[kind]);

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  @override
  void didUpdateWidget(covariant CommerceScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workspace != widget.workspace) {
      _queue.dispose();
      _data = null;
      _connections = [];
      _setupUnconfirmed = null;
      _partyNames = const {};
      _partiesFor = null;
      _selected = '';
      _panel = _Panel.overview;
      _busy = false;
      _setupDialogOpen = false;
      _error = null;
      _notice = null;
      _initialize();
    }
  }

  void _initialize() {
    _queue = CommerceCommandQueue(_workspace);
    _queue.load();
    _refresh();
  }

  @override
  void dispose() {
    _queue.dispose();
    super.dispose();
  }

  Future<void> _refresh({String? select}) async {
    final workspace = _workspace;
    final generation = ++_generation;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = inventoryRows(
        await workspace.api.get(commerceRoot(workspace)),
      );
      if (!mounted || generation != _generation) return;
      final intended = select ?? _selected;
      final selected = rows.any((row) => row['id'] == intended)
          ? intended
          : rows.isEmpty
          ? ''
          : inventoryText(rows.first['id']);
      setState(() {
        _connections = rows;
        if (_selected != selected) _data = null;
        _selected = selected;
        if (rows.isEmpty) _data = null;
      });
      if (selected.isEmpty) return;
      final data = inventoryObject(
        await workspace.api.get(
          '${commercePath(workspace, selected)}/workspace',
        ),
      );
      if (!mounted || generation != _generation) return;
      if (inventoryObject(data['connection'])['id'] != selected) {
        throw const FormatException(
          'The store workspace did not match the selected connection.',
        );
      }
      setState(() => _data = data);
      unawaited(_loadParties(workspace));
    } catch (failure) {
      if (mounted && generation == _generation) {
        setState(() {
          _data = null;
          _error = inventoryError(failure);
        });
      }
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  /// Names for the Customer column, as the web resolves `party_id` against its records.
  Future<void> _loadParties(WorkspaceContext workspace) async {
    if (_partiesFor == workspace) return;
    _partiesFor = workspace;
    try {
      final parties = await inventoryAllRecords(workspace, 'party');
      if (!mounted || workspace != _workspace) return;
      setState(
        () => _partyNames = {
          for (final party in parties)
            inventoryText(party['id']): inventoryText(party['name']),
        },
      );
    } catch (_) {
      // The order's own customer id is still shown.
      if (mounted && workspace == _workspace) _partiesFor = null;
    }
  }

  Future<void> _action(
    Future<void> Function() action, {
    required String success,
    bool refresh = true,
  }) async {
    if (!_available) return;
    final workspace = _workspace;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await action();
      if (!mounted || workspace != _workspace) return;
      if (success.isNotEmpty) setState(() => _notice = success);
      if (refresh) await _refresh();
    } catch (failure) {
      if (mounted && workspace == _workspace) {
        setState(() => _error = inventoryError(failure));
      }
    } finally {
      if (mounted && workspace == _workspace) setState(() => _busy = false);
    }
  }

  Future<void> _newConnection() async {
    if (!_owner || _setupUnconfirmed != null) return;
    final workspace = _workspace;
    await _action(
      () async {
        final banks = inventoryRows(
          await workspace.api.get('${workspace.path}/bank-accounts'),
        );
        if (!mounted || workspace != _workspace) return;
        final command = await _setupDialog<Json>(
          builder: (_) => CommerceConnectionForm(
            banks: banks.isEmpty
                ? const [
                    {'id': 'default', 'name': 'Bank clearing'},
                  ]
                : banks,
          ),
        );
        if (command == null || !mounted || workspace != _workspace) return;
        final Json result;
        try {
          result = inventoryObject(
            await workspace.api.post(commerceRoot(workspace), body: command),
          );
          if (result['id'] is! String || result['setup_secret'] is! String) {
            throw const FormatException(
              'The connection response did not contain its setup details.',
            );
          }
        } catch (failure) {
          if (mounted &&
              workspace == _workspace &&
              (failure is! ApexApiException ||
                  failure.uncertain ||
                  failure.status == 409)) {
            setState(
              () => _setupUnconfirmed = {
                'base_url': command['base_url'],
                'channel': command['channel'],
              },
            );
          }
          rethrow;
        }
        if (!mounted || workspace != _workspace) return;
        final id = result['id'] as String;
        await _setupDialog<void>(
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            title: const Text('One-time ApexBridge setup'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Enter these values in the Bagisto server configuration. The setup secret is shown once.',
                  ),
                  const SizedBox(height: 12),
                  const Text('Connection ID'),
                  SelectableText(id),
                  const Text('Channel'),
                  SelectableText(inventoryText(command['channel'])),
                  const Text('Setup secret'),
                  SelectableText(result['setup_secret'] as String),
                ],
              ),
            ),
            actions: [
              FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Done'),
              ),
            ],
          ),
        );
        if (mounted && workspace == _workspace) {
          await _refresh(select: id);
          if (mounted && workspace == _workspace) {
            setState(
              () => _notice = 'Connection created. Verify the installed bridge before activation.',
            );
          }
        }
      },
      success: '',
      refresh: false,
    );
  }

  Future<T?> _setupDialog<T>({
    required WidgetBuilder builder,
    bool barrierDismissible = true,
  }) async {
    final scope = _workspace;
    setState(() => _setupDialogOpen = true);
    try {
      return await showDialog<T>(
        context: context,
        builder: builder,
        barrierDismissible: barrierDismissible,
      );
    } finally {
      if (mounted && scope == _workspace) {
        setState(() => _setupDialogOpen = false);
      }
    }
  }

  Future<void> _checkConnections() async {
    final pending = _setupUnconfirmed;
    if (pending == null) return;
    await _refresh();
    if (!mounted || _error != null) return;
    final match = _connections
        .where(
          (row) =>
              row['base_url'] == pending['base_url'] &&
              row['channel'] == pending['channel'],
        )
        .firstOrNull;
    setState(
      () => _notice = match == null
          ? 'No matching connection is visible. The original request may still be running.'
          : 'A matching connection exists. Ask the administrator to review setup access.',
    );
  }

  Future<void> _verify() async {
    if (!_owner || _selected.isEmpty) return;
    final path = _path;
    if (!await _confirm(
      'Verify bridge',
      'Apex Books will check the installed ApexBridge on this store.',
    )) {
      return;
    }
    if (!mounted || path != _path) return;
    await _action(() async {
      await _workspace.api.post('$path/verify', body: const {});
    }, success: 'Bridge verified.');
  }

  Future<void> _state() async {
    if (!_owner || _selected.isEmpty) return;
    final active = _active;
    final path = _path;
    if (!await _confirm(
      active ? 'Pause connection' : 'Activate connection',
      active
          ? 'The store connection and its delivery processing will pause.'
          : 'The store can begin exchanging orders and stock after activation.',
    )) {
      return;
    }
    if (!mounted || path != _path) return;
    await _action(() async {
      await _workspace.api.put(
        '$path/state',
        body: {'status': active ? 'paused' : 'active'},
      );
    }, success: active ? 'Connection paused.' : 'Connection active.');
  }

  Future<bool> _confirm(String title, String details) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(title),
          content: Text(details),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Close'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Confirm'),
            ),
          ],
        ),
      ) ==
      true;

  Json _completed(String operation) => inventoryObject(
    _rows('outbox')
        .where(
          (row) => row['operation'] == operation && row['status'] == 'done',
        )
        .firstOrNull?['result'],
  );

  Future<void> _addMapping() async {
    final workspace = _workspace;
    final path = _path;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => CommerceMappingForm(
        workspace: workspace,
        storeProducts: inventoryRows(_completed('catalogue.scan')['products']),
      ),
    );
    if (!mounted || body == null || workspace != _workspace || path != _path) {
      return;
    }
    await _action(() async {
      await workspace.api.post('$path/links', body: body);
    }, success: 'Mapping saved.');
  }

  Future<void> _command(
    String operation,
    Json payload, {
    bool reviewed = false,
  }) async {
    if (!_canCommand) return;
    final connection = _selected;
    final workspace = _workspace;
    if (!reviewed &&
        !await _confirm(
          commerceLabel(operation),
          'Queue this action for ${_connection['name']}?',
        )) {
      return;
    }
    if (!mounted ||
        connection != _selected ||
        workspace != _workspace ||
        !_canCommand) {
      return;
    }
    await _action(() async {
      await _queue.submit(connection, operation, payload);
    }, success: 'Command accepted. Check Deliveries for its result.');
  }

  Future<void> _retryOriginal() async {
    final pending = _queue.pending;
    if (pending == null ||
        pending.connection != _selected ||
        !_active ||
        !_workspace.company.canWrite) {
      return;
    }
    await _action(() async {
      await _queue.retry(pending.connection);
    }, success: 'Original command confirmed. Check Deliveries for its result.');
  }

  Future<void> _retryDelivery(String direction, Json row) async {
    final path = _path;
    final id = Uri.encodeComponent(inventoryText(row['id']));
    if (!await _confirm(
      'Retry delivery',
      'Requeue this failed delivery using its existing identity.',
    )) {
      return;
    }
    if (!mounted || path != _path) return;
    await _action(() async {
      await _workspace.api.post('$path/retry/$direction/$id', body: const {});
    }, success: 'Delivery queued for retry.');
  }

  Future<void> _order(Json order) async {
    final connection = _selected;
    final intent = await showDialog<CommerceIntent>(
      context: context,
      builder: (_) => CommerceOrderForm(order: order, writable: _canCommand),
    );
    if (!mounted || intent == null || connection != _selected) return;
    await _command(intent.operation, intent.payload, reviewed: true);
  }

  Future<void> _money() async {
    final connection = _selected;
    final intent = await showDialog<CommerceIntent>(
      context: context,
      builder: (_) => CommerceMoneyForm(
        workspace: _workspace,
        orders: _rows('orders'),
        links: _rows('links'),
      ),
    );
    if (!mounted || intent == null || connection != _selected) return;
    await _command(intent.operation, intent.payload, reviewed: true);
  }

  Future<void> _evidence(CommerceEvidenceKind kind) async {
    if (!_canCommand) return;
    final connection = _selected;
    final workspace = _workspace;
    List<Json> banks = const [];
    if (kind == CommerceEvidenceKind.payout) {
      setState(() {
        _busy = true;
        _error = null;
      });
      try {
        banks = inventoryRows(
          await workspace.api.get('${workspace.path}/bank-accounts'),
        );
      } catch (failure) {
        if (mounted && workspace == _workspace) {
          setState(() => _error = inventoryError(failure));
        }
        return;
      } finally {
        if (mounted && workspace == _workspace) setState(() => _busy = false);
      }
    }
    if (!mounted ||
        workspace != _workspace ||
        connection != _selected ||
        !_canCommand) {
      return;
    }
    final gateway = inventoryText(
      inventoryObject(_connection['config'])['gateway_bank_id'],
    );
    final intent = await showDialog<CommerceIntent>(
      context: context,
      builder: (_) => CommerceEvidenceForm(
        workspace: workspace,
        kind: kind,
        orders: _rows('orders'),
        links: _rows('links'),
        stock: _rows('stock'),
        banks: banks,
        gatewayId: gateway.isEmpty ? 'default' : gateway,
      ),
    );
    if (!mounted ||
        intent == null ||
        workspace != _workspace ||
        connection != _selected) {
      return;
    }
    await _command(intent.operation, intent.payload, reviewed: true);
  }

  void _openRecord(String id) {
    if (id.isEmpty) return;
    final workspace = _workspace;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => Scaffold(
          body: SafeArea(
            child: BooksRecordDetail(
              data: BooksData(workspace.company.id, workspace.api.get),
              id: id,
              onBack: () => Navigator.of(context).pop(),
              onOpen: _openRecord,
              backLabel: 'Return to store deliveries',
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _queue,
    builder: (context, _) {
      final pending = _queue.pending;
      final sections = <Widget>[
        if (widget.onBack != null)
          Align(
            alignment: Alignment.centerLeft,
            child: IconButton(
              tooltip: 'Back to Settings',
              onPressed: _busy || _queue.busy ? null : widget.onBack,
              icon: const Icon(Icons.arrow_back),
            ),
          ),
        _heading(),
        if (!_setupDialogOpen && (_loading || _busy || _queue.busy))
          const LinearProgressIndicator(),
        if (_error != null) CommerceAlert(_error!, error: true),
        if (_notice?.isNotEmpty == true) CommerceAlert(_notice!),
        if (_queue.recoveryError != null)
          CommerceAlert(
            _queue.recoveryError!,
            action: TextButton(
              onPressed: _available ? _queue.load : null,
              child: const Text('Try again'),
            ),
          ),
        if (_setupUnconfirmed != null)
          CommerceAlert(
            'Connection creation is unconfirmed. Check existing connections before contacting the administrator. The setup secret cannot be recovered from the list.',
            action: TextButton(
              onPressed: _available ? _checkConnections : null,
              child: const Text('Check existing connections'),
            ),
          ),
        if (pending != null)
          CommerceAlert(
            '${commerceLabel(pending.operation)} is awaiting confirmation.',
            action: pending.connection != _selected
                ? TextButton(
                    onPressed: _available
                        ? () => _refresh(select: pending.connection)
                        : null,
                    child: const Text('Open original connection'),
                  )
                : TextButton(
                    onPressed:
                        _available && _active && _workspace.company.canWrite
                        ? _retryOriginal
                        : null,
                    child: const Text('Retry original command'),
                  ),
          ),
        if (_connections.isEmpty && !_loading)
          ApexPanel(
            child: const ApexEmptyState(
              icon: Icons.shopping_bag_outlined,
              title: 'Connect a Bagisto store to bring its orders, payments and stock into this company.',
            ),
          ),
        if (_connections.isNotEmpty) _storeBar(),
        if (_data != null) ...[
          CommerceTabBar<_Panel>(
            tabs: [for (final panel in _Panel.values) (panel, panel.label)],
            selected: _panel,
            onSelected: (panel) => setState(() => _panel = panel),
          ),
          ...switch (_panel) {
            _Panel.overview => _overview(_count),
            _Panel.catalogue => _catalogue(),
            _Panel.orders => _orders(),
            _Panel.payments => _payments(),
            _Panel.deliveries => _deliveries(),
            _Panel.reconciliation => _reconciliation(),
          },
        ],
      ];
      return ApexPage(
        maxWidth: 1100,
        children: [
          for (final (index, section) in sections.indexed) ...[
            if (index > 0) const SizedBox(height: 18),
            section,
          ],
        ],
      );
    },
  );

  int _count(String name) {
    final summary = inventoryObject(_data?['summary']);
    final inbox = inventoryObject(summary['inbox']);
    final outbox = inventoryObject(summary['outbox']);
    return (inbox[name] as int? ?? 0) + (outbox[name] as int? ?? 0);
  }

  Widget _heading() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        'SALES CHANNELS · ${_workspace.company.name}',
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.8,
          color: Apex.muted,
        ),
      ),
      const SizedBox(height: 4),
      ApexRegisterHeading(
        'Ecommerce',
        subtitle: 'Orders, inventory and books connected to the right company.',
        actions: [
          OutlinedButton.icon(
            onPressed: _available ? _refresh : null,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
          if (_owner)
            FilledButton.icon(
              onPressed: _available && _setupUnconfirmed == null
                  ? _newConnection
                  : null,
              icon: const Icon(Icons.add),
              label: const Text('Connect Bagisto'),
            ),
        ],
      ),
    ],
  );

  Widget _storeBar() => ApexPanel(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Wrap(
        spacing: 18,
        runSpacing: 14,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 280,
            child: DropdownButtonFormField<String>(
              key: ValueKey(_selected),
              initialValue: _selected,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Store channel'),
              items: [
                for (final row in _connections)
                  DropdownMenuItem(
                    value: inventoryText(row['id']),
                    child: Text(
                      '${row['name']} · ${row['channel']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: _available
                  ? (value) {
                      if (value != null) _refresh(select: value);
                    }
                  : null,
            ),
          ),
          if (_data != null) ...[
            CommerceStatus(_connection['status']),
            Text(
              '${inventoryText(_connection['currency'])} · ${inventoryText(_connection['base_url'])}',
              style: const TextStyle(fontSize: 12, color: Apex.muted),
            ),
          ],
          if (_owner && _data != null)
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _available ? _verify : null,
                  child: const Text('Verify bridge'),
                ),
                OutlinedButton(
                  onPressed:
                      _available &&
                          (_active ||
                              inventoryObject(
                                    _connection['config'],
                                  )['verified'] ==
                                  true)
                      ? _state
                      : null,
                  child: Text(_active ? 'Pause' : 'Activate'),
                ),
              ],
            ),
        ],
      ),
    ),
  );

  List<Widget> _overview(int Function(String) count) {
    final verified = inventoryObject(_connection['config'])['verified'] == true;
    final checks = [
      (true, 'Company ownership and channel saved'),
      (verified, 'Server bridge verified'),
      (_active, 'Connection active'),
      (_rows('stock').isNotEmpty, 'Store SKUs mapped'),
      (
        _rows('reconciliations').any((row) => row['status'] == 'balanced'),
        'Reconciliation completed',
      ),
    ];
    final reservations = _rows('reservations');
    return [
      CommerceMetrics([
        (Icons.shopping_bag_outlined, 'Store orders', _rows('orders').length),
        (Icons.inventory_2_outlined, 'Mapped SKUs', _rows('stock').length),
        (
          Icons.sync,
          'Waiting delivery',
          count('pending') + count('processing'),
        ),
        (Icons.error_outline, 'Needs review', count('review') + count('retry')),
      ]),
      CommerceGrid([
        CommerceSection(
          title: 'Connection checklist',
          note: 'Checkout reserves stock before accepting an order. Invoices post sales and GST; shipments update fulfilment. Captures enter clearing, and settlements move the bank net and fees.',
          children: [
            for (final (done, label) in checks)
              Row(
                children: [
                  Icon(
                    done ? Icons.check_circle : Icons.check_circle_outline,
                    size: 18,
                    color: done ? Apex.green : const Color(0xffbbc8cf),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      label,
                      style: const TextStyle(fontSize: 13, color: Apex.ink),
                    ),
                  ),
                ],
              ),
          ],
        ),
        CommerceSection(
          title: 'Review and repair',
          note: 'Unmapped items, tax differences and unsupported source rules stay visible for review. Correct the mapping or source, then retry the delivery.',
          actions: [
            OutlinedButton.icon(
              onPressed: () => setState(() => _panel = _Panel.deliveries),
              icon: const Icon(Icons.north_east, size: 16),
              label: const Text('Open delivery queue'),
            ),
            if (_workspace.company.canWrite) ...[
              OutlinedButton(
                onPressed: _canCommand
                    ? () => _command('history.scan', const {'after_id': 0})
                    : null,
                child: const Text('Scan store history'),
              ),
              if (_completed('history.scan')['next_after_id'] is int)
                OutlinedButton(
                  onPressed: _canCommand
                      ? () => _command('history.scan', {
                          'after_id': _completed(
                            'history.scan',
                          )['next_after_id'],
                        })
                      : null,
                  child: const Text('Scan next history page'),
                ),
            ],
          ],
        ),
      ]),
      if (reservations.isNotEmpty)
        CommerceSection(
          title: 'Stock reservations',
          children: [
            ApexTable(
              columns: const [
                ApexColumn('Reference', flex: 2),
                ApexColumn('Status'),
                ApexColumn('Expires'),
                ApexColumn('Lines', alignEnd: true),
              ],
              rowCount: reservations.length,
              cell: (row, column) {
                final hold = reservations[row];
                return switch (column) {
                  0 => CommerceCellTitle(inventoryText(hold['reference'])),
                  1 => CommerceStatus(hold['status']),
                  2 => CommerceCell(inventoryText(hold['expires_at'])),
                  _ => CommerceCell(
                    '${inventoryRows(hold['lines']).length} lines',
                  ),
                };
              },
              card: (row) {
                final hold = reservations[row];
                return CommerceListRow(
                  title: inventoryText(hold['reference']),
                  badge: CommerceStatus(hold['status']),
                  detail:
                      'Expires ${inventoryText(hold['expires_at'])} · ${inventoryRows(hold['lines']).length} lines',
                );
              },
            ),
          ],
        ),
    ];
  }

  List<Widget> _catalogue() {
    final canWrite = _workspace.company.canWrite;
    final stock = _rows('stock');
    final mappings = _rows('links')
        .where(
          (row) => const {'product', 'customer'}.contains(row['entity_type']),
        )
        .toList();
    return [
      CommerceSection(
        title: 'Product and customer mappings',
        note: 'Choose the accounting item or party in this company explicitly.',
        actions: [
          if (canWrite) ...[
            OutlinedButton(
              onPressed: _available ? _addMapping : null,
              child: const Text('Add mapping'),
            ),
            OutlinedButton(
              onPressed: _canCommand
                  ? () => _command('catalogue.scan', const {})
                  : null,
              child: const Text('Read store catalogue'),
            ),
            if (_completed('catalogue.scan')['next_after_id'] is int)
              OutlinedButton(
                onPressed: _canCommand
                    ? () => _command('catalogue.scan', {
                        'after_id': _completed(
                          'catalogue.scan',
                        )['next_after_id'],
                      })
                    : null,
                child: const Text('Read next catalogue page'),
              ),
          ],
        ],
        children: [
          if (mappings.isNotEmpty) ...[
            const CommerceSubheading('Mappings'),
            ApexTable(
              columns: const [
                ApexColumn('Mapping', flex: 2),
                ApexColumn('Accounting record', width: 180),
              ],
              rowCount: mappings.length,
              cell: (row, column) {
                final link = mappings[row];
                if (column == 0) {
                  return CommerceCellTitle(
                    '${commerceLabel(link['entity_type'])} ${link['external_id']}',
                    subtitle: inventoryText(
                      link['sku'] ?? inventoryObject(link['snapshot'])['name'],
                    ),
                  );
                }
                return inventoryText(link['record_id']).isEmpty
                    ? const SizedBox.shrink()
                    : TextButton(
                        onPressed: () =>
                            _openRecord(inventoryText(link['record_id'])),
                        child: const Text('Accounting record'),
                      );
              },
              card: (row) {
                final link = mappings[row];
                final hasRecord = inventoryText(link['record_id']).isNotEmpty;
                return CommerceListRow(
                  title:
                      '${commerceLabel(link['entity_type'])} ${link['external_id']}',
                  subtitle: inventoryText(
                    link['sku'] ?? inventoryObject(link['snapshot'])['name'],
                  ),
                  action: hasRecord
                      ? TextButton(
                          onPressed: () =>
                              _openRecord(inventoryText(link['record_id'])),
                          child: const Text('Accounting record'),
                        )
                      : null,
                );
              },
            ),
          ],
        ],
      ),
      CommerceSection(
        title: 'Sellable inventory',
        actions: [
          if (canWrite)
            OutlinedButton(
              onPressed: _canCommand
                  ? () => _command('catalogue.publish', const {})
                  : null,
              child: const Text('Publish accounting prices & stock'),
            ),
        ],
        children: [
          if (stock.isEmpty)
            const ApexEmptyState(
              icon: Icons.shopping_bag_outlined,
              title: 'No products mapped yet.',
            )
          else
            ApexTable(
              columns: const [
                ApexColumn('Item / SKU', flex: 2),
                ApexColumn('Book stock'),
                ApexColumn('Reserved'),
                ApexColumn('Sellable'),
                ApexColumn('Sale rate'),
              ],
              rowCount: stock.length,
              cell: (row, column) {
                final item = stock[row];
                return switch (column) {
                  0 => CommerceCellTitle(
                    inventoryText(item['name']),
                    subtitle: inventoryText(item['sku']),
                  ),
                  1 => CommerceCell(inventoryQuantity(item['book_quantity'])),
                  2 => CommerceCell(
                    inventoryQuantity(item['reserved_quantity']),
                  ),
                  3 => CommerceCell(
                    inventoryQuantity(item['available_quantity']),
                  ),
                  _ => CommerceCell(inventoryAmount(item['sale_rate'])),
                };
              },
              card: (row) {
                final item = stock[row];
                return CommerceListRow(
                  title: inventoryText(item['name']),
                  subtitle: inventoryText(item['sku']),
                  trailing: CommerceCell(inventoryAmount(item['sale_rate'])),
                  detail:
                      'Book ${inventoryQuantity(item['book_quantity'])} · Reserved ${inventoryQuantity(item['reserved_quantity'])} · Sellable ${inventoryQuantity(item['available_quantity'])}',
                );
              },
            ),
        ],
      ),
    ];
  }

  List<Widget> _orders() {
    final orders = _rows('orders');
    return [
      CommerceSection(
        title: 'Store orders',
        children: [
          if (orders.isEmpty)
            const ApexEmptyState(
              icon: Icons.shopping_bag_outlined,
              title: 'Accepted store orders appear here after delivery.',
            )
          else
            ApexTable(
              columns: const [
                ApexColumn('Order', flex: 2),
                ApexColumn('Customer'),
                ApexColumn('Status'),
                ApexColumn('Total', alignEnd: true),
                ApexColumn('', width: 130),
              ],
              rowCount: orders.length,
              onRowTap: (row) => _order(orders[row]),
              cell: (row, column) {
                final order = orders[row];
                return switch (column) {
                  0 => CommerceCellTitle(
                    inventoryText(order['number']),
                    subtitle: inventoryText(order['external_id']),
                  ),
                  1 => CommerceCell(
                    _partyNames[inventoryText(order['party_id'])] ??
                        inventoryText(
                          inventoryObject(order['snapshot'])['customer_id'],
                        ),
                  ),
                  2 => CommerceStatus(order['status']),
                  3 => CommerceCell(inventoryAmount(order['amount'])),
                  _ => OutlinedButton(
                    onPressed: () => _order(order),
                    child: const Text('Open order'),
                  ),
                };
              },
              card: (row) {
                final order = orders[row];
                return CommerceListRow(
                  title: inventoryText(order['number']),
                  subtitle: inventoryText(order['external_id']),
                  trailing: CommerceCell(inventoryAmount(order['amount'])),
                  badge: CommerceStatus(order['status']),
                  action: OutlinedButton(
                    onPressed: () => _order(order),
                    child: const Text('Open order'),
                  ),
                );
              },
            ),
        ],
      ),
    ];
  }

  List<Widget> _payments() {
    final canWrite = _workspace.company.canWrite;
    final paymentRows = _rows('links')
        .where(
          (row) => const {'capture', 'refund'}.contains(row['entity_type']),
        )
        .toList();
    return [
      CommerceSection(
        title: 'Payments, payouts & physical returns',
        note: 'Record confirmed source transactions. Invoice status alone does not prove money was received.',
        actions: [
          if (canWrite) ...[
            FilledButton(
              onPressed: _canCommand && _rows('orders').isNotEmpty
                  ? _money
                  : null,
              child: const Text('Record confirmed payment or refund'),
            ),
            for (final kind in CommerceEvidenceKind.values)
              OutlinedButton(
                onPressed:
                    _canCommand &&
                        (kind == CommerceEvidenceKind.payout ||
                            _rows('orders').isNotEmpty)
                    ? () => _evidence(kind)
                    : null,
                child: Text(kind.label),
              ),
          ],
        ],
        children: const [
          Text(
            'Record payment against a linked invoice or a refund against a linked credit note.',
            style: TextStyle(fontSize: 13, height: 1.6, color: Apex.muted),
          ),
        ],
      ),
      CommerceSection(
        title: 'Provider payments and refunds',
        children: [
          if (paymentRows.isEmpty)
            const ApexEmptyState(
              icon: Icons.payments_outlined,
              title: 'No provider payments or refunds recorded.',
            )
          else
            ApexTable(
              columns: const [
                ApexColumn('Reference', flex: 2),
                ApexColumn('Date'),
                ApexColumn('Amount', alignEnd: true),
              ],
              rowCount: paymentRows.length,
              onRowTap: (row) =>
                  _openRecord(inventoryText(paymentRows[row]['record_id'])),
              cell: (row, column) {
                final link = paymentRows[row];
                final snapshot = inventoryObject(link['snapshot']);
                return switch (column) {
                  0 => CommerceCellTitle(
                    '${link['entity_type'] == 'capture' ? 'Payment' : 'Refund'} ${link['external_id']}',
                  ),
                  1 => CommerceCell(inventoryText(snapshot['date'])),
                  _ => CommerceCell(inventoryAmount(snapshot['amount'])),
                };
              },
              card: (row) {
                final link = paymentRows[row];
                final snapshot = inventoryObject(link['snapshot']);
                return CommerceListRow(
                  title:
                      '${link['entity_type'] == 'capture' ? 'Payment' : 'Refund'} ${link['external_id']}',
                  subtitle: inventoryText(snapshot['date']),
                  trailing: CommerceCell(inventoryAmount(snapshot['amount'])),
                );
              },
            ),
        ],
      ),
    ];
  }

  List<Widget> _deliveries() {
    final canWrite = _workspace.company.canWrite;
    return [
      for (final direction in ['inbox', 'outbox'])
        CommerceSection(
          title: direction == 'inbox' ? 'Store → Books' : 'Books → Store',
          children: [
            if (_rows(direction).isEmpty)
              const ApexEmptyState(
                icon: Icons.local_shipping_outlined,
                title: 'No deliveries yet.',
              )
            else
              ApexTable(
                columns: const [
                  ApexColumn('Action / identity', flex: 2),
                  ApexColumn('Status'),
                  ApexColumn('Details', flex: 2),
                  ApexColumn('', width: 110),
                ],
                rowCount: _rows(direction).length,
                onRowTap: (row) {
                  final id = _deliveryRecord(_rows(direction)[row]);
                  if (id.isNotEmpty) _openRecord(id);
                },
                cell: (row, column) {
                  final delivery = _rows(direction)[row];
                  return switch (column) {
                    0 => CommerceCellTitle(
                      commerceLabel(
                        delivery['event_type'] ?? delivery['operation'],
                      ),
                      subtitle: inventoryText(
                        delivery['entity_id'] ?? delivery['command_id'],
                      ),
                    ),
                    1 => CommerceStatus(delivery['status']),
                    2 => CommerceCell(_deliveryDetail(delivery)),
                    _ =>
                      _canRetry(canWrite, delivery)
                          ? TextButton(
                              onPressed: _available
                                  ? () => _retryDelivery(direction, delivery)
                                  : null,
                              child: const Text('Retry'),
                            )
                          : const SizedBox.shrink(),
                  };
                },
                card: (row) {
                  final delivery = _rows(direction)[row];
                  return CommerceListRow(
                    title: commerceLabel(
                      delivery['event_type'] ?? delivery['operation'],
                    ),
                    subtitle: inventoryText(
                      delivery['entity_id'] ?? delivery['command_id'],
                    ),
                    badge: CommerceStatus(delivery['status']),
                    detail: _deliveryDetail(delivery),
                    action: _canRetry(canWrite, delivery)
                        ? TextButton(
                            onPressed: _available
                                ? () => _retryDelivery(direction, delivery)
                                : null,
                            child: const Text('Retry'),
                          )
                        : null,
                  );
                },
              ),
          ],
        ),
    ];
  }

  bool _canRetry(bool canWrite, Json delivery) =>
      canWrite && const {'review', 'retry'}.contains(delivery['status']);

  String _deliveryRecord(Json delivery) =>
      inventoryText(inventoryObject(delivery['result'])['record_id']);

  String _deliveryDetail(Json delivery) {
    final error = inventoryText(delivery['error'] ?? '');
    if (error.isNotEmpty) return error;
    return inventoryText(
      inventoryObject(delivery['result'])['invoice_number'] ?? '',
    );
  }

  List<Widget> _reconciliation() {
    final reports = _rows('reconciliations');
    return [
      CommerceSection(
        title: 'Store reconciliation',
        note: 'Compare source totals and mapped sellable stock. Results stay in this company’s audit trail.',
        actions: [
          if (_workspace.company.canWrite)
            FilledButton(
              onPressed: _canCommand
                  ? () => _command('reconcile.snapshot', const {})
                  : null,
              child: const Text('Reconcile now'),
            ),
        ],
        children: [
          if (reports.isEmpty)
            const ApexEmptyState(
              icon: Icons.fact_check_outlined,
              title: 'Run the first reconciliation after mapping products and importing orders.',
            ),
          for (final row in reports) _differenceReport(row),
        ],
      ),
    ];
  }

  Widget _differenceReport(Json row) {
    final report = inventoryObject(row['report']);
    final stock = inventoryRows(report['stock_differences']);
    final money = inventoryRows(report['financial_differences']);
    return ApexPanel(
      radius: 12,
      child: ExpansionTile(
        shape: const Border(),
        collapsedShape: const Border(),
        title: Text(
          '${commerceLabel(row['status'])} · ${inventoryText(row['created_at']).split('T').first}',
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          '${stock.length} stock differences · ${money.length} financial differences',
          style: const TextStyle(fontSize: 12, color: Apex.muted),
        ),
        children: [
          for (final line in stock)
            ListTile(
              title: Text('Product ${line['product_id']}'),
              subtitle: Text(
                'Apex Books ${line['expected']} · Store ${line['actual'] ?? 'missing'}',
              ),
            ),
          for (final line in money)
            ListTile(
              title: Text(commerceLabel(line['total'])),
              subtitle: Text(
                'Apex Books ${inventoryAmount(line['expected'])} · Store ${inventoryAmount(line['actual'])}',
              ),
            ),
        ],
      ),
    );
  }
}
