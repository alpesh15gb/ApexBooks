import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import '../../ui/apex_theme.dart';
import 'bank_data.dart';
import 'bank_widgets.dart';

const transferDirections = {
  'cash_to_bank': 'Cash deposit to bank',
  'bank_to_cash': 'Bank withdrawal to cash',
  'bank_to_bank': 'Transfer between banks',
};

/// Default record name per direction, as in the web app's cash transfer form.
String transferDefaultName(String direction) => switch (direction) {
  'cash_to_bank' => 'Cash deposit',
  'bank_to_bank' => 'Bank transfer',
  _ => 'Cash withdrawal',
};

const _directionLabels = {
  'cash_to_bank': 'Cash to bank',
  'bank_to_cash': 'Bank to cash',
  'bank_to_bank': 'Bank to bank',
};

class TransferForm extends StatefulWidget {
  const TransferForm({required this.accounts, required this.bank, super.key});
  final List<Json> accounts;
  final String bank;
  @override
  State<TransferForm> createState() => _TransferFormState();
}

class _TransferFormState extends State<TransferForm> {
  final _date = TextEditingController(text: businessDate());
  final _amount = TextEditingController();
  final _notes = TextEditingController();
  final _name = TextEditingController(text: transferDefaultName('cash_to_bank'));
  bool _nameEdited = false;
  late String _from = widget.bank;
  String? _to;
  String _direction = 'cash_to_bank';
  Json? _reviewed;
  String? _error;

  @override
  void dispose() {
    _date.dispose();
    _amount.dispose();
    _notes.dispose();
    _name.dispose();
    super.dispose();
  }

  void _edit([VoidCallback? change]) => setState(() {
    change?.call();
    _reviewed = null;
    _error = null;
  });

  void _review() {
    final date = validBankDate(_date.text);
    final amount = inventoryDecimal(_amount.text, 2);
    if (date == null || amount == null || amount <= BigInt.zero) {
      setState(
        () => _error = 'Enter a valid transfer date and positive amount.',
      );
      return;
    }
    if (_direction == 'bank_to_bank' && (_to == null || _from == _to)) {
      setState(() => _error = 'Choose a different destination bank.');
      return;
    }
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = 'Enter a description for this transfer.');
      return;
    }
    final notes = _notes.text.trim();
    setState(
      () => _reviewed = {
        'kind': 'bank_transfer',
        'name': name,
        'date': date,
        'amount': decimalMoney(amount),
        'data': {
          'direction': _direction,
          'bank_account_id': _from,
          if (_direction == 'bank_to_bank') 'to_bank_account_id': _to,
          if (notes.isNotEmpty) 'notes': notes,
        },
      },
    );
  }

  @override
  Widget build(BuildContext context) => BankFormDialog(
    title: 'Cash and bank transfer',
    subtitle: 'Record cash deposits, withdrawals or transfers between bank accounts.',
    error: _error,
    fields: [
      DropdownButtonFormField(
        initialValue: _direction,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Direction'),
        items: [
          for (final direction in transferDirections.entries)
            DropdownMenuItem(
              value: direction.key,
              child: Text(_directionLabels[direction.key]!),
            ),
        ],
        onChanged: (value) => _edit(() {
          _direction = value!;
          if (!_nameEdited) _name.text = transferDefaultName(value);
        }),
      ),
      BankChoice(
        label: 'Bank account',
        value: _from,
        accounts: widget.accounts,
        onChanged: (value) => _edit(() {
          _from = value!;
          if (_to == value) _to = null;
        }),
      ),
      if (_direction == 'bank_to_bank')
        BankChoice(
          label: 'Destination bank account',
          value: _to,
          // The source account cannot also be the destination.
          accounts: [
            for (final row in widget.accounts)
              if (inventoryText(row['id']) != _from) row,
          ],
          onChanged: (value) => _edit(() => _to = value),
        ),
      BankField(
        label: 'Description',
        controller: _name,
        maxLength: 120,
        onChanged: (_) => _edit(() => _nameEdited = true),
      ),
      BankField(
        label: 'Date (YYYY-MM-DD)',
        controller: _date,
        maxLength: 10,
        onChanged: (_) => _edit(),
      ),
      BankField(
        label: 'Amount (₹)',
        controller: _amount,
        maxLength: 16,
        keyboard: const TextInputType.numberWithOptions(decimal: true),
        onChanged: (_) => _edit(),
      ),
      BankField(
        label: 'Note (optional)',
        controller: _notes,
        maxLength: 500,
        onChanged: (_) => _edit(),
      ),
      if (_reviewed != null)
        Text(
          '${transferDirections[_direction]} · ${inventoryAmount(_reviewed!['amount'])}',
        ),
    ],
    primary: FilledButton(
      onPressed: _reviewed == null
          ? _review
          : () => Navigator.pop(context, _reviewed),
      child: Text(_reviewed == null ? 'Review transfer' : 'Post transfer'),
    ),
  );
}

class BankAccountForm extends StatefulWidget {
  const BankAccountForm({super.key});
  @override
  State<BankAccountForm> createState() => _BankAccountFormState();
}

class BankOpeningForm extends StatefulWidget {
  const BankOpeningForm({
    required this.accounts,
    required this.bank,
    super.key,
  });
  final List<Json> accounts;
  final String bank;

  @override
  State<BankOpeningForm> createState() => _BankOpeningFormState();
}

class _BankOpeningFormState extends State<BankOpeningForm> {
  final _date = TextEditingController(text: businessDate());
  final _amount = TextEditingController();
  late String _bank = widget.bank;
  String _type = 'cash';
  bool _overdraft = false;
  String? _error;
  Json? _body;

  @override
  void dispose() {
    _date.dispose();
    _amount.dispose();
    super.dispose();
  }

  void _edit([VoidCallback? change]) => setState(() {
    change?.call();
    _body = null;
    _error = null;
  });

  void _review() {
    final date = validBankDate(_date.text);
    final amount = inventoryDecimal(_amount.text, 2);
    if (date == null ||
        date.compareTo(businessDate()) > 0 ||
        amount == null ||
        amount <= BigInt.zero) {
      setState(
        () => _error = 'Enter a date through today and a positive amount.',
      );
      return;
    }
    setState(
      () => _body = {
        'kind': 'opening_balance',
        'date': date,
        'amount': decimalMoney(amount),
        'data': {
          'balance_kind': _type,
          if (_type == 'bank') 'bank_account_id': _bank,
          if (_type == 'bank' && _overdraft) 'overdraft': true,
        },
      },
    );
  }

  @override
  Widget build(BuildContext context) => BankFormDialog(
    title: 'Opening balance',
    error: _error,
    fields: [
      const Text(
        'Record the starting balance before the account’s first ledger movement.',
      ),
      DropdownButtonFormField<String>(
        initialValue: _type,
        decoration: const InputDecoration(labelText: 'Account type'),
        items: const [
          DropdownMenuItem(value: 'cash', child: Text('Cash')),
          DropdownMenuItem(value: 'bank', child: Text('Bank')),
        ],
        onChanged: (value) => _edit(() => _type = value!),
      ),
      if (_type == 'bank') ...[
        BankChoice(
          label: 'Bank account',
          value: _bank,
          accounts: widget.accounts,
          onChanged: (value) => _edit(() => _bank = value!),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Bank overdraft'),
          value: _overdraft,
          onChanged: (value) => _edit(() => _overdraft = value),
        ),
      ],
      BankField(
        label: 'Opening date (YYYY-MM-DD)',
        controller: _date,
        maxLength: 10,
        onChanged: (_) => _edit(),
      ),
      BankField(
        label: 'Opening amount (₹)',
        controller: _amount,
        maxLength: 16,
        keyboard: const TextInputType.numberWithOptions(decimal: true),
        onChanged: (_) => _edit(),
      ),
      if (_body != null)
        Text(
          '${_type == 'cash'
              ? 'Opening cash'
              : _overdraft
              ? 'Opening overdraft'
              : 'Opening bank balance'} · ${inventoryAmount(_body!['amount'])}',
        ),
    ],
    primary: FilledButton(
      onPressed: _body == null ? _review : () => Navigator.pop(context, _body),
      child: Text(_body == null ? 'Review opening' : 'Post opening'),
    ),
  );
}

class _BankAccountFormState extends State<BankAccountForm> {
  final _name = TextEditingController();
  final _hint = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _hint.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => BankFormDialog(
    title: 'New bank account',
    subtitle: 'Choose the account for its balance, statement and matches.',
    error: _error,
    fields: [
      BankField(label: 'Account name', controller: _name, maxLength: 120),
      BankField(
        label: 'Account hint (optional)',
        controller: _hint,
        maxLength: 32,
      ),
    ],
    primary: FilledButton(
      onPressed: () {
        if (_name.text.trim().isEmpty) {
          setState(() => _error = 'Enter a name for this bank account.');
          return;
        }
        Navigator.pop(context, {
          'name': _name.text.trim(),
          'account_hint': _hint.text.trim(),
        });
      },
      child: const Text('Create account'),
    ),
  );
}

class StatementImportForm extends StatefulWidget {
  const StatementImportForm({
    required this.preview,
    required this.bank,
    super.key,
  });
  final Future<Json> Function(Json body) preview;
  final String bank;
  @override
  State<StatementImportForm> createState() => _StatementImportFormState();
}

class _StatementImportFormState extends State<StatementImportForm> {
  final _csv = TextEditingController();
  bool _busy = false;
  Json? _body;
  Json? _preview;
  String? _error;
  List<List<String>> _table = const [];
  int _header = 0;
  Map<String, int?> _mapping = {};
  bool _dmy = true;
  List<Json>? _lines;
  String? _parseError;

  /// Re-reads the CSV text; [detect] also re-detects the header and columns.
  void _reparse({bool detect = false}) {
    _body = null;
    _preview = null;
    _error = null;
    try {
      if (detect) {
        _table = statementTable(_csv.text);
        _header = detectStatementHeader(_table);
        _mapping = detectStatementMapping(
          _header < _table.length ? _table[_header] : const [],
        );
      }
      _lines = _table.isEmpty
          ? null
          : buildStatementLines(
              _table,
              header: _header,
              mapping: _mapping,
              dmy: _dmy,
            );
      _parseError = null;
    } on FormatException catch (failure) {
      if (detect) {
        _table = const [];
        _mapping = {};
      }
      _lines = null;
      _parseError = failure.message;
    }
  }

  Future<void> _pick() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final file = await pickApexFile(['csv'], 1024 * 1024);
      if (!mounted || file == null) return;
      final contents = utf8.decode(file.bytes);
      setState(() {
        _csv.text = contents;
        _reparse(detect: true);
      });
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _csv.dispose();
    super.dispose();
  }

  List<Widget> _mappingFields() {
    final headers = _header < _table.length ? _table[_header] : <String>[];
    final lines = _lines;
    return [
      DropdownButtonFormField<int>(
        key: ValueKey('header-$_header-${_table.length}'),
        initialValue: _header,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Header row'),
        items: [
          for (var i = 0; i < _table.length && i < 20; i++)
            DropdownMenuItem(
              value: i,
              child: Text(
                '${i + 1}: ${_table[i].join(' · ')}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: _busy
            ? null
            : (value) => setState(() {
                _header = value!;
                _mapping = detectStatementMapping(_table[_header]);
                _reparse();
              }),
      ),
      DropdownButtonFormField<bool>(
        key: ValueKey('dmy-$_dmy'),
        initialValue: _dmy,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Date format'),
        items: const [
          DropdownMenuItem(value: true, child: Text('DD/MM/YYYY (India)')),
          DropdownMenuItem(value: false, child: Text('MM/DD/YYYY')),
        ],
        onChanged: _busy
            ? null
            : (value) => setState(() {
                _dmy = value!;
                _reparse();
              }),
      ),
      for (final field in statementFields)
        DropdownButtonFormField<int?>(
          key: ValueKey('map-$field-${_mapping[field]}-$_header'),
          initialValue: _mapping[field],
          isExpanded: true,
          decoration: InputDecoration(
            labelText: '${field[0].toUpperCase()}${field.substring(1)} column',
          ),
          items: [
            const DropdownMenuItem<int?>(value: null, child: Text('Not mapped')),
            for (var i = 0; i < headers.length; i++)
              DropdownMenuItem<int?>(
                value: i,
                child: Text('${i + 1} · ${headers[i]}', overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: _busy
              ? null
              : (value) => setState(() {
                  _mapping = {..._mapping, field: value};
                  _reparse();
                }),
        ),
      if (lines != null) ...[
        for (final line in lines.take(5))
          Text(
            '${line['date']} · ${line['description']} · ${line['amount']}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        Text('Showing ${lines.length < 5 ? lines.length : 5} of ${lines.length} rows.'),
      ],
    ];
  }

  Future<void> _review() async {
    setState(() {
      _busy = true;
      _body = null;
      _error = null;
    });
    try {
      final lines = _lines;
      if (lines == null) {
        throw FormatException(
          _parseError ?? 'Choose a statement CSV to import.',
        );
      }
      final body = {'bank_account_id': widget.bank, 'lines': lines};
      final outcome = await widget.preview({...body, 'dry_run': true});
      if (!mounted) return;
      setState(() {
        _body = body;
        _preview = outcome;
      });
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy,
    child: BankFormDialog(
      title: 'Import bank statement',
      subtitle: 'Map the date, description, reference and amount columns in your bank CSV.',
      error: _error,
      fields: [
        Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            onPressed: _busy ? null : _pick,
            icon: const Icon(Icons.attach_file),
            label: const Text('Choose CSV file'),
          ),
        ),
        const Text(
          'Choose or paste your bank CSV. Columns such as Narration, Txn Date, Withdrawal Amt and Deposit Amt are recognised, and you can correct the mapping below. Debit is paid and credit is received; a single amount column uses positive for received and negative for paid.',
        ),
        BankField(
          label: 'Statement CSV',
          controller: _csv,
          maxLength: 1000000,
          lines: 6,
          enabled: !_busy,
          onChanged: (_) => setState(() => _reparse(detect: true)),
        ),
        if (_table.isNotEmpty) ..._mappingFields(),
        if (_parseError != null && _csv.text.trim().isNotEmpty)
          Text(
            _parseError!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        if (_preview != null)
          Text(
            '${_preview!['added']} new · ${_preview!['duplicates']} already imported',
          ),
      ],
      primary: FilledButton(
        onPressed: _busy
            ? null
            : _body == null
            ? _review
            : () => Navigator.pop(context, _body),
        child: Text(
          _busy
              ? 'Checking…'
              : _body == null
              ? 'Preview import'
              : 'Import statement',
        ),
      ),
    ),
  );
}

class BankFormDialog extends StatelessWidget {
  const BankFormDialog({
    required this.title,
    required this.fields,
    required this.primary,
    this.subtitle,
    this.error,
    super.key,
  });
  final String title;
  final String? subtitle;
  final List<Widget> fields;
  final Widget primary;
  final String? error;

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Apex.sectionTitle),
        if (subtitle != null) ...[
          const SizedBox(height: 5),
          Text(subtitle!, style: Apex.note),
        ],
      ],
    ),
    scrollable: true,
    content: SizedBox(
      width: 480,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final field in fields)
            Padding(padding: const EdgeInsets.only(bottom: 12), child: field),
          if (error != null) BankNote(tone: BankTone.error, live: true, child: Text(error!)),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      primary,
    ],
  );
}

class BankReviewForm extends StatefulWidget {
  const BankReviewForm({required this.totals, super.key});
  final Json totals;

  @override
  State<BankReviewForm> createState() => _BankReviewFormState();
}

class _BankReviewFormState extends State<BankReviewForm> {
  final _note = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final totals = widget.totals;
    return BankFormDialog(
      title: 'Save reconciliation review',
      fields: [
        Text(
          'As of ${totals['as_of']} · Difference ${inventoryAmount(totals['difference'])}',
        ),
        BankField(
          label: 'Review note (optional)',
          controller: _note,
          maxLength: 500,
          lines: 2,
        ),
      ],
      primary: FilledButton(
        onPressed: () => Navigator.pop(context, {
          'bank_account_id': totals['bank_account_id'],
          'as_of': totals['as_of'],
          'opening_balance': totals['opening_balance'],
          'note': _note.text.trim(),
        }),
        child: const Text('Save review'),
      ),
    );
  }
}

class BankField extends StatelessWidget {
  const BankField({
    required this.label,
    required this.controller,
    this.maxLength,
    this.keyboard,
    this.onChanged,
    this.enabled = true,
    this.lines = 1,
    super.key,
  });
  final String label;
  final TextEditingController controller;
  final int? maxLength;
  final TextInputType? keyboard;
  final ValueChanged<String>? onChanged;
  final int lines;
  final bool enabled;

  @override
  Widget build(BuildContext context) => TextField(
    controller: controller,
    enabled: enabled,
    maxLength: maxLength,
    maxLines: lines,
    keyboardType: keyboard ?? (lines > 1 ? TextInputType.multiline : null),
    onChanged: onChanged,
    decoration: InputDecoration(labelText: label, counterText: ''),
  );
}

class BankChoice extends StatelessWidget {
  const BankChoice({
    required this.label,
    required this.value,
    required this.accounts,
    required this.onChanged,
    super.key,
  });
  final String label;
  final String? value;
  final List<Json> accounts;
  final ValueChanged<String?>? onChanged;

  @override
  Widget build(BuildContext context) => DropdownButtonFormField<String>(
    key: ValueKey((label, value)),
    initialValue: accounts.any((row) => row['id'] == value) ? value : null,
    isExpanded: true,
    decoration: InputDecoration(labelText: label),
    onChanged: onChanged,
    items: [
      for (final row in accounts)
        DropdownMenuItem(
          value: inventoryText(row['id']),
          child: Text(
            inventoryText(row['name']),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
    ],
  );
}
