import 'package:material_ui/material_ui.dart';

import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import 'books_data.dart';
import 'report_day_book.dart';
import 'report_statements.dart';
import 'report_widgets.dart';

part 'books_extended_reports.dart';

/// The body of one report, laid out like the web app's report pages.
class BooksReportContent extends StatelessWidget {
  const BooksReportContent({
    required this.report,
    required this.data,
    required this.onOpenRecord,
    this.asOf = '',
    this.party = '',
    super.key,
  });

  final BooksReport report;
  final BooksJson data;
  final ValueChanged<String> onOpenRecord;

  /// End date of the period (the "as of" date), used in panel titles.
  final String asOf;

  /// Party name applied to the party statement.
  final String party;

  @override
  Widget build(BuildContext context) {
    return switch (report) {
      BooksReport.summary => _summary(),
      BooksReport.sales ||
      BooksReport.purchases ||
      BooksReport.expenses => _register(),
      BooksReport.statements => ReportStatements(data: data),
      BooksReport.financial => _financial(),
      BooksReport.ageing => _ageing(),
      BooksReport.stock => _stock(),
      BooksReport.parties => _partyStatement(),
      BooksReport.credits || BooksReport.advances => _unapplied(),
      BooksReport.items => _items(),
      BooksReport.gst => _gstAnalysis(),
      BooksReport.gstr1 ||
      BooksReport.gstr2a ||
      BooksReport.gstr3b => _gstReturn(),
      BooksReport.dayBook => ReportDayBook(
        day: asOf,
        data: data,
        onOpenRecord: onOpenRecord,
      ),
      BooksReport.trial => _trialBalance(),
    };
  }

  Widget _summary() {
    final gst = data['gst'];
    final pending = gst is BooksJson && gst['input_pending_review'] is BooksJson
        ? booksObject(gst['input_pending_review'])
        : const <String, dynamic>{};
    final outward =
        gst is BooksJson && gst['outward_supply_values'] is BooksJson
        ? booksObject(gst['outward_supply_values'])
        : const <String, dynamic>{};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Net sales', booksMoney(data['sales'])),
          ReportMetric('Net purchases', booksMoney(data['purchases'])),
          ReportMetric('Receivables', booksMoney(data['receivables'])),
          ReportMetric('Payables', booksMoney(data['payables'])),
        ]),
        ReportPanelRow([
          ReportLinesPanel(
            title: 'Cash activity',
            lines: [
              ('Payments received', booksMoney(data['receipts'])),
              ('Payments out', booksMoney(data['payments'])),
              ('Expenses', booksMoney(data['expenses'])),
            ],
          ),
          if (gst is BooksJson)
            ReportLinesPanel(
              title: 'GST summary',
              intro: 'Input tax is pending review and is not a claimed credit.',
              lines: [
                for (final key in ['cgst', 'sgst', 'igst']) ...[
                  ('${key.toUpperCase()} output', booksMoney(gst[key])),
                  (
                    '${key.toUpperCase()} input pending',
                    booksMoney(pending[key]),
                  ),
                ],
                (
                  'Supplier GST included in cost',
                  booksMoney(gst['input_ineligible_in_cost']),
                ),
                for (final (key, label) in [
                  ('taxable', 'Outward taxable'),
                  ('nil_rated', 'Outward nil rated'),
                  ('exempt', 'Outward exempt'),
                  ('non_gst', 'Outward non-GST'),
                ])
                  (label, booksMoney(outward[key])),
              ],
            )
          else
            const ReportPanel(
              title: 'GST summary',
              padded: true,
              topGap: false,
              child: Text(
                'GST return figures are shown only for regular GST companies. Composition and unregistered purchases do not create input credit here.',
                style: TextStyle(
                  fontSize: 14,
                  height: 1.6,
                  color: Color(0xff606a77),
                ),
              ),
            ),
        ]),
        const ReportInfoBox(
          'Receivables and payables are outstanding as of the end date, including documents issued before the selected period. These figures are preparation aids, not filed returns.',
        ),
      ],
    );
  }

  Widget _register() {
    final name = switch (report) {
      BooksReport.sales => 'Sales',
      BooksReport.expenses => 'Expense',
      _ => 'Purchase',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Net total', booksMoney(data['total'])),
        ]),
        ReportTable(
          key: ObjectKey(data),
          title: '$name register',
          empty: 'No posted records in this period',
          columns: [
            reportText('Date', flex: .9),
            reportText('Document / party', flex: 1.5),
            reportText('Type', flex: 1.1),
            reportAmount('Taxable'),
            reportAmount('CGST'),
            reportAmount('SGST'),
            reportAmount('IGST'),
            reportAmount('Supplier tax'),
            reportAmount('GST in cost'),
            reportAmount('Total'),
          ],
          rows: [
            for (final row in reportRows(data['rows']))
              ReportTableRow([
                booksText(row['date']),
                ReportCell(
                  booksText(row['number']),
                  sub: booksText(row['party']),
                ),
                reportWords(row['kind']),
                booksMoney(row['taxable']),
                booksMoney(row['cgst']),
                booksMoney(row['sgst']),
                booksMoney(row['igst']),
                booksMoney(row['supplier_tax']),
                booksMoney(row['input_ineligible']),
                booksMoney(row['amount']),
              ]),
          ],
        ),
      ],
    );
  }

  Widget _financial() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Income', booksMoney(data['income'])),
          ReportMetric('Expenses', booksMoney(data['expenses'])),
          ReportMetric('Net profit', booksMoney(data['net_profit'])),
          ReportMetric('Assets', booksMoney(data['assets'])),
        ]),
        ReportPanelRow([
          ReportLinesPanel(
            title: asOf.isEmpty ? 'Balance sheet' : 'Balance sheet at $asOf',
            lines: [
              ('Assets', booksMoney(data['assets'])),
              ('Liabilities', booksMoney(data['liabilities'])),
              ('Equity', booksMoney(data['equity'])),
              ('Retained earnings', booksMoney(data['retained_earnings'])),
              ('Balance difference', booksMoney(data['balance_difference'])),
            ],
          ),
          ReportLinesPanel(
            title: 'Profit and loss',
            lines: [
              ('Income', booksMoney(data['income'])),
              ('Expenses and cost of goods sold', booksMoney(data['expenses'])),
              ('Net profit', booksMoney(data['net_profit'])),
            ],
          ),
        ]),
        ReportTable(
          key: ObjectKey(data),
          title: 'Account balances',
          empty: 'No ledger accounts are available.',
          columns: [
            reportText('Account', flex: 2),
            reportText('Category'),
            reportAmount('Period'),
            reportAmount('Closing'),
          ],
          rows: [
            for (final row in reportRows(data['accounts']))
              ReportTableRow([
                booksText(row['code']).startsWith('BANK-')
                    ? booksText(row['name'])
                    : '${booksText(row['code'])} · ${booksText(row['name'])}',
                booksText(row['category']),
                booksMoney(row['period_balance']),
                booksMoney(row['closing_balance']),
              ]),
          ],
        ),
        const ReportInfoBox(
          'Linked tracked purchases are carried as inventory at cost; tracked sales post cost of goods sold. Net realisable value write-downs and depreciation are not calculated.',
        ),
      ],
    );
  }

  Widget _ageing() {
    final totals = booksObject(data['totals']);
    final buckets = booksObject(data['buckets']);
    final receivable = booksObject(buckets['receivable']);
    final payable = booksObject(buckets['payable']);
    final basis = booksText(data['basis']);
    final date = booksText(data['as_of']).isEmpty
        ? asOf
        : booksText(data['as_of']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Receivable', booksMoney(totals['receivable'])),
          ReportMetric('Payable', booksMoney(totals['payable'])),
        ]),
        ReportTable(
          key: ObjectKey(buckets),
          title: 'Age buckets · as of $date',
          empty: 'No balances were outstanding on this date.',
          columns: [
            reportText('Document age'),
            reportAmount('Receivable'),
            reportAmount('Payable'),
          ],
          rows: [
            for (final age in ['0-30', '31-60', '61-90', '91+'])
              ReportTableRow([
                '$age days',
                booksMoney(receivable[age]),
                booksMoney(payable[age]),
              ]),
          ],
        ),
        ReportTable(
          key: ObjectKey(data),
          title: 'Open documents',
          empty: 'No open documents as of this date',
          columns: [
            reportText('Party / document', flex: 1.8),
            reportText('Type'),
            reportText('Date'),
            reportAmount('Age'),
            reportAmount('Original'),
            reportAmount('Applied'),
            reportAmount('Outstanding'),
          ],
          rows: [for (final row in reportRows(data['rows'])) _ageingRow(row)],
        ),
        ReportInfoBox(
          basis.isEmpty
              ? 'Age buckets use the document date. Where entered, the due date and days overdue are shown separately. Payments and linked notes dated through the selected day reduce open amounts. Manual ledger adjustments are not allocated to individual documents.'
              : basis,
        ),
      ],
    );
  }

  ReportTableRow _ageingRow(BooksJson row) {
    final id = booksText(row['document_id']);
    final due = booksText(row['due_date']);
    final overdue = num.tryParse(booksText(row['overdue_days'])) ?? 0;
    return ReportTableRow(onTap: id.isEmpty ? null : () => onOpenRecord(id), [
      ReportCell(
        booksText(row['party']),
        sub: [
          booksText(row['number']),
          if (due.isNotEmpty)
            'Due $due${overdue > 0 ? ' · $overdue days overdue' : ''}',
        ].where((value) => value.isNotEmpty).join('\n'),
      ),
      row['kind'] == 'sales_invoice' ? 'Receivable' : 'Payable',
      booksText(row['date']),
      '${booksText(row['age_days'])} days',
      booksMoney(row['original_amount']),
      booksMoney(row['applied_amount']),
      booksMoney(row['outstanding']),
    ]);
  }

  Widget _stock() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      ReportTable(
        key: ObjectKey(data),
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
        ],
        rows: [
          for (final row in reportRows(data['rows']))
            ReportTableRow(
              onTap: booksText(row['item_id']).isEmpty
                  ? null
                  : () => onOpenRecord(booksText(row['item_id'])),
              [
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
              ],
            ),
        ],
      ),
      const ReportInfoBox(
        'Only documents linked to stock-tracked item masters affect this report. Opening stock can be posted once for an item before its first movement. Count adjustments are shown separately and post gains or losses to the ledger. Closing cost uses moving weighted average for newly tracked stock. Net realisable value adjustments and other valuation cases still need review.',
      ),
    ],
  );
}
