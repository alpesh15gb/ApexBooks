import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../books/books_data.dart';
import '../books/books_entry_picker.dart';
import 'settings_blocks.dart';

class OpeningPartyPanel extends StatefulWidget {
  const OpeningPartyPanel({required this.workspace, super.key});

  final WorkspaceContext workspace;

  @override
  State<OpeningPartyPanel> createState() => _OpeningPartyPanelState();
}

class _OpeningPartyPanelState extends State<OpeningPartyPanel> {
  static const _operation = 'opening-party-balance';
  final _amount = TextEditingController();
  DateTime _date = DateTime.parse(businessDate());
  String _type = 'receivable';
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
    if (!retry &&
        (party == null ||
            !RegExp(r'^\d{1,12}(?:\.\d{1,2})?$').hasMatch(amount) ||
            (num.tryParse(amount) ?? 0) <= 0)) {
      setState(() => _message = 'Choose a party and enter a positive amount.');
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
            'party': party!.party,
            'body': {
              'kind': 'opening',
              'date': booksDate(_date),
              'amount': amount,
              'data': {'balance_kind': _type, 'party_id': party.id},
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

  @override
  Widget build(BuildContext context) {
    if (!_owner) {
      return const Text('Owner access is required to post opening balances.');
    }
    final pending = _pending;
    final body = pending == null
        ? const <String, dynamic>{}
        : booksObject(pending['body']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_busy) const LinearProgressIndicator(),
        if (_message case final message?) ...[
          SettingsNotice(message),
          const SizedBox(height: 12),
        ],
        if (pending != null) ...[
          Text(
            'Check the original balance for ${pending['party']} · ${booksMoney(body['amount'])} · ${body['date']}.',
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: _busy ? null : _post,
            child: const Text('Retry original opening balance'),
          ),
        ] else ...[
          const Text(
            'Enter the amount due before the first transaction for this party.',
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: _type,
            decoration: const InputDecoration(labelText: 'Balance type'),
            items: const [
              DropdownMenuItem(
                value: 'receivable',
                child: Text('Customer owes us'),
              ),
              DropdownMenuItem(
                value: 'payable',
                child: Text('We owe a supplier'),
              ),
            ],
            onChanged: _busy ? null : (value) => setState(() => _type = value!),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: _busy ? null : _pickParty,
                icon: const Icon(Icons.person_outline),
                label: Text(_party?.party ?? 'Choose a party'),
              ),
              OutlinedButton.icon(
                onPressed: _busy ? null : _pickDate,
                icon: const Icon(Icons.calendar_today_outlined),
                label: Text(booksDate(_date)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _amount,
            enabled: !_busy && _storageAvailable,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Opening amount (₹)'),
          ),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton(
              onPressed: _busy || !_storageAvailable ? null : _post,
              child: const Text('Post opening balance'),
            ),
          ),
        ],
      ],
    );
  }
}
