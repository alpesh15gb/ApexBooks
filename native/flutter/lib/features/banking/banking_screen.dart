import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'bank_data.dart';
import 'bank_forms.dart';
import 'bank_match.dart';
import 'bank_widgets.dart';

typedef BankView = ({
  List<Json> accounts,
  Json book,
  Json totals,
  List<Json> statement,
  List<Json> reviews,
});

class BankingScreen extends StatefulWidget {
  const BankingScreen({
    required this.workspace,
    this.active = true,
    this.revision = 0,
    super.key,
  });
  final WorkspaceContext workspace;
  final bool active;
  final int revision;

  @override
  State<BankingScreen> createState() => _BankingScreenState();
}

class _BankingScreenState extends State<BankingScreen> {
  static const _storage = 'banking';
  final _end = TextEditingController(text: businessDate());
  final _start = TextEditingController(
    text: '${businessDate().substring(0, 7)}-01',
  );
  final _opening = TextEditingController(text: '0');
  String _bank = 'default';
  bool _reconcile = false;
  bool _busy = false;
  bool _ready = false;
  String? _error;
  String? _notice;
  Json? _pending;
  BankView? _view;
  late Future<BankView> _data;

  WorkspaceContext get _workspace => widget.workspace;
  String get _base => _workspace.path;
  bool get _writable =>
      _workspace.company.canWrite && _ready && _pending == null && !_busy;

  @override
  void initState() {
    super.initState();
    _data = _fetch();
    _readPending();
  }

  @override
  void didUpdateWidget(covariant BankingScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.workspace.company.id != oldWidget.workspace.company.id) {
      _bank = 'default';
      _pending = null;
      _ready = false;
      _view = null;
      _busy = false;
      _error = null;
      _notice = null;
      _readPending();
      _data = _fetch();
    } else if (widget.active &&
        (!oldWidget.active || widget.revision != oldWidget.revision)) {
      _data = _fetch();
    }
  }

  @override
  void dispose() {
    _start.dispose();
    _end.dispose();
    _opening.dispose();
    super.dispose();
  }

  Future<BankView> _fetch() async {
    final api = _workspace.api;
    final base = _base;
    final bank = _bank;
    final from = validBankDate(_start.text);
    final to = validBankDate(_end.text);
    if (to == null) throw const FormatException('Enter a valid closing date.');
    final selected = {'bank_account_id': bank};
    if (!_reconcile) {
      if (from == null || from.compareTo(to) > 0) {
        throw const FormatException(
          'Enter a start date on or before the closing date.',
        );
      }
      final result = await Future.wait([
        api.get('$base/bank-accounts'),
        api.get(
          '$base/cash-book',
          query: {...selected, 'from_date': from, 'to_date': to},
        ),
      ]);
      return (
        accounts: inventoryRows(result[0]),
        book: inventoryObject(result[1]),
        totals: const <String, dynamic>{},
        statement: const <Json>[],
        reviews: const <Json>[],
      );
    }
    final opening = signedMoney(_opening.text);
    if (opening == null) {
      throw const FormatException('Enter a valid statement opening balance.');
    }
    final period = {...selected, 'as_of': to};
    final result = await Future.wait([
      api.get('$base/bank-accounts'),
      api.get(
        '$base/bank-reconciliation',
        query: {...period, 'opening_balance': decimalMoney(opening)},
      ),
      api.get('$base/bank-statement', query: period),
      api.get('$base/bank-reconciliation/reviews', query: selected),
    ]);
    return (
      accounts: inventoryRows(result[0]),
      book: const <String, dynamic>{},
      totals: inventoryObject(result[1]),
      statement: inventoryRows(result[2]),
      reviews: inventoryRows(result[3]),
    );
  }

  Future<void> _readPending() async {
    final owner = _workspace;
    try {
      final command = await owner.pending.load(_storage);
      if (!mounted || owner != _workspace) return;
      if (command != null &&
          (command['key'] is! String ||
              command['body'] is! Map ||
              !const {
                'transfer',
                'statement',
                'opening',
              }.contains(command['kind']))) {
        throw const FormatException('Invalid pending bank request.');
      }
      setState(() {
        _pending = command;
        _ready = true;
        _error = null;
      });
    } catch (_) {
      if (mounted && owner == _workspace) {
        setState(
          () => _error = 'The previous bank request could not be recovered. Try loading it again.',
        );
      }
    }
  }

  void _reload() {
    final data = _fetch();
    setState(() {
      _data = data;
    });
  }

  Future<void> _command(String kind, Json body) async {
    if (!_writable) return;
    final owner = _workspace;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final rng = Random.secure();
      final id = List.generate(
        20,
        (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0'),
      ).join();
      final command = {'kind': kind, 'key': 'flutter-bank-$id', 'body': body};
      await owner.pending.save(_storage, command);
      if (mounted && owner == _workspace) _pending = command;
      await _send(owner, command, retrying: false);
    } catch (error) {
      if (mounted && owner == _workspace) {
        setState(() => _error = inventoryError(error));
      }
    } finally {
      if (mounted && owner == _workspace) setState(() => _busy = false);
    }
  }

  Future<void> _send(
    WorkspaceContext owner,
    Json command, {
    required bool retrying,
  }) async {
    final kind = command['kind'];
    final endpoint = switch (kind) {
      'transfer' => 'records',
      'statement' => 'bank-statement/import',
      'opening' => 'opening-balances',
      _ => throw const FormatException('Invalid bank operation.'),
    };
    final path = '${owner.path}/$endpoint';
    final Json result;
    try {
      result = inventoryObject(
        await owner.api.post(
          path,
          body: inventoryObject(command['body']),
          idempotencyKey: command['key'] as String,
        ),
      );
      if (kind == 'statement'
          ? result['added'] is! int
          : inventoryText(result['id']).isEmpty) {
        throw const FormatException('The bank request could not be confirmed.');
      }
    } on ApexApiException catch (failure) {
      if (!retrying && !failure.uncertain) {
        await owner.pending.clear(_storage);
        if (mounted && owner == _workspace) _pending = null;
      }
      rethrow;
    }
    await owner.pending.clear(_storage);
    if (mounted && owner == _workspace) {
      setState(() {
        _pending = null;
        _notice = switch (kind) {
          'transfer' =>
            result['posted'] == false
                ? 'Transfer was cancelled.'
                : 'Transfer posted.',
          'opening' => 'Opening balance posted.',
          _ => '${result['added']} statement lines imported.',
        };
      });
      _reload();
    }
    await owner.refresh();
  }

  Future<void> _retry() async {
    final pending = _pending;
    final owner = _workspace;
    if (pending == null || _busy || !_workspace.company.canWrite) return;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await _send(owner, pending, retrying: true);
    } catch (failure) {
      if (mounted && owner == _workspace) {
        setState(() => _error = inventoryError(failure));
      }
    } finally {
      if (mounted && owner == _workspace) setState(() => _busy = false);
    }
  }

  Future<void> _change(
    Future<dynamic> Function(WorkspaceContext) send,
    String message, {
    void Function(dynamic value)? accept,
  }) async {
    if (!_writable) return;
    final owner = _workspace;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      final result = await send(owner);
      if (mounted && owner == _workspace) {
        setState(() {
          accept?.call(result);
          _notice = message;
        });
        _reload();
      }
      await owner.refresh();
    } catch (failure) {
      if (mounted && owner == _workspace) {
        _reload();
        setState(
          () => _error = failure is ApexApiException && failure.uncertain
              ? '${failure.message} Check the refreshed records before retrying.'
              : inventoryError(failure),
        );
      }
    } finally {
      if (mounted && owner == _workspace) setState(() => _busy = false);
    }
  }

  Future<void> _newBank() async {
    final owner = _workspace;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => const BankAccountForm(),
    );
    if (body == null || !mounted || owner != _workspace) return;
    await _change(
      (owner) => owner.api.post('${owner.path}/bank-accounts', body: body),
      'Bank account created.',
      accept: (value) => _bank = inventoryText(inventoryObject(value)['id']),
    );
  }

  Future<void> _transfer(List<Json> accounts) async {
    final owner = _workspace;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => TransferForm(accounts: accounts, bank: _bank),
    );
    if (body == null || !mounted || owner != _workspace) return;
    await _command('transfer', body);
  }

  Future<void> _openingBalance(List<Json> accounts) async {
    final owner = _workspace;
    if (owner.company.role != 'owner') return;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => BankOpeningForm(accounts: accounts, bank: _bank),
    );
    if (body == null || !mounted || owner != _workspace) return;
    await _command('opening', body);
  }

  Future<void> _import() async {
    final owner = _workspace;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => StatementImportForm(
        bank: _bank,
        preview: (body) async => inventoryObject(
          await owner.api.post(
            '${owner.path}/bank-statement/import',
            body: body,
          ),
        ),
      ),
    );
    if (body == null || !mounted || owner != _workspace) return;
    await _command('statement', body);
  }

  Future<void> _allocate(Json line) async {
    final owner = _workspace;
    final bank = _bank;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => BankMatchDialog(workspace: owner, bank: bank, line: line),
    );
    if (body == null || !mounted || owner != _workspace) return;
    final id = Uri.encodeComponent(inventoryText(line['id']));
    await _change(
      (owner) => owner.api.post(
        '${owner.path}/bank-statement/$id/allocations',
        body: body,
      ),
      'Statement line matched.',
    );
  }

  Future<void> _removeMatch(String id, {required bool allocation}) async {
    final owner = _workspace;
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove statement match?'),
        content: const Text('The accounting transaction stays in the books.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Keep match'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove match'),
          ),
        ],
      ),
    );
    if (confirm != true || !mounted || owner != _workspace) return;
    final encoded = Uri.encodeComponent(id);
    final suffix = allocation ? 'allocations/$encoded' : '$encoded/match';
    await _change(
      (owner) => owner.api.delete('${owner.path}/bank-statement/$suffix'),
      'Statement match removed.',
    );
  }

  Future<void> _review(Json totals) async {
    final owner = _workspace;
    final body = await showDialog<Json>(
      context: context,
      builder: (_) => BankReviewForm(totals: totals),
    );
    if (body == null || !mounted || owner != _workspace) return;
    await _change(
      (owner) => owner.api.post(
        '${owner.path}/bank-reconciliation/reviews',
        body: body,
      ),
      'Reconciliation review saved.',
    );
  }


  static String _money(Object? value) => apexMoney(apexNumber(value) ?? 0);

  String get _bankName {
    for (final account in _view?.accounts ?? const <Json>[]) {
      if (account['id'] == _bank) return inventoryText(account['name']);
    }
    return 'Bank clearing';
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<BankView>(
    future: _data,
    builder: (context, state) {
      final data = state.data;
      if (data != null) _view = data;
      final loading = state.connectionState != ConnectionState.done;
      final usable = _writable && !loading && !state.hasError;
      final ready = data != null && !loading && !state.hasError;
      final canWrite = _workspace.company.canWrite;
      final accounts = _view?.accounts ?? const <Json>[];
      final choices = [
        for (final row in accounts)
          (
            inventoryText(row['id']),
            inventoryText(row['name']) +
                (inventoryText(row['account_hint']).isEmpty ? '' : ' · ${inventoryText(row['account_hint'])}'),
          ),
      ];
      final sections = <Widget>[
        ApexRegisterHeading(
          'Cash & bank',
          subtitle: 'Track payments and reconcile each bank account separately.',
          actions: [
            if (canWrite)
              FilledButton.icon(
                onPressed: usable ? _import : null,
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Import statement CSV'),
              ),
          ],
        ),
        BankTabs(
          reconcile: _reconcile,
          onChanged: (value) => setState(() {
            _reconcile = value;
            _data = _fetch();
          }),
        ),
        BankPanel(
          title: 'Bank accounts',
          note: 'Choose the account for its balance, statement and matches.',
          children: [
            Wrap(
              spacing: 16,
              runSpacing: 14,
              crossAxisAlignment: WrapCrossAlignment.end,
              children: [
                if (choices.isNotEmpty)
                  ApexFilterSelect<String>(
                    label: 'Active bank',
                    width: 300,
                    value: choices.any((choice) => choice.$1 == _bank) ? _bank : choices.first.$1,
                    items: choices,
                    onChanged: (id) => setState(() {
                      _bank = id;
                      _data = _fetch();
                    }),
                  ),
                if (canWrite)
                  OutlinedButton(onPressed: _writable ? _newBank : null, child: const Text('Add bank account')),
              ],
            ),
            const SizedBox(height: 16),
            const Divider(height: 1, color: Apex.lineSoft),
            const SizedBox(height: 16),
            Wrap(
              spacing: 14,
              runSpacing: 14,
              crossAxisAlignment: WrapCrossAlignment.end,
              children: [
                if (!_reconcile) BankFilterField(label: 'From', controller: _start, hint: 'YYYY-MM-DD', maxLength: 10),
                BankFilterField(
                  label: _reconcile ? 'Reconcile through' : 'To',
                  controller: _end,
                  hint: 'YYYY-MM-DD',
                  maxLength: 10,
                ),
                if (_reconcile)
                  BankFilterField(
                    label: 'Statement opening balance (₹)',
                    controller: _opening,
                    width: 230,
                    maxLength: 17,
                    keyboard: const TextInputType.numberWithOptions(decimal: true, signed: true),
                  ),
                SizedBox(
                  height: 40,
                  child: OutlinedButton.icon(
                    onPressed: _busy ? null : _reload,
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Load'),
                  ),
                ),
              ],
            ),
            if (_reconcile) ...[
              const SizedBox(height: 12),
              const Text(
                'Compare the imported statement closing balance with the posted bank ledger through this date.',
                style: Apex.note,
              ),
            ],
          ],
        ),
        if (_pending != null)
          BankNote(
            live: true,
            child: Row(
              children: [
                const Expanded(child: Text('A bank request awaits confirmation.')),
                TextButton(
                  onPressed: !_busy && canWrite ? _retry : null,
                  child: const Text('Retry original'),
                ),
              ],
            ),
          ),
        if (_notice != null) BankNote(tone: BankTone.ok, live: true, child: Text(_notice!)),
        if (_error != null)
          BankNote(
            tone: BankTone.error,
            live: true,
            child: Row(
              children: [
                Expanded(child: Text(_error!)),
                if (!_ready) TextButton(onPressed: _readPending, child: const Text('Try again')),
              ],
            ),
          ),
        if (loading) const LinearProgressIndicator(),
        if (state.hasError) BankNote(tone: BankTone.error, live: true, child: Text(inventoryError(state.error!))),
        if (ready) ...(_reconcile ? _reconciliation(data, usable) : _cashBook(data, usable)),
      ];
      return ApexPage(
        children: [
          for (final (index, section) in sections.indexed) ...[
            if (index > 0) SizedBox(height: index == 1 ? 18 : 16),
            section,
          ],
        ],
      );
    },
  );

  List<Widget> _cashBook(BankView view, bool usable) {
    final opening = inventoryObject(view.book['opening']);
    final closing = inventoryObject(view.book['closing']);
    final rows = inventoryRows(view.book['rows']);
    final through = 'Through ${apexDate(_end.text.trim())}';
    final negative = (apexNumber(closing['cash']) ?? 0) < 0;
    final note = inventoryText(view.book['ordering_note']);
    final canWrite = _workspace.company.canWrite;
    return [
      BankMetricGrid([
        BankMetric(label: 'Cash balance', value: _money(closing['cash']), caption: through),
        BankMetric(label: '$_bankName balance', value: _money(closing['bank']), caption: through),
      ]),
      if (negative)
        BankNote(
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: 'Review negative cash through ${apexDate(_end.text.trim())}. ',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                const TextSpan(
                  text:
                      'The posted cash ledger is below zero. Check opening balances, missing or misdated receipts, cash payments, transfers and imported entries against your records. This is a review cue, not proof of the cause; do not add a balancing entry without supporting evidence. The recorded balance has not been changed. Same-day row order may affect intermediate balances; the closing balance shown here is for the selected end date.',
                ),
              ],
            ),
          ),
        ),
      BankPanel(
        title: 'Cash and bank book',
        note: 'Posted ledger movements for cash and the selected bank.',
        flush: true,
        children: [
          if (note.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(22, 0, 22, 14),
              child: BankNote(child: Text(note)),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(22, 0, 22, 14),
            child: Text(
              'Opening cash ${_money(opening['cash'])} · bank ${_money(opening['bank'])}',
              style: Apex.note,
            ),
          ),
          if (rows.isEmpty)
            const ApexEmptyState(icon: Icons.account_balance_wallet_outlined, title: 'No posted movements in this period')
          else
            ApexTable(
              columns: const [
                ApexColumn('Date', width: 120),
                ApexColumn('Reference / description', flex: 2.2),
                ApexColumn('Type', flex: 1),
                ApexColumn('Cash', flex: 1.2, alignEnd: true),
                ApexColumn('Bank', flex: 1.2, alignEnd: true),
                ApexColumn('Cash balance', flex: 1.3, alignEnd: true),
                ApexColumn('Bank balance', flex: 1.3, alignEnd: true),
              ],
              rowCount: rows.length,
              cell: (row, column) {
                final item = rows[row];
                return switch (column) {
                  0 => Text(apexDate(inventoryText(item['date'])), style: _cell),
                  1 => _referenceCell(item),
                  2 => Text(inventoryText(item['kind']).replaceAll('_', ' '), style: _cell),
                  3 => Text(_money(item['cash']), style: _cell),
                  4 => Text(_money(item['bank']), style: _cell),
                  5 => Text(_money(item['cash_balance']), style: _cell),
                  _ => Text(_money(item['bank_balance']), style: _cell),
                };
              },
              card: (row) {
                final item = rows[row];
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _referenceCell(item),
                    const SizedBox(height: 4),
                    Text(
                      '${apexDate(inventoryText(item['date']))} · ${inventoryText(item['kind']).replaceAll('_', ' ')}',
                      style: Apex.small,
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 16,
                      runSpacing: 4,
                      children: [
                        Text('Cash ${_money(item['cash'])}', style: _cell),
                        Text('Bank ${_money(item['bank'])}', style: _cell),
                        Text('Cash balance ${_money(item['cash_balance'])}', style: Apex.note),
                        Text('Bank balance ${_money(item['bank_balance'])}', style: Apex.note),
                      ],
                    ),
                  ],
                );
              },
            ),
        ],
      ),
      const BankNote(
        child: Text('Manual journals and reversals are included. Movements on the same date use a consistent order.'),
      ),
      if (canWrite)
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilledButton.icon(
              onPressed: usable ? () => _transfer(view.accounts) : null,
              icon: const Icon(Icons.swap_horiz, size: 18),
              label: const Text('Record transfer'),
            ),
            if (_workspace.company.role == 'owner')
              OutlinedButton(onPressed: usable ? () => _openingBalance(view.accounts) : null, child: const Text('Opening balance')),
          ],
        ),
    ];
  }

  static const _cell = TextStyle(fontSize: 13, color: Apex.inkSoft);

  Widget _referenceCell(Json item) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(inventoryText(item['reference']), style: _cell),
      if (inventoryText(item['description']).isNotEmpty) Text(inventoryText(item['description']), style: Apex.small),
    ],
  );

  List<Widget> _reconciliation(BankView data, bool usable) {
    final totals = data.totals;
    final canWrite = _workspace.company.canWrite;
    final asOf = inventoryText(totals['as_of']).isEmpty ? _end.text.trim() : inventoryText(totals['as_of']);
    return [
      const BankNote(
        child: Text(
          'Map the date, description, reference and amount columns in your bank CSV. Separate debit and credit columns are supported. Positive amounts are received; negative amounts are paid. Import into the selected account. Payment suggestions use amount, date, reference and party name; confirm every allocation.',
        ),
      ),
      BankMetricGrid([
        BankMetric(
          label: 'Statement closing',
          value: _money(totals['statement_closing_balance']),
          icon: Icons.account_balance_wallet_outlined,
        ),
        BankMetric(
          label: 'Ledger closing',
          value: _money(totals['ledger_closing_balance']),
          icon: Icons.description_outlined,
        ),
        BankMetric(label: 'Difference', value: _money(totals['difference']), icon: Icons.south_west_rounded),
        BankMetric(label: 'Unmatched', value: '${totals['unmatched'] ?? 0}', icon: Icons.search_rounded),
      ]),
      BankPanel(
        title: 'Reconciliation history',
        note:
            'Save a dated review of the current statement and ledger balances. Reviews with a difference or unmatched lines need follow-up.',
        children: [
          if (canWrite)
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                onPressed: usable ? () => _review(totals) : null,
                child: Text('Save review through $asOf'),
              ),
            ),
          if (canWrite) const SizedBox(height: 14),
          if (data.reviews.isEmpty)
            const Text('No saved reviews for this account.', style: Apex.lead)
          else
            for (final review in data.reviews)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${inventoryText(review['as_of'])} · ${review['status'] == 'balanced' ? 'Balanced' : 'Needs review'}',
                      style: Apex.strong,
                    ),
                    Text(
                      'Statement ${_money(review['statement_closing_balance'])} · Ledger ${_money(review['ledger_closing_balance'])} · Difference ${_money(review['difference'])} · ${review['unmatched'] ?? 0} unmatched${inventoryText(review['note']).isEmpty ? '' : ' · ${inventoryText(review['note'])}'}',
                      style: Apex.note,
                    ),
                  ],
                ),
              ),
        ],
      ),
      BankPanel(
        title: '$_bankName · statement lines',
        note: '${data.statement.length} imported lines · allocate a statement amount across one or more posted payments',
        flush: true,
        children: [
          if (data.statement.isEmpty)
            const ApexEmptyState(icon: Icons.receipt_long_outlined, title: 'No statement imported for this account')
          else
            ApexTable(
              columns: const [
                ApexColumn('Date', width: 120),
                ApexColumn('Description', flex: 2),
                ApexColumn('Amount', flex: 1, alignEnd: true),
                ApexColumn('Match', flex: 2.4),
              ],
              rowCount: data.statement.length,
              cell: (row, column) {
                final line = data.statement[row];
                return switch (column) {
                  0 => Text(apexDate(inventoryText(line['date'])), style: _cell),
                  1 => _lineText(line),
                  2 => Text(_money(line['amount']), style: Apex.strong),
                  _ => _matchCell(line, usable),
                };
              },
              card: (row) {
                final line = data.statement[row];
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: _lineText(line)),
                        const SizedBox(width: 10),
                        Text(_money(line['amount']), style: Apex.strong),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(apexDate(inventoryText(line['date'])), style: Apex.small),
                    const SizedBox(height: 8),
                    _matchCell(line, usable),
                  ],
                );
              },
            ),
        ],
      ),
    ];
  }

  Widget _lineText(Json line) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(inventoryText(line['description']), style: Apex.strong),
      if (inventoryText(line['reference']).isNotEmpty) Text(inventoryText(line['reference']), style: Apex.small),
    ],
  );

  Widget _matchCell(Json line, bool usable) {
    final canWrite = _workspace.company.canWrite;
    final remaining = signedMoney(inventoryText(line['remaining_amount'])) ?? BigInt.zero;
    if (inventoryText(line['matched_record_id']).isNotEmpty) {
      return ApexLink(
        'Matched · Unmatch',
        strong: true,
        onTap: usable && canWrite ? () => _removeMatch(inventoryText(line['id']), allocation: false) : null,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          remaining == BigInt.zero ? 'Fully matched' : '${_money(line['remaining_amount'])} remaining',
          style: Apex.strong,
        ),
        for (final allocation in inventoryRows(line['allocations']))
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Wrap(
              spacing: 10,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  '${inventoryText(allocation['number'])} · ${inventoryText(allocation['name'])} · ${_money(allocation['amount'])}',
                  style: Apex.note,
                ),
                if (canWrite)
                  Tooltip(
                    message: 'Remove allocation',
                    child: ApexLink(
                      'Remove',
                      onTap: usable
                          ? () => _removeMatch(inventoryText(allocation['id']), allocation: true)
                          : null,
                    ),
                  ),
              ],
            ),
          ),
        if (canWrite && remaining > BigInt.zero)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: OutlinedButton(
              onPressed: usable ? () => _allocate(line) : null,
              child: const Text('Match transaction'),
            ),
          ),
      ],
    );
  }
}
