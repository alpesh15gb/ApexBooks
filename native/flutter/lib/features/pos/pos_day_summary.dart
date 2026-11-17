import 'pos_models.dart';

/// Pure port of the web `posRegisterSummary.js`: the daily POS tender totals,
/// the drawer-count worksheet and its CSV export. All amounts are paise.
BigInt? parseDrawerMoney(String? value) {
  final match = RegExp(
    r'^(\d{1,13})(?:\.(\d{1,2}))?$',
  ).firstMatch((value ?? '').trim());
  if (match == null) return null;
  return BigInt.parse('${match[1]}${(match[2] ?? '').padRight(2, '0')}');
}

String _decimal(BigInt paise) {
  final absolute = paise.abs();
  final fraction = (absolute % BigInt.from(100)).toString().padLeft(2, '0');
  return '${paise.isNegative ? '-' : ''}${absolute ~/ BigInt.from(100)}.$fraction';
}

/// "₹1,234.50", with a leading minus for negatives, in Indian digit grouping.
String drawerMoneyText(BigInt paise) => registerMoneyText(paise);

({BigInt cash, BigInt bank})? _tenderAmounts(PosJson record) {
  final amount = _paise(record['amount']);
  if (amount == null || amount == BigInt.zero) return null;
  final data = record['data'] is Map<String, dynamic>
      ? record['data'] as PosJson
      : const <String, dynamic>{};
  final method = data['payment_account'] ?? 'cash';
  if (method == 'cash') return (cash: amount, bank: BigInt.zero);
  if (method == 'bank') return (cash: BigInt.zero, bank: amount);
  if (method == 'split' && record['kind'] == 'pos') {
    final cash = _paise(data['cash_amount']);
    final bank = _paise(data['bank_amount']);
    if (cash != null &&
        bank != null &&
        cash > BigInt.zero &&
        bank > BigInt.zero &&
        cash + bank == amount) {
      return (cash: cash, bank: bank);
    }
  }
  return null;
}

BigInt? _paise(Object? value) => parseDrawerMoney(posText(value));

bool _active(PosJson? record) =>
    record != null && record['posted'] == true && record['cancelled'] != true;

PosJson? _data(PosJson? record) =>
    record?['data'] is Map<String, dynamic> ? record!['data'] as PosJson : null;

class PosDayRow {
  const PosDayRow({
    required this.kind,
    required this.number,
    required this.receipt,
    required this.cash,
    required this.bank,
  });

  final String kind;
  final String number;
  final String receipt;
  final BigInt cash;
  final BigInt bank;
}

class PosDay {
  int saleCount = 0;
  int refundCount = 0;
  int cancelledCount = 0;
  int unresolvedCount = 0;
  BigInt cashSales = BigInt.zero;
  BigInt bankSales = BigInt.zero;
  BigInt cashRefunds = BigInt.zero;
  BigInt bankRefunds = BigInt.zero;
  final List<PosDayRow> rows = [];
}

PosDay summarizePosDay(List<PosJson> records, String date) {
  final byId = {for (final record in records) posText(record['id']): record};
  final day = PosDay();
  for (final record in records) {
    if (record['date'] != date) continue;
    PosJson? source = record;
    final refund = record['kind'] == 'customer_refund';
    if (refund) {
      final credit = byId[posText(_data(record)?['credit_note_id'])];
      source = credit?['kind'] == 'credit_note'
          ? byId[posText(_data(credit)?['applied_to'])]
          : null;
      if (!_active(credit) || !_active(source)) continue;
    }
    if (source?['kind'] != 'pos') continue;
    if (record['cancelled'] == true) {
      if (!refund) day.cancelledCount++;
      continue;
    }
    if (!_active(record)) continue;
    if (refund) {
      day.refundCount++;
    } else {
      day.saleCount++;
    }
    final tender = _tenderAmounts(record);
    if (tender == null) {
      day.unresolvedCount++;
      continue;
    }
    if (refund) {
      day.cashRefunds += tender.cash;
      day.bankRefunds += tender.bank;
    } else {
      day.cashSales += tender.cash;
      day.bankSales += tender.bank;
    }
    final number = posText(record['number']);
    final receipt = posText(source!['number']);
    day.rows.add(
      PosDayRow(
        kind: refund ? 'Refund' : 'Sale',
        number: number.isEmpty ? posText(record['id']) : number,
        receipt: receipt.isEmpty ? posText(source['id']) : receipt,
        cash: tender.cash,
        bank: tender.bank,
      ),
    );
  }
  return day;
}

class CashCountField {
  const CashCountField(this.key, this.label, {this.required = false});
  final String key;
  final String label;
  final bool required;
}

const cashCountFields = [
  CashCountField('openingFloat', 'Opening float', required: true),
  CashCountField('cashIn', 'Other cash added'),
  CashCountField('cashOut', 'Other cash removed'),
  CashCountField('cashCounted', 'Cash counted', required: true),
];

class PosReconciliation {
  const PosReconciliation({
    required this.figures,
    required this.invalidFields,
    required this.expected,
    required this.variance,
  });

  final Map<String, BigInt?> figures;
  final List<String> invalidFields;
  final BigInt? expected;
  final BigInt? variance;
}

PosReconciliation reconcilePosCash(PosDay day, Map<String, String> entries) {
  final invalid = <String>[];
  final figures = <String, BigInt?>{};
  for (final field in cashCountFields) {
    final value = (entries[field.key] ?? '').trim();
    final amount = value.isNotEmpty || field.required
        ? parseDrawerMoney(value)
        : BigInt.zero;
    if (value.isNotEmpty && amount == null) invalid.add(field.key);
    figures[field.key] = amount;
  }
  final opening = figures['openingFloat'];
  final cashIn = figures['cashIn'];
  final cashOut = figures['cashOut'];
  final counted = figures['cashCounted'];
  final expected =
      day.unresolvedCount > 0 ||
          opening == null ||
          cashIn == null ||
          cashOut == null
      ? null
      : opening + day.cashSales - day.cashRefunds + cashIn - cashOut;
  return PosReconciliation(
    figures: figures,
    invalidFields: invalid,
    expected: expected,
    variance: expected == null || counted == null ? null : counted - expected,
  );
}

String _csvText(String text) {
  // Company names and document numbers can begin with spreadsheet formulas.
  final unsafe =
      RegExp(r'^[\s\u0000-\u001F]*[=+\-@]').hasMatch(text) ||
      RegExp(r'^[\t\r\n]').hasMatch(text);
  final safe = unsafe ? "'$text" : text;
  return '"${safe.replaceAll('"', '""')}"';
}

String posCloseCsv({
  required String companyName,
  required String date,
  required PosDay day,
  required PosReconciliation reconciliation,
}) {
  final variance = reconciliation.variance;
  if (variance == null) {
    throw const FormatException('Enter valid drawer counts before exporting.');
  }
  final figures = reconciliation.figures;
  final header = <List<String>>[
    ['Company', _csvText(companyName)],
    ['Business date', _csvText(date)],
    ['Scope', 'Company-wide POS sales and linked refunds'],
    ['Posted sales', '${day.saleCount}'],
    ['Posted linked refunds', '${day.refundCount}'],
    ['Cancelled receipts excluded', '${day.cancelledCount}'],
    ['Figure', 'INR'],
  ];
  final totals = <List<String>>[
    for (final (label, value) in [
      ('Cash sales', day.cashSales),
      ('Cash refunds', day.cashRefunds),
      ('Bank / UPI / card sales', day.bankSales),
      ('Bank / UPI / card refunds', day.bankRefunds),
      ('Opening float', figures['openingFloat']!),
      ('Other cash added', figures['cashIn']!),
      ('Other cash removed', figures['cashOut']!),
      ('Expected cash', reconciliation.expected!),
      ('Counted cash', figures['cashCounted']!),
      ('Cash over / short', variance),
    ])
      [label, _decimal(value)],
  ];
  final detail = <List<String>>[
    [
      'Type',
      'Document number',
      'Original POS receipt',
      'Cash (INR)',
      'Bank / UPI / card (INR)',
    ],
    for (final row in day.rows)
      [
        row.kind,
        _csvText(row.number),
        _csvText(row.receipt),
        _decimal(row.cash),
        _decimal(row.bank),
      ],
  ];
  final lines = [...header, ...totals, <String>[], ...detail];
  return '﻿${lines.map((row) => row.join(',')).join('\r\n')}\r\n';
}
