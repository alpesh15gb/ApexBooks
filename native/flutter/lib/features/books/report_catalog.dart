import 'books_data.dart';

/// The web app's report library: groups, wording and search keywords.
class ReportGroup {
  const ReportGroup(this.title, this.description, this.reports);
  final String title;
  final String description;
  final List<BooksReport> reports;
}

const reportGroups = <ReportGroup>[
  ReportGroup(
    'Business & transactions',
    'Understand performance and review the books.',
    [
      BooksReport.summary,
      BooksReport.sales,
      BooksReport.purchases,
      BooksReport.expenses,
      BooksReport.statements,
      BooksReport.financial,
      // Not in the web library; kept here so the trial balance stays reachable.
      BooksReport.trial,
    ],
  ),
  ReportGroup(
    'Parties & balances',
    'Follow collections, dues and unapplied balances.',
    [
      BooksReport.parties,
      BooksReport.ageing,
      BooksReport.credits,
      BooksReport.advances,
    ],
  ),
  ReportGroup(
    'GST preparation',
    'Review book figures before filing or claiming credit.',
    [
      BooksReport.gst,
      BooksReport.gstr1,
      BooksReport.gstr2a,
      BooksReport.gstr3b,
    ],
  ),
  ReportGroup(
    'Items & inventory',
    'Check item movement, quantities and stock value.',
    [BooksReport.items, BooksReport.stock],
  ),
];

/// "16 reports · PDF & XLSX" counts the web library's reports.
const reportLibraryCount = 16;

const _descriptions = <BooksReport, String>{
  BooksReport.summary: 'Sales, purchases, cash activity and balances',
  BooksReport.sales: 'Invoices, POS sales and credit notes',
  BooksReport.purchases: 'Supplier bills and debit notes',
  BooksReport.expenses: 'Business spending and supplier tax',
  BooksReport.statements:
      'Formatted statements with gross profit and classified balances',
  BooksReport.financial:
      'Every ledger account for the period and closing balance',
  BooksReport.parties: "A party's transactions and running balance",
  BooksReport.ageing: 'Outstanding amounts by age',
  BooksReport.credits: 'Available customer and supplier credits',
  BooksReport.advances: 'Unapplied receipts and supplier advances',
  BooksReport.gst: 'Output tax and supplier tax pending review',
  BooksReport.gstr1: 'Outward supplies working paper',
  BooksReport.gstr2a: 'Calculated from entered bills, not the GST portal',
  BooksReport.gstr3b: 'Liability and input tax working paper',
  BooksReport.items: 'Sales and purchase quantities by item / HSN',
  BooksReport.stock: 'Opening, movements, closing quantity and cost',
};

String reportDescription(BooksReport report) =>
    _descriptions[report] ?? report.subtitle;

String reportGroupTitle(BooksReport report) {
  for (final group in reportGroups) {
    if (group.reports.contains(report)) return group.title;
  }
  return '';
}

const _keywords = <BooksReport, String>{
  BooksReport.statements: 'profit loss profitability income expenses assets liabilities equity financial performance',
  BooksReport.ageing: 'who owes money overdue unpaid customer invoices supplier bills collect pay due receivable payable aging',
  BooksReport.stock: 'inventory quantity on hand value cost available',
  BooksReport.parties: 'customer supplier vendor ledger balance statement',
  BooksReport.credits: 'refund credit return remaining',
  BooksReport.advances: 'deposit prepayment advance unapplied',
};

bool reportMatches(ReportGroup group, BooksReport report, String search) {
  final words = search
      .trim()
      .toLowerCase()
      .split(RegExp(r'\s+'))
      .where((word) => word.isNotEmpty);
  final haystack =
      '${group.title} ${report.title} ${reportDescription(report)} ${_keywords[report] ?? ''}'
          .toLowerCase();
  return words.every(haystack.contains);
}

/// Report-view subtitle under the title; the Day book has none.
String reportSubtitle(BooksReport report) =>
    report == BooksReport.dayBook ? '' : reportDescription(report);
