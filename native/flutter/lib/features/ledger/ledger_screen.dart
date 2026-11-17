import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../banking/bank_widgets.dart';
import '../books/books_data.dart';
import '../books/books_detail.dart';
import 'journal_editor.dart';

typedef _LedgerData = ({List<Json> accounts, List<Json> journals, Json? balance});

class LedgerScreen extends StatefulWidget {
  const LedgerScreen({required this.workspace, this.revision = 0, super.key});

  final WorkspaceContext workspace;
  final int revision;

  @override
  State<LedgerScreen> createState() => _LedgerScreenState();
}

class _LedgerScreenState extends State<LedgerScreen> {
  late Future<_LedgerData> _data;
  _LedgerData? _last;
  final _through = TextEditingController(text: businessDate());
  int _limit = 30;
  String? _source;

  @override
  void initState() {
    super.initState();
    _data = _load();
  }

  @override
  void didUpdateWidget(covariant LedgerScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.revision != oldWidget.revision) _data = _load();
  }

  @override
  void dispose() {
    _through.dispose();
    super.dispose();
  }

  Future<_LedgerData> _load() async {
    final workspace = widget.workspace;
    final through = _through.text.trim();
    final results = await Future.wait([
      workspace.api.get('${workspace.path}/accounts'),
      workspace.api.get('${workspace.path}/journals'),
    ]);
    Json? balance;
    if (RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(through)) {
      try {
        final value = await workspace.api.get(
          '${workspace.path}/trial-balance',
          query: {'through': through},
        );
        if (value is Json) balance = value;
      } catch (_) {
        balance = null;
      }
    }
    return (
      accounts: booksRows(results[0]),
      journals: booksRows(results[1]),
      balance: balance,
    );
  }

  void _reload() => setState(() => _data = _load());

  Future<void> _edit(List<Json> accounts, {Json? reverse}) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => JournalEditor(
        workspace: widget.workspace,
        accounts: accounts,
        reverse: reverse,
      ),
    );
    if (result == true && mounted) {
      _reload();
      await widget.workspace.refresh();
    }
  }

  Future<void> _changed() async {
    if (!mounted) return;
    _reload();
    await widget.workspace.refresh();
  }

  @override
  Widget build(BuildContext context) {
    final workspace = widget.workspace;
    if (_source case final id?) {
      return BooksRecordDetail(
        key: ValueKey(id),
        data: BooksData(workspace.company.id, workspace.api.get),
        id: id,
        onOpen: (next) => setState(() => _source = next),
        onBack: () => setState(() => _source = null),
        backLabel: 'Back to journal',
      );
    }
    final canWrite = workspace.company.canWrite;
    return FutureBuilder<_LedgerData>(
      future: _data,
      builder: (context, snapshot) {
        // Keep showing the last data while a reload runs so half-typed forms are not discarded.
        if (snapshot.data != null) _last = snapshot.data;
        final data = _last;
        final loading = snapshot.connectionState != ConnectionState.done;
        return ApexPage(
          maxWidth: 1240,
          children: [
            BankHeading(
              eyebrow: 'ACCOUNTING FOUNDATION',
              title: 'Ledger',
              subtitle: canWrite
                  ? 'Create accounts and record balanced manual journal entries.'
                  : 'Read-only access: review accounts, journals and trial balance.',
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                onPressed: loading ? null : _reload,
                child: const Text('Refresh journal history'),
              ),
            ),
            const SizedBox(height: 18),
            const BankNote(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Invoices, bills, payments, notes, POS sales and expenses post to the ledger automatically. Records created before automatic posting stay unposted.',
                  ),
                  SizedBox(height: 6),
                  Text(
                    'Unsaved journal and account drafts are kept for each company while you stay in this tab. Reloading or signing out discards them.',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(height: 4, child: loading ? const LinearProgressIndicator() : null),
            if (!loading && data == null)
              BankNote(
                tone: BankTone.error,
                live: true,
                child: Row(
                  children: [
                    const Expanded(child: Text('Couldn’t load the ledger.')),
                    TextButton(onPressed: _reload, child: const Text('Retry')),
                  ],
                ),
              ),
            if (data != null) ...[
              LayoutBuilder(
                key: const ValueKey('ledger-forms'),
                builder: (context, limits) {
                  final accounts = _accountsPanel(data, canWrite);
                  if (!canWrite) return accounts;
                  final journal = _newJournalPanel(data);
                  if (limits.maxWidth < 760) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [accounts, const SizedBox(height: 16), journal],
                    );
                  }
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: accounts),
                      const SizedBox(width: 16),
                      Expanded(child: journal),
                    ],
                  );
                },
              ),
              const SizedBox(height: 16),
              _history(data, canWrite),
              const SizedBox(height: 16),
              _trialBalance(data),
            ],
          ],
        );
      },
    );
  }

  Widget _accountsPanel(_LedgerData data, bool canWrite) => BankPanel(
    title: 'Chart of accounts',
    note: canWrite
        ? 'Add the accounts you need for manual entries.'
        : 'Accounts used by your company’s posted transactions.',
    children: [
      if (canWrite) ...[
        _AccountForm(workspace: widget.workspace, onAdded: _changed),
        const SizedBox(height: 18),
      ],
      if (data.accounts.isEmpty)
        const Text('No accounts added yet.', style: Apex.lead)
      else
        for (final (index, account) in data.accounts.indexed) ...[
          if (index > 0) const Divider(height: 1, color: Apex.lineSoft),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '${booksText(account['code'])} · ${booksText(account['name'])}',
                    style: Apex.strong,
                  ),
                ),
                const SizedBox(width: 10),
                Text(booksText(account['category']), style: Apex.note),
              ],
            ),
          ),
        ],
    ],
  );

  Widget _newJournalPanel(_LedgerData data) => BankPanel(
    title: 'New journal entry',
    note:
        'Each entry has an equal debit and credit. Use linked documents for party balances and tracked inventory.',
    children: [
      InlineJournalForm(
        workspace: widget.workspace,
        accounts: data.accounts,
        onPosted: _changed,
      ),
    ],
  );

  Widget _history(_LedgerData data, bool canWrite) {
    final names = {
      for (final account in data.accounts) account['id']: booksText(account['name']),
    };
    final shown = data.journals.take(_limit).toList();
    return BankPanel(
      title: 'Journal history',
      note: 'Posted entries are retained as an accounting record.',
      children: [
        if (data.journals.isEmpty)
          const ApexEmptyState(
            icon: Icons.menu_book_outlined,
            title: 'No journal entries',
            note: 'Your posted manual entries will appear here.',
          )
        else
          for (final (index, journal) in shown.indexed) ...[
            if (index > 0) const Divider(height: 24, color: Apex.lineSoft),
            _journalEntry(journal, names, data.accounts, canWrite),
          ],
        if (data.journals.length > _limit)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: () => setState(() => _limit += 30),
                child: const Text('Load more'),
              ),
            ),
          ),
      ],
    );
  }

  Widget _journalEntry(Json journal, Map<Object?, String> names, List<Json> accounts, bool canWrite) {
    final source = journal['source_document'];
    final sourceId = source is Json
        ? booksText(source['id'])
        : booksText(journal['source_record_id']);
    // Same tidy-up as the web (journalMemo.js): drop internal record ids and a memo that only repeats the kind.
    final rawMemo = booksText(journal['memo'])
        .replaceAll(RegExp(r'\s*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'), '')
        .trim();
    final kindText = source is Json ? booksText(source['kind']).replaceAll('_', ' ') : '';
    final memo = rawMemo == kindText ? '' : rawMemo;
    final status = journal['reversed_by'] != null
        ? ' · Reversed'
        : journal['reversal_of'] != null
        ? ' · Reversal'
        : '';
    final canReverse =
        canWrite &&
        journal['reversed_by'] == null &&
        journal['reversal_of'] == null &&
        journal['source_record_id'] == null;
    final label = source is Json
        ? '${booksText(source['number']).isEmpty ? 'View source document' : booksText(source['number'])} · ${booksText(source['name'])}'
        : booksText(journal['reference']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (source is Json && sourceId.isNotEmpty)
          ApexLink(label, strong: true, onTap: () => setState(() => _source = sourceId))
        else
          Text(label, style: Apex.strong),
        if (source is Json) ...[
          Text(booksText(source['kind']).replaceAll('_', ' ') + (source['cancelled'] == true ? ' · Cancelled' : ''), style: Apex.note),
          _JournalReference(booksText(journal['reference'])),
        ],
        Text('${booksText(journal['date'])}${memo.isEmpty ? '' : ' · $memo'}$status', style: Apex.note),
        if (canReverse)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: ApexLink('Reverse entry', onTap: () => _edit(accounts, reverse: journal)),
          ),
        const SizedBox(height: 8),
        for (final line in booksRows(journal['lines']))
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              children: [
                Expanded(
                  child: Text(names[line['account_id']] ?? 'Account', style: const TextStyle(fontSize: 13, color: Apex.inkSoft)),
                ),
                const SizedBox(width: 10),
                Text(
                  'Dr ${booksMoney(line['debit'])} · Cr ${booksMoney(line['credit'])}',
                  style: Apex.note,
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _trialBalance(_LedgerData data) {
    final balance = data.balance;
    final rows = balance == null ? const <Json>[] : booksRows(balance['accounts']);
    const total = TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Apex.ink);
    return BankPanel(
      title: 'Trial balance',
      note: 'All posted journal balances through the selected date.',
      flush: true,
      trailing: BankFilterField(
        label: 'Through',
        controller: _through,
        hint: 'YYYY-MM-DD',
        maxLength: 10,
        date: true,
        width: 170,
        onChanged: (value) {
          if (RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(value.trim())) _reload();
        },
      ),
      children: [
        if (balance == null)
          const ApexEmptyState(
            icon: Icons.balance_outlined,
            title: 'Trial balance unavailable',
            note: 'Enter a valid date and load again.',
          )
        else
          ApexTable(
            columns: const [
              ApexColumn('Account', flex: 2.4),
              ApexColumn('Debit', flex: 1, alignEnd: true),
              ApexColumn('Credit', flex: 1, alignEnd: true),
            ],
            rowCount: rows.length + 1,
            cell: (row, column) {
              if (row == rows.length) {
                return switch (column) {
                  0 => const Text('Total', style: total),
                  1 => Text(booksMoney(balance['total_debit']), style: total),
                  _ => Text(booksMoney(balance['total_credit']), style: total),
                };
              }
              final account = rows[row];
              return switch (column) {
                0 => Text('${booksText(account['code'])} · ${booksText(account['name'])}', style: const TextStyle(fontSize: 13, color: Apex.inkSoft)),
                1 => Text(booksMoney(account['debit']), style: const TextStyle(fontSize: 13, color: Apex.inkSoft)),
                _ => Text(booksMoney(account['credit']), style: const TextStyle(fontSize: 13, color: Apex.inkSoft)),
              };
            },
            card: (row) {
              if (row == rows.length) {
                return Row(
                  children: [
                    const Expanded(child: Text('Total', style: total)),
                    Text('Dr ${booksMoney(balance['total_debit'])} · Cr ${booksMoney(balance['total_credit'])}', style: total),
                  ],
                );
              }
              final account = rows[row];
              return Row(
                children: [
                  Expanded(child: Text('${booksText(account['code'])} · ${booksText(account['name'])}', style: Apex.strong)),
                  const SizedBox(width: 10),
                  Text('Dr ${booksMoney(account['debit'])} · Cr ${booksMoney(account['credit'])}', style: Apex.note),
                ],
              );
            },
          ),
      ],
    );
  }
}

/// "Journal reference" disclosure under a source document, like the web `<details>`.
class _JournalReference extends StatefulWidget {
  const _JournalReference(this.reference);
  final String reference;

  @override
  State<_JournalReference> createState() => _JournalReferenceState();
}

class _JournalReferenceState extends State<_JournalReference> {
  bool _open = false;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      InkWell(
        onTap: () => setState(() => _open = !_open),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(_open ? Icons.arrow_drop_down : Icons.arrow_right, size: 18, color: Apex.muted),
              const Text('Journal reference', style: Apex.small),
            ],
          ),
        ),
      ),
      if (_open)
        Padding(
          padding: const EdgeInsets.only(left: 18),
          child: Text(widget.reference, style: Apex.small),
        ),
    ],
  );
}

/// "Add account" form shown inline in the Chart of accounts panel, as on the web.
class _AccountForm extends StatefulWidget {
  const _AccountForm({required this.workspace, required this.onAdded});
  final WorkspaceContext workspace;
  final Future<void> Function() onAdded;

  @override
  State<_AccountForm> createState() => _AccountFormState();
}

class _AccountFormState extends State<_AccountForm> {
  final _name = TextEditingController();
  final _code = TextEditingController();
  String _category = 'asset';
  String? _error;
  bool _busy = false;

  Future<void> _save() async {
    if (_busy) return;
    final name = _name.text.trim();
    final code = _code.text.trim();
    if (name.isEmpty || !RegExp(r'^[a-zA-Z0-9_-]{1,32}$').hasMatch(code)) {
      setState(
        () => _error = 'Enter a name and an account code using letters, numbers, dashes or underscores.',
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final workspace = widget.workspace;
    var added = false;
    String? failure;
    try {
      await workspace.api.post(
        '${workspace.path}/accounts',
        body: {'name': name, 'code': code, 'category': _category},
      );
      added = true;
    } on ApexApiException catch (error) {
      if (error.uncertain && await _exists(code, name)) {
        added = true;
      } else {
        failure = error.uncertain
            ? 'The account could not be confirmed. Check the chart of accounts before trying again.'
            : error.message;
      }
    } catch (_) {
      failure = 'Couldn’t save the account.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
      if (added) {
        _name.clear();
        _code.clear();
        _category = 'asset';
      }
    });
    if (added) await widget.onAdded();
  }

  Future<bool> _exists(String code, String name) async {
    try {
      final rows = booksRows(
        await widget.workspace.api.get(
          '${widget.workspace.path}/accounts',
          query: {'code': code},
        ),
      );
      return rows.any(
        (row) =>
            row['code'] == code &&
            row['name'] == name &&
            row['category'] == _category,
      );
    } catch (_) {
      return false;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      BankFormRow(
        breakpoint: 360,
        [
          BankFilterField(label: 'Account code', controller: _code, width: null, hint: 'e.g. 100', maxLength: 32, enabled: !_busy),
          BankFilterField(label: 'Account name', controller: _name, width: null, hint: 'e.g. Cash', maxLength: 120, enabled: !_busy),
        ],
      ),
      const SizedBox(height: 14),
      BankSelectField<String>(
        label: 'Category',
        value: _category,
        items: [
          for (final type in const ['Asset', 'Liability', 'Equity', 'Income', 'Expense'])
            (type.toLowerCase(), type),
        ],
        onChanged: _busy ? null : (value) => setState(() => _category = value ?? 'asset'),
      ),
      if (_error != null) ...[
        const SizedBox(height: 14),
        BankNote(tone: BankTone.error, live: true, child: Text(_error!)),
      ],
      const SizedBox(height: 14),
      FilledButton(
        onPressed: _busy ? null : _save,
        child: Text(_busy ? 'Saving…' : 'Add account'),
      ),
    ],
  );
}
