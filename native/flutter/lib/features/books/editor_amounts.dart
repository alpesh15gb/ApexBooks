import 'books_entry_draft.dart';

/// Live document totals, computed on the device while the user types. This mirrors the server's
/// document calculation (paise arithmetic, half-up rounding) so the totals card moves as the web's
/// does. It is display only: the amount that is posted always comes from the server's review.
class EditorLineAmount {
  const EditorLineAmount(this.taxable, this.tax);
  final BigInt taxable;
  final BigInt tax;
  BigInt get total => taxable + tax;
}

class EditorTotals {
  const EditorTotals({
    required this.lines,
    required this.taxable,
    required this.cgst,
    required this.sgst,
    required this.igst,
    required this.supplierTax,
    required this.roundOff,
    required this.total,
  });

  /// One entry per draft line; null where the line is not yet calculable.
  final List<EditorLineAmount?> lines;
  final BigInt taxable;
  final BigInt cgst;
  final BigInt sgst;
  final BigInt igst;
  final BigInt supplierTax;
  final BigInt roundOff;
  final BigInt total;
}

class _Rat {
  const _Rat(this.n, this.d);
  final BigInt n;
  final BigInt d;

  static _Rat? parse(String raw) {
    final m = RegExp(r'^(\d+)(?:\.(\d+))?$').firstMatch(raw.trim());
    if (m == null) return null;
    final frac = m[2] ?? '';
    return _Rat(BigInt.parse('${m[1]}$frac'), BigInt.from(10).pow(frac.length));
  }

  static _Rat paise(BigInt cents) => _Rat(cents, BigInt.from(100));
  _Rat operator +(_Rat o) => _Rat(n * o.d + o.n * d, d * o.d);
  _Rat operator *(_Rat o) => _Rat(n * o.n, d * o.d);
  _Rat operator /(_Rat o) => _Rat(n * o.d, d * o.n);

  /// Round half up to whole paise.
  BigInt get money {
    final scaled = n * BigInt.from(100);
    return (scaled * BigInt.two + d) ~/ (d * BigInt.two);
  }
}

final _hundred = _Rat(BigInt.from(100), BigInt.one);
final _one = _Rat(BigInt.one, BigInt.one);

/// Returns null while no line can be calculated yet.
EditorTotals? editorTotals(BooksEntryDraft draft) {
  if (!draft.hasLines || draft.lines.isEmpty) return null;
  final docPct = _Rat.parse(draft.get('document_discount_percent')) ??
      _Rat(BigInt.zero, BigInt.one);
  final taxApplies = draft.regular || draft.purchase;
  var taxable = BigInt.zero;
  var tax = BigInt.zero;
  final results = <EditorLineAmount?>[];
  for (final line in draft.lines) {
    final qty = _Rat.parse(line.get('quantity'));
    final rate = _Rat.parse(line.get('rate'));
    if (qty == null || rate == null || qty.n == BigInt.zero) {
      results.add(null);
      continue;
    }
    final gst = taxApplies
        ? (_Rat.parse(line.get('gst_rate')) ?? _Rat(BigInt.zero, BigInt.one))
        : _Rat(BigInt.zero, BigInt.one);
    final gross = (qty * rate).money;
    BigInt discount;
    if (line.fixedDiscount) {
      discount = booksParsePaise(line.get('discount_amount')) ?? BigInt.zero;
      if (discount > gross) discount = gross;
    } else {
      final pct = _Rat.parse(line.get('discount_percent')) ??
          _Rat(BigInt.zero, BigInt.one);
      discount = (_Rat.paise(gross) * pct / _hundred).money;
    }
    final docDiscount =
        (_Rat.paise(gross - discount) * docPct / _hundred).money;
    final net = gross - discount - docDiscount;
    final BigInt base;
    final BigInt lineTax;
    if (line.inclusive) {
      base = (_Rat.paise(net) / (_one + gst / _hundred)).money;
      lineTax = net - base;
    } else {
      base = net;
      lineTax = (_Rat.paise(base) * gst / _hundred).money;
    }
    taxable += base;
    tax += lineTax;
    results.add(EditorLineAmount(base, lineTax));
  }
  if (results.every((row) => row == null)) return null;
  final origin = draft.purchase
      ? (draft.get('supplier_state').isNotEmpty
            ? draft.get('supplier_state')
            : draft.get('party_gstin').length >= 2
            ? draft.get('party_gstin').substring(0, 2)
            : draft.company.stateCode)
      : draft.company.stateCode;
  final place = draft.get('place_of_supply');
  final unclassified = !draft.regular &&
      draft.purchase &&
      tax > BigInt.zero &&
      (origin.isEmpty || place.isEmpty);
  final intra = taxApplies && origin == place && !unclassified;
  final cgst = intra ? (_Rat.paise(tax) / _Rat(BigInt.two, BigInt.one)).money : BigInt.zero;
  final sgst = intra ? tax - cgst : BigInt.zero;
  final igst = intra || unclassified ? BigInt.zero : tax;
  final supplier = unclassified ? tax : BigInt.zero;
  final total = taxable + tax;
  var rounded = total;
  if (draft.round) {
    rounded = ((total + BigInt.from(50)) ~/ BigInt.from(100)) * BigInt.from(100);
  }
  return EditorTotals(
    lines: results,
    taxable: taxable,
    cgst: cgst,
    sgst: sgst,
    igst: igst,
    supplierTax: supplier,
    roundOff: rounded - total,
    total: rounded,
  );
}
