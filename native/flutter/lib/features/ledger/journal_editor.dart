import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../banking/bank_widgets.dart';
import '../books/books_data.dart';

class JournalEditor extends StatefulWidget {
  const JournalEditor({
    required this.workspace,
    required this.accounts,
    this.reverse,
    super.key,
  });

  final WorkspaceContext workspace;
  final List<Json> accounts;
  final Json? reverse;

  @override
  State<JournalEditor> createState() => _JournalEditorState();
}

class _JournalLine {
  _JournalLine({required this.debit});
  String? account;
  bool debit;
  final amount = TextEditingController();

  void dispose() => amount.dispose();
}

BigInt? _paise(String raw) {
  final match = RegExp(r'^(\d{1,13})(?:\.(\d{1,2}))?$').firstMatch(raw.trim());
  if (match == null) return null;
  final fraction = (match.group(2) ?? '').padRight(2, '0');
  return BigInt.parse('${match.group(1)}$fraction');
}

String _decimal(BigInt value) =>
    '${value ~/ BigInt.from(100)}.${(value % BigInt.from(100)).toString().padLeft(2, '0')}';

class _JournalEditorState extends State<JournalEditor> {
  static const _controlAccounts = {
    'SYS-AR',
    'SYS-AP',
    'SYS-INVENTORY',
    'SYS-CUST-CREDIT',
    'SYS-SUPP-CREDIT',
    'SYS-CUST-ADV',
    'SYS-SUPP-ADV',
  };
  final _reference = TextEditingController();
  final _memo = TextEditingController();
  final _lines = [_JournalLine(debit: true), _JournalLine(debit: false)];
  late DateTime _date;
  bool _busy = false;
  String? _error;

  bool get _reversing => widget.reverse != null;
  DateTime get _today => DateTime.parse(businessDate());

  @override
  void initState() {
    super.initState();
    final original = DateTime.tryParse(booksText(widget.reverse?['date']));
    _date = original != null && original.isAfter(_today) ? original : _today;
  }

  (BigInt, BigInt) get _totals {
    var debits = BigInt.zero;
    var credits = BigInt.zero;
    for (final line in _lines) {
      final value = _paise(line.amount.text) ?? BigInt.zero;
      if (line.debit) {
        debits += value;
      } else {
        credits += value;
      }
    }
    return (debits, credits);
  }

  Future<void> _save() async {
    if (_busy) return;
    final workspace = widget.workspace;
    final reference = _reference.text.trim();
    final memo = _memo.text.trim();
    final reverse = widget.reverse;
    if (reference.isEmpty || (_reversing && memo.isEmpty)) {
      setState(
        () => _error = _reversing
            ? 'Enter a reference and reason.'
            : 'Enter a reference.',
      );
      return;
    }
    final (debits, credits) = _totals;
    if (!_reversing &&
        (debits == BigInt.zero ||
            debits != credits ||
            _lines.any(
              (line) =>
                  line.account == null ||
                  (_paise(line.amount.text) ?? BigInt.zero) == BigInt.zero,
            ))) {
      setState(
        () => _error = 'Choose an account and amount on each line. Total debits and credits must match.',
      );
      return;
    }
    final path = reverse == null
        ? '${workspace.path}/journals'
        : '${workspace.path}/journals/${reverse['id']}/reverse';
    final body = <String, dynamic>{
      'date': booksDate(_date),
      'reference': reference,
      if (_reversing)
        'reason': memo
      else ...{
        'memo': memo,
        'lines': [
          for (final line in _lines)
            {
              'account_id': line.account,
              'debit': line.debit ? _decimal(_paise(line.amount.text)!) : '0',
              'credit': line.debit ? '0' : _decimal(_paise(line.amount.text)!),
            },
        ],
      },
    };
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await workspace.api.post(path, body: body);
      if (mounted) Navigator.pop(context, true);
    } on ApexApiException catch (error) {
      final maybePosted = error.uncertain || error.status == 409;
      if (maybePosted && await _checkPosted(body)) {
        if (mounted) Navigator.pop(context, true);
        return;
      }
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = error.uncertain
            ? 'The journal could not be confirmed. Check this reference in the ledger before trying again.'
            : error.message;
      });
    } catch (_) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = 'Couldn’t save the journal.';
        });
      }
    }
  }

  Future<bool> _checkPosted(Json body) =>
      journalAlreadyPosted(widget.workspace, body, reverse: widget.reverse);

  Future<void> _chooseDate() async {
    final original = DateTime.tryParse(booksText(widget.reverse?['date']));
    final day = await showDatePicker(
      context: context,
      firstDate: original ?? DateTime(1900),
      lastDate: DateTime(_today.year + 5, 12, 31),
      initialDate: _date,
    );
    if (mounted && day != null) setState(() => _date = day);
  }

  @override
  void dispose() {
    _reference.dispose();
    _memo.dispose();
    for (final line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final (debits, credits) = _totals;
    return PopScope(
      canPop: !_busy,
      child: AlertDialog(
        title: Text(_reversing ? 'Reverse journal' : 'New journal'),
        scrollable: true,
        content: SizedBox(
          width: 580,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _busy ? null : _chooseDate,
                  icon: const Icon(Icons.calendar_today_outlined),
                  label: Text(booksDate(_date)),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _reference,
                enabled: !_busy,
                maxLength: 80,
                decoration: const InputDecoration(labelText: 'Reference'),
              ),
              TextField(
                controller: _memo,
                enabled: !_busy,
                maxLength: 500,
                decoration: InputDecoration(
                  labelText: _reversing ? 'Reason' : 'Memo (optional)',
                ),
              ),
              if (!_reversing) ...[
                for (final line in _lines) _line(line, _lines.indexOf(line)),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: _busy || _lines.length == 100
                        ? null
                        : () => setState(() {
                            _lines.add(_JournalLine(debit: true));
                          }),
                    icon: const Icon(Icons.add),
                    label: const Text('Add line'),
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 18,
                  runSpacing: 5,
                  children: [
                    Text('Debits ${booksMoney(_decimal(debits))}'),
                    Text('Credits ${booksMoney(_decimal(credits))}'),
                  ],
                ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      _error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _busy ? null : () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _busy ? null : _save,
            child: Text(
              _busy
                  ? 'Posting…'
                  : _reversing
                  ? 'Post reversal'
                  : 'Post journal',
            ),
          ),
        ],
      ),
    );
  }

  Widget _line(_JournalLine line, int index) => Padding(
    key: ObjectKey(line),
    padding: const EdgeInsets.only(bottom: 10),
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            DropdownButtonFormField<String>(
              initialValue: line.account,
              isExpanded: true,
              decoration: InputDecoration(labelText: 'Account ${index + 1}'),
              items: [
                for (final account in widget.accounts)
                  if (!_controlAccounts.contains(account['code']))
                    DropdownMenuItem(
                      value: booksText(account['id']),
                      child: Text(
                        '${account['code']} · ${account['name']}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
              ],
              onChanged: _busy
                  ? null
                  : (value) => setState(() => line.account = value),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<bool>(
                    initialValue: line.debit,
                    decoration: const InputDecoration(labelText: 'Side'),
                    items: const [
                      DropdownMenuItem(value: true, child: Text('Debit')),
                      DropdownMenuItem(value: false, child: Text('Credit')),
                    ],
                    onChanged: _busy
                        ? null
                        : (value) => setState(() => line.debit = value!),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: line.amount,
                    enabled: !_busy,
                    keyboardType: const TextInputType.numberWithOptions(
                      decimal: true,
                    ),
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(labelText: 'Amount (₹)'),
                  ),
                ),
                if (_lines.length > 2)
                  IconButton(
                    tooltip: 'Remove line ${index + 1}',
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                            _lines.remove(line);
                            WidgetsBinding.instance.addPostFrameCallback(
                              (_) => line.dispose(),
                            );
                          }),
                    icon: const Icon(Icons.delete_outline),
                  ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}

/// After a lost or conflicting response: is exactly this journal (or reversal) already in the ledger?
Future<bool> journalAlreadyPosted(WorkspaceContext workspace, Json body, {Json? reverse}) async {
  try {
    final rows = booksRows(
      await workspace.api.get(
        '${workspace.path}/journals',
        query: {'reference': body['reference'] as String},
      ),
    );
    if (rows.length != 1 || rows.single['date'] != body['date']) return false;
    final row = rows.single;
    if (reverse != null) {
      return row['reversal_of'] == reverse['id'] &&
          row['memo'] == body['reason'];
    }
    if (row['memo'] != body['memo'] ||
        row['reversal_of'] != null ||
        row['source_record_id'] != null) {
      return false;
    }
    List<String> keys(Object? lines) =>
        booksRows(lines)
            .map(
              (line) =>
                  '${line['account_id']}:${_paise(booksText(line['debit']))}:${_paise(booksText(line['credit']))}',
            )
            .toList()
          ..sort();
    final actual = keys(row['lines']);
    final expected = keys(body['lines']);
    if (actual.length != expected.length) return false;
    for (var i = 0; i < actual.length; i++) {
      if (actual[i] != expected[i]) return false;
    }
    return true;
  } catch (_) {
    return false;
  }
}

/// The "New journal entry" form shown inline on the Ledger page, as on the web: date, reference, memo,
/// one debit account, one credit account and an amount. Posting, the recovery check after a lost
/// response and the validation match [JournalEditor].
class InlineJournalForm extends StatefulWidget {
  const InlineJournalForm({
    required this.workspace,
    required this.accounts,
    required this.onPosted,
    super.key,
  });

  final WorkspaceContext workspace;
  final List<Json> accounts;
  final Future<void> Function() onPosted;

  @override
  State<InlineJournalForm> createState() => _InlineJournalFormState();
}

class _InlineJournalFormState extends State<InlineJournalForm> {
  final _date = TextEditingController(text: businessDate());
  final _reference = TextEditingController();
  final _memo = TextEditingController();
  final _amount = TextEditingController();
  String? _debit;
  String? _credit;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _date.dispose();
    _reference.dispose();
    _memo.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _post() async {
    if (_busy) return;
    final workspace = widget.workspace;
    final date = DateTime.tryParse(_date.text.trim());
    final reference = _reference.text.trim();
    final amount = _paise(_amount.text);
    if (date == null || booksDate(date) != _date.text.trim()) {
      setState(() => _error = 'Enter a valid date (YYYY-MM-DD).');
      return;
    }
    if (reference.isEmpty) {
      setState(() => _error = 'Enter a reference.');
      return;
    }
    if (_debit == null || _credit == null) {
      setState(() => _error = 'Choose a debit and a credit account.');
      return;
    }
    if (_debit == _credit) {
      setState(() => _error = 'Choose different accounts for debit and credit');
      return;
    }
    if (amount == null || amount == BigInt.zero) {
      setState(() => _error = 'Enter an amount greater than zero.');
      return;
    }
    final value = _decimal(amount);
    final body = <String, dynamic>{
      'date': booksDate(date),
      'reference': reference,
      'memo': _memo.text.trim(),
      'lines': [
        {'account_id': _debit, 'debit': value, 'credit': '0'},
        {'account_id': _credit, 'debit': '0', 'credit': value},
      ],
    };
    setState(() {
      _busy = true;
      _error = null;
    });
    var posted = false;
    String? failure;
    try {
      await workspace.api.post('${workspace.path}/journals', body: body);
      posted = true;
    } on ApexApiException catch (error) {
      if ((error.uncertain || error.status == 409) &&
          await journalAlreadyPosted(workspace, body)) {
        posted = true;
      } else {
        failure = error.uncertain
            ? 'The journal could not be confirmed. Check this reference in the ledger before trying again.'
            : error.message;
      }
    } catch (_) {
      failure = 'Couldn’t save the journal.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _error = failure;
      if (posted) {
        _reference.clear();
        _memo.clear();
        _amount.clear();
        _date.text = businessDate();
        _debit = null;
        _credit = null;
      }
    });
    if (posted) await widget.onPosted();
  }

  @override
  Widget build(BuildContext context) {
    final choices = [
      for (final account in widget.accounts)
        if (!_JournalEditorState._controlAccounts.contains(account['code']))
          (booksText(account['id']), '${account['code']} · ${account['name']}'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BankFormRow(
          breakpoint: 360,
          [
            BankFilterField(label: 'Date', controller: _date, width: null, hint: 'YYYY-MM-DD', maxLength: 10, date: true, enabled: !_busy),
            BankFilterField(label: 'Reference', controller: _reference, width: null, maxLength: 80, enabled: !_busy),
          ],
        ),
        const SizedBox(height: 14),
        BankFilterField(label: 'Memo', controller: _memo, width: null, maxLength: 500, enabled: !_busy),
        const SizedBox(height: 14),
        BankFormRow(
          breakpoint: 360,
          [
            BankSelectField<String>(
              label: 'Debit account',
              value: _debit,
              hint: 'Choose account',
              items: choices,
              onChanged: _busy ? null : (value) => setState(() => _debit = value),
            ),
            BankSelectField<String>(
              label: 'Credit account',
              value: _credit,
              hint: 'Choose account',
              items: choices,
              onChanged: _busy ? null : (value) => setState(() => _credit = value),
            ),
          ],
        ),
        const SizedBox(height: 14),
        BankFilterField(
          label: 'Amount (₹)',
          controller: _amount,
          width: null,
          maxLength: 16,
          keyboard: const TextInputType.numberWithOptions(decimal: true),
          enabled: !_busy,
        ),
        if (_error != null) ...[
          const SizedBox(height: 14),
          BankNote(tone: BankTone.error, live: true, child: Text(_error!)),
        ],
        const SizedBox(height: 14),
        FilledButton(
          onPressed: _busy || widget.accounts.length < 2 ? null : _post,
          child: Text(_busy ? 'Posting…' : 'Post journal'),
        ),
      ],
    );
  }
}
