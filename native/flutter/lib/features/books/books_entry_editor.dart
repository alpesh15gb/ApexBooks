import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'books_entry_draft.dart';
import 'books_entry_picker.dart';
import 'books_entry_posting.dart';
import 'books_party_insights.dart';
import 'books_return_capacity.dart';
import 'purchase_scan.dart';

class BooksEntryEditor extends StatefulWidget {
  const BooksEntryEditor({
    required this.draft,
    required this.posting,
    required this.onBack,
    required this.onSaved,
    super.key,
  });

  final BooksEntryDraft draft;
  final BooksPosting posting;
  final VoidCallback onBack;
  final void Function(BooksRecord record, String? reviewedAmount) onSaved;

  @override
  State<BooksEntryEditor> createState() => _BooksEntryEditorState();
}

class _BooksEntryEditorState extends State<BooksEntryEditor> {
  BooksCommand? _reviewed;
  BooksJson? _reviewData;
  String? _reviewAmount;
  String? _message;
  String? _scannedTotal;
  bool _busy = false;
  final _scroll = ScrollController();

  BooksEntryDraft get draft => widget.draft;
  BooksPosting get posting => widget.posting;
  WorkspaceContext get workspace => posting.workspace;
  bool get _editable => posting.canStart && !_busy && !draft.needsAmendmentData;

  @override
  void initState() {
    super.initState();
    if (draft.needsAmendmentData) _loadAmendmentData();
  }

  Future<void> _loadAmendmentData() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final lookup = BooksData(workspace.company.id, workspace.api.get).record;
      if (draft.editingPayment) {
        await draft.loadPaymentAmendment(lookup);
      } else {
        await draft.loadNoteAmendment(lookup);
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is FormatException
              ? error.message
              : error is ApexApiException
              ? error.message
              : 'Could not verify the original document links.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _edit(VoidCallback change) {
    if (!_editable) return;
    setState(() {
      change();
      _reviewed = null;
      _message = null;
    });
  }

  Future<void> _review() async {
    if (!_editable) return;
    final issue = draft.issue();
    if (issue != null) {
      setState(() => _message = issue);
      return;
    }
    final command = draft.command();
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      var amount = draft.cancel
          ? booksText(draft.intent.source?.json['amount'])
          : draft.amount;
      BooksJson? reviewData;
      if (draft.hasLines) {
        final response = booksObject(
          await workspace.api.post(
            '${posting.root}/documents/preview',
            body: draft.previewBody(command),
          ),
        );
        amount = booksText(response['amount']);
        reviewData = booksObject(response['data']);
        if (booksParsePaise(amount) == null) {
          throw const FormatException('Invalid review amount');
        }
        if (!booksDraftKinds.contains(draft.kind) && !booksPositive(amount)) {
          throw const ApexApiException(
            message: 'The posting amount must be greater than zero. Review prices and discounts.',
          );
        }
        if (draft.payAtEntry &&
            booksParsePaise(draft.get('pay_amount'))! >
                booksParsePaise(amount)!) {
          throw const ApexApiException(
            message: 'Payment cannot exceed the reviewed document total.',
          );
        }
      }
      if (!mounted || draft.command().payload != command.payload) return;
      setState(() {
        _reviewed = command;
        _reviewAmount = amount;
        _reviewData = reviewData;
      });
      _toTop();
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is ApexApiException
              ? error.message
              : 'Could not review this entry. Try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final command = _reviewed;
    if (!_editable || command == null) return;
    if (draft.command().payload != command.payload ||
        draft.command().operation != command.operation) {
      setState(() {
        _reviewed = null;
        _message = 'The entry changed. Review it again.';
      });
      return;
    }
    final saved = await posting.submit(command);
    if (!mounted) return;
    if (saved != null) {
      widget.onSaved(saved, _reviewAmount);
    } else if (posting.pending == null) {
      setState(() {
        _reviewed = null;
        _message = posting.message;
      });
    }
  }

  void _toTop() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _scroll.hasClients) _scroll.jumpTo(0);
    });
  }

  Future<void> _chooseParty() async {
    final party = await pickBooksRecord(
      context,
      workspace,
      title: draft.purchase ? 'Choose supplier' : 'Choose customer',
      kinds: const ['party'],
      accept: (party) {
        final type = booksText(party.data['party_type']);
        return party.data['is_active'] != false &&
            (type.isEmpty ||
                type == 'both' ||
                type == (draft.purchase ? 'supplier' : 'customer'));
      },
      detail: (party) => booksText(party.data['phone']),
    );
    if (mounted && party != null) _edit(() => draft.chooseParty(party));
  }

  Future<void> _scanBill() async {
    if (!_editable) return;
    final extracted = await scanPurchaseBill(context, workspace);
    if (!mounted || extracted == null || !_editable) return;
    try {
      _edit(() {
        draft.applyPurchaseScan(extracted);
        final total = booksText(extracted['total']);
        _scannedTotal = booksParsePaise(total) == null ? '' : total;
      });
    } on FormatException {
      setState(
        () => _message =
            'The scan returned an invalid draft. Enter the bill manually.',
      );
    }
  }

  Future<void> _chooseItem(BooksEntryLine line) async {
    final item = await pickBooksRecord(
      context,
      workspace,
      title: 'Choose item or service',
      kinds: const ['item'],
      accept: (item) => item.data['is_active'] != false,
      detail: (item) =>
          booksMoney(item.data[draft.purchase ? 'purchase_rate' : 'sale_rate']),
    );
    if (mounted && item != null) {
      _edit(
        () => line.chooseItem(
          item,
          purchase: draft.purchase,
          regular: draft.regular,
        ),
      );
    }
  }

  Future<void> _chooseNoteSource() async {
    final row = await pickBooksRecord(
      context,
      workspace,
      title: 'Choose source document',
      kinds: [draft.purchase ? 'purchase_bill' : 'sales_invoice'],
      accept: _posted,
      detail: (row) => '${row.date} · ${booksMoney(row.json['amount'])}',
    );
    if (!mounted || row == null || !_editable) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final exact = await BooksData(
        workspace.company.id,
        workspace.api.get,
      ).record(row.id);
      if (!mounted) return;
      if (!_posted(exact)) {
        throw const ApexApiException(
          message: 'The source document is no longer posted.',
        );
      }
      setState(() => draft.chooseNoteSource(exact));
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is ApexApiException
              ? error.message
              : 'Could not load the source document.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _chooseAllocation({bool settlement = false}) async {
    final kinds = draft.purchase
        ? ['purchase_bill', if (!settlement) 'opening_payable']
        : ['sales_invoice', if (!settlement) 'opening_receivable'];
    final party = draft.get('name').trim().toLowerCase();
    final row = await pickBooksRecord(
      context,
      workspace,
      title: 'Choose outstanding document',
      kinds: kinds,
      accept: (row) => settlement
          ? _posted(row) &&
                booksPositive(row.json['outstanding']) &&
                row.party.trim().toLowerCase() == party
          : draft.acceptsPaymentDocument(row) &&
                (draft.allocationCapacity(row) ?? BigInt.zero) > BigInt.zero &&
                (!draft.editingPayment ||
                    row.date.compareTo(draft.get('date')) <= 0) &&
                draft.allocations.every(
                  (allocation) => allocation.document.id != row.id,
                ),
      detail: (row) =>
          '${row.date} · ${booksMoney(draft.editingPayment && !settlement ? booksDecimal(draft.allocationCapacity(row) ?? BigInt.zero) : row.json['outstanding'])} ${draft.editingPayment && !settlement ? 'available to allocate' : 'outstanding'}',
    );
    if (!mounted || row == null) return;
    if (!settlement && draft.editingPayment) {
      await _addAmendmentAllocation(row.id);
      return;
    }
    _edit(() {
      if (!settlement) {
        draft.addAllocation(row);
        return;
      }
      draft.settlementTarget = row;
      final available = booksParsePaise(row.json['outstanding'])!;
      final source =
          booksParsePaise(
            draft.intent.source!.json[draft.advanceSettlement
                ? 'advance_remaining'
                : 'credit_remaining'],
          ) ??
          BigInt.zero;
      draft.set(
        'amount',
        booksDecimal(available < source ? available : source),
      );
      if (draft.get('date').compareTo(row.date) < 0) {
        draft.set('date', row.date);
      }
    });
  }

  Future<void> _addAmendmentAllocation(String id) async {
    if (!_editable) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final exact = await BooksData(
        workspace.company.id,
        workspace.api.get,
      ).record(id);
      if (!mounted) return;
      if (!draft.acceptsPaymentDocument(exact) ||
          (draft.allocationCapacity(exact) ?? BigInt.zero) <= BigInt.zero ||
          exact.date.compareTo(draft.get('date')) > 0) {
        throw const FormatException(
          'This document is no longer available for this payment.',
        );
      }
      setState(() {
        draft.addAllocation(exact);
        _reviewed = null;
      });
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is FormatException
              ? error.message
              : error is ApexApiException
              ? error.message
              : 'Could not verify the selected document.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  static bool _posted(BooksRecord row) =>
      row.json['posted'] == true && row.json['cancelled'] != true;

  Future<void> _chooseBank() async {
    final chosen = await showDialog<BooksJson>(
      context: context,
      builder: (context) => _BankPicker(workspace: workspace),
    );
    if (mounted && chosen != null) {
      _edit(() {
        draft.set('bank_account_id', booksText(chosen['id']));
        draft.set('bank_name', booksText(chosen['name']));
      });
    }
  }

  Future<void> _date(String key) async {
    final now = DateTime.parse(businessDate());
    final date = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(draft.get(key)) ?? now,
      currentDate: now,
      firstDate: DateTime(1900),
      lastDate: DateTime(now.year + 20, 12, 31),
    );
    if (mounted && date != null) _edit(() => draft.set(key, booksDate(date)));
  }

  Future<void> _usePaymentTerms() async {
    if (!_editable) return;
    final party = draft.get('party_id');
    final day = draft.get('date');
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final due = await suggestedBooksDueDate(workspace, party, day);
      if (!mounted ||
          draft.get('date') != day ||
          draft.get('party_id') != party) {
        return;
      }
      setState(() {
        if (due != null) {
          draft.set('due_date', booksDate(due));
        } else {
          _message = 'This party has no saved payment terms.';
        }
      });
    } on ApexApiException catch (error) {
      if (mounted) setState(() => _message = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _message = 'Could not check the saved payment terms.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pastPrices(BooksEntryLine line) async {
    if (!_editable) return;
    final party = draft.get('party_id');
    final item = line.get('item_id');
    final price = await showBooksPriceHistory(
      context,
      workspace,
      party,
      item,
      purchase: draft.purchase,
    );
    if (!mounted ||
        price == null ||
        !draft.lines.contains(line) ||
        draft.get('party_id') != party ||
        line.get('item_id') != item) {
      return;
    }
    _edit(() {
      line.set('rate', price.rate);
      line.inclusive = price.inclusive;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    _sectionNumber = 0;
    final reviewed = _reviewed != null;
    final company = workspace.company;
    final profile = switch (company.taxMode) {
      'regular' => 'Regular GST',
      'composition' => 'Composition',
      'unregistered' => 'Non-GST business',
      _ => '',
    };
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1200),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final wide =
                constraints.maxWidth >=
                MediaQuery.textScalerOf(context).scale(820);
            final gutter = wide ? 24.0 : 16.0;
            return Column(
              children: [
                Padding(
                  padding: EdgeInsets.fromLTRB(
                    gutter,
                    wide ? 20 : 8,
                    gutter,
                    6,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: posting.busy ? null : widget.onBack,
                          icon: const Icon(Icons.arrow_back, size: 18),
                          label: const Text('Back to transactions'),
                          style: TextButton.styleFrom(
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(0, 40),
                            foregroundColor: Apex.link,
                          ),
                        ),
                      ),
                      Semantics(
                        header: true,
                        child: Text(
                          draft.title,
                          style: Apex.registerTitle.copyWith(
                            fontSize: wide ? 26 : 22,
                          ),
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        [
                          company.displayName(),
                          profile,
                        ].where((value) => value.isNotEmpty).join(' · '),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Apex.note,
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: ListView(
                    controller: _scroll,
                    padding: EdgeInsets.fromLTRB(gutter, 8, gutter, 16),
                    children: [
                      if (reviewed)
                        _reviewCard(theme, wide)
                      else
                        ..._fields(wide),
                    ],
                  ),
                ),
                _footer(theme, reviewed: reviewed, wide: wide, gutter: gutter),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _footer(
    ThemeData theme, {
    required bool reviewed,
    required bool wide,
    required double gutter,
  }) {
    final busy = _busy || posting.busy;
    final total = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text('DOCUMENT TOTAL', style: Apex.tableHeader),
        Text(
          reviewed
              ? 'Total  ${booksMoney(_reviewAmount)}'
              : 'Total available after review',
          key: const ValueKey('books-entry-footer-total'),
          style: reviewed ? Apex.panelTitle : Apex.note,
        ),
      ],
    );
    final actions = Wrap(
      alignment: WrapAlignment.end,
      spacing: 8,
      runSpacing: 8,
      children: [
        OutlinedButton(
          onPressed: busy ? null : widget.onBack,
          child: const Text('Cancel'),
        ),
        if (reviewed)
          OutlinedButton(
            onPressed: _editable
                ? () => setState(() => _reviewed = null)
                : null,
            child: const Text('Edit entry'),
          ),
        FilledButton(
          onPressed: _editable ? (reviewed ? _save : _review) : null,
          child: Text(reviewed ? _postLabel : 'Review entry'),
        ),
      ],
    );
    return Material(
      color: Apex.card,
      elevation: wide ? 0 : 6,
      shadowColor: const Color(0x33204132),
      child: SafeArea(
        top: false,
        child: Container(
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: Apex.line)),
          ),
          padding: EdgeInsets.fromLTRB(gutter, 10, gutter, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_message case final error?)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      error,
                      style: const TextStyle(color: Apex.red, fontSize: 13),
                    ),
                  ),
                ),
              if (busy)
                const LinearProgressIndicator(
                  semanticsLabel: 'Working on accounting entry',
                ),
              if (wide)
                Row(
                  children: [
                    Expanded(child: total),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Align(
                        alignment: Alignment.centerRight,
                        child: actions,
                      ),
                    ),
                  ],
                )
              else ...[
                total,
                const SizedBox(height: 6),
                actions,
              ],
            ],
          ),
        ),
      ),
    );
  }

  String get _postLabel => draft.cancel
      ? 'Confirm cancellation'
      : draft.payAtEntry
      ? 'Post with payment'
      : booksDraftKinds.contains(draft.kind)
      ? 'Save draft'
      : draft.intent.editing
      ? 'Save amendment'
      : 'Post entry';

  Widget _reviewCard(ThemeData theme, bool wide) {
    final data = _reviewData;
    final lines = data?['lines'] is List
        ? booksRows(data!['lines'])
        : const <Json>[];
    final entry = <Widget>[
      if (draft.cancel) ...[
        const Text(
          'The journal, stock and allocations will be reversed where applicable. The original record stays in the books.',
        ),
        Text(draft.reason.trim()),
      ] else ...[
        if (draft.get('name').isNotEmpty)
          Text(draft.get('name'), style: theme.textTheme.titleMedium),
        Text(
          [
            draft.get('date'),
            if (draft.get('due_date').isNotEmpty)
              'Due ${draft.get('due_date')}',
          ].join(' · '),
          style: theme.textTheme.bodyMedium,
        ),
        if (lines.isNotEmpty) ...[
          const Divider(),
          for (final row in lines)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              minVerticalPadding: 6,
              title: Text(booksText(row['description'])),
              subtitle: Text(
                [
                  booksText(row['quantity']),
                  booksText(row['unit']),
                  '× ${booksMoney(row['rate'])}',
                ].where((value) => value.isNotEmpty).join(' '),
              ),
              trailing: Text(
                booksMoney(
                  booksDecimal(
                    (booksParsePaise(row['taxable']) ?? BigInt.zero) +
                        (booksParsePaise(row['tax']) ?? BigInt.zero),
                  ),
                ),
              ),
            ),
        ],
        if (draft.usesPaymentAccount)
          Text(
            draft.get('payment_account') == 'cash'
                ? 'Cash'
                : draft
                      .get('bank_name')
                      .ifEmpty(
                        draft.get('bank_account_id') == 'default'
                            ? 'Bank clearing'
                            : 'Bank account',
                      ),
          ),
        if (draft.settlementTarget case final row?)
          Text('Apply to ${row.label}'),
        if (draft.noteSource case final row?) Text('Source ${row.label}'),
      ],
      if (draft.payment && !draft.advance)
        for (final entry in draft.allocations)
          Text('${entry.document.label}  ${booksMoney(entry.amount)}'),
    ];
    final totals = Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Apex.tint,
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
      child: _group([
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: Text('Total', style: theme.textTheme.titleMedium)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                booksMoney(_reviewAmount),
                textAlign: TextAlign.end,
                style: theme.textTheme.headlineSmall,
              ),
            ),
          ],
        ),
        if (data != null)
          Text('Calculated by Apex Books', style: theme.textTheme.bodySmall),
        for (final (label, value) in [
          if (data != null)
            for (final (key, label) in [
              ('taxable', 'Taxable'),
              ('cgst', 'CGST'),
              ('sgst', 'SGST'),
              ('igst', 'IGST'),
              ('supplier_tax', 'Supplier tax'),
              ('round_off', 'Round off'),
            ])
              if (key == 'taxable' ||
                  (booksParsePaise(data[key]) ?? BigInt.zero) != BigInt.zero)
                (label, booksMoney(data[key])),
          if (draft.payAtEntry) ...[
            (
              draft.purchase ? 'Paid now' : 'Received now',
              booksMoney(draft.get('pay_amount')),
            ),
            (
              'Remaining balance',
              booksMoney(
                booksDecimal(
                  booksParsePaise(_reviewAmount)! -
                      booksParsePaise(draft.get('pay_amount'))!,
                ),
              ),
            ),
          ],
        ])
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: Text(label)),
              const SizedBox(width: 8),
              Expanded(child: Text(value, textAlign: TextAlign.end)),
            ],
          ),
      ]),
    );
    return _section('Review before saving', [
      _paired(wide: wide, main: _group(entry), side: totals),
      if (workspace.features.contains('party_credit_limits') &&
          const {
            'sales_invoice',
            'estimate',
            'proforma',
            'sales_order',
          }.contains(draft.kind) &&
          !draft.cancel &&
          !draft.intent.editing &&
          draft.get('party_id').isNotEmpty &&
          booksPositive(_reviewAmount))
        BooksPartyCredit(
          key: ValueKey((
            draft.get('party_id'),
            draft.get('date'),
            _reviewAmount,
          )),
          workspace: workspace,
          party: draft.get('party_id'),
          day: draft.get('date'),
          amount: _reviewAmount!,
        ),
    ]);
  }

  List<Widget> _fields(bool wide) {
    if (draft.needsAmendmentData) {
      return [
        _section(
          draft.editingPayment ? 'Original payment' : 'Original return',
          [
            if (_busy)
              const Text('Checking the original document links…')
            else ...[
              OutlinedButton(
                onPressed: _loadAmendmentData,
                child: const Text('Retry loading original documents'),
              ),
              const Text(
                'You can return to the entry to edit its reference and notes.',
              ),
            ],
          ],
        ),
      ];
    }
    if (draft.cancel) {
      return [
        _section('Cancellation reason', [
          Text(
            '${draft.intent.source!.party} · ${booksMoney(draft.intent.source!.json['amount'])}',
          ),
          _input(
            'Reason',
            draft.reason,
            (value) => draft.reason = value,
            maxLength: 200,
          ),
        ]),
      ];
    }
    if (draft.settlement) {
      return [
        _section('Settlement', [
          Text(draft.intent.source!.label),
          _select('Action', draft.refund ? 'refund' : 'apply', const {
            'apply': 'Apply to document',
            'refund': 'Refund',
          }, (value) => draft.refund = value == 'refund'),
          if (!draft.refund)
            OutlinedButton(
              onPressed: _editable
                  ? () => _chooseAllocation(settlement: true)
                  : null,
              child: Text(draft.settlementTarget?.label ?? 'Choose document'),
            ),
          _field('Amount (₹)', 'amount', numeric: true),
          _dateButton('Date', 'date'),
          if (draft.usesPaymentAccount) ..._paymentFields(),
        ]),
      ];
    }
    final partyFields = _group([
      if (draft.kind == 'purchase_bill' && draft.canPayAtEntry) ...[
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: _editable ? _scanBill : null,
            icon: const Icon(Icons.document_scanner_outlined),
            label: const Text('Scan supplier bill'),
          ),
        ),
        if (_scannedTotal case final total?)
          Text(
            total.isEmpty
                ? 'Review the extracted details against your bill.'
                : 'Printed total ${booksMoney(total)}. Review the extracted details against your bill.',
          ),
      ],
      if (draft.note && !draft.intent.editing)
        OutlinedButton(
          onPressed: _editable ? _chooseNoteSource : null,
          child: Text(
            draft.noteSource?.label ??
                'Choose source ${draft.purchase ? 'bill' : 'invoice'}',
          ),
        ),
      if (draft.note && draft.intent.editing)
        if (draft.noteSource case final source?) Text('Source ${source.label}'),
      if (draft.payment && !draft.editingPayment)
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Record advance'),
          value: draft.advance,
          onChanged: _editable
              ? (value) => _edit(() => draft.switchAdvance(value))
              : null,
        ),
      if (!draft.partyLocked) ...[
        _input(
          draft.expense
              ? 'Payee or description'
              : draft.purchase
              ? 'Supplier name'
              : 'Customer name',
          draft.get('name'),
          draft.setPartyName,
          maxLength: 120,
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: _editable ? _chooseParty : null,
            icon: const Icon(Icons.person_search_outlined),
            label: Text(
              draft.purchase
                  ? 'Choose existing supplier'
                  : 'Choose existing customer',
            ),
          ),
        ),
      ] else if (draft.get('name').isNotEmpty)
        Text(draft.get('name'), style: Theme.of(context).textTheme.titleSmall),
      if (draft.expense) _field('Category', 'category', maxLength: 100),
      if (draft.expense && !draft.intent.editing)
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Itemize expenses'),
          value: draft.itemizedExpense,
          onChanged: _editable
              ? (value) => _edit(() {
                  draft.itemizedExpense = value;
                  if (value && draft.lines.isEmpty) {
                    draft.lines.add(BooksEntryLine());
                  }
                })
              : null,
        ),
    ]);
    final datedDocument = const {
      'sales_invoice',
      'purchase_bill',
    }.contains(draft.kind);
    final documentFields = _group([
      _field('Reference', 'number', hint: 'Automatic if blank', maxLength: 16),
      Wrap(
        spacing: 8,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          _dateButton('Date', 'date'),
          if (datedDocument) ...[
            _dateButton('Due date', 'due_date'),
            if (workspace.features.contains('party_payment_terms') &&
                draft.get('party_id').isNotEmpty)
              TextButton(
                onPressed: _editable ? _usePaymentTerms : null,
                child: const Text('Use party terms'),
              ),
            if (draft.get('due_date').isNotEmpty)
              IconButton(
                icon: const Icon(Icons.clear),
                tooltip: 'Clear due date',
                onPressed: _editable
                    ? () => _edit(() => draft.set('due_date', ''))
                    : null,
              ),
          ],
        ],
      ),
    ]);
    return [
      _section(
        datedDocument
            ? (draft.purchase
                  ? 'Supplier & document details'
                  : 'Customer & document details')
            : 'Document details',
        [_paired(wide: wide, main: partyFields, side: documentFields)],
      ),
      if (draft.hasLines)
        _section('Line items', [
          for (final (index, line) in draft.lines.indexed)
            _line(index, line, wide),
          if (draft.note) ...[
            if (draft.noteSource != null && draft.sourceLines.isEmpty)
              const Text('No source lines are available.'),
            for (final (index, line) in draft.sourceLines.indexed)
              if (booksReturnStartingQuantity(line) != null)
                OutlinedButton.icon(
                  onPressed:
                      !_editable ||
                          draft.lines.length >= 100 ||
                          draft.lines.any(
                            (existing) => existing.returnSourceIndex == index,
                          )
                      ? null
                      : () => _edit(() => draft.addSourceLine(line)),
                  icon: const Icon(Icons.add),
                  label: Text(
                    '${booksText(line['description'])} · ${booksText(line['remaining_return_quantity'] ?? line['quantity'])} available',
                  ),
                ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Move returned items in stock'),
              value: draft.returnStock,
              onChanged: _editable
                  ? (value) => _edit(() => draft.returnStock = value)
                  : null,
            ),
          ] else
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                onPressed: _editable && draft.lines.length < 100
                    ? () => _edit(() => draft.lines.add(BooksEntryLine()))
                    : null,
                icon: const Icon(Icons.add),
                label: const Text('Add line'),
              ),
            ),
        ]),
      if (draft.payment && !draft.advance)
        _section('Apply payment', [
          for (final allocation in draft.allocations)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                '${allocation.document.label} · ${allocation.document.party}',
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (draft.editingPayment)
                    Text(
                      '${booksMoney(booksDecimal(draft.allocationCapacity(allocation.document) ?? BigInt.zero))} available to allocate',
                    ),
                  _input(
                    'Allocated amount (₹)',
                    allocation.amount,
                    (value) => allocation.amount = value,
                    numeric: true,
                  ),
                ],
              ),
              trailing: IconButton(
                onPressed: _editable
                    ? () => _edit(() => draft.allocations.remove(allocation))
                    : null,
                tooltip: 'Remove allocation',
                icon: const Icon(Icons.delete_outline),
              ),
            ),
          OutlinedButton(
            onPressed: _editable && draft.allocations.length < 100
                ? _chooseAllocation
                : null,
            child: const Text('Choose invoice or bill'),
          ),
          Text('Total payment  ${booksMoney(draft.amount)}'),
        ]),
      if (draft.canPayAtEntry &&
          workspace.features.contains('payment_at_entry'))
        _section(draft.purchase ? 'Supplier payment' : 'Customer payment', [
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(draft.purchase ? 'Paid now' : 'Received now'),
            value: draft.payAtEntry,
            onChanged: _editable
                ? (value) => _edit(() => draft.payAtEntry = value)
                : null,
          ),
          if (draft.payAtEntry) ...[
            _field('Payment amount (₹)', 'pay_amount', numeric: true),
            ..._paymentFields(),
            _field('Payment reference', 'pay_reference', maxLength: 200),
          ],
        ]),
      if (draft.usesPaymentAccount && !draft.payAtEntry)
        _section('Payment', [
          if (!draft.hasLines && (!draft.payment || draft.advance))
            _field('Amount (₹)', 'amount', numeric: true),
          ..._paymentFields(),
          if (draft.advance && draft.regular && !draft.purchase) ...[
            _select('Advance for', draft.get('advance_supply'), const {
              'goods': 'Goods',
              'services': 'Services',
            }, (value) => draft.set('advance_supply', value)),
            if (draft.get('advance_supply') == 'services') ...[
              _field('Advance GST rate (%)', 'advance_gst_rate', numeric: true),
              _field(
                'Place of supply (state code)',
                'place_of_supply',
                maxLength: 2,
                digits: true,
              ),
            ],
          ],
        ]),
      if (!draft.payment)
        _section('Billing and notes', [
          if (draft.hasLines) ...[
            _field('GSTIN', 'party_gstin', maxLength: 15, upper: true),
            if (draft.regular || draft.purchase)
              _field(
                'Place of supply (state code)',
                'place_of_supply',
                maxLength: 2,
                digits: true,
              ),
            if (draft.purchase)
              _field(
                'Supplier state code',
                'supplier_state',
                maxLength: 2,
                digits: true,
              ),
            _field(
              'Document discount (%)',
              'document_discount_percent',
              numeric: true,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Round total to nearest rupee'),
              value: draft.round,
              onChanged: _editable
                  ? (value) => _edit(() => draft.round = value)
                  : null,
            ),
          ],
          _field('Billing address', 'party_address', maxLength: 1000),
          if (!draft.purchase)
            _field('Shipping address', 'shipping_address', maxLength: 1000),
          _field('Notes', 'notes', lines: 2, maxLength: 1000),
        ]),
    ];
  }

  Widget _line(int index, BooksEntryLine line, bool wide) {
    final theme = Theme.of(context);
    final remove = IconButton(
      onPressed: _editable ? () => _edit(() => draft.lines.remove(line)) : null,
      tooltip: 'Remove line ${index + 1}',
      icon: const Icon(Icons.delete_outline, size: 20),
    );
    final description = _lineField(
      line,
      'Description',
      'description',
      maxLength: 200,
      locked: draft.note || line.get('item_id').isNotEmpty,
    );
    final quantity = _lineField(line, 'Quantity', 'quantity', numeric: true);
    final rate = _lineField(line, 'Unit rate (₹)', 'rate', numeric: true);
    final discount = _lineField(
      line,
      line.fixedDiscount ? 'Discount (₹)' : 'Discount (%)',
      line.fixedDiscount ? 'discount_amount' : 'discount_percent',
      numeric: true,
    );
    return Container(
      key: ObjectKey(line),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
      decoration: BoxDecoration(
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
        color: Apex.tint,
      ),
      child: Semantics(
        container: true,
        label: 'Line ${index + 1}',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (wide)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 10,
                children: [
                  Expanded(flex: 5, child: description),
                  Expanded(flex: 2, child: quantity),
                  Expanded(flex: 2, child: rate),
                  Expanded(flex: 2, child: discount),
                  remove,
                ],
              )
            else ...[
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Line ${index + 1}',
                      style: theme.textTheme.titleSmall,
                    ),
                  ),
                  remove,
                ],
              ),
              description,
            ],
            if (!draft.note)
              Wrap(
                spacing: 8,
                children: [
                  TextButton(
                    onPressed: _editable ? () => _chooseItem(line) : null,
                    child: Text(
                      line.get('item_id').isEmpty
                          ? 'Choose saved item'
                          : 'Change saved item',
                    ),
                  ),
                  if (line.get('item_id').isNotEmpty)
                    TextButton(
                      onPressed: _editable
                          ? () => _edit(() => line.set('item_id', ''))
                          : null,
                      child: const Text('Clear item link'),
                    ),
                  if (line.get('item_id').isNotEmpty &&
                      draft.get('party_id').isNotEmpty &&
                      workspace.features.contains('party_price_history') &&
                      !draft.expense)
                    TextButton(
                      onPressed: _editable ? () => _pastPrices(line) : null,
                      child: const Text('Past prices'),
                    ),
                ],
              ),
            if (!wide)
              LayoutBuilder(
                builder: (context, constraints) =>
                    constraints.maxWidth >=
                        MediaQuery.textScalerOf(context).scale(216)
                    ? Row(
                        spacing: 8,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: quantity),
                          Expanded(child: rate),
                        ],
                      )
                    : Column(children: [quantity, rate]),
              ),
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              dense: true,
              shape: const Border(),
              collapsedShape: const Border(),
              title: const Text('Tax, unit and discount'),
              children: [
                _paired(
                  wide: wide,
                  main: _lineField(line, 'Unit', 'unit', maxLength: 24),
                  side: _lineField(line, 'HSN/SAC', 'hsn', maxLength: 16),
                ),
                if (draft.regular || draft.purchase) ...[
                  _select(
                    'GST treatment',
                    line.get('tax_treatment'),
                    const {
                      'taxable': 'Taxable',
                      'nil_rated': 'Nil rated',
                      'exempt': 'Exempt',
                      'non_gst': 'Non-GST',
                    },
                    (value) {
                      line.set('tax_treatment', value);
                      if (value != 'taxable') line.set('gst_rate', '0');
                    },
                    locked: draft.note,
                  ),
                  if (line.get('tax_treatment') == 'taxable')
                    _lineField(
                      line,
                      'GST rate (%)',
                      'gst_rate',
                      numeric: true,
                      locked: draft.note,
                    ),
                  if (draft.purchase && draft.regular)
                    _select(
                      'Supplier input GST',
                      line.get('itc_treatment'),
                      const {
                        'pending_review': 'Pending input-credit review',
                        'ineligible': 'Ineligible',
                      },
                      (value) => line.set('itc_treatment', value),
                      locked: draft.note,
                    ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Rate includes GST'),
                    value: line.inclusive,
                    onChanged: _editable && !draft.note
                        ? (value) => _edit(() => line.inclusive = value)
                        : null,
                  ),
                ],
                _select(
                  'Discount type',
                  line.fixedDiscount ? 'amount' : 'percent',
                  const {'percent': 'Percent', 'amount': 'Fixed amount'},
                  (value) {
                    line.fixedDiscount = value == 'amount';
                    line.set('discount_percent', '');
                    line.set('discount_amount', '');
                  },
                ),
                if (!wide) discount,
              ],
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _paymentFields() => [
    _select('Payment method', draft.get('payment_account'), const {
      'cash': 'Cash',
      'bank': 'Bank / UPI / card',
    }, (value) => draft.set('payment_account', value)),
    if (draft.get('payment_account') == 'bank')
      OutlinedButton(
        onPressed: _editable ? _chooseBank : null,
        child: Text(
          draft
              .get('bank_name')
              .ifEmpty(
                draft.get('bank_account_id') == 'default'
                    ? 'Bank clearing (legacy)'
                    : draft.get('bank_account_id').isEmpty
                    ? 'Choose bank account'
                    : 'Saved bank account',
              ),
        ),
      ),
  ];

  Widget _group(List<Widget> children, {double spacing = 10}) => Column(
    spacing: spacing,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: children,
  );

  Widget _paired({
    required bool wide,
    required Widget main,
    required Widget side,
  }) {
    if (!wide) return _group([main, side], spacing: 16);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 24,
      children: [
        Expanded(flex: 3, child: main),
        Expanded(flex: 2, child: side),
      ],
    );
  }

  Widget _section(String label, List<Widget> children) {
    final number = (++_sectionNumber).toString().padLeft(2, '0');
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: ApexPanel(
        padding: const EdgeInsets.all(16),
        child: Material(
          type: MaterialType.transparency,
          child: _group([
            Row(
              spacing: 10,
              children: [
                Container(
                  width: 28,
                  height: 28,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Apex.mintIcon,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    number,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Apex.greenText,
                    ),
                  ),
                ),
                Expanded(
                  child: Semantics(
                    header: true,
                    child: Text(label, style: Apex.panelTitle),
                  ),
                ),
              ],
            ),
            ...children,
          ], spacing: 12),
        ),
      ),
    );
  }

  int _sectionNumber = 0;

  Widget _dateButton(String label, String key) => OutlinedButton.icon(
    onPressed: _editable ? () => _date(key) : null,
    icon: const Icon(Icons.calendar_today_outlined),
    label: Text(draft.get(key).isEmpty ? label : '$label  ${draft.get(key)}'),
  );

  Widget _field(
    String label,
    String key, {
    String? hint,
    int? maxLength,
    bool numeric = false,
    bool digits = false,
    bool upper = false,
    int lines = 1,
  }) => _input(
    label,
    draft.get(key),
    (value) => draft.set(key, upper ? value.toUpperCase() : value),
    hint: hint,
    maxLength: maxLength,
    numeric: numeric,
    digits: digits,
    lines: lines,
  );

  Widget _lineField(
    BooksEntryLine line,
    String label,
    String key, {
    int? maxLength,
    bool numeric = false,
    bool locked = false,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: _input(
      label,
      line.get(key),
      (value) => line.set(key, value),
      maxLength: maxLength,
      numeric: numeric,
      locked: locked,
    ),
  );

  Widget _input(
    String label,
    String value,
    ValueChanged<String> onChange, {
    String? hint,
    int? maxLength,
    bool numeric = false,
    bool digits = false,
    bool locked = false,
    int lines = 1,
  }) => _SyncedField(
    label: label,
    value: value,
    onChange: (value) => _edit(() => onChange(value)),
    enabled: _editable && !locked,
    hint: hint,
    maxLength: maxLength,
    numeric: numeric,
    digits: digits,
    lines: lines,
  );

  Widget _select(
    String label,
    String current,
    Map<String, String> choices,
    ValueChanged<String> change, {
    bool locked = false,
  }) => DropdownButtonFormField<String>(
    key: ValueKey((label, current)),
    initialValue: choices.containsKey(current) ? current : null,
    decoration: InputDecoration(labelText: label),
    isExpanded: true,
    items: [
      for (final entry in choices.entries)
        DropdownMenuItem(value: entry.key, child: Text(entry.value)),
    ],
    onChanged: !_editable || locked
        ? null
        : (value) {
            if (value != null) _edit(() => change(value));
          },
  );
}

class _SyncedField extends StatefulWidget {
  const _SyncedField({
    required this.label,
    required this.value,
    required this.onChange,
    required this.enabled,
    required this.numeric,
    required this.digits,
    required this.lines,
    this.hint,
    this.maxLength,
  });
  final String label;
  final String value;
  final ValueChanged<String> onChange;
  final bool enabled;
  final bool numeric;
  final bool digits;
  final int lines;
  final String? hint;
  final int? maxLength;

  @override
  State<_SyncedField> createState() => _SyncedFieldState();
}

class _SyncedFieldState extends State<_SyncedField> {
  late final _controller = TextEditingController(text: widget.value);

  @override
  void didUpdateWidget(covariant _SyncedField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_controller.text != widget.value) {
      _controller.value = TextEditingValue(
        text: widget.value,
        selection: TextSelection.collapsed(offset: widget.value.length),
      );
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
    controller: _controller,
    onChanged: widget.onChange,
    enabled: widget.enabled,
    maxLength: widget.maxLength,
    minLines: widget.lines,
    maxLines: widget.lines,
    keyboardType: widget.numeric || widget.digits
        ? TextInputType.numberWithOptions(decimal: widget.numeric)
        : null,
    decoration: InputDecoration(
      labelText: widget.label,
      hintText: widget.hint,
      counterText: '',
    ),
  );
}

class _BankPicker extends StatefulWidget {
  const _BankPicker({required this.workspace});
  final WorkspaceContext workspace;

  @override
  State<_BankPicker> createState() => _BankPickerState();
}

class _BankPickerState extends State<_BankPicker> {
  late Future<List<BooksJson>> _future;
  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<BooksJson>> _load() async => booksRows(
    await widget.workspace.api.get('${widget.workspace.path}/bank-accounts'),
  );

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Choose bank account'),
    content: SizedBox(
      width: 420,
      child: FutureBuilder<List<BooksJson>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const LinearProgressIndicator(
              semanticsLabel: 'Loading bank accounts',
            );
          }
          if (!snapshot.hasData) {
            return OutlinedButton(
              onPressed: () => setState(() => _future = _load()),
              child: const Text('Retry loading accounts'),
            );
          }
          return ListView(
            shrinkWrap: true,
            children: [
              if (snapshot.data!.isEmpty)
                const Text('No bank accounts are available.'),
              for (final item in snapshot.data!)
                ListTile(
                  title: Text(booksText(item['name'])),
                  onTap: () => Navigator.of(context).pop(item),
                ),
            ],
          );
        },
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Close'),
      ),
    ],
  );
}
