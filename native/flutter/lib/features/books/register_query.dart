import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';

/// Filtering, ordering and summary rules of the transaction register, mirroring
/// the web app's RegisterOverview / RegisterControls / registerOrder logic.

const registerInvoiceKinds = {'sales_invoice', 'purchase_bill'};
const registerDraftKinds = {
  'estimate',
  'proforma',
  'sales_order',
  'purchase_order',
};
const registerTransactionKinds = {
  'payment_in',
  'payment_out',
  'expense',
  'credit_note',
  'debit_note',
};

/// Number of rows per page, as in the web register.
const registerPageSize = 50;

class BooksRegisterQuery {
  const BooksRegisterQuery({
    this.period = 'all',
    this.from = '',
    this.to = '',
    this.party = '',
    this.sort = 'newest',
    this.tab = 'all',
    this.search = '',
  });

  final String period;
  final String from;
  final String to;
  final String party;
  final String sort;
  final String tab;
  final String search;

  BooksRegisterQuery copyWith({
    String? period,
    String? from,
    String? to,
    String? party,
    String? sort,
    String? tab,
    String? search,
  }) => BooksRegisterQuery(
    period: period ?? this.period,
    from: from ?? this.from,
    to: to ?? this.to,
    party: party ?? this.party,
    sort: sort ?? this.sort,
    tab: tab ?? this.tab,
    search: search ?? this.search,
  );

  /// Party and non-default sort: the filters hidden behind "More filters" on phones.
  int get extraFilters =>
      (party.isNotEmpty ? 1 : 0) + (sort != 'newest' ? 1 : 0);

  bool get hasFilters =>
      search.isNotEmpty ||
      from.isNotEmpty ||
      to.isNotEmpty ||
      party.isNotEmpty ||
      period != 'all' ||
      sort != 'newest' ||
      tab != 'all';
}

/// From/to dates of a period choice ("today", "month", …), on the business calendar.
({String from, String to}) registerPeriodDates(
  String period, [
  DateTime? clock,
]) {
  final today = businessToday(clock);
  String iso(int year, int month, int day) =>
      DateTime.utc(year, month, day).toIso8601String().substring(0, 10);
  final now = businessDate(clock);
  switch (period) {
    case 'all':
      return (from: '', to: '');
    case 'today':
      return (from: now, to: now);
    case 'month':
      return (
        from: iso(today.year, today.month, 1),
        to: iso(today.year, today.month + 1, 0),
      );
    case 'last_month':
      return (
        from: iso(today.year, today.month - 1, 1),
        to: iso(today.year, today.month, 0),
      );
    default:
      final year = today.year - (today.month < 4 ? 1 : 0);
      return (from: '$year-04-01', to: now);
  }
}

bool _flag(Object? value) => value == true;

double _number(Object? value) => double.tryParse(booksText(value)) ?? 0;

bool _hasOutstanding(BooksRecord r) {
  final text = booksText(r.json['outstanding']);
  return text.isNotEmpty && double.tryParse(text) != null;
}

bool registerPosted(BooksRecord r) =>
    _flag(r.json['posted']) && !_flag(r.json['cancelled']);

bool registerOpen(BooksRecord r) =>
    registerPosted(r) && _number(r.json['outstanding']) > 0;

bool registerSettled(BooksRecord r) =>
    registerPosted(r) &&
    _hasOutstanding(r) &&
    _number(r.json['outstanding']) == 0;

bool registerConverted(BooksRecord r) =>
    booksText(r.json['converted_to']).isNotEmpty;

bool registerActive(BooksRecord r) =>
    !registerConverted(r) && !_flag(r.json['cancelled']);

bool registerUnposted(BooksRecord r) =>
    r.json['posted'] == false && !_flag(r.json['cancelled']);

bool registerOverdue(BooksRecord r, String today) {
  final due = booksText(r.data['due_date']);
  return registerOpen(r) && due.isNotEmpty && due.compareTo(today) < 0;
}

/// Records inside the chosen dates and party (the web app's "scoped" records).
List<BooksRecord> registerScope(
  Iterable<BooksRecord> records,
  BooksRegisterQuery query,
) => [
  for (final r in records)
    if ((query.from.isEmpty || r.date.compareTo(query.from) >= 0) &&
        (query.to.isEmpty || r.date.compareTo(query.to) <= 0) &&
        (query.party.isEmpty || r.party == query.party))
      r,
];

bool registerTabMatches(
  String kind,
  BooksRecord r,
  String tab,
  String today,
) {
  if (tab == 'all') return true;
  if (kind.isEmpty) return r.status == tab;
  return switch (tab) {
    'unpaid' => registerOpen(r),
    'paid' => registerSettled(r),
    'overdue' => registerOverdue(r, today),
    'draft' => registerActive(r),
    'converted' => registerConverted(r),
    'posted' => registerPosted(r),
    'unposted' => registerUnposted(r),
    'cancelled' => _flag(r.json['cancelled']),
    _ => true,
  };
}

int _newestFirst(BooksRecord a, BooksRecord b) {
  final byDate = b.date.compareTo(a.date);
  if (byDate != 0) return byDate;
  final byCreated = booksText(
    b.data['created_at'],
  ).compareTo(booksText(a.data['created_at']));
  return byCreated != 0 ? byCreated : b.id.compareTo(a.id);
}

int registerCompare(BooksRecord a, BooksRecord b, String sort) {
  switch (sort) {
    case 'oldest':
      return _newestFirst(b, a);
    case 'amount':
      final byAmount = _number(
        b.json['amount'],
      ).compareTo(_number(a.json['amount']));
      return byAmount != 0 ? byAmount : _newestFirst(a, b);
    case 'balance':
      final byBalance = _number(
        b.json['outstanding'],
      ).compareTo(_number(a.json['outstanding']));
      return byBalance != 0 ? byBalance : _newestFirst(a, b);
    default:
      return _newestFirst(a, b);
  }
}

/// Scoped records narrowed by search text and status tab, ordered as chosen.
List<BooksRecord> registerVisible(
  String kind,
  List<BooksRecord> scoped,
  BooksRegisterQuery query,
  String today,
) =>
    [
      for (final r in scoped)
        if (registerTabMatches(kind, r, query.tab, today) &&
            r.matches(query.search))
          r,
    ]..sort((a, b) => registerCompare(a, b, query.sort));

class RegisterStat {
  const RegisterStat(this.label, this.value, this.icon);
  final String label;
  final String value;
  final IconData icon;
}

/// The summary cards above the register; none for the "All transactions" page.
List<RegisterStat> registerStats(String kind, List<BooksRecord> rows) {
  double sum(Iterable<BooksRecord> list, String key) =>
      list.fold(0.0, (total, r) => total + _number(r.json[key]));
  final posted = rows.where(registerPosted).toList();
  final open = posted.where(registerOpen).toList();
  if (registerInvoiceKinds.contains(kind)) {
    return [
      RegisterStat(
        'Posted value',
        apexMoney(sum(posted, 'amount')),
        Icons.description_outlined,
      ),
      RegisterStat(
        'Outstanding',
        apexMoney(sum(open, 'outstanding')),
        Icons.account_balance_wallet_outlined,
      ),
      RegisterStat('Unpaid documents', '${open.length}', Icons.schedule),
      RegisterStat(
        'Settled documents',
        '${rows.where(registerSettled).length}',
        Icons.done_all,
      ),
    ];
  }
  if (registerTransactionKinds.contains(kind)) {
    return [
      RegisterStat(
        'Posted value',
        apexMoney(sum(posted, 'amount')),
        Icons.account_balance_wallet_outlined,
      ),
      RegisterStat('Posted transactions', '${posted.length}', Icons.done_all),
      RegisterStat(
        'Unposted records',
        '${rows.where(registerUnposted).length}',
        Icons.schedule,
      ),
      RegisterStat(
        'Cancelled',
        '${rows.where((r) => _flag(r.json['cancelled'])).length}',
        Icons.done_all,
      ),
    ];
  }
  if (registerDraftKinds.contains(kind)) {
    final active = rows.where(registerActive).toList();
    return [
      RegisterStat(
        'Active drafts',
        '${active.length}',
        Icons.description_outlined,
      ),
      RegisterStat(
        'Draft value',
        apexMoney(sum(active, 'amount')),
        Icons.account_balance_wallet_outlined,
      ),
      RegisterStat(
        'Converted',
        '${rows.where(registerConverted).length}',
        Icons.done_all,
      ),
    ];
  }
  return const [];
}

/// Status tabs with counts: (key, label, count).
List<(String, String, int)> registerTabs(
  String kind,
  List<BooksRecord> rows,
  String today,
) {
  final cancelled = rows.where((r) => _flag(r.json['cancelled'])).length;
  if (registerInvoiceKinds.contains(kind)) {
    return [
      ('all', 'All', rows.length),
      ('unpaid', 'Unpaid', rows.where(registerOpen).length),
      ('paid', 'Settled', rows.where(registerSettled).length),
      ('overdue', 'Overdue', rows.where((r) => registerOverdue(r, today)).length),
      ('cancelled', 'Cancelled', cancelled),
    ];
  }
  if (registerTransactionKinds.contains(kind)) {
    return [
      ('all', 'All', rows.length),
      ('posted', 'Posted', rows.where(registerPosted).length),
      ('unposted', 'Unposted', rows.where(registerUnposted).length),
      ('cancelled', 'Cancelled', cancelled),
    ];
  }
  if (registerDraftKinds.contains(kind)) {
    return [
      ('all', 'All', rows.length),
      ('draft', 'Draft', rows.where(registerActive).length),
      ('converted', 'Converted', rows.where(registerConverted).length),
    ];
  }
  return [
    ('all', 'All', rows.length),
    for (final status in const [
      'Posted',
      'Draft',
      'Unposted',
      'Converted',
      'Receiving started',
      'Cancelled',
    ])
      (status, status, rows.where((r) => r.status == status).length),
  ];
}

/// Subtitles the web app shows under each register title.
const registerSubtitles = <String, String>{
  'payment_in': 'Record receipts and apply them to customer invoices.',
  'payment_out': 'Pay suppliers and track allocated payments.',
  'sales_invoice': 'Create invoices, follow collections and review balances.',
  'purchase_bill': 'Record supplier bills and keep track of what you owe.',
  'estimate': 'Prepare quotations and convert accepted work to invoices.',
  'expense': 'Record business spending and review expense categories.',
  'purchase_order': 'Review supplier orders and receive deliveries.',
};

/// The web row's status label (Posted, Open draft, Legacy · unposted, …).
String registerStatusLabel(BooksRecord r) {
  if (_flag(r.json['cancelled'])) return 'Cancelled';
  if (registerConverted(r)) return 'Converted';
  if (r.kind == 'purchase_order' &&
      r.data['purchase_order_receiving_started'] == true) {
    return 'Receiving started';
  }
  if (registerDraftKinds.contains(r.kind)) return 'Open draft';
  return r.json['posted'] == false ? 'Legacy · unposted' : 'Posted';
}

/// Unpaid / Part settled / Settled under an invoice's status.
String registerSettlement(BooksRecord r) {
  if (!_flag(r.json['posted']) ||
      _flag(r.json['cancelled']) ||
      !const {'sales_invoice', 'purchase_bill', 'pos'}.contains(r.kind) ||
      !_hasOutstanding(r)) {
    return '';
  }
  final balance = _number(r.json['outstanding']);
  if (balance <= 0) return 'Settled';
  return balance < _number(r.json['amount']) ? 'Part settled' : 'Unpaid';
}
