import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';

export 'bank_statement_csv.dart';

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
  // A cancelled entry keeps its posting but has been reversed; it is not a bank movement.
  if (record['posted'] != true || record['cancelled'] == true) return null;
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
