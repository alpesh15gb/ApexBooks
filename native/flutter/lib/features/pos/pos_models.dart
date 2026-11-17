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
      number = posText(row['number']),
      data = posObject(row['data']);

  final String id;
  final String name;
  final String number;
  final PosJson data;

  /// Shelf ids from the item's `location_ids` (names come from inventory setup).
  List<String> get locationIds => [
    for (final id in data['location_ids'] is List
        ? data['location_ids'] as List
        : const [])
      if (id is String) id,
  ];

  String get thumbnail => posText(data['image_thumbnail']);

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

  /// Same text the web POS searches: name, number, HSN, barcode, shelf names,
  /// part number, brand, grade and the vehicles the part fits.
  String searchText(Map<String, String> shelves) {
    String tidy(Object? value) =>
        posText(value).replaceAll(RegExp(r'\s+'), ' ').trim();
    const grades = {
      'oem': 'OEM',
      'aftermarket': 'Aftermarket',
      'used': 'Used',
      'refurbished': 'Refurbished',
    };
    final fits = [
      for (final row in data['vehicle_fitment'] is List
          ? data['vehicle_fitment'] as List
          : const [])
        if (row is Map)
          [
            tidy(row['make']),
            tidy(row['model']),
            _years(posText(row['year_from']), posText(row['year_to'])),
          ].where((part) => part.isNotEmpty).join(' '),
    ];
    return [
      name,
      number,
      hsn,
      barcode,
      ...posLocationNames(this, shelves),
      tidy(data['oem_number']),
      tidy(data['part_brand']),
      grades[posText(data['part_grade'])] ?? '',
      ...fits,
    ].where((part) => part.isNotEmpty).join(' ').toLowerCase();
  }
}

String _years(String from, String to) {
  if (from.isNotEmpty && to.isNotEmpty) {
    return from == to ? from : '$from–$to';
  }
  if (from.isNotEmpty) return '$from onwards';
  if (to.isNotEmpty) return 'up to $to';
  return '';
}

/// Names of the shelves an item sits on, in the item's own order.
List<String> posLocationNames(PosProduct product, Map<String, String> shelves) =>
    [
      for (final id in product.locationIds)
        if (shelves[id] case final name? when name.isNotEmpty) name,
    ];

/// A customer from Parties, used for the customer suggestions.
class PosParty {
  PosParty.fromJson(PosJson row)
    : name = posText(row['name']),
      address = posText(posObject(row['data'])['address']),
      gstin = posText(posObject(row['data'])['gstin']),
      phone = posText(posObject(row['data'])['phone']);

  final String name;
  final String address;
  final String gstin;
  final String phone;
}

/// A sale set aside at the counter. Held sales live in memory only and do not
/// reserve stock, the same as the web POS.
class PosHeldSale {
  PosHeldSale({
    required this.lines,
    required this.customer,
    required this.address,
    required this.gstin,
    required this.phone,
    required this.place,
    required this.tender,
    required this.bankId,
    required this.inclusive,
    required this.round,
  }) : id = newPosKey();

  final String id;
  final List<PosLine> lines;
  final String customer;
  final String address;
  final String gstin;
  final String phone;
  final String place;
  final PosTender tender;
  final String bankId;
  final bool inclusive;
  final bool round;
}

/// Per-company held sales for this app session (the web keeps them in a
/// session-long in-memory draft; nothing is written to disk).
class PosHeldStore {
  PosHeldStore();

  static final _byCompany = <String, PosHeldStore>{};
  static PosHeldStore forCompany(String companyId) =>
      _byCompany.putIfAbsent(companyId, PosHeldStore.new);

  static const limit = 12;
  final List<PosHeldSale> sales = [];
}

class PosLine {
  PosLine(this.product) : rate = product.rate;

  final PosProduct product;
  String quantity = '1';
  String rate;
  String discount = '';

  PosLine copy() => PosLine(product)
    ..quantity = quantity
    ..rate = rate
    ..discount = discount;

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
    // Like the web counter, leaving the cash box empty means the exact amount.
    final tendered = tenderedText.trim().isEmpty
        ? cash
        : parsePosMoney(tenderedText);
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

const _posMonths = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sept',
  'Oct',
  'Nov',
  'Dec',
];

/// "14 Nov 2026, 3:45 pm" in business (India) time, like the web register.
String posDateTime(String iso) {
  final parsed = DateTime.tryParse(iso);
  if (parsed == null) return iso;
  final time = parsed.toUtc().add(const Duration(hours: 5, minutes: 30));
  final hour = time.hour % 12 == 0 ? 12 : time.hour % 12;
  final minute = time.minute.toString().padLeft(2, '0');
  return '${time.day} ${_posMonths[time.month - 1]} ${time.year}, '
      '$hour:$minute ${time.hour < 12 ? 'am' : 'pm'}';
}
