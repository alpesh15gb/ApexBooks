import '../../core/workspace.dart';
import 'bank_data.dart';

/// Header aliases, ported from the web app's StatementImportPreview.jsx.
const statementAliases = <String, List<String>>{
  'date': ['date', 'transactiondate', 'txndate', 'valuedate', 'postingdate'],
  'description': ['description', 'narration', 'particulars', 'remarks', 'details'],
  'reference': [
    'reference',
    'referenceno',
    'refno',
    'chequeno',
    'utr',
    'transactionid',
  ],
  'amount': ['amount', 'transactionamount', 'netamount'],
  'debit': ['debit', 'withdrawal', 'withdrawals', 'debitamount', 'withdrawalamt'],
  'credit': ['credit', 'deposit', 'deposits', 'creditamount', 'depositamt'],
};

const statementFields = ['date', 'description', 'reference', 'amount', 'debit', 'credit'];

String normalizeStatementHeader(String value) =>
    value.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');

bool _isDateHeader(String value) =>
    statementAliases['date']!.contains(normalizeStatementHeader(value));

/// Splits the CSV into trimmed rows, sniffing tab, semicolon or comma.
List<List<String>> statementTable(String input) {
  if (input.length > 1024 * 1024 || input.contains('\u0000')) {
    throw const FormatException('Use a UTF-8 CSV file below 1 MB.');
  }
  final sample = input.split(RegExp(r'\r?\n')).take(20).toList();
  int score(String sep) {
    var best = 0;
    for (final line in sample) {
      final values = line.split(sep);
      final value = values.any(_isDateHeader) ? values.length * 10 : values.length;
      if (value > best) best = value;
    }
    return best;
  }

  final candidates = ['\t', ';', ','];
  var sep = candidates.first;
  for (final candidate in candidates.skip(1)) {
    if (score(candidate) > score(sep)) sep = candidate;
  }
  final text = input.startsWith('﻿') ? input.substring(1) : input;
  final rows = <List<String>>[];
  var row = <String>[];
  final field = StringBuffer();
  var quoted = false;
  var closed = false;
  var line = 1;
  void cell() {
    row.add(field.toString());
    field.clear();
    closed = false;
  }

  void finish() {
    cell();
    if (row.any((value) => value.trim().isNotEmpty)) rows.add(row);
    row = [];
  }

  for (var i = 0; i < text.length; i++) {
    final ch = text[i];
    final next = i + 1 < text.length ? text[i + 1] : '';
    if (quoted) {
      if (ch == '"') {
        if (next == '"') {
          field.write('"');
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else {
        field.write(ch);
        if (ch == '\n' || (ch == '\r' && next != '\n')) line++;
      }
      continue;
    }
    if (ch == sep) {
      cell();
      continue;
    }
    if (ch == '\n' || ch == '\r') {
      if (ch == '\r' && next == '\n') i++;
      finish();
      line++;
      continue;
    }
    if (closed) {
      if (ch == ' ' || ch == '\t') continue;
      throw FormatException('CSV row $line: unexpected text after a closing quote.');
    }
    if (ch == '"') {
      if (field.isNotEmpty) {
        throw FormatException('CSV row $line: quote must begin a field.');
      }
      quoted = true;
    } else {
      field.write(ch);
    }
  }
  if (quoted) throw FormatException('CSV row $line: unclosed quoted field.');
  finish();
  if (rows.length > 5021) {
    throw const FormatException('Import up to 5,000 transactions per CSV');
  }
  return [
    for (final r in rows)
      [for (final value in r) value.replaceAll('﻿', '').trim()],
  ];
}

/// First row containing a date header (0 when none).
int detectStatementHeader(List<List<String>> rows) {
  final index = rows.indexWhere((row) => row.any(_isDateHeader));
  return index < 0 ? 0 : index;
}

/// Maps each field to the first column whose header matches an alias.
Map<String, int?> detectStatementMapping(List<String> headers) => {
  for (final entry in statementAliases.entries)
    entry.key: () {
      final index = headers.indexWhere(
        (h) => entry.value.contains(normalizeStatementHeader(h)),
      );
      return index < 0 ? null : index;
    }(),
};

String statementAmount(String raw) {
  var value = raw.replaceAll(RegExp(r'[₹,\s]'), '');
  if (value.isEmpty) return '';
  if (RegExp(r'^\(.*\)$').hasMatch(value)) {
    value = '-${value.substring(1, value.length - 1)}';
  }
  final suffix = RegExp(r'(Cr|Dr)$', caseSensitive: false).firstMatch(value);
  if (suffix != null) {
    value = value.substring(0, value.length - 2);
    if (suffix.group(1)!.toLowerCase() == 'dr' && !value.startsWith('-')) {
      value = '-$value';
    }
  }
  if (!RegExp(r'^[+-]?\d+(\.\d{1,2})?$').hasMatch(value)) {
    throw const FormatException('invalid amount');
  }
  return value;
}

const _months = [
  'january', 'february', 'march', 'april', 'may', 'june', 'july',
  'august', 'september', 'october', 'november', 'december',
];

/// Returns YYYY-MM-DD. [dmy] picks day-first for numeric dates, as in React.
/// Two-digit years (DD/MM/YY, common in Indian bank exports) are read as 20YY.
String statementDate(String raw, {required bool dmy}) {
  int y, m, d;
  RegExpMatch? parts = RegExp(r'^(\d{4})-(\d{1,2})-(\d{1,2})$').firstMatch(raw);
  if (parts != null) {
    y = int.parse(parts.group(1)!);
    m = int.parse(parts.group(2)!);
    d = int.parse(parts.group(3)!);
  } else if ((parts = RegExp(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})$').firstMatch(raw)) != null) {
    final year = parts!.group(3)!;
    y = int.parse(year.length == 2 ? '20$year' : year);
    d = int.parse(parts.group(dmy ? 1 : 2)!);
    m = int.parse(parts.group(dmy ? 2 : 1)!);
  } else if ((parts = RegExp(r'^(\d{1,2})[- /]+([A-Za-z]{3,9})[- /,]+(\d{4}|\d{2})$').firstMatch(raw)) != null) {
    d = int.parse(parts!.group(1)!);
    final year = parts.group(3)!;
    y = int.parse(year.length == 2 ? '20$year' : year);
    final name = parts.group(2)!.toLowerCase();
    m = _months.indexWhere((n) => n == name || n.substring(0, 3) == name) + 1;
  } else {
    throw const FormatException('invalid date');
  }
  final value = DateTime.utc(y, m, d);
  if (value.year != y || value.month != m || value.day != d) {
    throw const FormatException('invalid date');
  }
  return '${y.toString().padLeft(4, '0')}-${m.toString().padLeft(2, '0')}-${d.toString().padLeft(2, '0')}';
}

/// Builds the backend `lines` payload from a mapped table.
List<Json> buildStatementLines(
  List<List<String>> table, {
  required int header,
  required Map<String, int?> mapping,
  required bool dmy,
}) {
  if (mapping['date'] == null ||
      mapping['description'] == null ||
      (mapping['amount'] == null &&
          (mapping['debit'] == null || mapping['credit'] == null))) {
    throw const FormatException(
      'Map date, description and either amount or both debit and credit columns.',
    );
  }
  String get(List<String> cells, String key) {
    final index = mapping[key];
    return index == null || index >= cells.length ? '' : cells[index].trim();
  }

  final lines = <Json>[];
  final body = table.skip(header + 1).toList();
  for (var i = 0; i < body.length; i++) {
    final cells = body[i];
    try {
      BigInt? cents;
      if (mapping['amount'] != null) {
        final raw = statementAmount(get(cells, 'amount'));
        cents = raw.isEmpty ? null : signedMoney(raw);
      } else {
        final debitText = statementAmount(get(cells, 'debit'));
        final creditText = statementAmount(get(cells, 'credit'));
        final debit = signedMoney(debitText.isEmpty ? '0' : debitText)!;
        final credit = signedMoney(creditText.isEmpty ? '0' : creditText)!;
        if (debit.isNegative ||
            credit.isNegative ||
            (debit > BigInt.zero && credit > BigInt.zero)) {
          throw const FormatException('use one positive debit or credit');
        }
        cents = debit > BigInt.zero ? -debit : credit;
      }
      if (cents == null || cents == BigInt.zero) {
        throw const FormatException('amount is zero or empty');
      }
      final description = get(cells, 'description');
      if (description.isEmpty) {
        throw const FormatException('description is empty');
      }
      if (description.length > 500) {
        throw const FormatException('description is too long');
      }
      final reference = mapping['reference'] == null ? '' : get(cells, 'reference');
      if (reference.length > 120) throw const FormatException('reference is too long');
      lines.add({
        'date': statementDate(get(cells, 'date'), dmy: dmy),
        'description': description,
        'reference': reference,
        'amount': decimalMoney(cents),
      });
    } on FormatException catch (e) {
      throw FormatException('CSV row ${header + i + 2}: ${e.message}');
    }
  }
  if (lines.isEmpty || lines.length > 5000) {
    throw const FormatException('Choose a CSV containing 1–5,000 transactions');
  }
  return lines;
}

/// One-shot parse with automatic header and column detection.
List<Json> statementEntries(String csv, {bool dmy = true}) {
  final table = statementTable(csv);
  final header = detectStatementHeader(table);
  return buildStatementLines(
    table,
    header: header,
    mapping: detectStatementMapping(header < table.length ? table[header] : const []),
    dmy: dmy,
  );
}
