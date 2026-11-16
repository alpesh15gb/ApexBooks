import 'books_data.dart';

class BooksReturnCapacity {
  BooksReturnCapacity._(this.lines, this.originalIndexes);

  factory BooksReturnCapacity.forAmendment(
    BooksRecord note,
    BooksRecord source,
  ) {
    final sourceLines = booksRows(source.json['return_capacity_lines']);
    final originals = booksRows(note.data['lines']);
    if (sourceLines.isEmpty || originals.isEmpty) {
      throw const FormatException(
        'The original source lines could not be verified.',
      );
    }
    final indexes = <int>[];
    final restored = <int, _Quantity>{};
    for (final line in originals) {
      final index = _sourceIndex(line, source.id, sourceLines);
      final quantity = _Quantity.parse(line['quantity']);
      if (index == null || quantity == null || !quantity.positive) {
        throw const FormatException(
          'An original return line cannot be matched to exactly one source line.',
        );
      }
      indexes.add(index);
      restored.update(
        index,
        (previous) => previous + quantity,
        ifAbsent: () => quantity,
      );
    }
    final lines = <BooksJson>[];
    for (final (index, line) in sourceLines.indexed) {
      final committed = restored[index];
      final remaining = _Quantity.parse(line['remaining_return_quantity']);
      if (committed == null) {
        lines.add(
          _sourceIndex(line, source.id, sourceLines) == index
              ? line
              : {...line, 'remaining_return_quantity': null},
        );
        continue;
      }
      final original = _Quantity.parse(line['quantity']);
      if (remaining == null ||
          original == null ||
          (remaining + committed).compareTo(original) > 0) {
        throw const FormatException(
          'The remaining quantity for an original return line could not be verified.',
        );
      }
      lines.add({
        ...line,
        'remaining_return_quantity': (remaining + committed).decimal,
      });
    }
    return BooksReturnCapacity._(
      List.unmodifiable(lines),
      List.unmodifiable(indexes),
    );
  }

  final List<BooksJson> lines;
  final List<int> originalIndexes;

  static int? _sourceIndex(
    BooksJson line,
    String sourceId,
    List<BooksJson> lines,
  ) {
    final id = booksText(line['source_line_id']);
    final owner = booksText(line['source_document_id']);
    final item = booksText(line['item_id']);
    final description = booksText(line['description']).toLowerCase();
    if ((id.isNotEmpty && owner != sourceId) ||
        (id.isEmpty && owner.isNotEmpty)) {
      return null;
    }
    final candidates = [
      for (final (index, original) in lines.indexed)
        if (id.isNotEmpty
            ? booksText(original['source_line_id']) == id &&
                  booksText(original['item_id']) == item
            : item.isNotEmpty
            ? booksText(original['item_id']) == item
            : description.isNotEmpty &&
                  booksText(original['description']).toLowerCase() ==
                      description)
          index,
    ];
    return candidates.length == 1 ? candidates.single : null;
  }

  bool accepts(List<(int?, String)> proposed) {
    final totals = <int, _Quantity>{};
    for (final (index, raw) in proposed) {
      final quantity = _Quantity.parse(raw);
      if (index == null ||
          index < 0 ||
          index >= lines.length ||
          quantity == null ||
          !quantity.positive) {
        return false;
      }
      totals.update(
        index,
        (prior) => prior + quantity,
        ifAbsent: () => quantity,
      );
    }
    return totals.entries.every((row) {
      final capacity = _Quantity.parse(
        lines[row.key]['remaining_return_quantity'],
      );
      return capacity != null && row.value.compareTo(capacity) <= 0;
    });
  }
}

String? booksReturnStartingQuantity(BooksJson line) {
  final available = _Quantity.parse(
    line.containsKey('remaining_return_quantity')
        ? line['remaining_return_quantity']
        : line['quantity'],
  );
  if (available == null || !available.positive) return null;
  return available.compareTo(_Quantity(BigInt.one, 0)) < 0
      ? available.decimal
      : '1';
}

class _Quantity implements Comparable<_Quantity> {
  const _Quantity(this.units, this.scale);
  final BigInt units;
  final int scale;

  static _Quantity? parse(Object? value) {
    final raw = booksText(value);
    if (raw.length > 100) return null;
    final parts = RegExp(r'^([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]{1,3}))?$')
        .firstMatch(raw);
    if (parts == null) return null;
    final fraction = parts[2] ?? '';
    final exponent = int.tryParse(parts[3] ?? '') ?? 0;
    if (exponent.abs() > 100) return null;
    final scale = fraction.length - exponent;
    final units = BigInt.parse('${parts[1]}$fraction');
    return scale < 0
        ? _Quantity(units * _ten(-scale), 0)
        : _Quantity(units, scale);
  }

  bool get positive => units > BigInt.zero;
  static BigInt _ten(int power) => BigInt.from(10).pow(power);
  BigInt _atScale(int target) => units * _ten(target - scale);

  @override
  int compareTo(_Quantity other) {
    final common = scale > other.scale ? scale : other.scale;
    return _atScale(common).compareTo(other._atScale(common));
  }

  _Quantity operator +(_Quantity other) {
    final common = scale > other.scale ? scale : other.scale;
    return _Quantity(_atScale(common) + other._atScale(common), common);
  }

  String get decimal {
    if (scale == 0) return units.toString();
    final digits = units.toString().padLeft(scale + 1, '0');
    final point = digits.length - scale;
    return '${digits.substring(0, point)}.${digits.substring(point)}';
  }
}
