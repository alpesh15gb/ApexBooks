import 'dart:convert';

typedef InventoryJson = Map<String, dynamic>;

InventoryJson inventoryObject(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : const {};

List<InventoryJson> inventoryRows(Object? value) => value is List
    ? value.whereType<Map>().map(inventoryObject).toList()
    : const [];

String inventoryText(Object? value) => value?.toString() ?? '';

String inventoryQuantity(Object? value) {
  final text = inventoryText(value);
  if (!text.contains('.') || text.contains(RegExp('[eE]'))) return text;
  return text.replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '');
}

BigInt? inventoryDecimal(String value, int scale) {
  final text = value.trim();
  if (!RegExp('^\\d+(?:\\.\\d{1,$scale})?\$').hasMatch(text)) return null;
  final parts = text.split('.');
  final whole = parts.first.replaceFirst(RegExp(r'^0+(?=\d)'), '');
  if (whole.length > 15 - scale) return null;
  final fraction = parts.length > 1 ? parts.last : '';
  return BigInt.parse('$whole${fraction.padRight(scale, '0')}');
}

String inventoryAmount(Object? value) {
  final text = inventoryText(value);
  final match = RegExp(r'^(-?)(\d+)(?:\.(\d{1,2}))?$').firstMatch(text);
  if (match == null) return text.isEmpty ? '—' : '₹$text';
  final whole = match[2]!;
  final groups = <String>[];
  var end = whole.length;
  var length = 3;
  while (end > 0) {
    final start = end > length ? end - length : 0;
    groups.insert(0, whole.substring(start, end));
    end = start;
    length = 2;
  }
  return '${match[1]}₹${groups.join(',')}.${(match[3] ?? '').padRight(2, '0')}';
}

bool itemMatches(
  InventoryJson item,
  String query,
  Map<String, String> locations, {
  bool automobileEnabled = false,
}) {
  final data = inventoryObject(item['data']);
  final tokens = query
      .trim()
      .toLowerCase()
      .split(RegExp(r'\s+'))
      .where((token) => token.isNotEmpty);
  final ids = data['location_ids'];
  final text = [
    item['name'],
    data['sku'],
    data['barcode'],
    if (automobileEnabled) ...[data['oem_number'], data['part_brand']],
    data['hsn'],
    if (ids is List) ...ids.map((id) => locations[id]),
  ].whereType<Object>().join(' ').toLowerCase();
  if (tokens.every(text.contains)) return true;
  if (!automobileEnabled) return false;
  return inventoryRows(data['vehicle_fitment']).any((fit) {
    final vehicle =
        '${inventoryText(fit['make'])} ${inventoryText(fit['model'])}'
            .toLowerCase();
    final from = int.tryParse(inventoryText(fit['year_from']));
    final to = int.tryParse(inventoryText(fit['year_to']));
    return tokens.every((token) {
      if (text.contains(token) || vehicle.contains(token)) return true;
      final year = token.length == 4 ? int.tryParse(token) : null;
      return year != null &&
          year >= 1950 &&
          year <= 2100 &&
          (from != null || to != null) &&
          (from == null || year >= from) &&
          (to == null || year <= to);
    });
  });
}

class InventoryOperation {
  InventoryOperation({
    required this.key,
    required this.kind,
    required this.recordId,
    required this.name,
    required InventoryJson body,
  }) : _body = jsonDecode(jsonEncode(body)) as InventoryJson;

  factory InventoryOperation.fromJson(InventoryJson value) {
    final key = inventoryText(value['key']);
    final kind = inventoryText(value['kind']);
    final recordId = inventoryText(value['record_id']);
    if (key.isEmpty ||
        key.length > 80 ||
        recordId.isEmpty ||
        !const {'receipt', 'count', 'opening', 'adjustment'}.contains(kind) ||
        value['body'] is! Map) {
      throw const FormatException('Invalid pending inventory request');
    }
    return InventoryOperation(
      key: key,
      kind: kind,
      recordId: recordId,
      name: inventoryText(value['name']),
      body: inventoryObject(value['body']),
    );
  }

  final String key;
  final String kind;
  final String recordId;
  final String name;
  final InventoryJson _body;
  InventoryJson get body => jsonDecode(jsonEncode(_body)) as InventoryJson;

  InventoryJson toJson() => {
    'key': key,
    'kind': kind,
    'record_id': recordId,
    'name': name,
    'body': body,
  };
}
