import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../books/books_data.dart';
import '../books/books_entry_picker.dart';
import 'settings_blocks.dart';
import 'settings_fields.dart';

class OpeningPartyPanel extends StatefulWidget {
  const OpeningPartyPanel({required this.workspace, super.key});

  final WorkspaceContext workspace;

  @override
  State<OpeningPartyPanel> createState() => _OpeningPartyPanelState();
}

class _OpeningPartyPanelState extends State<OpeningPartyPanel> {
  static const _operation = 'opening-party-balance';
  static const _typeLabels = {
    'receivable': 'Customer owes us',
    'payable': 'We owe supplier',
    'cash': 'Cash in hand',
    'bank': 'Bank balance',
  };
  final _amount = TextEditingController();
  DateTime _date = DateTime.parse(businessDate());
  String _type = 'receivable';
  String _bank = 'default';
  bool _overdraft = false;
  List<Json> _banks = const [];
  bool _banksLoaded = false;
  BooksRecord? _party;
  Json? _pending;
  String? _message;
  bool _busy = true;
  bool _storageAvailable = true;

  WorkspaceContext get _workspace => widget.workspace;
  bool get _owner => _workspace.company.role == 'owner';

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    try {
      final saved = await _workspace.pending.load(_operation);
      if (saved != null &&
          (saved['body'] is! Json || booksText(saved['key']).isEmpty)) {
        throw const FormatException('Invalid saved opening balance.');
      }
      if (mounted) setState(() => _pending = saved);
    } catch (_) {
      if (mounted) {
        setState(() {
          _storageAvailable = false;
          _message = 'Saved requests could not be read. Reopen this page to check again.';
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickParty() async {
    final party = await pickBooksRecord(
      context,
      _workspace,
      title: 'Choose a party',
      kinds: const ['party'],
      accept: (party) => party.data['is_active'] != false,
    );
    if (mounted && party != null) setState(() => _party = party);
  }

  Future<void> _pickDate() async {
    final today = DateTime.parse(businessDate());
    final date = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(1900),
      lastDate: today,
      helpText: 'Choose opening balance date',
    );
    if (mounted && date != null) setState(() => _date = date);
  }

  Future<void> _post() async {
    if (_busy || !_owner || !_storageAvailable) return;
    final party = _party;
    final amount = _amount.text.trim();
    final retry = _pending != null;
    final needsParty = _type == 'receivable' || _type == 'payable';
    if (!retry &&
        ((needsParty && party == null) ||
            !RegExp(r'^\d{1,12}(?:\.\d{1,2})?$').hasMatch(amount) ||
            (num.tryParse(amount) ?? 0) <= 0)) {
      setState(
        () => _message = needsParty
            ? 'Choose a party and enter a positive amount.'
            : 'Enter a positive amount.',
      );
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final random = Random.secure();
      final request =
          _pending ??
          {
            'key': List.generate(
              24,
              (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
            ).join(),
            'party': party?.party ?? _typeLabels[_type],
            'body': {
              'kind': 'opening',
              'date': booksDate(_date),
              'amount': amount,
              'data': {
                'balance_kind': _type,
                'party_id': needsParty ? party!.id : '',
                'bank_account_id': _type == 'bank' ? _bank : 'default',
                'overdraft': _type == 'bank' && _overdraft,
              },
            },
          };
      if (!retry) {
        await _workspace.pending.save(_operation, request);
        if (mounted) setState(() => _pending = request);
      }
      final result = booksObject(
        await _workspace.api.post(
          '${_workspace.path}/opening-balances',
          body: booksObject(request['body']),
          idempotencyKey: booksText(request['key']),
        ),
      );
      if (booksText(result['id']).isEmpty) {
        throw const FormatException(
          'The opening balance could not be confirmed.',
        );
      }
      await _workspace.pending.clear(_operation);
      if (mounted) {
        _amount.clear();
        setState(() {
          _pending = null;
          _message = 'Opening balance posted to the ledger.';
        });
      }
      await _workspace.refresh();
    } on ApexApiException catch (error) {
      if (!retry && !error.uncertain) {
        try {
          await _workspace.pending.clear(_operation);
          if (mounted) setState(() => _pending = null);
        } catch (_) {
          if (mounted) {
            setState(
              () => _message = 'The saved copy could not be cleared. Retry the original balance.',
            );
          }
          return;
        }
      }
      if (mounted) setState(() => _message = error.message);
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is FormatException
              ? error.message
              : 'Could not confirm the opening balance.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _loadBanks() async {
    if (_banksLoaded) return;
    _banksLoaded = true;
    try {
      final rows = booksRows(
        await _workspace.api.get('${_workspace.path}/bank-accounts'),
      );
      if (mounted) setState(() => _banks = rows);
    } catch (_) {
      _banksLoaded = false;
      if (mounted) {
        setState(() => _message = 'Bank accounts could not be loaded.');
      }
    }
  }

  Widget _pseudoField(String label, String value, VoidCallback? onTap, IconData icon) =>
      SettingsLabeled(
        label: label,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(4),
          child: InputDecorator(
            decoration: InputDecoration(
              suffixIcon: Icon(icon, size: 18),
              enabled: onTap != null,
            ),
            child: Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (!_owner) {
      return const Text('Owner access is required to post opening balances.');
    }
    final pending = _pending;
    final body = pending == null
        ? const <String, dynamic>{}
        : booksObject(pending['body']);
    final needsParty = _type == 'receivable' || _type == 'payable';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_busy) const LinearProgressIndicator(),
        if (_message case final message?) ...[
          SettingsNotice(message),
          const SizedBox(height: 12),
        ],
        if (pending != null) ...[
          SettingsInfoBox(
            children: [
              Text(
                'Check the original balance for ${pending['party']} · ${booksMoney(body['amount'])} · ${body['date']}.',
                style: const TextStyle(fontSize: 13, height: 1.6),
              ),
              const SizedBox(height: 10),
              SettingsButton(
                'Retry original opening balance',
                primary: true,
                onPressed: _busy ? null : _post,
              ),
            ],
          ),
        ] else
          SettingsGrid([
            SettingsCell(
              SettingsSelect(
                label: 'Balance type',
                value: _type,
                options: [
                  for (final entry in _typeLabels.entries)
                    (entry.key, entry.value),
                ],
                onChanged: _busy
                    ? null
                    : (value) {
                        setState(() {
                          _type = value;
                          _overdraft = false;
                        });
                        if (value == 'bank') _loadBanks();
                      },
              ),
            ),
            if (needsParty)
              SettingsCell(
                _pseudoField(
                  'Party',
                  _party?.party ?? 'Choose a party',
                  _busy ? null : _pickParty,
                  Icons.arrow_drop_down,
                ),
              ),
            if (_type == 'bank') ...[
              SettingsCell(
                SettingsSelect(
                  label: 'Bank account',
                  value: _bank,
                  options: [
                    for (final bank in _banks)
                      (booksText(bank['id']), booksText(bank['name'])),
                  ],
                  onChanged: _busy ? null : (value) => setState(() => _bank = value),
                ),
              ),
              SettingsCell(
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  dense: true,
                  value: _overdraft,
                  title: const Text('Overdraft (credit balance)'),
                  onChanged: _busy
                      ? null
                      : (value) => setState(() => _overdraft = value ?? false),
                ),
              ),
            ],
            SettingsCell(
              _pseudoField(
                'As of date',
                booksDate(_date),
                _busy ? null : _pickDate,
                Icons.calendar_today_outlined,
              ),
            ),
            SettingsCell(
              SettingsTextField(
                label: 'Amount',
                controller: _amount,
                enabled: !_busy && _storageAvailable,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
              ),
            ),
            SettingsCell(
              SettingsButton(
                _busy ? 'Posting…' : 'Post opening balance',
                primary: true,
                onPressed: _busy || !_storageAvailable ? null : _post,
              ),
              full: true,
            ),
          ]),
      ],
    );
  }
}
