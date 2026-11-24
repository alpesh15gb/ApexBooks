import 'dart:async';
import 'dart:math' as math;

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import '../books/register_query.dart';

/// Dashboard periods, as offered by the web app.
enum _Period {
  financialYear('This financial year'),
  month('This month'),
  last30('Last 30 days');

  const _Period(this.label);
  final String label;

  (String, String) get dates {
    final now = businessToday();
    final start = switch (this) {
      _Period.month => DateTime.utc(now.year, now.month, 1),
      _Period.last30 => DateTime.utc(now.year, now.month, now.day - 29),
      _Period.financialYear => DateTime.utc(now.month < 4 ? now.year - 1 : now.year, 4, 1),
    };
    return (start.toIso8601String().substring(0, 10), businessDate());
  }
}

const _documentNames = {
  'sales_invoice': 'Sales invoice',
  'purchase_bill': 'Purchase bill',
  'payment_in': 'Payment received',
  'payment_out': 'Payment made',
  'expense': 'Expense',
  'estimate': 'Estimate',
  'sales_order': 'Sales order',
  'proforma': 'Proforma invoice',
  'credit_note': 'Credit note',
  'debit_note': 'Debit note',
  'pos': 'POS sale',
  'purchase_order': 'Purchase order',
  'bank_transfer': 'Bank transfer',
};

/// The dashboard's view of one record.
class _Entry {
  _Entry(this.json);
  final Json json;

  String get id => '${json['id'] ?? ''}';
  String get kind => '${json['kind'] ?? ''}';
  String get name => '${json['name'] ?? ''}';
  String get number => '${json['number'] ?? ''}';
  String get date => '${json['date'] ?? ''}';
  Json get data => json['data'] is Json ? json['data'] as Json : const {};
  String get createdAt => '${data['created_at'] ?? ''}';
  num get amount => apexNumber(json['amount']) ?? 0;
  num get outstanding => apexNumber(json['outstanding']) ?? 0;
  bool get posted => json['posted'] == true;
  bool get cancelled => json['cancelled'] == true || data['cancelled'] == true;
  bool get converted => '${json['converted_to'] ?? ''}'.isNotEmpty;
  bool get isMaster => const {'party', 'item', 'bank_account'}.contains(kind);
  bool get isPurchase => const {'purchase_bill', 'payment_out', 'expense'}.contains(kind);

  static int newestFirst(_Entry a, _Entry b) {
    final byDate = b.date.compareTo(a.date);
    if (byDate != 0) return byDate;
    final byCreated = b.createdAt.compareTo(a.createdAt);
    return byCreated != 0 ? byCreated : b.id.compareTo(a.id);
  }

  (String, ApexBadgeTone) get status {
    if (cancelled) return ('Cancelled', ApexBadgeTone.cancelled);
    if (converted) return ('Converted', ApexBadgeTone.converted);
    if (posted) return ('Posted', ApexBadgeTone.posted);
    const quotes = {'estimate', 'sales_order', 'proforma', 'purchase_order'};
    return (quotes.contains(kind) ? 'Draft' : 'Unposted', ApexBadgeTone.draft);
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    required this.workspace,
    required this.revision,
    required this.openCheckout,
    required this.openPage,
    required this.openReport,
    required this.openRegister,
    required this.openBank,
    required this.newEntry,
    required this.verifyPassword,
    super.key,
  });

  final WorkspaceContext workspace;
  final int revision;
  final VoidCallback openCheckout;
  final void Function(BooksReport report, DateTimeRange range) openReport;
  final void Function(String kind, String tab) openRegister;
  final ValueChanged<String?> openBank;

  /// Opens a workspace page by its web key, such as 'purchase_order' or 'day_book'.
  final ValueChanged<String> openPage;

  /// Starts a new document of a type, or null when the user cannot post.
  final ValueChanged<String>? newEntry;
  final Future<void> Function(String) verifyPassword;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  // Kept for the whole session so hidden amounts stay hidden when returning to the dashboard.
  static final _hiddenCompanies = <String>{};

  _Period _period = _Period.financialYear;
  Json? _summary;
  Json? _financial;
  List<Json>? _banks;
  Json? _unmatched;
  List<_Entry>? _records;
  String? _error;
  int _generation = 0;
  int _recordsGeneration = 0;
  bool _recordsFailed = false;
  bool _chartData = false;

  bool get _hidden => _hiddenCompanies.contains(widget.workspace.company.id);

  @override
  void initState() {
    super.initState();
    _load();
    _loadRecords();
  }

  @override
  void didUpdateWidget(covariant HomeScreen old) {
    super.didUpdateWidget(old);
    if (old.revision != widget.revision || old.workspace.company.id != widget.workspace.company.id) {
      _load();
      _loadRecords();
    }
  }

  Future<void> _load() async {
    final generation = ++_generation;
    final workspace = widget.workspace;
    final (from, to) = _period.dates;
    setState(() {
      _summary = null;
      _financial = null;
      _banks = null;
      _error = null;
    });
    Future<T?> read<T>(String path, [Map<String, String>? query]) async {
      try {
        final response = await workspace.api.get('${workspace.path}$path', query: query);
        return response is T ? response : throw const FormatException('Unexpected response');
      } catch (error) {
        if (mounted && generation == _generation) {
          setState(() => _error = error is ApexApiException ? error.message : 'Some figures could not load.');
        }
        return null;
      }
    }

    final query = {'from_date': from, 'to_date': to};
    final results = await Future.wait([
      read<Json>('/reports/summary', query),
      read<Json>('/reports/financial', query),
      read<List<dynamic>>('/bank-accounts'),
    ]);
    if (!mounted || generation != _generation) return;
    setState(() {
      _summary = results[0] as Json?;
      _financial = results[1] as Json?;
      _banks = (results[2] as List<dynamic>?)?.whereType<Json>().toList();
    });
    try {
      final counts = await workspace.api.get(
        '${workspace.path}/bank-reconciliation/unmatched',
        query: {'as_of': to},
      );
      if (mounted && generation == _generation) {
        setState(() => _unmatched = counts is Json ? counts : null);
      }
    } catch (_) {
      if (mounted && generation == _generation) setState(() => _unmatched = null);
    }
  }

  /// Every record, newest first, for the chart, work queue and recent activity.
  Future<void> _loadRecords() async {
    final generation = ++_recordsGeneration;
    final workspace = widget.workspace;
    final rows = <String, Json>{};
    try {
      const pageSize = 500;
      for (var offset = 0; ; offset += pageSize) {
        final page = await workspace.api.get(
          '${workspace.path}/records',
          query: {'compact': 'true', 'limit': '$pageSize', 'offset': '$offset'},
        );
        final list = page is List ? page.whereType<Json>().toList() : <Json>[];
        final before = rows.length;
        for (final row in list) {
          rows['${row['id']}'] = row;
        }
        if (list.length < pageSize || rows.length == before) break;
      }
      if (!mounted || generation != _recordsGeneration) return;
      setState(() {
        _records = rows.values.map(_Entry.new).toList()..sort(_Entry.newestFirst);
        _recordsFailed = false;
      });
    } catch (_) {
      if (!mounted || generation != _recordsGeneration) return;
      setState(() {
        _records = null;
        _recordsFailed = true;
      });
    }
  }

  String _show(num? value) => _hidden && value != null ? '₹ ••••••' : apexMoney(value);

  Future<void> _toggleAmounts() async {
    final company = widget.workspace.company.id;
    if (!_hidden) {
      setState(() => _hiddenCompanies.add(company));
      return;
    }
    final verified = await showDialog<bool>(
      context: context,
      builder: (context) => _RevealAmounts(verify: widget.verifyPassword),
    );
    if (verified == true && mounted) setState(() => _hiddenCompanies.remove(company));
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final width = limits.maxWidth;
      final phone = width < 700;
      final wide = width >= 1100;
      final gutter = phone ? 16.0 : 28.0;
      final company = widget.workspace.company;
      final (start, end) = _period.dates;
      final canWrite = widget.newEntry != null;
      final records = _records;
      final ready = records != null;
      return SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(gutter, phone ? 20 : 30, gutter, 40),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1540),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ApexPageHeading(
                  'Business overview',
                  subtitle: company.displayName() + (company.canWrite ? '' : ' · View only'),
                  compact: phone,
                  actions: [
                    OutlinedButton.icon(
                      onPressed: _toggleAmounts,
                      icon: Icon(_hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined, size: 17),
                      label: Text(_hidden ? 'Show amounts' : 'Hide amounts'),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                _financialHeading(start, end, phone),
                const SizedBox(height: 12),
                if (_error != null) ...[
                  _ErrorBanner(message: _error!, retry: _load),
                  const SizedBox(height: 12),
                ],
                _metrics(start, end, company.taxMode),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    if (canWrite) ...[
                      FilledButton.icon(
                        onPressed: () => widget.newEntry!('sales_invoice'),
                        icon: const Icon(Icons.add, size: 17),
                        label: const Text('New invoice'),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => widget.newEntry!('payment_in'),
                        icon: const Icon(Icons.south_west_rounded, size: 17),
                        label: const Text('Record receipt'),
                      ),
                      OutlinedButton.icon(
                        onPressed: () => widget.newEntry!('expense'),
                        icon: const Icon(Icons.account_balance_wallet_outlined, size: 17),
                        label: const Text('Record expense'),
                      ),
                    ],
                    OutlinedButton.icon(
                      onPressed: widget.openCheckout,
                      icon: const Icon(Icons.point_of_sale_outlined, size: 17),
                      label: const Text('Open checkout'),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _workQueue(records),
                const SizedBox(height: 16),
                _pair(
                  wide: wide,
                  flex: (5, 3),
                  first: ApexPanel(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(23, 22, 23, 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          ApexPanelHeading(
                            'Sales & purchases',
                            note: 'Your trading activity for the selected period.',
                            trailing: TextButton(
                              onPressed: () => widget.openReport(
                                BooksReport.statements,
                                _range(start, end),
                              ),
                              child: const Text('Profit & loss'),
                            ),
                          ),
                          const SizedBox(height: 18),
                          if (_recordsFailed)
                            TextButton.icon(
                              onPressed: _loadRecords,
                              icon: const Icon(Icons.refresh),
                              label: const Text('Retry loading transactions'),
                            )
                          else if (!ready)
                            const _ChartMessage(icon: Icons.hourglass_empty_rounded, title: 'Loading transactions…')
                          else if (_hidden)
                            const _ChartMessage(
                              icon: Icons.visibility_off_outlined,
                              title: 'Chart hidden',
                              note: 'Show amounts to see sales and purchases.',
                            )
                          else
                            _SalesChart(
                              series: _series(records, start, end),
                              showData: _chartData,
                              toggleData: () => setState(() => _chartData = !_chartData),
                            ),
                        ],
                      ),
                    ),
                  ),
                  second: _bankCard(),
                ),
                const SizedBox(height: 16),
                _recent(records, phone),
                if (ready) ...[
                  const SizedBox(height: 18),
                  _SetupGuide(workspace: widget.workspace, records: records, newEntry: widget.newEntry, openPage: widget.openPage),
                ],
              ],
            ),
          ),
        ),
      );
    },
  );

  /// Two panels side by side on wide screens, stacked otherwise.
  Widget _pair({
    required bool wide,
    required (int, int) flex,
    required Widget first,
    required Widget second,
  }) {
    if (!wide) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [first, const SizedBox(height: 14), second],
      );
    }
    final row = Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(flex: flex.$1, child: first),
        const SizedBox(width: 14),
        Expanded(flex: flex.$2, child: second),
      ],
    );
    return IntrinsicHeight(child: row);
  }

  Widget _financialHeading(String start, String end, bool phone) {
    final picker = _PeriodPicker(
      value: _period,
      onChanged: (period) {
        setState(() => _period = period);
        _load();
      },
    );
    final heading = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Financial summary', style: Apex.sectionTitle),
        const SizedBox(height: 4),
        Text('${apexDate(start)} – ${apexDate(end)}', style: Apex.note),
      ],
    );
    return phone
        ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [heading, const SizedBox(height: 10), picker])
        : Row(crossAxisAlignment: CrossAxisAlignment.end, children: [Expanded(child: heading), picker]);
  }

  DateTimeRange _range(String from, String to) =>
      DateTimeRange(start: DateTime.parse(from), end: DateTime.parse(to));

  List<Json>? get _cashAccounts {
    final financial = _financial;
    final banks = _banks;
    if (financial == null || banks == null) return null;
    final codes = {
      'SYS-CASH',
      'SYS-BANK',
      for (final bank in banks) bank['ledger_code'],
    };
    return [
      for (final account
          in (financial['accounts'] as List? ?? const []).whereType<Json>())
        if (codes.contains(account['code'])) account,
    ];
  }

  Widget _metrics(String start, String end, String taxMode) {
    final accounts = _cashAccounts;
    final total = accounts?.fold<num>(
      0,
      (sum, account) => sum + (apexNumber(account['closing_balance']) ?? 0),
    );
    final asOf = 'As of ${apexDate(end)}';
    void openAgeing() =>
        widget.openReport(BooksReport.ageing, _range(end, end));
    return ApexStatGrid([
      _Metric(
        label: 'Cash & bank',
        value: _show(total),
        note: asOf,
        icon: Icons.account_balance_outlined,
        tone: _MetricTone.green,
        open: () => widget.openBank(null),
      ),
      _Metric(
        label: 'To collect',
        value: _show(apexNumber(_summary?['receivables'])),
        note: asOf,
        icon: Icons.south_west_rounded,
        tone: _MetricTone.amber,
        open: openAgeing,
      ),
      _Metric(
        label: 'To pay',
        value: _show(apexNumber(_summary?['payables'])),
        note: asOf,
        icon: Icons.account_balance_wallet_outlined,
        tone: _MetricTone.purple,
        open: openAgeing,
      ),
      _Metric(
        label: 'Net sales',
        value: _show(apexNumber(_summary?['sales'])),
        note: taxMode == 'regular'
            ? 'Selected period · incl. GST'
            : 'Selected period',
        icon: Icons.trending_up_rounded,
        tone: _MetricTone.blue,
        open: () => widget.openReport(BooksReport.sales, _range(start, end)),
      ),
    ], wideBreakpoint: 720);
  }

  List<_Month> _series(List<_Entry> records, String start, String end) {
    final months = <_Month>[];
    var cursor = DateTime.utc(int.parse(start.substring(0, 4)), int.parse(start.substring(5, 7)));
    final last = end.substring(0, 7);
    while (months.length < 13) {
      final key = '${cursor.year}-${cursor.month.toString().padLeft(2, '0')}';
      if (key.compareTo(last) > 0) break;
      months.add(_Month(key, apexMonth(cursor.month)));
      cursor = DateTime.utc(cursor.year, cursor.month + 1);
    }
    for (final record in records) {
      if (!record.posted || record.cancelled || record.date.compareTo(start) < 0 || record.date.compareTo(end) > 0) continue;
      final month = months.where((row) => record.date.startsWith(row.key)).firstOrNull;
      if (month == null) continue;
      switch (record.kind) {
        case 'sales_invoice' || 'pos':
          month.sales += record.amount;
        case 'credit_note':
          month.sales -= record.amount;
        case 'purchase_bill':
          month.purchases += record.amount;
        case 'debit_note':
          month.purchases -= record.amount;
      }
    }
    return months;
  }

  Widget _bankCard() {
    const text = Color(0xff16392a);
    const soft = Color(0xff3e614e);
    final accounts = _cashAccounts ?? const <Json>[];
    final ready = _cashAccounts != null;
    return ApexPanel(
      color: const Color(0xfff0f7f3),
      borderColor: const Color(0xffd4e4da),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(23, 22, 23, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ApexPanelHeading(
              'Cash movement',
              note: 'Selected period · excludes account transfers',
              titleColor: text,
              noteColor: soft,
              trailing: const Icon(Icons.account_balance_outlined, size: 20, color: Color(0xff286349)),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                for (final (icon, label, key) in const [
                  (Icons.south_west_rounded, 'Money in', 'receipts'),
                  (Icons.north_east_rounded, 'Money out', 'payments'),
                ])
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(icon, size: 14, color: soft),
                            const SizedBox(width: 5),
                            Text(label, style: const TextStyle(fontSize: 11, color: soft)),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _summary == null ? '—' : _show(apexNumber(_summary![key])),
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, letterSpacing: -.36, color: text),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            const Divider(color: Color(0xffcbded1)),
            if (accounts.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 14),
                child: Text(
                  ready ? 'Add an account to start tracking your money.' : _error != null ? 'Balances are unavailable. Please retry.' : 'Loading balances…',
                  style: const TextStyle(fontSize: 12, color: soft),
                ),
              )
            else
              for (final account in accounts.take(3))
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 7),
                  child: Row(
                    children: [
                      ApexIconTile(
                        account['code'] == 'SYS-CASH' ? Icons.payments_outlined : Icons.account_balance_outlined,
                        background: const Color(0xffe2efe7),
                        foreground: soft,
                        size: 29,
                        iconSize: 16,
                      ),
                      const SizedBox(width: 9),
                      Expanded(
                        child: Text('${account['name']}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11, color: Color(0xff3c5547))),
                      ),
                      Text(
                        _show(apexNumber(account['closing_balance'])),
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: text),
                      ),
                    ],
                  ),
                ),
            const Divider(color: Color(0xffcbded1)),
            InkWell(
              onTap: () => widget.openBank(null),
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 10),
                child: Row(
                  children: [
                    Expanded(
                      child: Text('View accounts & reconcile', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xff126444))),
                    ),
                    Icon(Icons.north_east_rounded, size: 15, color: Color(0xff126444)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _workQueue(List<_Entry>? records) {
    final entries = records?.map((row) => BooksRecord(row.json));
    final today = businessDate();
    final overdue = entries?.where(
      (row) => row.kind == 'sales_invoice' && registerOverdue(row, today),
    );
    final held = entries?.where(registerUnallocated);
    num? sum(Iterable<BooksRecord>? rows, String key) => rows?.fold<num>(
      0,
      (total, row) => total + (apexNumber(row.json[key]) ?? 0),
    );
    final banks = [
      for (final bank in _banks ?? const <Json>[])
        if ((_unmatched?['${bank['id']}'] as num? ?? 0) > 0) bank,
    ];
    return ApexPanel(
      padding: const EdgeInsets.fromLTRB(16, 13, 16, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const ApexPanelHeading('Needs attention'),
          const SizedBox(height: 5),
          _queueRow(
            'Overdue invoices',
            overdue?.length,
            sum(overdue, 'outstanding'),
            () => widget.openRegister('sales_invoice', 'overdue'),
          ),
          const Divider(height: 1, color: Apex.lineSoft),
          _queueRow(
            'Unallocated receipts',
            held?.length,
            sum(held, 'amount'),
            () => widget.openRegister('payment_in', 'unallocated'),
          ),
          if (banks.isEmpty) ...[
            const Divider(height: 1, color: Apex.lineSoft),
            _queueRow(
              'Unmatched bank lines',
              _unmatched == null || _banks == null ? null : 0,
              null,
              () => widget.openBank(null),
            ),
          ],
          for (final bank in banks) ...[
            const Divider(height: 1, color: Apex.lineSoft),
            _queueRow(
              'Unmatched bank lines · ${bank['name']}',
              (_unmatched!['${bank['id']}'] as num).toInt(),
              null,
              () => widget.openBank('${bank['id']}'),
            ),
          ],
        ],
      ),
    );
  }

  Widget _queueRow(
    String label,
    int? count,
    num? amount,
    VoidCallback open,
  ) => Material(
    type: MaterialType.transparency,
    child: InkWell(
      onTap: open,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            Container(
              constraints: const BoxConstraints(minWidth: 28),
              alignment: Alignment.center,
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              decoration: BoxDecoration(
                color: (count ?? 0) > 0 ? const Color(0xfffff3d8) : Apex.tint,
                borderRadius: BorderRadius.circular(5),
              ),
              child: Text(count == null ? '—' : '$count', style: Apex.small),
            ),
            const SizedBox(width: 10),
            Expanded(child: Text(label, style: Apex.strong)),
            if (amount != null)
              Padding(
                padding: const EdgeInsets.only(left: 8),
                child: Text(_show(amount), style: Apex.small),
              ),
            const SizedBox(width: 8),
            const Icon(
              Icons.chevron_right_rounded,
              size: 18,
              color: Apex.muted,
            ),
          ],
        ),
      ),
    ),
  );

  Widget _recent(List<_Entry>? records, bool phone) {
    final rows = (records ?? const <_Entry>[]).where((row) => !row.isMaster).take(6).toList();
    void open(_Entry row) => widget.openPage(row.kind);
    return ApexPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(25, 22, 23, 16),
            child: ApexPanelHeading(
              'Recent transactions',
              note: phone ? null : 'Your latest business activity, in one place.',
              trailing: TextButton.icon(
                onPressed: () => widget.openPage('day_book'),
                iconAlignment: IconAlignment.end,
                icon: const Icon(Icons.north_east_rounded, size: 15),
                label: const Text('View day book'),
              ),
            ),
          ),
          if (rows.isEmpty)
            _ChartMessage(
              icon: Icons.description_outlined,
              title: records == null ? 'Loading transactions…' : 'Your books start here',
              note: records == null ? 'Your latest activity will appear here.' : 'Create your first invoice or add a purchase bill.',
            )
          else if (phone)
            for (final row in rows) ...[
              const Divider(color: Apex.lineSoft),
              InkWell(
                onTap: () => open(row),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(18, 12, 14, 12),
                  child: Row(
                    children: [
                      _RecentIcon(purchase: row.isPurchase),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(row.name.isEmpty ? 'Untitled' : row.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xff486574))),
                            const SizedBox(height: 3),
                            Text('${_documentNames[row.kind] ?? row.kind} · ${row.number.isEmpty ? '—' : row.number} · ${apexDate(row.date)}', maxLines: 1, overflow: TextOverflow.ellipsis, style: Apex.small),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(_show(row.amount), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Apex.inkSoft)),
                          const SizedBox(height: 4),
                          ApexStatusBadge(row.status.$1, tone: row.status.$2),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ]
          else
            _RecentTable(rows: rows, amount: _show, open: open),
        ],
      ),
    );
  }
}

class _Month {
  _Month(this.key, this.label);
  final String key;
  final String label;
  num sales = 0;
  num purchases = 0;
}

enum _MetricTone { green, blue, amber, purple }

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    required this.note,
    required this.icon,
    required this.tone,
    required this.open,
  });

  final String label;
  final String value;
  final String note;
  final IconData icon;
  final _MetricTone tone;
  final VoidCallback open;

  @override
  Widget build(BuildContext context) {
    final green = tone == _MetricTone.green;
    final (iconBackground, iconColor) = switch (tone) {
      _MetricTone.green => (const Color(0xffd4eddd), Apex.greenText),
      _MetricTone.blue => (const Color(0xffe7f3fb), const Color(0xff0077b7)),
      _MetricTone.amber => (const Color(0xfffff4d8), const Color(0xff98620b)),
      _MetricTone.purple => (const Color(0xfff3edf8), const Color(0xff765499)),
    };
    return Semantics(
      container: true,
      button: true,
      onTap: open,
      label: '$label, $value, $note',
      child: ExcludeSemantics(
        child: ApexPanel(
          color: green ? Apex.mintSoft : Colors.white,
          borderColor: green ? Apex.mintLine : Apex.line,
          child: Material(
            type: MaterialType.transparency,
            child: InkWell(
              onTap: open,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(13, 11, 13, 11),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            label,
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: Color(0xff42554b),
                            ),
                          ),
                        ),
                        ApexIconTile(
                          icon,
                          background: iconBackground,
                          foreground: iconColor,
                          size: 28,
                          iconSize: 16,
                          circle: true,
                        ),
                      ],
                    ),
                    const SizedBox(height: 7),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(
                        value,
                        style: Apex.money.copyWith(
                          color: green ? Apex.greenDark : Apex.ink,
                        ),
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      note,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 11, color: Apex.muted),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PeriodPicker extends StatelessWidget {
  const _PeriodPicker({required this.value, required this.onChanged});

  final _Period value;
  final ValueChanged<_Period> onChanged;

  @override
  Widget build(BuildContext context) => PopupMenuButton<_Period>(
    tooltip: 'Dashboard period',
    initialValue: value,
    position: PopupMenuPosition.under,
    onSelected: onChanged,
    itemBuilder: (context) => [
      for (final period in _Period.values) CheckedPopupMenuItem(value: period, checked: period == value, child: Text(period.label)),
    ],
    child: Container(
      height: 44,
      padding: const EdgeInsets.symmetric(horizontal: 13),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(Apex.radiusControl),
        border: Border.all(color: Apex.lineStrong),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.calendar_month_outlined, size: 16, color: Color(0xff424c59)),
          const SizedBox(width: 9),
          Text(value.label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: Color(0xff424c59))),
          const SizedBox(width: 4),
          const Icon(Icons.expand_more_rounded, size: 17, color: Color(0xff424c59)),
        ],
      ),
    ),
  );
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, required this.retry});
  final String message;
  final VoidCallback retry;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(color: const Color(0xfffcf1ef), borderRadius: BorderRadius.circular(8)),
    child: Padding(
      padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
      child: Row(
        children: [
          Expanded(
            child: Text('Some financial figures are unavailable. $message', style: const TextStyle(fontSize: 12, color: Color(0xffa4413d))),
          ),
          TextButton.icon(onPressed: retry, icon: const Icon(Icons.refresh_rounded, size: 15), label: const Text('Retry')),
        ],
      ),
    ),
  );
}

class _ChartMessage extends StatelessWidget {
  const _ChartMessage({required this.icon, required this.title, this.note});
  final IconData icon;
  final String title;
  final String? note;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 46, horizontal: 20),
    child: Column(
      children: [
        Icon(icon, size: 30, color: const Color(0xff8693a9)),
        const SizedBox(height: 10),
        Text(title, textAlign: TextAlign.center, style: Apex.strong),
        if (note != null) ...[
          const SizedBox(height: 4),
          Text(note!, textAlign: TextAlign.center, style: Apex.small),
        ],
      ],
    ),
  );
}

class _SalesChart extends StatelessWidget {
  const _SalesChart({required this.series, required this.showData, required this.toggleData});

  final List<_Month> series;
  final bool showData;
  final VoidCallback toggleData;

  static const sales = Color(0xff218253);
  static const purchases = Color(0xff82a8b9);

  @override
  Widget build(BuildContext context) {
    final empty = series.every((row) => row.sales == 0 && row.purchases == 0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: 16,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (final (color, label) in const [(sales, 'Net sales'), (purchases, 'Net purchases')])
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(width: 7, height: 7, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
                  const SizedBox(width: 6),
                  Text(label, style: const TextStyle(fontSize: 12, color: Color(0xff847061))),
                ],
              ),
          ],
        ),
        const SizedBox(height: 14),
        if (empty)
          const _ChartMessage(
            icon: Icons.bar_chart_rounded,
            title: 'No net movement in this period',
            note: 'Posted sales and purchases will appear here.',
          )
        else
          Semantics(
            label: 'Monthly net sales and purchases from posted documents',
            child: SizedBox(height: 200, child: CustomPaint(painter: _ChartPainter(series), size: Size.infinite)),
          ),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: toggleData,
            icon: Icon(showData ? Icons.arrow_drop_down_rounded : Icons.arrow_right_rounded, size: 18),
            label: Text(showData ? 'Hide chart data' : 'View chart data', style: const TextStyle(fontWeight: FontWeight.w400, fontSize: 12)),
          ),
        ),
        if (showData)
          Table(
            columnWidths: const {0: FlexColumnWidth(1.2), 1: FlexColumnWidth(), 2: FlexColumnWidth()},
            border: const TableBorder(horizontalInside: BorderSide(color: Apex.lineSoft)),
            children: [
              TableRow(
                decoration: const BoxDecoration(color: Apex.tableHead),
                children: [for (final title in ['MONTH', 'NET SALES', 'NET PURCHASES']) _cell(title, header: true)],
              ),
              for (final row in series)
                TableRow(children: [_cell(row.label), _cell(apexMoney(row.sales)), _cell(apexMoney(row.purchases))]),
            ],
          ),
      ],
    );
  }

  Widget _cell(String text, {bool header = false}) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
    child: Text(text, style: header ? Apex.tableHeader : const TextStyle(fontSize: 12, color: Apex.muted)),
  );
}

class _ChartPainter extends CustomPainter {
  _ChartPainter(this.series);
  final List<_Month> series;

  @override
  void paint(Canvas canvas, Size size) {
    final values = [for (final row in series) ...[row.sales, row.purchases]];
    final high = values.fold<num>(0, math.max);
    final low = values.fold<num>(0, math.min);
    final span = (high - low) == 0 ? 1 : high - low;
    double y(num value) => 159 - (value - low) / span * 128;
    final base = y(0);
    const left = 50.0;
    final right = size.width - 10;
    final dash = Paint()
      ..color = const Color(0xffe7eaf0)
      ..strokeWidth = 1;
    for (final value in {high, (high + low) / 2, low}) {
      final level = y(value);
      for (var x = left; x < right; x += 9) {
        canvas.drawLine(Offset(x, level), Offset(math.min(x + 4, right), level), dash);
      }
      _text(canvas, apexCompact(value), Offset(39, level), align: TextAlign.right, color: const Color(0xff778591), size: 11);
    }
    canvas.drawLine(Offset(left, base), Offset(right, base), Paint()..color = const Color(0xffbac1cd));
    final space = (size.width - 66) / math.max(series.length, 1);
    final bar = math.min(21.0, space * .27);
    for (final (index, row) in series.indexed) {
      final center = 53 + index * space + space / 2;
      for (final (offset, value, color) in [
        (-bar - 3, row.sales, _SalesChart.sales),
        (3.0, row.purchases, _SalesChart.purchases),
      ]) {
        final top = math.min(base, y(value));
        final height = (base - y(value)).abs();
        if (height < .5) continue;
        canvas.drawRRect(
          RRect.fromRectAndRadius(Rect.fromLTWH(center + offset, top, bar, height), const Radius.circular(4)),
          Paint()..color = color,
        );
      }
      _text(canvas, row.label, Offset(center, 186), align: TextAlign.center, color: const Color(0xff71818c), size: 12);
    }
  }

  void _text(Canvas canvas, String text, Offset at, {required TextAlign align, required Color color, required double size}) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: TextStyle(fontFamily: Apex.body, fontSize: size, color: color)),
      textDirection: TextDirection.ltr,
      textAlign: align,
    )..layout();
    final dx = switch (align) {
      TextAlign.right => at.dx - painter.width,
      TextAlign.center => at.dx - painter.width / 2,
      _ => at.dx,
    };
    painter.paint(canvas, Offset(dx, at.dy - painter.height / 2));
  }

  @override
  bool shouldRepaint(covariant _ChartPainter old) => true;
}

class _RecentIcon extends StatelessWidget {
  const _RecentIcon({required this.purchase});
  final bool purchase;

  @override
  Widget build(BuildContext context) => ApexIconTile(
    Icons.description_outlined,
    background: purchase ? const Color(0xffedf5fa) : const Color(0xfff0f4f9),
    foreground: purchase ? const Color(0xff3c6c8a) : const Color(0xff576c89),
    size: 32,
    iconSize: 17,
  );
}

class _RecentTable extends StatelessWidget {
  const _RecentTable({required this.rows, required this.amount, required this.open});

  final List<_Entry> rows;
  final String Function(num) amount;
  final ValueChanged<_Entry> open;

  @override
  Widget build(BuildContext context) {
    const head = Apex.tableHeader;
    Widget header(String text, {bool right = false}) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
      child: Text(text, textAlign: right ? TextAlign.right : TextAlign.left, style: head),
    );
    return Table(
      columnWidths: const {
        0: FlexColumnWidth(2.3),
        1: FlexColumnWidth(1.3),
        2: FlexColumnWidth(1),
        3: FlexColumnWidth(1),
        4: FlexColumnWidth(1.1),
        5: FixedColumnWidth(60),
      },
      defaultVerticalAlignment: TableCellVerticalAlignment.middle,
      border: const TableBorder(horizontalInside: BorderSide(color: Apex.lineSoft)),
      children: [
        TableRow(
          decoration: const BoxDecoration(
            color: Apex.tableHead,
            border: Border(top: BorderSide(color: Apex.lineStrong), bottom: BorderSide(color: Apex.lineStrong)),
          ),
          children: [header('TRANSACTION'), header('REFERENCE'), header('DATE'), header('STATUS'), header('AMOUNT', right: true), const SizedBox()],
        ),
        for (final row in rows)
          TableRow(
            children: [
              _tap(
                row,
                Row(
                  children: [
                    _RecentIcon(purchase: row.isPurchase),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(row.name.isEmpty ? 'Untitled' : row.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xff486574))),
                          const SizedBox(height: 4),
                          Text(_documentNames[row.kind] ?? row.kind.replaceAll('_', ' '), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: Apex.muted)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              _tap(row, Text(row.number.isEmpty ? '—' : row.number, style: const TextStyle(fontSize: 12, color: Color(0xff607785)))),
              _tap(row, Text(apexDate(row.date), style: const TextStyle(fontSize: 12, color: Color(0xff607785)))),
              _tap(row, Align(alignment: Alignment.centerLeft, child: ApexStatusBadge(row.status.$1, tone: row.status.$2))),
              _tap(row, Text(amount(row.amount), textAlign: TextAlign.right, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Apex.inkSoft))),
              Padding(
                padding: const EdgeInsets.only(right: 23),
                child: Align(
                  alignment: Alignment.centerRight,
                  child: Tooltip(
                    message: 'Open ${row.number.isEmpty ? row.name : row.number}',
                    child: InkWell(
                      onTap: () => open(row),
                      borderRadius: BorderRadius.circular(9),
                      child: Container(
                        width: 31,
                        height: 31,
                        decoration: BoxDecoration(
                          color: const Color(0xfff4f7fa),
                          borderRadius: BorderRadius.circular(9),
                          border: Border.all(color: const Color(0xffd9e2eb)),
                        ),
                        child: const Icon(Icons.chevron_right_rounded, size: 17, color: Apex.link),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
      ],
    );
  }

  Widget _tap(_Entry row, Widget child) => InkWell(
    onTap: () => open(row),
    child: Padding(padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 15), child: child),
  );
}

/// Getting-started steps, as on the web dashboard. Dismissed for the session.
class _SetupGuide extends StatefulWidget {
  const _SetupGuide({required this.workspace, required this.records, required this.newEntry, required this.openPage});

  final WorkspaceContext workspace;
  final List<_Entry> records;
  final ValueChanged<String>? newEntry;
  final ValueChanged<String> openPage;

  @override
  State<_SetupGuide> createState() => _SetupGuideState();
}

class _SetupGuideState extends State<_SetupGuide> {
  static final _dismissed = <String>{};
  Json? _branding;
  bool _expanded = false;

  @override
  void initState() {
    super.initState();
    unawaited(_loadBranding());
  }

  Future<void> _loadBranding() async {
    try {
      final value = await widget.workspace.api.get('${widget.workspace.path}/document-branding');
      if (mounted) setState(() => _branding = value is Json ? value : const {});
    } catch (_) {
      if (mounted) setState(() => _branding = const {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final company = widget.workspace.company;
    final branding = _branding;
    if (branding == null || _dismissed.contains(company.id)) return const SizedBox.shrink();
    final records = widget.records;
    final parties = records.where((row) => row.kind == 'party').length;
    final items = records.where((row) => row.kind == 'item').length;
    final invoices = records.where((row) => (row.kind == 'sales_invoice' || row.kind == 'pos') && row.posted && !row.cancelled).length;
    final registered = company.taxMode == 'regular' || company.taxMode == 'composition';
    final business = company.address.trim().isNotEmpty && (!registered || company.gstin.isNotEmpty);
    final payment = ['bank_name', 'account_number', 'upi_id'].any((key) => '${branding[key] ?? ''}'.isNotEmpty);
    String plural(int count, String one, String many) => '$count ${count == 1 ? one : many}';
    final steps = [
      (Icons.domain_rounded, 'Business details', business ? 'Your address appears on your documents.' : 'Add your address so it prints on invoices.', business, business ? 'Review' : 'Add details', null, 'settings'),
      (Icons.account_balance_outlined, 'Bank & UPI on invoices', payment ? 'Bank / UPI details print on invoices' : 'Add bank account and UPI ID so customers can pay you.', payment, payment ? 'Review' : 'Add bank & UPI', null, 'settings'),
      (Icons.people_alt_outlined, 'Customers & suppliers', parties > 0 ? '${plural(parties, 'party', 'parties')} ready' : 'Save contacts once, use them on every document.', parties > 0, parties > 0 ? 'View parties' : 'Open parties', null, 'parties'),
      (Icons.inventory_2_outlined, 'Items & services', items > 0 ? '${plural(items, 'item', 'items')} in your catalogue' : 'Set prices, tax and optional stock tracking.', items > 0, items > 0 ? 'View catalogue' : 'Open items', null, 'items'),
      (Icons.description_outlined, 'First invoice', invoices > 0 ? '${plural(invoices, 'invoice', 'invoices')} posted' : 'Bill a customer and share it on WhatsApp.', invoices > 0, invoices > 0 ? 'View invoices' : 'Create invoice', 'sales_invoice', 'sales_invoice'),
    ];
    final done = steps.where((step) => step.$4).length;
    if (done == steps.length) return const SizedBox.shrink();
    final canWrite = widget.newEntry != null;
    return ApexPanel(
      radius: 6,
      borderColor: Apex.lineStrong,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 14, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LayoutBuilder(
              builder: (context, limits) {
                final intro = Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const ApexIconTile(Icons.verified_user_outlined, background: Color(0xffedf7f0), foreground: Color(0xff176c3e), size: 43, iconSize: 23, radius: 13),
                    const SizedBox(width: 14),
                    Flexible(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('YOUR WORKSPACE · $done OF ${steps.length} READY', style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1.2, color: Color(0xff596472))),
                          const SizedBox(height: 6),
                          const Text('Make this workspace yours.', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: -.32, color: Apex.ink)),
                          const SizedBox(height: 4),
                          Text(canWrite ? 'Your details, your people, your way of doing business.' : 'An owner or editor can finish these steps.', style: const TextStyle(fontSize: 12, color: Apex.muted)),
                        ],
                      ),
                    ),
                  ],
                );
                final controls = Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 90,
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: LinearProgressIndicator(
                          value: done / steps.length,
                          minHeight: 5,
                          color: const Color(0xff2ca01c),
                          backgroundColor: const Color(0xfff8efe6),
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    OutlinedButton.icon(
                      onPressed: () => setState(() => _expanded = !_expanded),
                      iconAlignment: IconAlignment.end,
                      icon: Icon(_expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded, size: 17),
                      label: Text(_expanded ? 'Close setup' : 'Continue setup'),
                    ),
                    IconButton(
                      tooltip: 'Hide setup checklist',
                      onPressed: () => setState(() => _dismissed.add(company.id)),
                      icon: const Icon(Icons.close_rounded, size: 18),
                    ),
                  ],
                );
                return limits.maxWidth >= 860
                    ? Row(children: [Expanded(child: Align(alignment: Alignment.centerLeft, child: intro)), controls])
                    : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [intro, const SizedBox(height: 12), controls]);
              },
            ),
            if (_expanded) ...[
              const SizedBox(height: 16),
              LayoutBuilder(
                builder: (context, limits) {
                  final columns = limits.maxWidth >= 1000 ? 5 : limits.maxWidth >= 600 ? 3 : 1;
                  const gap = 10.0;
                  final width = (limits.maxWidth - gap * (columns - 1)) / columns;
                  return Wrap(
                    spacing: gap,
                    runSpacing: gap,
                    children: [
                      for (final (index, (icon, title, note, complete, label, create, page)) in steps.indexed)
                        SizedBox(
                          width: width,
                          child: ApexPanel(
                            radius: 9,
                            color: complete ? Apex.mintSoft : Colors.white,
                            borderColor: complete ? Apex.mintLine : Apex.line,
                            child: Padding(
                              padding: const EdgeInsets.all(14),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      ApexIconTile(complete ? Icons.check_rounded : icon, size: 32, iconSize: 18),
                                      const Spacer(),
                                      Text('0${index + 1}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Apex.muted)),
                                    ],
                                  ),
                                  const SizedBox(height: 10),
                                  Text(title, style: Apex.strong),
                                  const SizedBox(height: 4),
                                  Text(note, style: Apex.small),
                                  const SizedBox(height: 8),
                                  if (canWrite || complete)
                                    TextButton(
                                      style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: const Size(0, 30)),
                                      onPressed: () => !complete && create != null ? widget.newEntry!(create) : widget.openPage(page),
                                      child: Text(label),
                                    )
                                  else
                                    const Text('Owner or editor action', style: Apex.small),
                                ],
                              ),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RevealAmounts extends StatefulWidget {
  const _RevealAmounts({required this.verify});
  final Future<void> Function(String) verify;

  @override
  State<_RevealAmounts> createState() => _RevealAmountsState();
}

class _RevealAmountsState extends State<_RevealAmounts> {
  final _password = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    if (_busy || _password.text.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.verify(_password.text);
      if (mounted) Navigator.pop(context, true);
    } on ApexApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Show overview amounts'),
    content: TextField(
      controller: _password,
      autofocus: true,
      enabled: !_busy,
      obscureText: true,
      autocorrect: false,
      enableSuggestions: false,
      onSubmitted: (_) => _submit(),
      decoration: InputDecoration(
        labelText: 'Account password',
        errorText: _error,
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _busy ? null : _submit,
        child: Text(_busy ? 'Verifying…' : 'Show amounts'),
      ),
    ],
  );
}
