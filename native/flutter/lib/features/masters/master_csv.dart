import '../../core/workspace.dart';
import '../shared/csv_rows.dart';

typedef MasterCsv = ({List<Json> rows, List<int> lines});

const _aliases = {
  'type': 'party_type',
  'hsn / sac': 'hsn',
  'hsn/sac': 'hsn',
  'stock_tracked': 'track_stock',
  'billing_address': 'address',
  'payment_terms_(days)': 'payment_terms_days',
  'credit_limit_(₹)': 'credit_limit',
};

const _contacts = {
  'name',
  'party_type',
  'gstin',
  'address',
  'phone',
  'email',
  'payment_terms_days',
  'credit_limit',
  'shipping_address',
  'is_active',
};
const _items = {
  'name',
  'hsn',
  'unit',
  'sale_rate',
  'purchase_rate',
  'gst_rate',
  'track_stock',
  'barcode',
  'item_type',
  'tax_treatment',
  'low_stock_threshold',
  'is_active',
};

String _header(String name) {
  final value = name.trim().toLowerCase();
  return _aliases[value] ??
      _aliases[value.replaceAll(' ', '_')] ??
      value.replaceAll(RegExp(r'\s+'), '_');
}

bool? _boolean(String value) => switch (value.toLowerCase()) {
  'yes' || 'true' || '1' => true,
  'no' || 'false' || '0' => false,
  _ => null,
};

MasterCsv masterCsv(String input, String kind) {
  final allowed = switch (kind) {
    'item' => _items,
    'party' => _contacts,
    _ => throw const FormatException('Choose contacts or items.'),
  };
  final file = csvRows(input, maxDataRows: 500);
  final fields = file.first.values.map(_header).toList();
  final populatedFields = fields.where((field) => field.isNotEmpty).toList();
  if (!fields.contains('name') ||
      populatedFields.length != populatedFields.toSet().length) {
    throw const FormatException(
      'Include a Name column and use each column only once.',
    );
  }
  final names = <Json>[];
  final lines = <int>[];
  for (final row in file.skip(1)) {
    if (row.values.length != fields.length) {
      throw FormatException(
        'CSV row ${row.line} has ${row.values.length} columns. Expected ${fields.length}.',
      );
    }
    final values = <String, dynamic>{};
    for (var index = 0; index < fields.length; index++) {
      final field = fields[index];
      final value = row.values[index];
      if (value.isEmpty) continue;
      if (!allowed.contains(field)) {
        throw FormatException(
          'Column ${file.first.values[index]} is unsupported on CSV row ${row.line}.',
        );
      }
      if (field == 'track_stock' || field == 'is_active') {
        final state = _boolean(value);
        if (state == null) {
          throw FormatException(
            'Enter Yes or No for ${file.first.values[index]} on CSV row ${row.line}.',
          );
        }
        values[field] = state;
      } else if (field == 'payment_terms_days') {
        final terms = int.tryParse(value);
        if (terms == null || terms < 0 || terms > 3650) {
          throw FormatException(
            'Enter payment terms from 0 to 3,650 days on CSV row ${row.line}.',
          );
        }
        values[field] = terms;
      } else {
        values[field] = switch (field) {
          'party_type' => value.toLowerCase(),
          'item_type' =>
            value.toLowerCase() == 'service' ? 'services' : value.toLowerCase(),
          'tax_treatment' => value.toLowerCase().replaceAll(
            RegExp(r'[\s-]+'),
            '_',
          ),
          _ => value,
        };
      }
    }
    if (values['name'] == null) {
      throw FormatException('Enter a name on CSV row ${row.line}.');
    }
    names.add(values);
    lines.add(row.line);
  }
  return (rows: names, lines: lines);
}
