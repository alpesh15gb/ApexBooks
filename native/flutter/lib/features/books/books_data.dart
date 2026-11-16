typedef BooksGet = Future<dynamic> Function(
  String path, {
  Map<String, String>? query,
});
typedef BooksJson = Map<String, dynamic>;

const booksKinds = <String, String>{
  'sales_invoice': 'Sales invoice',
  'pos': 'POS sale',
  'credit_note': 'Credit note',
  'purchase_bill': 'Purchase bill',
  'debit_note': 'Debit note',
  'payment_in': 'Payment in',
  'payment_out': 'Payment out',
  'expense': 'Expense',
  'purchase_order': 'Purchase order',
  'sales_order': 'Sales order',
  'estimate': 'Estimate',
  'proforma': 'Pro forma invoice',
  'opening_receivable': 'Opening receivable',
  'opening_payable': 'Opening payable',
  'customer_refund': 'Customer refund',
  'supplier_refund': 'Supplier refund',
  'advance_application': 'Advance application',
  'advance_refund': 'Advance refund',
  'credit_application': 'Credit application',
  'bank_transfer': 'Bank transfer',
  'stock_opening': 'Opening stock',
  'stock_adjustment': 'Stock adjustment',
  'journal': 'Journal',
};

String booksKindLabel(String kind) => booksKinds[kind] ?? 'Transaction';

BooksJson booksObject(Object? value) {
  if (value is! Map<String, dynamic>) {
    throw const FormatException('Expected a record');
  }
  return value;
}

List<BooksJson> booksRows(Object? value) {
  if (value is! List) throw const FormatException('Expected a list of records');
  return List<BooksJson>.unmodifiable(value.map(booksObject));
}

String booksText(Object? value) => switch (value) {
  String() => value.trim(),
  num() => value.toString(),
  _ => '',
};

String booksMoney(Object? value) {
  final match = RegExp(r'^([+-]?)(\d+)(?:\.(\d+))?$')
      .firstMatch(booksText(value));
  if (match == null) return '—';
  final fraction = match.group(3) ?? '';
  final padded = fraction.padRight(3, '0');
  final cents =
      BigInt.parse(match.group(2)!) * BigInt.from(100) +
      BigInt.parse(padded.substring(0, 2)) +
      (int.parse(padded[2]) >= 5 ? BigInt.one : BigInt.zero);
  var rupees = (cents ~/ BigInt.from(100)).toString();
  var suffix = '';
  if (rupees.length > 3) {
    suffix = ',${rupees.substring(rupees.length - 3)}';
    rupees = rupees.substring(0, rupees.length - 3);
    while (rupees.length > 2) {
      suffix = ',${rupees.substring(rupees.length - 2)}$suffix';
      rupees = rupees.substring(0, rupees.length - 2);
    }
  }
  final sign = match.group(1) == '-' && cents != BigInt.zero ? '−' : '';
  return '$sign₹$rupees$suffix.${(cents % BigInt.from(100)).toString().padLeft(2, '0')}';
}

String booksDate(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

class BooksRecord {
  BooksRecord(this.json) {
    if (id.isEmpty || kind.isEmpty) {
      throw const FormatException('Missing record identity');
    }
  }

  final BooksJson json;
  String get id => booksText(json['id']);
  String get kind => booksText(json['kind']);
  String get number => booksText(json['number']);
  String get party => booksText(json['name']);
  String get date => booksText(json['date']);
  String get label => number.isNotEmpty ? number : booksKindLabel(kind);
  BooksJson get data =>
      json['data'] is BooksJson ? json['data'] as BooksJson : const {};

  bool get isTransaction =>
      !const {'item', 'party', 'bank_account'}.contains(kind);

  String get status {
    if (json['cancelled'] == true) return 'Cancelled';
    if (booksText(json['converted_to']).isNotEmpty) return 'Converted';
    if (kind == 'purchase_order' &&
        data['purchase_order_receiving_started'] == true) {
      return 'Receiving started';
    }
    if (json['posted'] == true || json['stock_posted'] == true) return 'Posted';
    if (const {
      'estimate',
      'proforma',
      'sales_order',
      'purchase_order',
    }.contains(kind)) {
      return 'Draft';
    }
    return 'Unposted';
  }

  bool matches(String query) {
    final fields = [
      number,
      party,
      date,
      booksKindLabel(kind),
      booksText(data['reference']),
    ].join(' ').toLowerCase();
    return query
        .toLowerCase()
        .trim()
        .split(RegExp(r'\s+'))
        .every(fields.contains);
  }
}

class BooksRecordPage {
  const BooksRecordPage(this.records, this.nextOffset, this.hasMore);

  final List<BooksRecord> records;
  final int nextOffset;
  final bool hasMore;
}

enum BooksReport {
  summary(
    'Transaction summary',
    'Sales, purchases, cash activity and balances',
    '/reports/summary',
  ),
  sales(
    'Sales register',
    'Invoices, POS sales and credit notes',
    '/reports/register',
    group: 'sales',
  ),
  purchases(
    'Purchase register',
    'Supplier bills and debit notes',
    '/reports/register',
    group: 'purchases',
  ),
  expenses(
    'Expense register',
    'Posted expenses and supplier tax',
    '/reports/register',
    group: 'expenses',
  ),
  statements(
    'Profit & loss and balance sheet',
    'Period earnings and classified balances',
    '/reports/statements',
  ),
  financial(
    'Account balances',
    'Period movement and closing balance by ledger account',
    '/reports/financial',
  ),
  ageing(
    'Receivables & payables ageing',
    'Unpaid balances and due dates',
    '/reports/ageing',
    singleDate: 'as_of',
  ),
  parties(
    'Party statement',
    'Customer and supplier movements and running balances',
    '/reports/parties',
  ),
  credits(
    'Credit balances',
    'Unapplied customer and supplier credit notes',
    '/reports/credits',
    singleDate: 'as_of',
  ),
  advances(
    'Advance balances',
    'Unapplied customer deposits and supplier advances',
    '/reports/advances',
    singleDate: 'as_of',
  ),
  gst(
    'GST analysis',
    'Posted tax and input credit pending review',
    '/reports/gst',
  ),
  gstr1('GSTR-1', 'Outward supplies working paper', '/gst-returns/gstr1'),
  gstr2a(
    'GSTR-2A · purchase books',
    'Supplier tax from entered bills and returns',
    '/gst-returns/gstr2a',
  ),
  gstr3b(
    'GSTR-3B',
    'Liability, input credit and estimated cash payable',
    '/gst-returns/gstr3b',
  ),
  items(
    'Item activity',
    'Sales and purchases by item and HSN',
    '/reports/items',
  ),
  stock(
    'Tracked stock',
    'Opening quantity, stock movements and closing value',
    '/reports/stock',
  ),
  dayBook(
    'Day book',
    'One day of transactions, journals and money movements',
    '/day-book',
    singleDate: 'day',
    exportable: false,
  ),
  trial(
    'Trial balance',
    'Debits and credits through a selected date',
    '/trial-balance',
    singleDate: 'through',
    exportable: false,
  );

  const BooksReport(
    this.title,
    this.subtitle,
    this.path, {
    this.group,
    this.singleDate,
    this.exportable = true,
  });

  final String title;
  final String subtitle;
  final String path;
  final String? group;
  final String? singleDate;
  final bool exportable;

  bool get asOfOnly => singleDate != null;
  bool get gstReturn => path.startsWith('/gst-returns/');

  Map<String, String> query(DateTime from, DateTime to, {String? party}) => {
    if (singleDate case final parameter?)
      parameter: booksDate(to)
    else ...{
      'from_date': booksDate(from),
      'to_date': booksDate(to),
    },
    'group': ?group,
    if (this == parties && (party?.trim().isNotEmpty ?? false))
      'party': party!.trim(),
  };
}

class BooksData {
  const BooksData(this.companyId, this._get);

  final String companyId;
  final BooksGet _get;

  String get _root => '/api/companies/${Uri.encodeComponent(companyId)}';

  Future<BooksRecordPage> records({
    String? kind,
    int offset = 0,
    int limit = 100,
  }) async {
    final result = await _get(
      '$_root/records',
      query: {
        'compact': 'true',
        'offset': '$offset',
        'limit': '$limit',
        'kind': ?kind,
      },
    );
    final rows = booksRows(result);
    return BooksRecordPage(
      List<BooksRecord>.unmodifiable(
        rows.map(BooksRecord.new).where((row) => row.isTransaction),
      ),
      offset + rows.length,
      rows.length == limit,
    );
  }

  Future<BooksRecord> record(String id) async {
    final record = BooksRecord(
      booksObject(await _get('$_root/records/${Uri.encodeComponent(id)}')),
    );
    if (record.id != id) {
      throw const FormatException('The record reference did not match');
    }
    return record;
  }

  Future<BooksJson> report(
    BooksReport report, {
    required DateTime from,
    required DateTime to,
    String? party,
  }) async {
    if (from.isAfter(to) && !report.asOfOnly) {
      throw ArgumentError('Choose an end date on or after the start date');
    }
    return booksObject(
      await _get(
        '$_root${report.path}',
        query: report.query(from, to, party: party),
      ),
    );
  }
}
