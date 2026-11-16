import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';
import '../shared/csv_rows.dart';

BigInt? signedMoney(String value) {
  final text = value.trim();
  final negative = text.startsWith('-');
  final abs = inventoryDecimal(
    negative || text.startsWith('+') ? text.substring(1) : text,
    2,
  );
  return abs == null
      ? null
      : negative
      ? -abs
      : abs;
}

String decimalMoney(BigInt cents) {
  final absolute = cents.abs();
  final hundred = BigInt.from(100);
  return '${cents.isNegative ? '-' : ''}${absolute ~/ hundred}.${(absolute % hundred).toString().padLeft(2, '0')}';
}

String? validBankDate(String value) {
  final date = value.trim();
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(date)) return null;
  final parsed = DateTime.tryParse(date);
  return parsed?.toIso8601String().substring(0, 10) == date ? date : null;
}

BigInt? bankMovement(Json record, String bank) {
  if (record['posted'] != true) return null;
  final kind = record['kind'];
  final data = inventoryObject(record['data']);
  final account = data['bank_account_id'] ?? 'default';
  final amount = signedMoney(inventoryText(record['amount']));
  if (amount == null || amount <= BigInt.zero) return null;
  if (kind == 'bank_transfer') {
    final direction = data['direction'];
    if (direction == 'bank_to_bank' &&
        (data['to_bank_account_id'] ?? 'default') == bank) {
      return amount;
    }
    if (account != bank) return null;
    return direction == 'cash_to_bank' ? amount : -amount;
  }
  if (account != bank) return null;
  if (kind == 'pos' && data['payment_account'] == 'split') {
    return signedMoney(inventoryText(data['bank_amount']));
  }
  if (data['payment_account'] != 'bank') return null;
  if (kind == 'advance_refund') {
    return data['payment_kind'] == 'payment_out' ? amount : -amount;
  }
  if (const {'payment_in', 'pos', 'supplier_refund'}.contains(kind)) {
    return amount;
  }
  if (const {'payment_out', 'expense', 'customer_refund'}.contains(kind)) {
    return -amount;
  }
  return null;
}

List<Json> statementEntries(String csv) {
  final rows = csvRows(csv, maxDataRows: 5000);
  final headers = rows.first.values
      .map((entry) => entry.toLowerCase())
      .toList();
  final date = headers.indexOf('date');
  final description = headers.indexOf('description');
  final amount = headers.indexOf('amount');
  final reference = headers.indexOf('reference');
  if (date < 0 ||
      description < 0 ||
      amount < 0 ||
      headers.toSet().length != headers.length) {
    throw const FormatException(
      'Use Date, Description, Amount and an optional Reference column.',
    );
  }
  final lines = <Json>[];
  for (final entry in rows.skip(1)) {
    final row = entry.values;
    if (row.length != headers.length ||
        validBankDate(row[date]) == null ||
        row[description].isEmpty ||
        row[description].length > 500 ||
        (reference >= 0 && row[reference].length > 120)) {
      throw FormatException(
        'Check the date and statement details on CSV row ${entry.line}.',
      );
    }
    final cents = signedMoney(row[amount]);
    if (cents == null || cents == BigInt.zero) {
      throw FormatException('Enter a nonzero amount on CSV row ${entry.line}.');
    }
    lines.add({
      'date': row[date],
      'description': row[description],
      'amount': decimalMoney(cents),
      if (reference >= 0) 'reference': row[reference],
    });
  }
  return lines;
}
