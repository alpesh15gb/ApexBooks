import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import 'books_data.dart';
import 'report_widgets.dart';

enum _Tone { section, line, group, subtotal, total, grand, muted }

class _Entry {
  const _Entry(this.label, this.tone, {this.value, this.detail});
  final String label;
  final _Tone tone;
  final String? value;
  final String? detail;
}

/// Profit and loss beside the balance sheet, in the web app's statement layout.
class ReportStatements extends StatelessWidget {
  const ReportStatements({required this.data, super.key});
  final BooksJson data;

  List<_Entry> _lines(Object? source) => [
    for (final line in reportRows(source))
      _Entry(
        booksText(line['name']),
        _Tone.line,
        value: booksMoney(line['amount']),
      ),
  ];

  List<_Entry> _sections(Object? source, String none) {
    final sections = reportRows(source);
    if (sections.isEmpty) return [_Entry(none, _Tone.muted)];
    return [
      for (final section in sections) ...[
        _Entry(
          booksText(section['label']),
          _Tone.group,
          value: booksMoney(section['total']),
        ),
        if (reportRows(section['lines']).length > 1)
          ..._lines(section['lines']),
      ],
    ];
  }

  @override
  Widget build(BuildContext context) {
    final pl = booksObject(data['profit_loss']);
    final bs = booksObject(data['balance_sheet']);
    final revenue = booksObject(pl['revenue']);
    final cost = booksObject(pl['cost_of_sales']);
    final other = booksObject(pl['other_income']);
    final expenses = booksObject(pl['operating_expenses']);
    final assets = booksObject(bs['assets']);
    final liabilities = booksObject(bs['liabilities']);
    final equity = booksObject(bs['equity']);
    final margin = pl['gross_margin_percent'];
    final net = booksText(pl['net_profit']);
    final difference = booksText(bs['difference']);
    final balanced = (num.tryParse(difference) ?? 0) == 0;
    List<_Entry> block(
      String heading,
      BooksJson group,
      String none,
      String total,
    ) => [
      _Entry(heading, _Tone.section),
      if (reportRows(group['lines']).isEmpty)
        _Entry(none, _Tone.muted)
      else
        ..._lines(group['lines']),
      _Entry(total, _Tone.subtotal, value: booksMoney(group['total'])),
    ];
    final profitRows = [
      ...block('Revenue', revenue, 'No sales in this period', 'Total revenue'),
      ...block(
        'Cost of sales',
        cost,
        'No cost of sales',
        'Total cost of sales',
      ),
      _Entry(
        'Gross profit',
        _Tone.total,
        value: booksMoney(pl['gross_profit']),
        detail: margin == null ? null : '${booksText(margin)}% of revenue',
      ),
      if (reportRows(other['lines']).isNotEmpty) ...[
        _Entry('Other income', _Tone.section),
        ..._lines(other['lines']),
        _Entry(
          'Total other income',
          _Tone.subtotal,
          value: booksMoney(other['total']),
        ),
      ],
      ...block(
        'Operating expenses',
        expenses,
        'No expenses recorded',
        'Total operating expenses',
      ),
      _Entry(
        net.startsWith('-') ? 'Net loss' : 'Net profit',
        _Tone.grand,
        value: booksMoney(pl['net_profit']),
      ),
    ];
    final balanceRows = [
      const _Entry('Assets', _Tone.section),
      ..._sections(assets['sections'], 'No assets'),
      _Entry('Total assets', _Tone.total, value: booksMoney(assets['total'])),
      const _Entry('Liabilities', _Tone.section),
      ..._sections(liabilities['sections'], 'No liabilities'),
      _Entry(
        'Total liabilities',
        _Tone.total,
        value: booksMoney(liabilities['total']),
      ),
      const _Entry('Equity', _Tone.section),
      ..._lines(equity['lines']),
      _Entry('Total equity', _Tone.total, value: booksMoney(equity['total'])),
      _Entry(
        'Total liabilities and equity',
        _Tone.grand,
        value: booksMoney(bs['total_liabilities_and_equity']),
      ),
    ];
    final basis = booksText(data['basis']);
    final limitations = booksText(data['limitations']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportPanelRow([
          _StatementPanel(
            title: 'Profit and loss',
            period:
                '${booksText(data['from_date'])} to ${booksText(data['to_date'])}',
            entries: profitRows,
          ),
          _StatementPanel(
            title: 'Balance sheet',
            period: 'As of ${booksText(bs['as_of'])}',
            entries: balanceRows,
            status: balanced
                ? 'Balance sheet balances: assets equal liabilities plus equity.'
                : 'Out of balance by ${booksMoney(difference)}. Contact support before relying on these figures.',
            statusOk: balanced,
          ),
        ]),
        ReportInfoBox(
          '$basis ${limitations.isEmpty ? 'Depreciation, net realisable value write-downs and accruals are not calculated; review with your accountant before using these statements for filing or lending.' : limitations}',
        ),
      ],
    );
  }
}

class _StatementPanel extends StatelessWidget {
  const _StatementPanel({
    required this.title,
    required this.period,
    required this.entries,
    this.status,
    this.statusOk = true,
  });

  final String title;
  final String period;
  final List<_Entry> entries;
  final String? status;
  final bool statusOk;

  @override
  Widget build(BuildContext context) => ReportPanel(
    title: title,
    subtitle: period,
    topGap: false,
    padded: true,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final entry in entries) _StatementRow(entry),
        if (status != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: statusOk
                    ? const Color(0xffe9f4ee)
                    : const Color(0xfffcecea),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 10,
                ),
                child: Text(
                  status!,
                  style: TextStyle(
                    fontSize: 12,
                    color: statusOk ? Apex.greenDark : Apex.red,
                  ),
                ),
              ),
            ),
          ),
      ],
    ),
  );
}

class _StatementRow extends StatelessWidget {
  const _StatementRow(this.entry);
  final _Entry entry;

  @override
  Widget build(BuildContext context) {
    final tone = entry.tone;
    if (tone == _Tone.section) {
      return Padding(
        padding: const EdgeInsets.only(top: 18, bottom: 4),
        child: Text(
          entry.label.toUpperCase(),
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: .9,
            color: Apex.greenText,
          ),
        ),
      );
    }
    final heavy =
        tone == _Tone.group ||
        tone == _Tone.subtotal ||
        tone == _Tone.total ||
        tone == _Tone.grand;
    final label = Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                entry.label,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: heavy ? FontWeight.w700 : FontWeight.w400,
                  color: tone == _Tone.muted ? Apex.muted : Apex.ink,
                ),
              ),
              if (entry.detail != null) Text(entry.detail!, style: Apex.small),
            ],
          ),
        ),
        if (entry.value != null) ...[
          const SizedBox(width: 12),
          Text(
            entry.value!,
            style: TextStyle(
              fontSize: 14,
              fontWeight: heavy ? FontWeight.w700 : FontWeight.w400,
              color: tone == _Tone.line ? Apex.inkSoft : Apex.ink,
            ),
          ),
        ],
      ],
    );
    final border = switch (tone) {
      _Tone.subtotal => const Border(top: BorderSide(color: Apex.lineStrong)),
      _Tone.total => const Border(
        top: BorderSide(color: Apex.green, width: 1.5),
      ),
      _Tone.grand => const Border(
        top: BorderSide(color: Apex.green, width: 1.5),
        bottom: BorderSide(color: Apex.ink, width: 3),
      ),
      _ => null,
    };
    return Padding(
      padding: EdgeInsets.only(top: tone == _Tone.grand ? 6 : 0),
      child: DecoratedBox(
        decoration: BoxDecoration(border: border),
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            tone == _Tone.line || tone == _Tone.muted ? 18 : 0,
            tone == _Tone.grand ? 12 : 8,
            0,
            tone == _Tone.grand ? 12 : 8,
          ),
          child: label,
        ),
      ),
    );
  }
}
