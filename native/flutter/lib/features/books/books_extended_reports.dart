part of 'books_report_content.dart';

String _sumAmounts(Object? values) {
  if (values is! Map) return booksMoney('0');
  var total = 0.0;
  for (final value in values.values) {
    total += num.tryParse(booksText(value)) ?? 0;
  }
  return booksMoney(total.toStringAsFixed(2));
}

extension on BooksReportContent {
  Widget _partyStatement() {
    final note = booksText(data['ordering_note']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric(
            'Opening receivable',
            booksMoney(data['opening_receivable']),
          ),
          ReportMetric('Opening payable', booksMoney(data['opening_payable'])),
          ReportMetric(
            'Closing receivable',
            booksMoney(data['closing_receivable']),
          ),
          ReportMetric('Closing payable', booksMoney(data['closing_payable'])),
        ]),
        ReportTable(
          key: ObjectKey(data),
          title: '${party.isEmpty ? 'All parties' : party} · Statement',
          subtitle: note.isEmpty ? null : note,
          empty: 'No activity in this period',
          columns: [
            reportText('Date', flex: .9),
            reportText('Party / reference', flex: 1.6),
            reportText('Type', flex: 1.1),
            reportAmount('Amount'),
            reportAmount('Receivable'),
            reportAmount('Payable'),
          ],
          rows: [
            for (final row in reportRows(data['rows']))
              ReportTableRow([
                booksText(row['date']),
                ReportCell(
                  booksText(row['party']),
                  sub: booksText(row['number']),
                ),
                reportWords(row['kind']),
                booksMoney(row['amount']),
                booksMoney(row['receivable']),
                booksMoney(row['payable']),
              ]),
          ],
        ),
        const ReportInfoBox(
          'Party names are matched by text. Posted opening balances and settlements are included; activity before the selected start date forms the opening balance.',
        ),
      ],
    );
  }

  Widget _unapplied() {
    final totals = booksObject(data['totals']);
    final isCredit = report == BooksReport.credits;
    final date = booksText(data['as_of']).isEmpty
        ? asOf
        : booksText(data['as_of']);
    String applied(BooksJson row) {
      if (!isCredit) return booksMoney(row['applied']);
      final issued = num.tryParse(booksText(row['issued']));
      final offset = num.tryParse(booksText(row['original_offset']));
      final available = num.tryParse(booksText(row['available']));
      if (issued == null || offset == null || available == null) return '—';
      return booksMoney((issued - offset - available).toStringAsFixed(2));
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Customer balance', booksMoney(totals['customer'])),
          ReportMetric('Supplier balance', booksMoney(totals['supplier'])),
        ]),
        ReportTable(
          key: ObjectKey(data),
          title: '${isCredit ? 'Credit' : 'Advance'} balances as of $date',
          empty: 'No balances to display',
          columns: [
            reportText('Date', flex: .9),
            reportText('Reference / party', flex: 1.5),
            reportText('Side', flex: .8),
            reportAmount('Original'),
            if (isCredit) reportAmount('Original offset'),
            reportAmount(
              isCredit ? 'Later applied / refunded' : 'Applied / refunded',
            ),
            reportAmount('Available'),
          ],
          rows: [
            for (final row in reportRows(data['rows']))
              ReportTableRow(
                onTap: booksText(row['id']).isEmpty
                    ? null
                    : () => onOpenRecord(booksText(row['id'])),
                [
                  booksText(row['date']),
                  ReportCell(
                    booksText(row['number']),
                    sub: booksText(row['party']),
                  ),
                  booksText(row['side']),
                  booksMoney(row['issued'] ?? row['amount']),
                  if (isCredit) booksMoney(row['original_offset']),
                  applied(row),
                  booksMoney(row['available']),
                ],
              ),
          ],
        ),
      ],
    );
  }

  Widget _items() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      ReportTable(
        key: ObjectKey(data),
        title: 'Item activity',
        empty: 'No posted item activity',
        columns: [
          reportText('Item / HSN', flex: 1.8),
          reportAmount('Net before period'),
          reportAmount('Purchased net'),
          reportAmount('Sold net'),
          reportAmount('Net through end date'),
          reportAmount('Sales value'),
        ],
        rows: [
          for (final row in reportRows(data['rows']))
            ReportTableRow([
              ReportCell(booksText(row['name']), sub: booksText(row['hsn'])),
              booksText(row['opening_quantity']),
              booksText(row['purchased_quantity']),
              booksText(row['sold_quantity']),
              booksText(row['closing_quantity']),
              booksMoney(row['sales_value']),
            ]),
        ],
      ),
      const ReportInfoBox(
        'Purchase/sales document movement only, grouped by description and HSN/SAC. Stock introductions and adjustments are excluded; these net quantities are not stock on hand. Use the tracked stock report for on-hand quantities and moving-average cost value.',
      ),
    ],
  );

  Widget _gstAnalysis() {
    if (data['applicable'] == false) {
      return const ReportInfoBox(
        'This regular-GST analysis does not apply to the selected company profile or period. Composition and unregistered purchases can still show supplier GST included in cost in the purchase register.',
      );
    }
    final totals = booksObject(data['totals']);
    final inward = booksObject(totals['inward']);
    final outward = booksObject(totals['outward']);
    final documents = booksText(data['document_count']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Outward supply value', booksMoney(outward['taxable'])),
          ReportMetric('Output GST', booksMoney(outward['tax'])),
          ReportMetric(
            'Input pending review',
            booksMoney(inward['pending_input']),
          ),
          ReportMetric('GST in cost', booksMoney(inward['ineligible_input'])),
        ]),
        ReportTable(
          key: ObjectKey(data),
          title: 'GST by supply class and rate',
          subtitle: documents.isEmpty
              ? null
              : '$documents posted GST documents in this period',
          empty: 'No posted GST documents in this period',
          columns: [
            reportText('Side', flex: .9),
            reportText('Classification', flex: 1.3),
            reportAmount('Rate', flex: .7),
            reportAmount('Supply value'),
            reportAmount('Tax'),
            reportAmount('Input pending'),
            reportAmount('Input in cost'),
          ],
          rows: [
            for (final row in reportRows(data['rows']))
              ReportTableRow([
                row['side'] == 'outward' ? 'Sales' : 'Purchases',
                reportWords(row['treatment']),
                '${booksText(row['gst_rate'])}%',
                booksMoney(row['taxable']),
                booksMoney(row['tax']),
                booksMoney(row['pending_input']),
                booksMoney(row['ineligible_input']),
              ]),
          ],
        ),
        ReportInfoBox(
          '${booksText(data['note'])} Input tax is pending review, not a claimed credit. Credit and debit notes reduce the related totals.',
        ),
      ],
    );
  }

  Widget _gstReturn() {
    final columns = reportRows(data['columns']);
    final schedules = data['return_tables'];
    final export = data['export_info'];
    final standard = booksText(data['standard']);
    final tables = schedules is List && schedules.isNotEmpty
        ? reportRows(schedules)
        : [
            {
              'name': 'Register',
              'title': data['title'],
              'headers': [for (final c in columns) c['label']],
              'rows': [
                for (final row in reportRows(data['rows']))
                  [for (final c in columns) row[c['key']]],
              ],
              'money_columns': [
                for (final (i, c) in columns.indexed)
                  if (const {
                    'taxable',
                    'cgst',
                    'sgst',
                    'igst',
                    'total',
                    'proposed_itc',
                    'ineligible',
                  }.contains(c['key']))
                    i,
              ],
            },
          ];
    final hsn = reportRows(data['hsn']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ReportMetricGrid([
          ReportMetric('Output GST', _sumAmounts(data['output'])),
          ReportMetric(
            'Input from entered bills',
            _sumAmounts(data['book_itc']),
          ),
          ReportMetric(
            'Estimated cash payable',
            booksMoney(data['cash_total']),
          ),
        ]),
        if (export is BooksJson) _gstExportNotes(export, standard),
        for (final table in tables) _gstSchedule(table),
        ReportInfoBox(booksText(data['note'])),
        if (hsn.isNotEmpty)
          ReportTable(
            key: ObjectKey(hsn),
            title: 'HSN / SAC summary',
            empty: 'No HSN / SAC rows',
            columns: [
              reportText('HSN/SAC'),
              reportText('Rate'),
              reportText('Qty'),
              reportText('Base'),
              reportText('GST'),
            ],
            rows: [
              for (final row in hsn)
                ReportTableRow([
                  booksText(row['hsn']).isEmpty
                      ? 'Not entered'
                      : booksText(row['hsn']),
                  '${booksText(row['rate'])}%',
                  booksText(row['quantity']),
                  booksMoney(row['taxable']),
                  booksMoney(row['tax']),
                ]),
            ],
          ),
      ],
    );
  }

  Widget _gstExportNotes(BooksJson export, String standard) {
    final issues = reportRows(export['issues']);
    final warnings = export['warnings'] is List
        ? (export['warnings'] as List).map(booksText).where((m) => m.isNotEmpty)
        : const <String>[];
    final schedules = reportRows(export['schedules']);
    final intro = switch (standard) {
      'GSTR-1' =>
        'Section worksheets follow GSTN ${booksText(export['template'])}. Review the XLSX or draft JSON in the current offline tool before upload.',
      'GSTR-2A' => 'Purchase-book workbook: supplier bills, buyer-issued purchase returns and unregistered suppliers. Supplier filing details need the portal GSTR-2A.',
      _ => 'Numbered 3B schedules with a separate book estimate. Blank fields require external records; they do not mean zero.',
    };
    return ReportPanel(
      title: 'Export format & preparation checks',
      padded: true,
      child: Builder(
        builder: (context) => Material(
          type: MaterialType.transparency,
          child: Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  intro,
                  style: const TextStyle(
                    fontSize: 14,
                    height: 1.6,
                    color: Apex.muted,
                  ),
                ),
                if (issues.isNotEmpty)
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(
                      '${issues.length} preparation ${issues.length == 1 ? 'check' : 'checks'}${standard == 'GSTR-1' ? ' · JSON unavailable until resolved' : ' · review before use'}',
                      style: Apex.strong,
                    ),
                    children: [
                      for (final issue in issues)
                        ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            booksText(issue['document']),
                            style: Apex.strong,
                          ),
                          subtitle: Text(booksText(issue['message'])),
                        ),
                    ],
                  ),
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: const Text(
                    'Included schedules & review notes',
                    style: Apex.strong,
                  ),
                  expandedAlignment: Alignment.centerLeft,
                  children: [
                    if (schedules.isNotEmpty)
                      Text(
                        schedules
                            .map(
                              (s) =>
                                  '${booksText(s['name'])} (${booksText(s['rows'])})',
                            )
                            .join(' · '),
                        style: Apex.note,
                      ),
                    for (final message in warnings)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text('• $message', style: Apex.note),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _gstSchedule(BooksJson section) {
    final headers = section['headers'] is List
        ? (section['headers'] as List).map(booksText).toList()
        : <String>[];
    final money = section['money_columns'] is List
        ? (section['money_columns'] as List).whereType<num>().toSet()
        : <num>{};
    final values =
        (section['rows'] is List ? section['rows'] as List : const [])
            .whereType<List>()
            .toList();
    final title = booksText(section['title']).isEmpty
        ? booksText(section['name'])
        : booksText(section['title']);
    return ReportTable(
      key: ObjectKey(section),
      title: title,
      empty: 'No applicable entries in this period.',
      minColumnWidth: 128,
      columns: [
        for (final (i, header) in headers.indexed)
          ApexColumn(header, alignEnd: money.contains(i)),
      ],
      rows: [
        for (final row in values)
          ReportTableRow([
            for (var i = 0; i < headers.length; i++)
              i >= row.length || row[i] == null
                  ? 'Needs review'
                  : money.contains(i)
                  ? booksMoney(row[i])
                  : booksText(row[i]),
          ]),
      ],
    );
  }

  Widget _trialBalance() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      ReportMetricGrid([
        ReportMetric('Debits', booksMoney(data['total_debit'])),
        ReportMetric('Credits', booksMoney(data['total_credit'])),
      ]),
      ReportTable(
        key: ObjectKey(data),
        title: 'Trial balance',
        empty: 'No ledger accounts were found.',
        columns: [
          reportText('Account', flex: 2),
          reportAmount('Debit'),
          reportAmount('Credit'),
        ],
        rows: [
          for (final row in reportRows(data['accounts']))
            ReportTableRow([
              ReportCell(booksText(row['name']), sub: booksText(row['code'])),
              booksMoney(row['debit']),
              booksMoney(row['credit']),
            ]),
        ],
      ),
    ],
  );
}
