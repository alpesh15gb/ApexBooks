import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import '../books/books_detail.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';

/// A party's ledger statement (the web app's "Party ledger" modal).
class PartyStatementPage extends StatefulWidget {
  const PartyStatementPage({required this.workspace, required this.party, super.key});
  final WorkspaceContext workspace;
  final Json party;

  @override
  State<PartyStatementPage> createState() => _PartyStatementPageState();
}

class _PartyStatementPageState extends State<PartyStatementPage> {
  late final String _initialFrom;
  late final String _initialTo;
  late String _to;
  late String _from;
  late Future<Json> _statement;
  bool _exporting = false;

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
    _statement = _fetch();
  }

  String get _root => '${widget.workspace.path}/parties/${Uri.encodeComponent(inventoryText(widget.party['id']))}';
  Map<String, String> get _range => {'from_date': _from, 'to_date': _to};

  Future<Json> _fetch() async => inventoryObject(await widget.workspace.api.get('$_root/ledger', query: _range));

  void _reload() {
    final statement = _fetch();
    setState(() {
      _statement = statement;
    });
  }

  Future<void> _pick(bool start) async {
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.parse(start ? _from : _to),
      firstDate: start ? DateTime(1900) : DateTime.parse(_from),
      lastDate: start ? DateTime.parse(_to) : DateTime.parse(businessDate()),
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

  Future<void> _export(String format) async {
    setState(() => _exporting = true);
    try {
      final filename = 'party-statement-$_from-$_to.$format';
      final bytes = await widget.workspace.api.download('$_root/statement.$format', query: _range);
      final mime = format == 'pdf'
          ? 'application/pdf'
          : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      if (mounted) await saveApexFile(filename, bytes, mime);
    } catch (failure) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(inventoryError(failure))));
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  void _open(String id) {
    if (id.isEmpty) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => Scaffold(
          body: SafeArea(
            child: BooksRecordDetail(
              data: BooksData(widget.workspace.company.id, widget.workspace.api.get),
              id: id,
              onBack: () => Navigator.of(context).pop(),
              onOpen: _open,
              backLabel: 'Return to party statement',
            ),
          ),
        ),
      ),
    );
  }

  String _balance(Object? amount, Object? side) {
    final text = inventoryAmount(amount ?? '0');
    final suffix = inventoryText(side);
    return suffix.isEmpty ? text : '$text $suffix';
  }

  String _balanceOf(Object? value) {
    final data = inventoryObject(value);
    return _balance(data['amount'], data['side']);
  }

  String _plain(Object? value) {
    final text = inventoryText(value);
    return text.isEmpty ? '' : inventoryAmount(text).replaceFirst('₹', '');
  }

  Widget _text(String text, {bool bold = false, bool end = false, Color? color}) => Text(
    text,
    textAlign: end ? TextAlign.right : TextAlign.left,
    style: TextStyle(fontSize: 13, fontWeight: bold ? FontWeight.w700 : FontWeight.w500, color: color ?? Apex.inkSoft),
  );

  Widget _button(String label, VoidCallback? onTap, {IconData? icon}) => OutlinedButton.icon(
    onPressed: onTap,
    icon: icon == null ? const SizedBox.shrink() : Icon(icon, size: 16),
    label: Text(label),
  );

  @override
  Widget build(BuildContext context) {
    final data = widget.party['data'] is Map ? inventoryObject(widget.party['data']) : const <String, dynamic>{};
    final contact = [
      data['phone'],
      data['email'],
      data['gstin'],
      data['address'],
    ].map(inventoryText).where((value) => value.isNotEmpty).join(' · ');
    final custom = _from != _initialFrom || _to != _initialTo;
    return Scaffold(
      appBar: AppBar(
        title: Text(inventoryText(widget.party['name'])),
        actions: [IconButton(onPressed: _reload, tooltip: 'Refresh statement', icon: const Icon(Icons.refresh))],
      ),
      body: SafeArea(
        child: FutureBuilder<Json>(
          future: _statement,
          builder: (context, state) {
            final ledger = state.data ?? const <String, dynamic>{};
            final ready = state.connectionState == ConnectionState.done && state.hasData;
            final rows = inventoryRows(ledger['rows']);
            final totals = inventoryObject(ledger['totals']);
            // Opening row, ledger rows, then the "Current total" and "Closing balance" rows.
            final lines = <List<String>>[
              if (ready) ['', 'Opening balance', '', '', '', '', _balanceOf(ledger['opening'])],
              for (final row in rows)
                [
                  apexDate(inventoryText(row['date'])),
                  inventoryText(row['particulars']),
                  inventoryText(row['voucher_type']),
                  inventoryText(row['voucher_number']),
                  _plain(row['debit']),
                  _plain(row['credit']),
                  _balance(row['balance'], row['balance_side']),
                ],
              if (ready) ...[
                ['', 'Current total', '', '', _plain(totals['debit']), _plain(totals['credit']), ''],
                ['', 'Closing balance', '', '', '', '', _balanceOf(ledger['closing'])],
              ],
            ];
            return ApexPage(
              maxWidth: 1100,
              children: [
                ApexRegisterHeading(
                  inventoryText(widget.party['name']),
                  subtitle: 'Party ledger',
                  actions: [
                    _button('Export XLSX', ready && !_exporting ? () => _export('xlsx') : null, icon: Icons.download_outlined),
                    _button('Export PDF', ready && !_exporting ? () => _export('pdf') : null, icon: Icons.download_outlined),
                  ],
                ),
                const SizedBox(height: 18),
                ApexPanel(
                  radius: Apex.radiusPanel,
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (contact.isNotEmpty) ...[Text(contact, style: Apex.lead), const SizedBox(height: 8)],
                      Text(
                        '${custom ? 'Custom date range' : 'This financial year'} · ${apexDate(_from)} to ${apexDate(_to)}',
                        style: Apex.lead,
                      ),
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 12,
                        runSpacing: 10,
                        children: [
                          _button('From date  ${apexDate(_from)}', () => _pick(true), icon: Icons.event_outlined),
                          _button('To date  ${apexDate(_to)}', () => _pick(false), icon: Icons.event_outlined),
                        ],
                      ),
                      if (ready) ...[
                        const SizedBox(height: 16),
                        Text.rich(
                          TextSpan(
                            children: [
                              TextSpan(
                                text: 'Closing ledger balance: ${_balanceOf(ledger['closing'])}',
                                style: const TextStyle(fontWeight: FontWeight.w700, color: Apex.ink),
                              ),
                              TextSpan(text: ' · Through ${apexDate(_to)}'),
                            ],
                          ),
                          style: const TextStyle(fontSize: 14, color: Apex.muted),
                        ),
                        if (rows.isEmpty) ...[
                          const SizedBox(height: 8),
                          const Text('No posted transactions in this date range.', style: Apex.note),
                        ],
                        if (inventoryText(ledger['ordering_note']).isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text(inventoryText(ledger['ordering_note']), style: Apex.note),
                        ],
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                ApexPanel(
                  radius: Apex.radiusPanel,
                  child: !ready && state.connectionState != ConnectionState.done
                      ? const Padding(padding: EdgeInsets.all(26), child: LinearProgressIndicator())
                      : state.hasError
                      ? ApexEmptyState(icon: Icons.error_outline, title: inventoryError(state.error!))
                      : ApexTable(
                          columns: const [
                            ApexColumn('Date', width: 120),
                            ApexColumn('Particulars', flex: 2.4),
                            ApexColumn('Vch Type', flex: 1.2),
                            ApexColumn('Vch No.', flex: 1.2),
                            ApexColumn('Debit', flex: 1.2, alignEnd: true),
                            ApexColumn('Credit', flex: 1.2, alignEnd: true),
                            ApexColumn('Balance', flex: 1.5, alignEnd: true),
                          ],
                          rowCount: lines.length,
                          onRowTap: (index) {
                            final at = index - 1;
                            if (at >= 0 && at < rows.length) _open(inventoryText(rows[at]['id']));
                          },
                          cell: (row, column) {
                            final summary = lines[row][1] == 'Opening balance' ||
                                lines[row][1] == 'Closing balance' ||
                                lines[row][1] == 'Current total';
                            return _text(lines[row][column], bold: summary, end: column >= 4);
                          },
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
                                [
                                  lines[row][0],
                                  lines[row][2],
                                  lines[row][3],
                                ].where((value) => value.isNotEmpty).join(' · '),
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
              ],
            );
          },
        ),
      ),
    );
  }
}
