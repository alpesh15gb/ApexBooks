import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import 'books_data.dart';
import 'report_widgets.dart';

const _movementKinds = {
  'stock_opening': 'Opening stock',
  'stock_adjustment': 'Stock adjustment',
  'purchase_bill': 'Purchase bill',
  'debit_note': 'Purchase return',
  'sales_invoice': 'Sales invoice',
  'pos': 'POS receipt',
  'credit_note': 'Sales return',
  'stock_return': 'Stock return',
};

/// Tracked stock table with the web's "View movements" row action: the item's movements open
/// under the table and each source document opens from its link.
class ReportStockTable extends StatefulWidget {
  const ReportStockTable({
    required this.data,
    required this.fetch,
    required this.root,
    required this.from,
    required this.to,
    required this.history,
    required this.onOpenRecord,
    super.key,
  });

  final BooksJson data;
  final BooksGet fetch;

  /// Company root, for example `/api/companies/<id>`.
  final String root;
  final String from;
  final String to;

  /// The server supports `stock_movement_history`.
  final bool history;
  final ValueChanged<String> onOpenRecord;

  @override
  State<ReportStockTable> createState() => _ReportStockTableState();
}

class _ReportStockTableState extends State<ReportStockTable> {
  String? _open;

  @override
  Widget build(BuildContext context) {
    final rows = reportRows(widget.data['rows']);
    final opened = rows
        .where((row) => booksText(row['item_id']) == _open)
        .toList();
    return ReportTable(
      title: 'Tracked stock quantities',
      empty: 'No stock-tracked items',
      columns: [
        reportText('Item / unit', flex: 1.6),
        reportAmount('Opening'),
        reportAmount('Introduced'),
        reportAmount('Adjustments net'),
        reportAmount('Purchased net'),
        reportAmount('Sold net'),
        reportAmount('Closing'),
        reportAmount('Cost value'),
        if (widget.history) reportText('History', flex: 1.2),
      ],
      rows: [
        for (final row in rows)
          ReportTableRow([
            ReportCell(booksText(row['name']), sub: booksText(row['unit'])),
            booksText(row['opening_quantity']),
            booksText(row['introduced_quantity']),
            booksText(row['adjustment_quantity']),
            booksText(row['purchased_quantity']),
            booksText(row['sold_quantity']),
            booksText(row['closing_quantity']),
            row['closing_value'] == null
                ? 'Needs migration'
                : booksMoney(row['closing_value']),
            if (widget.history)
              ReportCell(
                _open == booksText(row['item_id'])
                    ? 'Hide movements'
                    : 'View movements',
                link: true,
                onTap: () => setState(() {
                  final id = booksText(row['item_id']);
                  _open = _open == id ? null : id;
                }),
              ),
          ]),
      ],
      below: opened.isEmpty
          ? null
          : ReportStockMovements(
              key: ValueKey((
                booksText(opened.first['item_id']),
                widget.from,
                widget.to,
              )),
              fetch: widget.fetch,
              root: widget.root,
              item: opened.first,
              from: widget.from,
              to: widget.to,
              onOpenRecord: widget.onOpenRecord,
            ),
    );
  }
}

/// One item's stock movements, paged with the server's cursor like the web section.
class ReportStockMovements extends StatefulWidget {
  const ReportStockMovements({
    required this.fetch,
    required this.root,
    required this.item,
    required this.from,
    required this.to,
    required this.onOpenRecord,
    super.key,
  });

  final BooksGet fetch;
  final String root;
  final BooksJson item;
  final String from;
  final String to;
  final ValueChanged<String> onOpenRecord;

  @override
  State<ReportStockMovements> createState() => _ReportStockMovementsState();
}

class _ReportStockMovementsState extends State<ReportStockMovements> {
  BooksJson? _page;
  BooksJson? _result;
  String _error = '';
  int _attempt = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final page = _page;
    final attempt = ++_attempt;
    try {
      final id = Uri.encodeComponent(booksText(widget.item['item_id']));
      final value = booksObject(
        await widget.fetch(
          '${widget.root}/reports/stock/$id/movements',
          query: {
            'from_date': widget.from,
            'to_date': widget.to,
            if (page != null) 'before_date': booksText(page['date']),
            if (page != null) 'before_id': booksText(page['id']),
          },
        ),
      );
      if (mounted && attempt == _attempt) setState(() => _result = value);
    } catch (failure) {
      if (mounted && attempt == _attempt) {
        setState(() => _error = 'Could not load stock movements.');
      }
    }
  }

  void _go(BooksJson? page) {
    setState(() {
      _result = null;
      _error = '';
      _page = page;
    });
    _load();
  }

  static String _signed(Object? value) {
    final text = booksText(value);
    return (num.tryParse(text) ?? 0) > 0 ? '+$text' : text;
  }

  @override
  Widget build(BuildContext context) {
    final title = 'Stock movements for ${booksText(widget.item['name'])}';
    final result = _result;
    final rows = result == null
        ? const <BooksJson>[]
        : reportRows(result['rows']);
    final next = result?['next'] is Map ? booksObject(result!['next']) : null;
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Apex.line)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Apex.strong.copyWith(fontSize: 15)),
            const SizedBox(height: 10),
            if (_error.isNotEmpty)
              Row(
                children: [
                  Flexible(
                    child: Text(
                      _error,
                      style: const TextStyle(color: Apex.red, fontSize: 13),
                    ),
                  ),
                  TextButton(
                    onPressed: () {
                      setState(() => _error = '');
                      _load();
                    },
                    child: const Text('Retry'),
                  ),
                ],
              )
            else if (result == null)
              const Text(
                'Loading stock movements…',
                style: TextStyle(fontSize: 13, color: Apex.muted),
              )
            else if (rows.isEmpty)
              const Text(
                'No movements during this period.',
                style: TextStyle(fontSize: 13),
              )
            else
              for (final row in rows) _movement(row),
            if (_page != null || next != null) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                children: [
                  if (_page != null)
                    OutlinedButton(
                      onPressed: () => _go(null),
                      child: const Text('First page'),
                    ),
                  if (next != null)
                    OutlinedButton(
                      onPressed: () => _go(next),
                      child: const Text('Next page'),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _movement(BooksJson row) {
    final kind = booksText(row['kind']);
    final number = booksText(row['number']);
    final description =
        '${_movementKinds[kind] ?? kind.replaceAll('_', ' ')}${number.isEmpty ? '' : ' · $number'}';
    final unit = booksText(widget.item['unit']);
    final cost = row['cost_value'] == null
        ? 'Unvalued'
        : booksMoney(row['cost_value']);
    final recordId = booksText(row['record_id']);
    const style = TextStyle(fontSize: 13, color: Apex.inkSoft);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Wrap(
        spacing: 16,
        runSpacing: 2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 96,
            child: Text(booksText(row['date']), style: style),
          ),
          SizedBox(
            width: 220,
            child: recordId.isEmpty
                ? Text(description, style: style)
                : InkWell(
                    onTap: () => widget.onOpenRecord(recordId),
                    child: Text(
                      description,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: Apex.link,
                      ),
                    ),
                  ),
          ),
          SizedBox(
            width: 110,
            child: Text('${_signed(row['quantity'])} $unit', style: style),
          ),
          Text(cost, style: style),
        ],
      ),
    );
  }
}
