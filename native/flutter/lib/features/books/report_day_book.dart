import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import 'books_data.dart';
import 'report_widgets.dart';

num _sum(Object? a, Object? b) =>
    (num.tryParse(booksText(a)) ?? 0) + (num.tryParse(booksText(b)) ?? 0);

/// Day navigation bar: previous, date field, next, and Today when away from today.
class ReportDayBar extends StatelessWidget {
  const ReportDayBar({
    required this.day,
    required this.today,
    required this.onShift,
    required this.onPick,
    required this.onToday,
    super.key,
  });

  final DateTime day;
  final DateTime today;
  final ValueChanged<int> onShift;
  final VoidCallback onPick;
  final VoidCallback onToday;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    runSpacing: 8,
    crossAxisAlignment: WrapCrossAlignment.center,
    children: [
      OutlinedButton(
        onPressed: () => onShift(-1),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(44, 44),
          padding: EdgeInsets.zero,
        ),
        child: const Icon(
          Icons.chevron_left_rounded,
          size: 20,
          semanticLabel: 'Previous day',
        ),
      ),
      Semantics(
        button: true,
        label: 'Day',
        child: InkWell(
          onTap: onPick,
          borderRadius: BorderRadius.circular(Apex.radiusChip),
          child: Container(
            height: 44,
            width: 170,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(Apex.radiusChip),
              border: Border.all(color: Apex.fieldBorder),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '${day.day.toString().padLeft(2, '0')}-${day.month.toString().padLeft(2, '0')}-${day.year}',
                    style: const TextStyle(fontSize: 14, color: Apex.ink),
                  ),
                ),
                const Icon(
                  Icons.calendar_today_outlined,
                  size: 16,
                  color: Apex.ink,
                ),
              ],
            ),
          ),
        ),
      ),
      OutlinedButton(
        onPressed: () => onShift(1),
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(44, 44),
          padding: EdgeInsets.zero,
        ),
        child: const Icon(
          Icons.chevron_right_rounded,
          size: 20,
          semanticLabel: 'Next day',
        ),
      ),
      if (booksDate(day) != booksDate(today))
        OutlinedButton(
          onPressed: onToday,
          style: OutlinedButton.styleFrom(minimumSize: const Size(48, 44)),
          child: const Text('Today'),
        ),
    ],
  );
}

/// Daily totals and the entries table. [data] is null while loading or after a failure.
class ReportDayBook extends StatelessWidget {
  const ReportDayBook({
    required this.day,
    required this.data,
    required this.onOpenRecord,
    this.failed = false,
    super.key,
  });

  final String day;
  final BooksJson? data;
  final bool failed;
  final ValueChanged<String> onOpenRecord;

  @override
  Widget build(BuildContext context) {
    final data = this.data;
    final totals = data == null ? null : booksObject(data['totals']);
    String money(Object? value) => totals == null ? '—' : booksMoney(value);
    final rows = data == null ? const <BooksJson>[] : reportRows(data['rows']);
    final count = data == null
        ? 0
        : (num.tryParse(booksText(data['count'])) ?? rows.length).toInt();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Sales', money(totals?['sales'])),
          ReportMetric(
            'Purchases & expenses',
            totals == null
                ? '—'
                : booksMoney(
                    _sum(
                      totals['purchases'],
                      totals['expenses'],
                    ).toStringAsFixed(2),
                  ),
          ),
          ReportMetric(
            'Money in',
            money(totals?['money_in']),
            color: Apex.greenText,
          ),
          ReportMetric(
            'Money out',
            money(totals?['money_out']),
            color: Apex.red,
            note: totals == null ? null : 'Net ${booksMoney(totals['net'])}',
          ),
        ]),
        if (data == null)
          ReportPanel(
            title: 'Day book · $day',
            subtitle:
                '${failed ? 'Day book unavailable' : 'Loading…'} · cash and bank movement from posted entries',
            child: const SizedBox(height: 4),
          )
        else
          ReportTable(
            title: 'Day book · $day',
            subtitle:
                '$count ${count == 1 ? 'entry' : 'entries'} · cash and bank movement from posted entries',
            empty: 'Nothing recorded on this day',
            columns: [
              reportText('Type', flex: 1.2),
              reportText('Number / party', flex: 1.8),
              reportAmount('Amount'),
              reportAmount('Money in'),
              reportAmount('Money out'),
            ],
            rows: [for (final row in rows) _row(row)],
          ),
      ],
    );
  }

  ReportTableRow _row(BooksJson row) {
    final kind = booksText(row['kind']);
    final id = booksText(row['id']);
    final cancelled = row['cancelled'] == true;
    final status = booksText(row['status']);
    final posted = row['posted'] == true;
    final label = booksKinds[kind] ?? reportWords(kind);
    final suffix = cancelled
        ? ' · cancelled'
        : status == 'converted'
        ? ' · converted'
        : !posted && kind != 'journal'
        ? (status == 'non_posting' ? ' · non-posting' : ' · unposted')
        : '';
    final display = booksText(row['display_number']);
    final number = booksText(row['number']);
    final name = booksText(row['name']);
    final shown = display.isNotEmpty ? display : number;
    final opens = kind != 'journal' && id.isNotEmpty;
    final journal = kind == 'journal' && row['debit_total'] != null;
    final moneyIn = num.tryParse(booksText(row['money_in'])) ?? 0;
    final moneyOut = num.tryParse(booksText(row['money_out'])) ?? 0;
    return ReportTableRow(
      muted: cancelled,
      onTap: opens ? () => onOpenRecord(id) : null,
      [
        '$label$suffix',
        ReportCell(
          opens
              ? (shown.isNotEmpty
                    ? shown
                    : name.isNotEmpty
                    ? name
                    : 'Open document')
              : (shown.isEmpty ? '—' : shown),
          sub: name,
          link: opens,
        ),
        ReportCell(
          booksMoney(row['amount']),
          sub: journal
              ? 'Debit ${booksMoney(row['debit_total'])} · Credit ${booksMoney(row['credit_total'])}'
              : null,
        ),
        ReportCell(
          moneyIn == 0 ? '' : booksMoney(row['money_in']),
          color: Apex.greenText,
        ),
        ReportCell(
          moneyOut == 0 ? '' : booksMoney(row['money_out']),
          color: Apex.red,
        ),
      ],
    );
  }
}
