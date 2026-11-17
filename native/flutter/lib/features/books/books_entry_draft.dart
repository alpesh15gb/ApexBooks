import '../../core/workspace.dart';
import 'books_data.dart';
import 'books_entry_posting.dart';
import 'books_return_capacity.dart';

const booksEntryKinds = [
  'sales_invoice',
  'purchase_bill',
  'payment_in',
  'payment_out',
  'expense',
  'estimate',
  'sales_order',
  'purchase_order',
  'proforma',
  'credit_note',
  'debit_note',
];
const booksDraftKinds = {
  'estimate',
  'proforma',
  'sales_order',
  'purchase_order',
};
const booksPaymentKinds = {'payment_in', 'payment_out'};

BigInt? booksParsePaise(Object? raw) {
  final parts = RegExp(r'^(\d{1,13})(?:\.(\d{1,2}))?$')
      .firstMatch(booksText(raw));
  if (parts == null) return null;
  return BigInt.parse(parts[1]!) * BigInt.from(100) +
      BigInt.parse((parts[2] ?? '').padRight(2, '0'));
}

String booksDecimal(BigInt cents) =>
    '${cents ~/ BigInt.from(100)}.${(cents % BigInt.from(100)).toString().padLeft(2, '0')}';
bool booksPositive(Object? raw) =>
    (booksParsePaise(raw) ?? BigInt.zero) > BigInt.zero;

class BooksEntryIntent {
  const BooksEntryIntent(
    this.kind, {
    this.source,
    this.operation = BooksOperation.create,
    this.convert = false,
  });

  final String kind;
  final BooksRecord? source;
  final BooksOperation operation;
  final bool convert;

  bool get editing =>
      operation == BooksOperation.amend || operation == BooksOperation.draft;
}

class BooksEntryLine {
  int? returnSourceIndex;
  BooksEntryLine([BooksJson initial = const {}, this.scanned = false]) {
    for (final key in _keys) {
      final value = booksText(initial[key]);
      if (value.isNotEmpty) values[key] = value;
    }
    values.putIfAbsent('quantity', () => '1');
    values.putIfAbsent('gst_rate', () => '0');
    values.putIfAbsent('tax_treatment', () => 'taxable');
    values.putIfAbsent('itc_treatment', () => 'pending_review');
    inclusive = initial['price_includes_tax'] == true;
    fixedDiscount =
        initial['discount_amount'] != null &&
        (booksPositive(initial['discount_amount']) ||
            !booksPositive(initial['discount_percent']));
  }

  static const _keys = [
    'description',
    'details',
    'item_id',
    'quantity',
    'rate',
    'hsn',
    'unit',
    'mrp',
    'gst_rate',
    'tax_treatment',
    'itc_treatment',
    'discount_percent',
    'discount_amount',
    'source_line_id',
    'source_document_id',
  ];
  final bool scanned;
  final values = <String, String>{};
  late bool inclusive;
  late bool fixedDiscount;
  String get(String key) => values[key] ?? '';
  void set(String key, String value) => values[key] = value;

  void chooseItem(
    BooksRecord item, {
    required bool purchase,
    required bool regular,
  }) {
    final data = item.data;
    set('item_id', item.id);
    if (scanned) {
      set('unit', booksText(data['unit']));
      return;
    }
    set('description', item.party);
    for (final key in ['unit', 'hsn']) {
      set(key, booksText(data[key]));
    }
    set('rate', booksText(data[purchase ? 'purchase_rate' : 'sale_rate']));
    set(
      'gst_rate',
      (regular || purchase) ? booksText(data['gst_rate']).ifEmpty('0') : '0',
    );
    var treatment = booksText(data['tax_treatment']).ifEmpty('taxable');
    if (regular &&
        !purchase &&
        treatment == 'taxable' &&
        !booksPositive(get('gst_rate'))) {
      treatment = 'nil_rated';
    }
    set('tax_treatment', treatment);
  }

  BooksJson body() => {
    for (final key in _keys)
      if (get(key).trim().isNotEmpty &&
          key != (fixedDiscount ? 'discount_percent' : 'discount_amount'))
        key: get(key).trim(),
    'price_includes_tax': inclusive,
  };
}

class BooksAllocation {
  BooksAllocation(this.document, this.amount);
  final BooksRecord document;
  String amount;
}

class BooksEntryDraft {
  BooksEntryDraft(this.intent, this.company) {
    set('date', businessDate());
    final source = intent.source;
    if (source != null) {
      if (intent.editing || intent.convert) {
        _copyParty(source);
        for (final key in [
          'place_of_supply',
          'supplier_state',
          'notes',
          'terms',
          'category',
          'document_discount_percent',
          'payment_account',
          'bank_account_id',
          'advance_supply',
          'advance_gst_rate',
        ]) {
          final value = booksText(source.data[key]);
          if (value.isNotEmpty) set(key, value);
        }
        round = source.data['round_total'] == true;
        returnStock = source.data['return_stock'] != false;
        advance = source.data['is_advance'] == true;
        if (intent.editing) {
          set('date', source.date);
          set('number', source.number);
          set('due_date', booksText(source.data['due_date']));
          set('amount', booksText(source.json['amount']));
          if (payment &&
              get('payment_account') == 'bank' &&
              get('bank_account_id').isEmpty) {
            set('bank_account_id', 'default');
          }
          if (payment && advance && regular && !purchase) {
            final supply = booksText(source.data['advance_supply']);
            set(
              'advance_supply',
              const {'goods', 'services'}.contains(supply) ? supply : '',
            );
            set('advance_gst_rate', booksText(source.data['advance_gst_rate']));
          }
        }
        if (!payment) {
          final raw = source.data['lines'];
          if (raw is List) lines.addAll(booksRows(raw).map(BooksEntryLine.new));
        }
        itemizedExpense = lines.isNotEmpty;
      } else if (payment && intent.operation == BooksOperation.create) {
        addAllocation(source);
      } else if (note && intent.operation == BooksOperation.create) {
        chooseNoteSource(source);
      } else {
        _copyParty(source);
        set(
          'amount',
          booksText(
            source.json[advanceSettlement
                ? 'advance_remaining'
                : 'credit_remaining'],
          ),
        );
      }
      if (!intent.editing && get('date').compareTo(source.date) < 0) {
        set('date', source.date);
      }
    }
    if (hasLines && !note && lines.isEmpty) lines.add(blankLine());
    // The web app files a new expense under "General" unless changed.
    if (expense && !intent.editing && get('category').isEmpty) {
      set('category', 'General');
    }
  }

  final BooksEntryIntent intent;
  final ApexCompany company;

  /// A new empty line; GST-registered (regular) companies start at 18%, like the web app.
  BooksEntryLine blankLine() =>
      BooksEntryLine({'gst_rate': company.taxMode == 'regular' ? '18' : '0'});
  final values = <String, String>{};
  final lines = <BooksEntryLine>[];
  final allocations = <BooksAllocation>[];
  Map<String, BigInt> _originalPaymentShares = const {};
  bool _paymentAmendmentLoaded = false;
  BooksReturnCapacity? _returnAmendment;
  BooksRecord? noteSource;
  BooksRecord? settlementTarget;
  bool advance = false;
  bool round = false;
  bool returnStock = true;
  bool itemizedExpense = false;
  bool refund = false;
  bool payAtEntry = false;
  String reason = '';

  String get kind => intent.kind;
  bool get payment => booksPaymentKinds.contains(kind);
  bool get note => kind == 'credit_note' || kind == 'debit_note';
  bool get purchase => const {
    'purchase_bill',
    'purchase_order',
    'debit_note',
    'expense',
    'payment_out',
  }.contains(kind);
  bool get regular => company.taxMode == 'regular';
  bool get expense => kind == 'expense';
  bool get cancel => intent.operation == BooksOperation.cancel;
  bool get settlement =>
      intent.operation == BooksOperation.credit || advanceSettlement;
  bool get advanceSettlement => intent.operation == BooksOperation.advanceApply;
  bool get hasLines =>
      !payment && !cancel && !settlement && (!expense || itemizedExpense);
  bool get usesPaymentAccount =>
      (settlement && refund) ||
      (!settlement && !cancel && (payment || expense || payAtEntry));
  bool get canPayAtEntry =>
      intent.operation == BooksOperation.create &&
      !intent.convert &&
      (kind == 'sales_invoice' || kind == 'purchase_bill');
  bool get editingPayment => payment && intent.editing;
  bool get needsPaymentAmendmentData =>
      editingPayment && !_paymentAmendmentLoaded;
  bool get needsNoteAmendmentData =>
      note && intent.editing && _returnAmendment == null;
  bool get needsAmendmentData =>
      needsPaymentAmendmentData || needsNoteAmendmentData;
  bool get partyLocked =>
      intent.convert ||
      note ||
      settlement ||
      (payment && !advance) ||
      editingPayment;
  BigInt get allocated => allocations.fold(
    BigInt.zero,
    (sum, row) => sum + (booksParsePaise(row.amount) ?? BigInt.zero),
  );
  String get amount => payment && !advance && !settlement
      ? booksDecimal(allocated)
      : get('amount');

  String get title => cancel
      ? 'Cancel ${intent.source!.label}'
      : settlement
      ? (advanceSettlement ? 'Settle advance' : 'Settle credit')
      : intent.editing
      ? 'Edit ${booksKindLabel(kind).toLowerCase()}'
      : intent.convert
      ? 'Convert to ${booksKindLabel(kind).toLowerCase()}'
      : 'New ${booksKindLabel(kind).toLowerCase()}';

  String get(String key) =>
      values[key] ??
      switch (key) {
        'place_of_supply' || 'supplier_state' => company.stateCode,
        'document_discount_percent' => '0',
        'payment_account' => 'cash',
        'advance_supply' => 'goods',
        'advance_gst_rate' => '18',
        _ => '',
      };
  void set(String key, String value) => values[key] = value;

  void applyPurchaseScan(Json extracted) {
    final items = booksRows(extracted['items']);
    final gstin = booksText(extracted['supplier_gstin']).trim().toUpperCase();
    final suppliedDate = booksText(extracted['invoice_date']).trim();
    final date = DateTime.tryParse(suppliedDate);
    final supply = booksText(extracted['place_of_supply']).trim();
    final state = RegExp(r'^\d{2}');
    values.addAll({
      'name': booksText(extracted['supplier_name']).trim(),
      'party_id': '',
      'party_gstin': gstin,
      'party_address': booksText(extracted['supplier_address']).trim(),
      'party_phone': '',
      'shipping_address': '',
      'supplier_state': state.stringMatch(gstin) ?? company.stateCode,
      'place_of_supply': RegExp(r'^\d{2}$').hasMatch(supply)
          ? supply
          : company.stateCode,
      'number': booksText(extracted['invoice_number']).trim(),
      'date':
          date != null &&
              date.year >= 1900 &&
              date.year <= DateTime.now().year + 20 &&
              booksDate(date) == suppliedDate
          ? suppliedDate
          : businessDate(),
      'due_date': '',
      'document_discount_percent': '0',
      'pay_amount': '',
    });
    round = false;
    payAtEntry = false;
    lines
      ..clear()
      ..addAll(
        items.isEmpty
            ? [blankLine()]
            : [
                for (final item in items)
                  BooksEntryLine({
                    for (final key in [
                      'description',
                      'quantity',
                      'rate',
                      'gst_rate',
                      'hsn',
                    ])
                      key: booksText(item[key]).trim(),
                  }, true)..set('quantity', booksText(item['quantity']).trim()),
              ],
      );
  }

  void _copyParty(BooksRecord record) {
    set('name', record.party);
    for (final key in [
      'party_id',
      'party_gstin',
      'party_address',
      'party_phone',
      'shipping_address',
    ]) {
      set(key, booksText(record.data[key]));
    }
  }

  void chooseParty(BooksRecord party) {
    set('name', party.party);
    set('party_id', party.id);
    final data = party.data;
    for (final (client, master) in [
      ('party_gstin', 'gstin'),
      ('party_address', 'address'),
      ('party_phone', 'phone'),
      ('shipping_address', 'shipping_address'),
    ]) {
      set(client, booksText(data[master]));
    }
    final gst = get('party_gstin');
    final local = company.taxMode == 'composition' && !purchase;
    set(
      purchase && !payment ? 'supplier_state' : 'place_of_supply',
      !local && gst.length >= 2 ? gst.substring(0, 2) : company.stateCode,
    );
  }

  void setPartyName(String value) {
    if (get('name').trim().toLowerCase() != value.trim().toLowerCase() &&
        get('party_id').isNotEmpty) {
      for (final key in [
        'party_id',
        'party_gstin',
        'party_address',
        'party_phone',
        'shipping_address',
      ]) {
        set(key, '');
      }
      set('place_of_supply', company.stateCode);
      set('supplier_state', company.stateCode);
    }
    set('name', value);
  }

  void chooseNoteSource(BooksRecord source) {
    noteSource = source;
    _copyParty(source);
    for (final key in ['place_of_supply', 'supplier_state']) {
      final value = booksText(source.data[key]);
      if (value.isNotEmpty) set(key, value);
    }
    if (get('date').compareTo(source.date) < 0) set('date', source.date);
    lines.clear();
    // Like the web app, start with every line that still has a verified
    // returnable quantity, at that full quantity; the user trims from there.
    if (source.json['return_capacity_lines'] is List) {
      for (final original in sourceLines) {
        final remaining = booksText(original['remaining_return_quantity']);
        if (booksReturnStartingQuantity(original) == null ||
            remaining.isEmpty ||
            lines.length >= 100) {
          continue;
        }
        addSourceLine(original);
        final line = lines.last;
        line.set('quantity', remaining);
        if (remaining == booksText(original['quantity']) &&
            booksText(original['discount_amount']).isNotEmpty) {
          // Returning the whole line keeps its own fixed discount.
          line.set('discount_amount', booksText(original['discount_amount']));
        }
      }
    }
  }

  List<BooksJson> get sourceLines {
    if (_returnAmendment case final capacity?) return capacity.lines;
    final source = noteSource;
    if (source == null) return const [];
    return booksRows(
      source.json['return_capacity_lines'] ?? source.data['lines'] ?? const [],
    );
  }

  void addSourceLine(BooksJson original) {
    final initial = booksReturnStartingQuantity(original);
    final index = sourceLines.indexOf(original);
    if (index < 0 ||
        initial == null ||
        lines.any((line) => line.returnSourceIndex == index)) {
      return;
    }
    final line = BooksEntryLine(original);
    line.returnSourceIndex = index;
    line.set('quantity', initial);
    // A source line's fixed gross discount belongs to the source quantity.
    // The cashier must explicitly review any fixed discount for the returned portion.
    if (line.fixedDiscount) line.set('discount_amount', '0');
    lines.add(line);
  }

  Future<void> loadNoteAmendment(
    Future<BooksRecord> Function(String id) find,
  ) async {
    if (!needsNoteAmendmentData) return;
    final original = intent.source!;
    final id = booksText(original.data['applied_to']);
    if (id.isEmpty || original.data['pos_return'] == true) {
      throw const FormatException(
        'Financial edits require an original sales invoice or purchase bill.',
      );
    }
    final source = await find(id);
    if (source.id != id ||
        source.kind != (purchase ? 'purchase_bill' : 'sales_invoice') ||
        source.json['posted'] != true ||
        source.json['cancelled'] == true ||
        source.party.trim().toLowerCase() != get('name').trim().toLowerCase()) {
      throw const FormatException(
        'The posted source invoice or bill could not be verified. POS returns retain their original sale amounts.',
      );
    }
    final capacity = BooksReturnCapacity.forAmendment(original, source);
    if (capacity.originalIndexes.length != lines.length) {
      throw const FormatException(
        'The original return lines could not be verified.',
      );
    }
    for (final (index, line) in lines.indexed) {
      line.returnSourceIndex = capacity.originalIndexes[index];
    }
    noteSource = source;
    _returnAmendment = capacity;
  }

  void addAllocation(BooksRecord document) {
    if (!acceptsPaymentDocument(document)) return;
    if (allocations.isEmpty && !editingPayment) _copyParty(document);
    if (document.party.trim().toLowerCase() !=
            get('name').trim().toLowerCase() ||
        allocations.any((row) => row.document.id == document.id)) {
      return;
    }
    final available = allocationCapacity(document);
    if (available == null || available <= BigInt.zero) return;
    final unpaid = (booksParsePaise(get('amount')) ?? BigInt.zero) - allocated;
    final suggested = editingPayment && unpaid < available
        ? (unpaid > BigInt.zero ? unpaid : BigInt.zero)
        : available;
    allocations.add(BooksAllocation(document, booksDecimal(suggested)));
    if (!intent.editing && get('date').compareTo(document.date) < 0) {
      set('date', document.date);
    }
  }

  BigInt? allocationCapacity(BooksRecord document) {
    final outstanding = booksParsePaise(document.json['outstanding']);
    if (outstanding == null) return null;
    return outstanding + (_originalPaymentShares[document.id] ?? BigInt.zero);
  }

  bool acceptsPaymentDocument(BooksRecord row) =>
      row.json['posted'] == true &&
      row.json['cancelled'] != true &&
      (purchase
              ? const {'purchase_bill', 'opening_payable'}
              : const {'sales_invoice', 'opening_receivable'})
          .contains(row.kind) &&
      ((!editingPayment && allocations.isEmpty) ||
          row.party.trim().toLowerCase() == get('name').trim().toLowerCase());

  Future<void> loadPaymentAmendment(
    Future<BooksRecord> Function(String id) find,
  ) async {
    if (!needsPaymentAmendmentData) return;
    final source = intent.source!;
    final rows = source.json['allocations'];
    if (rows is! List ||
        (!advance && rows.isEmpty) ||
        (advance && rows.isNotEmpty) ||
        !const {'cash', 'bank'}.contains(get('payment_account'))) {
      throw const FormatException(
        'The saved payment does not have verifiable allocations or a supported payment method.',
      );
    }
    final shares = <String, BigInt>{};
    for (final allocation in booksRows(rows)) {
      final id = booksText(allocation['document_id']);
      final value = booksParsePaise(allocation['amount']);
      if (id.isEmpty || value == null || value <= BigInt.zero) {
        throw const FormatException(
          'A saved allocation could not be verified.',
        );
      }
      shares.update(id, (previous) => previous + value, ifAbsent: () => value);
    }
    if (!advance &&
        shares.values.fold(BigInt.zero, (a, b) => a + b) !=
            booksParsePaise(source.json['amount'])) {
      throw const FormatException(
        'The saved allocations do not equal the posted payment.',
      );
    }
    final exact = await Future.wait(
      shares.entries.map((entry) async {
        final document = await find(entry.key);
        if (document.id != entry.key ||
            !acceptsPaymentDocument(document) ||
            allocationCapacity(document) == null) {
          throw const FormatException(
            'A linked document or its balance could not be verified.',
          );
        }
        return BooksAllocation(document, booksDecimal(entry.value));
      }),
    );
    _originalPaymentShares = Map.unmodifiable(shares);
    allocations
      ..clear()
      ..addAll(exact);
    _paymentAmendmentLoaded = true;
  }

  void switchAdvance(bool enabled) {
    advance = enabled;
    allocations.clear();
    set('amount', '');
  }

  String? issue() {
    if (cancel) {
      return reason.trim().length < 3
          ? 'Enter a cancellation reason of 3–200 characters.'
          : null;
    }
    if (get('name').trim().isEmpty) return 'Enter a party or description.';
    if (needsPaymentAmendmentData) {
      return 'Load the original payment before reviewing this amendment.';
    }
    if (needsNoteAmendmentData) {
      return 'Load the original source lines before reviewing this amendment.';
    }
    if (payment && !settlement && advance && regular && !purchase) {
      if (!const {'goods', 'services'}.contains(get('advance_supply'))) {
        return 'Choose what this advance is for.';
      }
      if (get('advance_supply') == 'services') {
        final rate = booksParsePaise(get('advance_gst_rate'));
        if (rate == null || rate > BigInt.from(10000)) {
          return 'Enter the advance GST rate from 0 to 100 percent.';
        }
      }
    }
    if (usesPaymentAccount &&
        get('payment_account') == 'bank' &&
        get('bank_account_id').isEmpty) {
      return 'Choose the bank account.';
    }
    if (payAtEntry && (!canPayAtEntry || !booksPositive(get('pay_amount')))) {
      return 'Enter the payment received or paid at entry.';
    }
    if (hasLines) {
      if (lines.isEmpty) {
        return note
            ? 'Choose the source lines to return.'
            : 'Add an item or service.';
      }
      if (lines.any(
        (line) =>
            line.get('description').trim().isEmpty ||
            !RegExp(r'^\d+(?:\.\d+)?$').hasMatch(line.get('quantity')) ||
            (num.tryParse(line.get('quantity')) ?? 0) <= 0 ||
            !RegExp(r'^\d+(?:\.\d+)?$').hasMatch(line.get('rate')),
      )) {
        return 'Enter a description, positive quantity and valid rate on each line.';
      }
    } else if (!booksPositive(amount)) {
      return 'Enter an amount greater than zero.';
    }
    if (payment && !advance && !settlement) {
      if (allocations.any((row) => !booksPositive(row.amount))) {
        return 'Enter a positive amount for each allocation.';
      }
      if (allocations.any(
        (row) =>
            booksParsePaise(row.amount)! >
            (allocationCapacity(row.document) ?? BigInt.zero),
      )) {
        return 'An allocation exceeds its document balance.';
      }
      if (allocations.any(
        (row) => row.document.date.compareTo(get('date')) > 0,
      )) {
        return 'Payment date cannot be before a linked document.';
      }
    }
    if (_returnAmendment case final capacity?) {
      if (!capacity.accepts(
        lines
            .map((line) => (line.returnSourceIndex, line.get('quantity')))
            .toList(),
      )) {
        return 'A return quantity exceeds the available source quantity.';
      }
    } else if (note && !intent.editing) {
      // New returns: check against the server's remaining quantities before posting.
      final capacityLines = booksRows(
        noteSource?.json['return_capacity_lines'] ?? const [],
      );
      final linked = [
        for (final line in lines)
          if (line.returnSourceIndex != null)
            (line.returnSourceIndex, line.get('quantity')),
      ];
      if (capacityLines.isNotEmpty &&
          linked.isNotEmpty &&
          !BooksReturnCapacity.forSource(capacityLines).accepts(linked)) {
        return 'A return quantity exceeds the available source quantity.';
      }
    }
    if (settlement) {
      final available =
          booksParsePaise(
            intent.source!.json[advanceSettlement
                ? 'advance_remaining'
                : 'credit_remaining'],
          ) ??
          BigInt.zero;
      if (booksParsePaise(amount)! > available) {
        return 'Amount exceeds the available balance.';
      }
      if (!refund) {
        final target = settlementTarget;
        if (target == null) return 'Choose the document to settle.';
        if (booksParsePaise(amount)! >
            (booksParsePaise(target.json['outstanding']) ?? BigInt.zero)) {
          return 'Amount exceeds the selected document balance.';
        }
        if (target.date.compareTo(get('date')) > 0) {
          return 'Settlement date cannot be before the linked document.';
        }
      }
    }
    final linked =
        noteSource ?? (intent.convert || settlement ? intent.source : null);
    if (linked != null && linked.date.compareTo(get('date')) > 0) {
      return 'Entry date cannot be before the source document.';
    }
    if (get('due_date').isNotEmpty &&
        get('due_date').compareTo(get('date')) < 0) {
      return 'Due date must be on or after the document date.';
    }
    return null;
  }

  BooksCommand command() {
    final source = intent.source;
    if (needsAmendmentData) {
      throw StateError('Original amendment data not loaded');
    }
    if (cancel) {
      return BooksCommand(BooksOperation.cancel, source!.id, {
        'reason': reason.trim(),
      });
    }
    if (settlement) {
      final operation = advanceSettlement && refund
          ? BooksOperation.advanceRefund
          : intent.operation;
      return BooksCommand(operation, source!.id, {
        'kind': kind,
        'name': source.party,
        'date': get('date'),
        'amount': amount.trim(),
        'data': {
          if (!advanceSettlement) 'action': refund ? 'refund' : 'apply',
          if (!refund) 'applied_to': settlementTarget?.id,
          if (refund) ..._paymentData(),
        },
      });
    }
    final body = <String, dynamic>{
      'kind': kind,
      'name': get('name').trim(),
      'date': get('date'),
      'number': get('number').trim(),
      'amount': hasLines ? '0' : amount.trim(),
      'data': {
        for (final key in [
          'party_id',
          'party_gstin',
          'party_address',
          'party_phone',
          'shipping_address',
          'notes',
          'terms',
          'category',
          'place_of_supply',
          'supplier_state',
          'due_date',
        ])
          // On edit, send a cleared field only if the saved document had it;
          // an empty value for an absent key reads as a change on the server.
          if (get(key).isNotEmpty ||
              (intent.editing && booksText(source?.data[key]).isNotEmpty))
            key: get(key).trim(),
        if (hasLines) ...{
          'lines': lines.map((line) => line.body()).toList(),
          'round_total': round,
          'document_discount_percent': get('document_discount_percent')
              .trim()
              .ifEmpty('0'),
        } else if (expense && intent.editing)
          'lines': [],
        if (note) 'return_stock': returnStock,
        if (note)
          'applied_to': noteSource?.id ?? booksText(source?.data['applied_to']),
        if (intent.convert) 'source_document_id': source!.id,
        if (usesPaymentAccount && !payAtEntry) ..._paymentData(),
        if (payment) ...{
          'is_advance': advance,
          if (advance && regular && !purchase)
            'advance_supply': get('advance_supply'),
          if (advance &&
              regular &&
              !purchase &&
              get('advance_supply') == 'services')
            'advance_gst_rate': get('advance_gst_rate'),
          if (!advance)
            'allocations': allocations
                .map(
                  (row) => {
                    'document_id': row.document.id,
                    'amount': row.amount.trim(),
                  },
                )
                .toList(),
        },
        if (intent.editing) 'version': source!.data['version'] ?? 0,
      },
    };
    if (payAtEntry) {
      return BooksCommand(BooksOperation.withPayment, '', {
        'document': body,
        'payment': {
          ..._paymentData(),
          'amount': get('pay_amount').trim(),
          if (get('pay_reference').trim().isNotEmpty)
            'reference': get('pay_reference').trim(),
        },
      });
    }
    return BooksCommand(
      intent.operation,
      intent.editing ? source!.id : '',
      body,
    );
  }

  BooksJson _paymentData() => {
    'payment_account': get('payment_account'),
    'bank_account_id': get('payment_account') == 'bank'
        ? get('bank_account_id')
        : 'default',
  };

  BooksJson previewBody(BooksCommand command) {
    final body = command.operation == BooksOperation.withPayment
        ? booksObject(command.body['document'])
        : command.body;
    if (intent.editing && kind == 'debit_note') {
      booksObject(body['data'])['editing_record_id'] = intent.source!.id;
    }
    return body;
  }
}

extension BooksTextFallback on String {
  String ifEmpty(String alternative) => isEmpty ? alternative : this;
}
