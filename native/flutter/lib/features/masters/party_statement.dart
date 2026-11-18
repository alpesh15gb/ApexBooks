import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import '../books/books_detail.dart';
import '../books/receipt_correction.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import 'credit_status.dart';

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/// 2024-04-05 -> 05-Apr-2024, as Tally writes dates (the web ledger's date format).
String ledgerDate(String iso) {
  final parts = iso.split('-');
  if (parts.length != 3) return iso;
  final month = int.tryParse(parts[1]);
  if (month == null || month < 1 || month > 12) return iso;
  return '${parts[2]}-${_months[month - 1]}-${parts[0]}';
}

/// Indian grouping with two decimals and no rupee sign; blank stays blank.
String ledgerAmount(Object? value) {
  final text = inventoryText(value);
  if (text.isEmpty) return '';
  return inventoryAmount(text).replaceFirst('₹', '');
}

String ledgerBalance(Object? amount, Object? side) {
  final text = ledgerAmount(inventoryText(amount).isEmpty ? '0' : amount);
  final suffix = inventoryText(side);
  return suffix.isEmpty ? text : '$text $suffix';
}

const _pdfKinds = {
  'sales_invoice',
  'purchase_bill',
  'credit_note',
  'debit_note',
  'estimate',
  'proforma',
  'purchase_order',
  'pos',
  'expense',
  'payment_in',
  'payment_out',
};

/// A party's ledger statement: the web app's "Party ledger" modal. Show it with `showDialog`.
class PartyStatementPage extends StatefulWidget {
  const PartyStatementPage({required this.workspace, required this.party, super.key});
  final WorkspaceContext workspace;
  final Json party;

  @override
  State<PartyStatementPage> createState() => _PartyStatementPageState();
}

class _Loaded {
  const _Loaded(this.statement, this.ledger);
  final Json statement;
  final Json ledger;
}

class _PartyStatementPageState extends State<PartyStatementPage> {
  late final String _initialFrom;
  late final String _initialTo;
  late String _to;
  late String _from;
  late Future<_Loaded> _loaded;
  bool _exporting = false;
  bool _includeCorrections = false;

  @override
  void initState() {
    super.initState();
    // The web app opens on the current financial year (1 April onwards).
    final today = DateTime.parse(businessDate());
    final startYear = today.month >= 4 ? today.year : today.year - 1;
    _initialFrom = '$startYear-04-01';
    _initialTo = businessDate();
    _from = _initialFrom;
    _to = _initialTo;
    _loaded = _fetch();
  }

  String get _root => '${widget.workspace.path}/parties/${Uri.encodeComponent(inventoryText(widget.party['id']))}';
  Map<String, String> get _range => {'from_date': _from, 'to_date': _to};
  Map<String, String> get _ledgerRange => {
    ..._range,
    if (_includeCorrections) 'include_corrections': 'true',
  };
  bool get _canWrite => widget.workspace.company.canWrite;

  Future<_Loaded> _fetch() async {
    final api = widget.workspace.api;
    final range = _range;
    final results = await Future.wait([
      api.get('$_root/statement', query: range),
      api.get('$_root/ledger', query: _ledgerRange),
    ]);
    return _Loaded(inventoryObject(results[0]), inventoryObject(results[1]));
  }

  void _reload() {
    final loaded = _fetch();
    setState(() {
      _loaded = loaded;
    });
  }

  Future<void> _pick(bool start) async {
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.parse(start ? _from : _to),
      firstDate: DateTime(1900),
      lastDate: DateTime(2100),
    );
    if (date == null || !mounted) return;
    final iso = date.toIso8601String().substring(0, 10);
    if (start) {
      _from = iso;
    } else {
      _to = iso;
    }
    _reload();
  }

  void _message(String text) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  Future<void> _export(String format) async {
    setState(() => _exporting = true);
    try {
      final filename = 'party-statement.$format';
      final bytes = await widget.workspace.api.download('$_root/statement.$format', query: _ledgerRange);
      final mime = format == 'pdf'
          ? 'application/pdf'
          : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      if (mounted) await saveApexFile(filename, bytes, mime);
    } catch (failure) {
      if (mounted) _message('Party statement export failed');
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _pdf(Json row) async {
    try {
      final bytes = await widget.workspace.api.download(
        '${widget.workspace.path}/documents/${Uri.encodeComponent(inventoryText(row['id']))}.pdf',
      );
      final label = inventoryText(row['number']).isEmpty ? inventoryText(row['id']) : inventoryText(row['number']);
      if (mounted) {
        await saveApexFile('${label.replaceAll(RegExp(r'[^a-zA-Z0-9_-]+'), '-')}.pdf', bytes, 'application/pdf');
      }
    } catch (failure) {
      if (mounted) _message('Document export failed');
    }
  }

  Future<void> _open(String id) async {
    if (id.isEmpty) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => Scaffold(
          body: SafeArea(
            child: BooksRecordDetail(
              data: BooksData(widget.workspace.company.id, widget.workspace.api.get),
              id: id,
              workspace: widget.workspace,
              onBack: () => Navigator.of(context).pop(),
              onOpen: _open,
              backLabel: 'Return to party statement',
            ),
          ),
        ),
      ),
    );
    if (mounted) _reload();
  }

  Widget _text(String text, {bool bold = false, bool end = false, Color? color}) => Text(
    text,
    textAlign: end ? TextAlign.right : TextAlign.left,
    style: TextStyle(fontSize: 13, fontWeight: bold ? FontWeight.w700 : FontWeight.w500, color: color ?? Apex.inkSoft),
  );

  Widget _dateField(String label, String iso, bool start) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: Apex.label)),
      const SizedBox(height: 7),
      InkWell(
        onTap: () => _pick(start),
        borderRadius: BorderRadius.circular(Apex.radiusControl),
        child: Container(
          height: 46,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Apex.radiusControl),
            border: Border.all(color: Apex.fieldBorder),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  iso.split('-').reversed.join('-'),
                  semanticsLabel: '$label ${ledgerDate(iso)}',
                  style: const TextStyle(fontSize: 14, color: Apex.ink),
                ),
              ),
              const Icon(Icons.calendar_today_outlined, size: 16, color: Apex.muted),
            ],
          ),
        ),
      ),
    ],
  );

  Widget _details(String title, Widget child) => Theme(
    data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
    child: ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      shape: const Border(),
      collapsedShape: const Border(),
      controlAffinity: ListTileControlAffinity.leading,
      dense: true,
      title: Text(title, style: Apex.strong.copyWith(fontSize: 16)),
      children: [child],
    ),
  );

  Widget _balanceComponents(Json balances) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final entry in balances.entries)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Apex.lineSoft))),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  entry.key
                      .replaceAll('_', ' ')
                      .split(' ')
                      .map((word) => word.isEmpty ? word : word[0].toUpperCase() + word.substring(1))
                      .join(' '),
                  style: const TextStyle(fontSize: 14, color: Apex.ink),
                ),
              ),
              Text(
                apexMoney(apexNumber(entry.value) ?? 0),
                style: const TextStyle(fontSize: 14, color: Apex.ink),
              ),
            ],
          ),
        ),
    ],
  );

  Widget _ledgerTable(Json ledger) {
    final rows = inventoryRows(ledger['rows']);
    final totals = inventoryObject(ledger['totals']);
    final opening = inventoryObject(ledger['opening']);
    final closing = inventoryObject(ledger['closing']);
    // Opening row, ledger rows, then the "Current total" and "Closing balance" rows.
    final lines = <List<String>>[
      ['', 'Opening balance', '', '', '', '', ledgerBalance(opening['amount'], opening['side'])],
      for (final row in rows)
        [
          ledgerDate(inventoryText(row['date'])),
          [row['particulars'], row['details']].map(inventoryText).where((value) => value.isNotEmpty).join(' · '),
          inventoryText(row['voucher_type']),
          inventoryText(row['voucher_number']),
          ledgerAmount(row['debit']),
          ledgerAmount(row['credit']),
          ledgerBalance(row['balance'], row['balance_side']),
        ],
      ['', 'Current total', '', '', ledgerAmount(totals['debit']), ledgerAmount(totals['credit']), ''],
      ['', 'Closing balance', '', '', '', '', ledgerBalance(closing['amount'], closing['side'])],
    ];
    bool summary(int row) => row == 0 || row >= lines.length - 2;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Apex.radiusControl),
        border: Border.all(color: Apex.line),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(Apex.radiusControl - 1),
        child: ApexTable(
          columns: const [
            ApexColumn('Date', width: 130),
            ApexColumn('Particulars', flex: 2.2),
            ApexColumn('Vch Type', flex: 1.1),
            ApexColumn('Vch No.', flex: 1.5),
            ApexColumn('Debit', flex: 1.1, alignEnd: true),
            ApexColumn('Credit', flex: 1.1, alignEnd: true),
            ApexColumn('Balance', flex: 1.4, alignEnd: true),
          ],
          cardBreakpoint: 560,
          rowCount: lines.length,
          onRowTap: (index) {
            final at = index - 1;
            if (at >= 0 && at < rows.length) _open(inventoryText(rows[at]['id']));
          },
          cell: (row, column) => _text(lines[row][column], bold: summary(row), end: column >= 4),
          card: (row) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: _text(lines[row][1], bold: true)),
                  _text(lines[row][6], bold: true),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                [lines[row][0], lines[row][2], lines[row][3]].where((value) => value.isNotEmpty).join(' · '),
                style: Apex.small,
              ),
              if (lines[row][4].isNotEmpty || lines[row][5].isNotEmpty)
                Text(
                  [
                    if (lines[row][4].isNotEmpty) 'Debit ${lines[row][4]}',
                    if (lines[row][5].isNotEmpty) 'Credit ${lines[row][5]}',
                  ].join(' · '),
                  style: Apex.small,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _documents(List<Json> rows) {
    if (rows.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 10),
        child: Text('No transactions in this date range.', style: Apex.lead),
      );
    }
    String type(Json row) =>
        '${inventoryText(row['kind']).replaceAll('_', ' ')}${row['posted'] == true ? '' : ' · draft'}';
    Widget actions(Json row) => Wrap(
      spacing: 10,
      children: [
        if (_canWrite && (row['editable'] == true ||
            row['posted'] == true && const {'payment_in', 'advance_application'}.contains(row['kind'])))
          ApexLink('Open', onTap: () => _open(inventoryText(row['id']))),
        if (_pdfKinds.contains(inventoryText(row['kind']))) ApexLink('PDF', onTap: () => _pdf(row)),
      ],
    );
    String outstanding(Json row) => row['outstanding'] == null ? '—' : apexMoney(apexNumber(row['outstanding']) ?? 0);
    String document(Json row) =>
        inventoryText(row['number']).isEmpty ? inventoryText(row['name']) : inventoryText(row['number']);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(Apex.radiusControl),
        border: Border.all(color: Apex.line),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(Apex.radiusControl - 1),
        child: ApexTable(
          columns: const [
            ApexColumn('Date', width: 130),
            ApexColumn('Document', flex: 1.8),
            ApexColumn('Type', flex: 1.4),
            ApexColumn('Total', flex: 1.2, alignEnd: true),
            ApexColumn('Outstanding', flex: 1.2, alignEnd: true),
            ApexColumn('Actions', width: 100, alignEnd: true),
          ],
          cardBreakpoint: 560,
          rowCount: rows.length,
          cell: (row, column) => switch (column) {
            0 => _text(ledgerDate(inventoryText(rows[row]['date']))),
            1 => _text(document(rows[row])),
            2 => _text(type(rows[row])),
            3 => _text(apexMoney(apexNumber(rows[row]['amount']) ?? 0), end: true),
            4 => _text(outstanding(rows[row]), end: true),
            _ => actions(rows[row]),
          },
          card: (row) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: _text(document(rows[row]), bold: true)),
                  _text(apexMoney(apexNumber(rows[row]['amount']) ?? 0), bold: true),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                '${ledgerDate(inventoryText(rows[row]['date']))} · ${type(rows[row])}',
                style: Apex.small,
              ),
              Text('Outstanding ${outstanding(rows[row])}', style: Apex.small),
              const SizedBox(height: 6),
              actions(rows[row]),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _body(_Loaded loaded) {
    final statement = loaded.statement;
    final ledger = loaded.ledger;
    final closing = inventoryObject(ledger['closing']);
    final history = inventoryRows(ledger['correction_history'] ?? []);
    return [
      if (widget.workspace.features.contains('party_credit_limits')) ...[
        CreditStatus(workspace: widget.workspace, partyId: inventoryText(widget.party['id']), asOf: _to),
        const SizedBox(height: 16),
      ],
      const Divider(height: 1, color: Apex.line),
      const SizedBox(height: 14),
      Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: 'Closing ledger balance: ${ledgerBalance(closing['amount'], closing['side'])}',
              style: const TextStyle(fontWeight: FontWeight.w700, color: Apex.ink),
            ),
            TextSpan(text: ' · Through ${ledgerDate(_to)}'),
          ],
        ),
        style: const TextStyle(fontSize: 14, color: Apex.muted),
      ),
      const SizedBox(height: 4),
      if (ledger['has_held_receipts'] == true)
        Text('Customer receipts received ${booksMoney(inventoryObject(ledger['totals'])['receipts'])}'),
      _details('Balance components', _balanceComponents(inventoryObject(statement['balances']))),
      const Divider(height: 1, color: Apex.line),
      const SizedBox(height: 14),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          OutlinedButton(onPressed: _exporting ? null : () => _export('xlsx'), child: const Text('Export XLSX')),
          OutlinedButton(onPressed: _exporting ? null : () => _export('pdf'), child: const Text('Export PDF')),
        ],
      ),
      if (inventoryText(ledger['ordering_note']).isNotEmpty) ...[
        const SizedBox(height: 14),
        Text(inventoryText(ledger['ordering_note']), style: Apex.lead.copyWith(fontSize: 13)),
      ],
      const SizedBox(height: 14),
      _ledgerTable(ledger),
      for (final row in history)
        ListTile(
          title: Text(inventoryText(row['details'])),
          subtitle: Text('${ledgerDate(inventoryText(row['date']))} · ${row['number']}'),
          onTap: () => _open(inventoryText(row['id'])),
        ),
      const SizedBox(height: 10),
      _details('Documents, drafts and estimates', _documents(inventoryRows(statement['transactions']))),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final phone = MediaQuery.sizeOf(context).width < 600;
    final pad = phone ? 18.0 : 26.0;
    final data = widget.party['data'] is Map ? inventoryObject(widget.party['data']) : const <String, dynamic>{};
    final contact = [
      data['phone'],
      data['email'],
      data['gstin'],
      data['address'],
    ].map(inventoryText).where((value) => value.isNotEmpty).join(' · ');
    final custom = _from != _initialFrom || _to != _initialTo;
    return Dialog(
      insetPadding: phone ? const EdgeInsets.all(12) : const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1000),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(pad, 22, pad - 8, 14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(inventoryText(widget.party['name']), style: Apex.panelTitle.copyWith(fontSize: 21)),
                        const SizedBox(height: 4),
                        const Text('Party ledger', style: TextStyle(fontSize: 13, color: Apex.muted)),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close_rounded, size: 20),
                  ),
                ],
              ),
            ),
            const Divider(height: 1, color: Apex.line),
            Flexible(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(pad, 18, pad, 24),
                child: FutureBuilder<_Loaded>(
                  future: _loaded,
                  builder: (context, state) => Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (contact.isNotEmpty) ...[Text(contact, style: Apex.lead), const SizedBox(height: 14)],
                      Text(
                        '${custom ? 'Custom date range' : 'This financial year'} · ${ledgerDate(_from)} to ${ledgerDate(_to)}',
                        style: Apex.lead,
                      ),
                      const SizedBox(height: 14),
                      LayoutBuilder(
                        builder: (context, limits) {
                          final from = _dateField('From date', _from, true);
                          final to = _dateField('To date', _to, false);
                          if (limits.maxWidth < 420) {
                            return Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [from, const SizedBox(height: 12), to],
                            );
                          }
                          return Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [Expanded(child: from), const SizedBox(width: 16), Expanded(child: to)],
                          );
                        },
                      ),
                      const SizedBox(height: 16),
                      if (widget.workspace.features.contains(receiptCorrectionsFeature))
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('Include correction history'),
                          value: _includeCorrections,
                          onChanged: _exporting ? null : (value) {
                            _includeCorrections = value == true;
                            _reload();
                          },
                        ),
                      if (state.connectionState != ConnectionState.done)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 20),
                          child: LinearProgressIndicator(semanticsLabel: 'Loading statement'),
                        )
                      else if (state.hasError) ...[
                        Text(inventoryError(state.error!), style: const TextStyle(color: Apex.red, fontSize: 13)),
                        const SizedBox(height: 10),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: OutlinedButton(onPressed: _reload, child: const Text('Try again')),
                        ),
                      ] else
                        ..._body(state.data!),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
