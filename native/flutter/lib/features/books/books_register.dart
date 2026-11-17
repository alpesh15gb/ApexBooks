import 'dart:async';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import 'books_data.dart';
import 'books_attachments.dart';
import 'books_detail.dart';
import 'books_document_output.dart';
import 'books_edit_details.dart';
import 'books_entry_draft.dart';
import 'books_entry_editor.dart';
import 'books_entry_posting.dart';
import 'books_recurring.dart';
import 'register_list.dart';
import 'register_query.dart';

class BooksRegister extends StatefulWidget {
  const BooksRegister({
    required this.workspace,
    this.active = true,
    this.revision = 0,
    this.entryRequest = 0,
    this.kind = '',
    this.title = 'Transactions',
    this.recurringRequest = 0,
    super.key,
  });

  final WorkspaceContext workspace;
  final bool active;
  final int revision;
  final int entryRequest;

  /// Document type this page shows ('' for every type), as chosen in the navigation.
  final String kind;
  final String title;

  /// Changes when the navigation asks for recurring drafts.
  final int recurringRequest;

  @override
  State<BooksRegister> createState() => _BooksRegisterState();
}

class _BooksRegisterState extends State<BooksRegister> {
  final _search = TextEditingController();
  final _records = <String, BooksRecord>{};
  final _details = <String>[];
  late BooksPosting _posting;
  BooksEntryDraft? _editor;
  BooksRecord? _detailsToEdit;
  bool _recurring = false;
  BooksRecord? _recurringSource;
  String? _notice;
  bool _loadingSource = false;
  String? _editorNotice;
  int _detailRevision = 0;
  String _kind = '';
  BooksRegisterQuery _query = const BooksRegisterQuery();
  int _page = 1;
  bool _moreFilters = false;
  int _offset = 0;
  int _generation = 0;
  bool _hasMore = true;
  bool _loading = false;
  bool _failed = false;
  int _seenEntryRequest = 0;
  bool _showingEntryChooser = false;

  BooksData get _data =>
      BooksData(widget.workspace.company.id, widget.workspace.api.get);

  @override
  void initState() {
    super.initState();
    _kind = widget.kind;
    _recurring = widget.recurringRequest != 0;
    _posting = BooksPosting(widget.workspace)..addListener(_checkEntryRequest);
    if (widget.active) unawaited(_posting.recover());
    if (widget.active) unawaited(_load());
    _checkEntryRequest();
  }

  @override
  void didUpdateWidget(covariant BooksRegister oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workspace.company.id != widget.workspace.company.id ||
        oldWidget.workspace.api != widget.workspace.api ||
        oldWidget.workspace.company.role != widget.workspace.company.role) {
      _posting.dispose();
      _posting = BooksPosting(widget.workspace)
        ..addListener(_checkEntryRequest);
      _editor = null;
      _detailsToEdit = null;
      _recurring = false;
      _recurringSource = null;
      _notice = null;
      _details.clear();
      _kind = '';
      _resetView();
      if (widget.active) unawaited(_posting.recover());
      _reload();
    } else if (oldWidget.kind != widget.kind ||
        oldWidget.recurringRequest != widget.recurringRequest) {
      // A different page in the navigation: show its list, not the last open record.
      _kind = widget.kind;
      _resetView();
      _details.clear();
      _recurring = widget.recurringRequest != 0;
      _recurringSource = null;
      _notice = null;
      if (!oldWidget.active && !_posting.ready) unawaited(_posting.recover());
      _reload();
    } else if (widget.active &&
        (!oldWidget.active || oldWidget.revision != widget.revision)) {
      if (!oldWidget.active && !_posting.ready) unawaited(_posting.recover());
      _reload();
    } else if (oldWidget.active && !widget.active) {
      _generation++;
      _loading = false;
    }
    _checkEntryRequest();
  }

  @override
  void dispose() {
    _search.dispose();
    _posting.dispose();
    super.dispose();
  }

  void _resetView() {
    _search.clear();
    _query = const BooksRegisterQuery();
    _page = 1;
    _moreFilters = false;
  }

  void _reload() {
    _generation++;
    _offset = 0;
    _hasMore = true;
    _loading = false;
    _records.clear();
    if (widget.active) unawaited(_load());
  }

  /// Loads every page of the selected kind so counts and totals are complete.
  Future<void> _load() async {
    if (!widget.active || _loading || !_hasMore) return;
    final generation = _generation;
    final data = _data;
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      do {
        final page = await data.records(
          kind: _kind.isEmpty ? null : _kind,
          offset: _offset,
        );
        if (!mounted || generation != _generation) return;
        setState(() {
          for (final row in page.records) {
            _records[row.id] = row;
          }
          _offset = page.nextOffset;
          _hasMore = page.hasMore;
        });
      } while (_hasMore);
    } catch (_) {
      if (mounted && generation == _generation) setState(() => _failed = true);
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  void _open(String id) => setState(() => _details.add(id));

  bool get _canOpenEntryChooser =>
      widget.active &&
      _posting.canStart &&
      _editor == null &&
      _detailsToEdit == null &&
      !_recurring &&
      !_showingEntryChooser;

  void _checkEntryRequest() {
    final request = widget.entryRequest;
    if (!widget.active ||
        request == 0 ||
        request == _seenEntryRequest ||
        _posting.checking) {
      return;
    }
    _seenEntryRequest = request;
    if (!_canOpenEntryChooser) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && widget.entryRequest == request) unawaited(_newEntry());
    });
  }

  Future<void> _newEntry() async {
    if (!_canOpenEntryChooser) return;
    // A page for one document type creates that type directly, like the web app's "Add" button.
    if (booksEntryKinds.contains(widget.kind)) {
      _start(BooksEntryIntent(widget.kind));
      return;
    }
    final posting = _posting;
    _showingEntryChooser = true;
    String? kind;
    try {
      kind = await showDialog<String>(
        context: context,
        builder: (context) => SimpleDialog(
          title: const Text('New entry'),
          children: [
            for (final kind in booksEntryKinds)
              SimpleDialogOption(
                onPressed: () => Navigator.of(context).pop(kind),
                child: Text(booksKindLabel(kind)),
              ),
          ],
        ),
      );
    } finally {
      _showingEntryChooser = false;
    }
    if (mounted &&
        widget.active &&
        identical(_posting, posting) &&
        kind != null) {
      _start(BooksEntryIntent(kind));
    }
  }

  void _start(BooksEntryIntent intent) {
    if (!_posting.canStart || !widget.active || _loadingSource) return;
    final source = intent.source;
    // Register rows are compact and omit item lines; edits, conversions and
    // returns need the full document, like the web app loads before editing.
    if (source != null && _compactSource(source)) {
      unawaited(_startWithFullSource(intent, source));
      return;
    }
    _openEditor(intent);
  }

  static bool _compactSource(BooksRecord source) {
    // Compact rows carry neither item lines nor a payment's allocations.
    if (booksPaymentKinds.contains(source.kind)) {
      return source.json['allocations'] == null;
    }
    final lines = source.data['lines'];
    return lines is List && lines.isEmpty;
  }

  Future<void> _startWithFullSource(
    BooksEntryIntent intent,
    BooksRecord source,
  ) async {
    final posting = _posting;
    setState(() => _loadingSource = true);
    try {
      final full = await _data.record(source.id);
      if (!mounted || !widget.active || !identical(posting, _posting)) return;
      _loadingSource = false;
      _openEditor(
        BooksEntryIntent(
          intent.kind,
          source: full,
          operation: intent.operation,
          convert: intent.convert,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      setState(
        () => _notice =
            'Could not load ${source.label}. Check the connection and try again.',
      );
    } finally {
      if (mounted && _loadingSource) setState(() => _loadingSource = false);
    }
  }

  void _openEditor(BooksEntryIntent intent) {
    if (!_posting.canStart || !widget.active) return;
    setState(() {
      _editor = BooksEntryDraft(intent, widget.workspace.company);
      _editorNotice = null;
      _notice = null;
    });
  }

  Future<void> _retryWrite() async {
    final posting = _posting;
    final record = await posting.retry();
    if (mounted && identical(posting, _posting) && record != null) {
      _saved(record, null);
    }
  }

  /// "Save & new": the saved document is recorded and a fresh draft of the same type opens.
  void _savedAndNew(BooksRecord record, String? reviewedAmount) {
    final kind = _editor?.kind;
    if (kind == null || record.kind == 'recurring_template') {
      _saved(record, reviewedAmount);
      return;
    }
    final actual = booksParsePaise(record.json['amount']);
    final reviewed = booksParsePaise(reviewedAmount);
    setState(() {
      _editor = BooksEntryDraft(BooksEntryIntent(kind), widget.workspace.company);
      _editorNotice = reviewed != null && actual != null && reviewed != actual
          ? '${record.label} saved at ${booksMoney(record.json['amount'])}. The posted amount differs from the reviewed amount.'
          : '${record.label} saved.';
      _detailRevision++;
    });
    _reload();
    unawaited(_refreshAfterSave());
  }

  void _saved(BooksRecord record, String? reviewedAmount) {
    if (record.kind == 'recurring_template') {
      setState(() {
        _recurring = true;
        _notice = null;
      });
      return;
    }
    final actual = booksParsePaise(record.json['amount']);
    final reviewed = booksParsePaise(reviewedAmount);
    setState(() {
      _editor = null;
      _detailsToEdit = null;
      _recurring = false;
      _detailRevision++;
      if (_details.lastOrNull != record.id) _details.add(record.id);
      _notice = reviewed != null && actual != null && reviewed != actual
          ? '${record.label} saved at ${booksMoney(record.json['amount'])}. The posted amount differs from the reviewed amount.'
          : '${record.label} saved.';
    });
    _reload();
    unawaited(_refreshAfterSave());
  }

  Future<void> _refreshAfterSave() async {
    try {
      await widget.workspace.refresh();
    } catch (_) {
      // The server has confirmed posting. A workspace refresh cannot change that outcome.
    }
  }

  /// The write actions available for a record, in display order. Shared by the
  /// detail screen (full buttons) and the register rows (primary link + menu).
  List<RegisterRowAction> _rowActions(BooksRecord row) {
    if (!_posting.canStart || row.json['cancelled'] == true) return const [];
    final rowPosted = row.json['posted'] == true;
    final editableDraft =
        booksDraftKinds.contains(row.kind) &&
        booksText(row.json['converted_to']).isEmpty &&
        row.data['purchase_order_receiving_started'] != true;
    final receivesPurchase = widget.workspace.features.contains(
      'purchase_order_receiving',
    );
    final receivable = const {'sales_invoice', 'opening_receivable'}.contains(
      row.kind,
    );
    return [
      if (rowPosted &&
          const {
            'sales_invoice',
            'purchase_bill',
            'opening_receivable',
            'opening_payable',
          }.contains(row.kind) &&
          booksPositive(row.json['outstanding']))
        RegisterRowAction(
          label: row.kind == 'sales_invoice'
              ? 'Collect payment'
              : row.kind == 'purchase_bill'
              ? 'Pay bill'
              : receivable
              ? 'Record receipt'
              : 'Record payment',
          detailLabel: receivable ? 'Record receipt' : 'Record payment',
          style: RegisterActionStyle.tonal,
          run: () => _start(
            BooksEntryIntent(
              receivable ? 'payment_in' : 'payment_out',
              source: row,
            ),
          ),
        ),
      if (rowPosted &&
          const {'sales_invoice', 'purchase_bill'}.contains(row.kind))
        RegisterRowAction(
          label: row.kind == 'sales_invoice'
              ? 'Sales return'
              : 'Purchase return',
          detailLabel: row.kind == 'sales_invoice'
              ? 'Create credit note'
              : 'Create debit note',
          run: () => _start(
            BooksEntryIntent(
              row.kind == 'sales_invoice' ? 'credit_note' : 'debit_note',
              source: row,
            ),
          ),
        ),
      if (rowPosted &&
          const {'credit_note', 'debit_note'}.contains(row.kind) &&
          booksPositive(row.json['credit_remaining']))
        RegisterRowAction(
          label: 'Settle credit',
          run: () => _start(
            BooksEntryIntent(
              row.kind,
              source: row,
              operation: BooksOperation.credit,
            ),
          ),
        ),
      if (rowPosted &&
          booksPaymentKinds.contains(row.kind) &&
          row.data['is_advance'] == true &&
          booksPositive(row.json['advance_remaining']))
        RegisterRowAction(
          label: 'Settle advance',
          run: () => _start(
            BooksEntryIntent(
              row.kind,
              source: row,
              operation: BooksOperation.advanceApply,
            ),
          ),
        ),
      if (editableDraft && row.kind != 'purchase_order')
        RegisterRowAction(
          label: 'Convert to invoice',
          run: () => _start(
            BooksEntryIntent('sales_invoice', source: row, convert: true),
          ),
        ),
      if (editableDraft &&
          widget.workspace.features.contains('recurring_drafts'))
        RegisterRowAction(
          label: 'Recurring schedule',
          run: () => setState(() {
            _recurring = true;
            _recurringSource = row;
          }),
        ),
      if (editableDraft && const {'estimate', 'proforma'}.contains(row.kind))
        RegisterRowAction(
          label: 'Convert to sales order',
          run: () => _start(
            BooksEntryIntent('sales_order', source: row, convert: true),
          ),
        ),
      if (editableDraft && row.kind == 'purchase_order' && !receivesPurchase)
        RegisterRowAction(
          label: 'Convert to purchase bill',
          run: () => _start(
            BooksEntryIntent('purchase_bill', source: row, convert: true),
          ),
        ),
      if (widget.workspace.api is ApexWriteApi &&
          (editableDraft ||
              (rowPosted &&
                  (const {
                        'sales_invoice',
                        'purchase_bill',
                        'expense',
                        ...booksPaymentKinds,
                      }.contains(row.kind) ||
                      (const {'credit_note', 'debit_note'}.contains(row.kind) &&
                          row.data['pos_return'] != true &&
                          booksText(row.data['applied_to']).isNotEmpty)))))
        RegisterRowAction(
          label: editableDraft ? 'Edit draft' : 'Amend entry',
          run: () => _start(
            BooksEntryIntent(
              row.kind,
              source: row,
              operation: editableDraft
                  ? BooksOperation.draft
                  : BooksOperation.amend,
            ),
          ),
        ),
      if (widget.workspace.api is ApexWriteApi &&
          supportsBooksDetailAmendment(row))
        RegisterRowAction(
          label: 'Edit details',
          run: () => setState(() => _detailsToEdit = row),
        ),
      if (rowPosted &&
          booksEntryKinds.contains(row.kind) &&
          widget.workspace.features.contains('document_cancellation'))
        RegisterRowAction(
          label: 'Cancel posted entry',
          style: RegisterActionStyle.text,
          run: () => _start(
            BooksEntryIntent(
              row.kind,
              source: row,
              operation: BooksOperation.cancel,
            ),
          ),
        ),
    ];
  }

  Widget _entryActions(BooksRecord row) {
    final actions = _rowActions(row);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BooksDocumentOutput(workspace: widget.workspace, record: row),
        if (widget.workspace.features.contains('document_attachments') &&
            const {'purchase_bill', 'expense'}.contains(row.kind))
          BooksAttachments(workspace: widget.workspace, record: row),
        if (_notice case final notice?)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Semantics(liveRegion: true, child: Text(notice)),
          ),
        if (actions.isNotEmpty)
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              for (final action in actions)
                switch (action.style) {
                  RegisterActionStyle.tonal => FilledButton.tonal(
                    onPressed: action.run,
                    child: Text(action.detailLabel ?? action.label),
                  ),
                  RegisterActionStyle.outlined => OutlinedButton(
                    onPressed: action.run,
                    child: Text(action.detailLabel ?? action.label),
                  ),
                  RegisterActionStyle.text => TextButton(
                    onPressed: action.run,
                    child: Text(action.detailLabel ?? action.label),
                  ),
                },
            ],
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active &&
        _editor == null &&
        _detailsToEdit == null &&
        !_recurring) {
      return const SizedBox.shrink();
    }
    return ListenableBuilder(
      listenable: _posting,
      builder: (context, _) => _content(context),
    );
  }

  Widget _content(BuildContext context) {
    final confirmingInPlace =
        _posting.busy &&
        (_editor != null || _detailsToEdit != null || _recurring);
    if ((_posting.pending != null && !confirmingInPlace) ||
        _posting.recoveryError != null) {
      final attempt = _posting.pending;
      return Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: ListView(
            padding: const EdgeInsets.all(20),
            shrinkWrap: true,
            children: [
              Text(
                attempt == null
                    ? 'Check saved accounting requests'
                    : '${attempt.command.label} awaiting confirmation',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                _posting.recoveryError ??
                    _posting.message ??
                    'Retry the saved request to confirm its result.',
              ),
              const SizedBox(height: 12),
              if (_posting.busy || _posting.checking)
                const LinearProgressIndicator()
              else
                FilledButton(
                  onPressed: attempt == null || !_posting.ready
                      ? _posting.recover
                      : _retryWrite,
                  child: Text(
                    attempt == null || !_posting.ready
                        ? 'Check saved requests'
                        : 'Retry original request',
                  ),
                ),
            ],
          ),
        ),
      );
    }
    if (_editor case final editor?) {
      return BooksEntryEditor(
        key: ObjectKey(editor),
        draft: editor,
        posting: _posting,
        onBack: () => setState(() => _editor = null),
        onSaved: _saved,
        onSavedAndNew: _savedAndNew,
        notice: _editorNotice,
      );
    }
    if (_detailsToEdit case final record?) {
      return BooksEditDetails(
        key: ObjectKey(record),
        posting: _posting,
        record: record,
        onBack: () => setState(() {
          _detailsToEdit = null;
          _detailRevision++;
        }),
        onSaved: (saved) => _saved(saved, null),
      );
    }
    if (_recurring) {
      return BooksRecurring(
        showBack: widget.recurringRequest == 0,
        posting: _posting,
        source: _recurringSource,
        onBack: () => setState(() {
          _recurring = false;
          _recurringSource = null;
        }),
        onGenerated: (record) => _saved(record, null),
      );
    }
    if (_details.isNotEmpty) {
      final id = _details.last;
      return BooksRecordDetail(
        key: ValueKey((_data.companyId, id, widget.revision, _detailRevision)),
        data: _data,
        id: id,
        onBack: () => setState(() => _details.removeLast()),
        onOpen: _open,
        backLabel: _details.length == 1 ? 'Transactions' : 'Previous record',
        actions: _entryActions,
      );
    }
    final all = _records.values.toList(growable: false);
    final query = _query.copyWith(search: _search.text);
    final today = businessDate();
    final scoped = registerScope(all, query);
    final visible = registerVisible(_kind, scoped, query, today);
    final singular = widget.title.endsWith('s')
        ? widget.title.substring(0, widget.title.length - 1)
        : widget.title;
    return BooksRegisterList(
      kind: _kind,
      title: widget.title,
      addLabel: booksEntryKinds.contains(widget.kind)
          ? 'Add ${singular.toLowerCase()}'
          : 'New entry',
      allRecords: all,
      scoped: scoped,
      visible: visible,
      query: query,
      today: today,
      search: _search,
      page: _page,
      expandedFilters: _moreFilters,
      loading: _loading,
      failed: _failed,
      canWrite: widget.workspace.company.canWrite,
      onAdd: _posting.canStart ? _newEntry : null,
      onRecurring: widget.workspace.features.contains('recurring_drafts')
          ? () => setState(() {
              _recurring = true;
              _recurringSource = null;
            })
          : null,
      onRefresh: _loading ? null : _reload,
      onRetry: _load,
      onOpen: _open,
      actionsFor: _rowActions,
      onQuery: (value) => setState(() {
        _query = value.copyWith(search: '');
        _page = 1;
      }),
      onSearch: () => setState(() => _page = 1),
      onPage: (value) => setState(() => _page = value),
      onExpandFilters: (value) => setState(() => _moreFilters = value),
      onReset: () => setState(() {
        _search.clear();
        _query = const BooksRegisterQuery();
        _page = 1;
      }),
      onKind: widget.kind.isEmpty
          ? (value) {
              setState(() {
                _kind = value;
                _query = _query.copyWith(tab: 'all', party: '');
                _page = 1;
              });
              _reload();
            }
          : null,
    );
  }
}
