import 'dart:convert';
import 'dart:math';

typedef PosJson = Map<String, dynamic>;

PosJson posObject(Object? value) => switch (value) {
  Map<String, dynamic>() => value,
  _ => throw const FormatException('The server response is incomplete.'),
};

List<dynamic> posList(Object? value) => switch (value) {
  List<dynamic>() => value,
  _ => throw const FormatException('The server response is incomplete.'),
};

String posText(Object? value) => value?.toString() ?? '';

int? parsePosDecimal(String value, int scale, {int wholeDigits = 13}) {
  final text = value.trim();
  if (!RegExp(r'^(?:\d+(?:\.\d*)?|\.\d+)$').hasMatch(text)) return null;
  final parts = text.split('.');
  final integer = parts.first.replaceFirst(RegExp(r'^0+'), '');
  final fraction = parts.length == 2 ? parts[1] : '';
  if (integer.length > wholeDigits || fraction.length > scale) return null;
  return int.tryParse(
    '${integer.isEmpty ? '0' : integer}${fraction.padRight(scale, '0')}',
  );
}

int? parsePosMoney(String value) => parsePosDecimal(value, 2);

String posDecimalText(int value, int scale) {
  final digits = value.abs().toString().padLeft(scale + 1, '0');
  final decimalPoint = digits.length - scale;
  return '${value < 0 ? '-' : ''}${digits.substring(0, decimalPoint)}.${digits.substring(decimalPoint)}';
}

String posMoneyText(int paise) => _formatPosMoney(paise.toString());

String registerMoneyText(BigInt paise) => _formatPosMoney(paise.toString());

String _formatPosMoney(String minorUnits) {
  final negative = minorUnits.startsWith('-');
  final digits = (negative ? minorUnits.substring(1) : minorUnits).padLeft(
    3,
    '0',
  );
  final fraction = digits.substring(digits.length - 2);
  var rupees = digits.substring(0, digits.length - 2);
  if (rupees.length > 3) {
    final tail = rupees.substring(rupees.length - 3);
    final groups = <String>[tail];
    rupees = rupees.substring(0, rupees.length - 3);
    while (rupees.length > 2) {
      groups.insert(0, rupees.substring(rupees.length - 2));
      rupees = rupees.substring(0, rupees.length - 2);
    }
    groups.insert(0, rupees);
    rupees = groups.join(',');
  }
  return '${negative ? '−' : ''}₹$rupees.$fraction';
}

String newPosKey() {
  final random = Random.secure();
  return List.generate(
    24,
    (_) => random.nextInt(256),
  ).map((value) => value.toRadixString(16).padLeft(2, '0')).join();
}

class PosProduct {
  PosProduct.fromJson(PosJson row)
    : id = posText(row['id']),
      name = posText(row['name']),
      data = posObject(row['data']);

  final String id;
  final String name;
  final PosJson data;

  String get barcode => posText(data['barcode']);
  String get unit => posText(data['unit']);
  String get hsn => posText(data['hsn']);
  String get rate => posText(data['sale_rate'] ?? '0');
  String get gst => posText(data['gst_rate'] ?? '0');
  bool get tracked => data['track_stock'] == true;
  bool get active => data['is_active'] != false;

  String get treatment {
    final value = posText(data['tax_treatment']);
    if (const {'taxable', 'nil_rated', 'exempt', 'non_gst'}.contains(value)) {
      return value == 'taxable' && parsePosMoney(gst) == 0
          ? 'nil_rated'
          : value;
    }
    return (parsePosMoney(gst) ?? 0) > 0 ? 'taxable' : 'nil_rated';
  }

  bool matches(String query) =>
      '$name $barcode $hsn'.toLowerCase().contains(query.trim().toLowerCase());
}

class PosLine {
  PosLine(this.product) : rate = product.rate;

  final PosProduct product;
  String quantity = '1';
  String rate;
  String discount = '';

  int? get quantityMilli => parsePosDecimal(quantity, 3, wholeDigits: 12);

  bool get valid =>
      (quantityMilli ?? 0) > 0 &&
      parsePosMoney(rate) != null &&
      (discount.isEmpty || parsePosMoney(discount) != null);

  PosJson toJson({required bool regularTax, required bool inclusive}) => {
    'item_id': product.id,
    'description': product.name,
    'quantity': quantity.trim(),
    'unit': product.unit,
    'rate': rate.trim(),
    'gst_rate': regularTax && product.treatment == 'taxable'
        ? product.gst
        : '0',
    'tax_treatment': product.treatment,
    'hsn': product.hsn,
    'price_includes_tax': regularTax && inclusive,
    if (discount.isNotEmpty) 'discount_amount': discount.trim(),
  };
}

class PosBank {
  PosBank.fromJson(PosJson row)
    : id = posText(row['id']),
      name = posText(row['name']),
      hint = posText(row['account_hint']);

  final String id;
  final String name;
  final String hint;

  String get label => hint.isEmpty ? name : '$name · $hint';
}

class PosQuote {
  PosQuote.fromJson(PosJson json, this.date)
    : amount = posText(json['amount']),
      paise =
          parsePosMoney(posText(json['amount'])) ??
          (throw const FormatException(
            'The server did not return a valid total.',
          )),
      data = posObject(json['data']);

  final String amount;
  final int paise;
  final String date;
  final PosJson data;
}

class PosReceipt {
  PosReceipt.fromJson(PosJson row)
    : id = posText(row['id']),
      number = posText(row['number']),
      customer = posText(row['name']),
      date = posText(row['date']),
      paise =
          parsePosMoney(posText(row['amount'])) ??
          (throw const FormatException('The receipt total is missing.')),
      posted = row['posted'] == true && row['cancelled'] != true,
      data = posObject(row['data']),
      returnCapacity = row['return_capacity_lines'] is List
          ? posList(row['return_capacity_lines']).map(posObject).toList()
          : null {
    if (id.isEmpty || number.isEmpty || row['kind'] != 'pos') {
      throw const FormatException(
        'The sale response did not include its receipt.',
      );
    }
  }

  final String id;
  final String number;
  final String customer;
  final String date;
  final int paise;
  final bool posted;
  final PosJson data;
  final List<PosJson>? returnCapacity;

  int get change => parsePosMoney(posText(data['change_amount'])) ?? 0;
}

class PosPendingSale {
  PosPendingSale.create(PosJson body)
    : key = newPosKey(),
      payload = jsonEncode(body);

  PosPendingSale.fromJson(PosJson json)
    : key = posText(json['key']),
      payload = posText(json['payload']) {
    final data = body;
    if (!RegExp(r'^[0-9a-f]{48}$').hasMatch(key) ||
        data['kind'] != 'pos' ||
        data['date'] is! String ||
        data['data'] is! Map<String, dynamic>) {
      throw const FormatException('The saved sale is incomplete.');
    }
  }

  final String key;
  final String payload;
  PosJson get body => posObject(jsonDecode(payload));
  PosJson toJson() => {'key': key, 'payload': payload};
}

enum PosTender { cash, bank, split }

class PosPayment {
  const PosPayment({
    required this.cash,
    required this.bank,
    required this.tendered,
    required this.error,
  });

  final int cash;
  final int bank;
  final int tendered;
  final String? error;
  int get change => tendered - cash;
  bool get valid => error == null;

  static PosPayment evaluate(
    int total,
    PosTender method,
    String tenderedText,
    String bankText,
  ) {
    const empty = PosPayment(
      cash: 0,
      bank: 0,
      tendered: 0,
      error: 'Review the sale total.',
    );
    if (total <= 0) return empty;
    if (method == PosTender.bank) {
      return PosPayment(cash: 0, bank: total, tendered: 0, error: null);
    }
    final bank = method == PosTender.split ? parsePosMoney(bankText) : 0;
    if (bank == null ||
        (method == PosTender.split && (bank <= 0 || bank >= total))) {
      return const PosPayment(
        cash: 0,
        bank: 0,
        tendered: 0,
        error: 'Enter a bank amount below the total.',
      );
    }
    final cash = total - bank;
    final tendered = parsePosMoney(tenderedText);
    if (tendered == null) {
      return PosPayment(
        cash: cash,
        bank: bank,
        tendered: 0,
        error: 'Enter cash received.',
      );
    }
    return PosPayment(
      cash: cash,
      bank: bank,
      tendered: tendered,
      error: tendered < cash
          ? 'Cash still due ${posMoneyText(cash - tendered)}'
          : null,
    );
  }
}
