import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import 'books_data.dart';
import 'books_entry_posting.dart';

bool supportsBooksDetailAmendment(BooksRecord record) =>
    record.json['posted'] == true &&
    record.json['cancelled'] != true &&
    const {
      'payment_in',
      'payment_out',
      'credit_note',
      'debit_note',
    }.contains(record.kind);

String booksStoredNotes(BooksRecord record) =>
    record.data['notes'] is String ? record.data['notes'] as String : '';

BooksCommand booksDetailAmendment(
  BooksRecord record,
  String reference,
  String notes,
) {
  final number = reference.trim();
  final amount = booksText(record.json['amount']);
  if (!supportsBooksDetailAmendment(record) ||
      record.party.isEmpty ||
      record.date.isEmpty ||
      amount.isEmpty) {
    throw const FormatException(
      'Reload this posted entry before editing its details.',
    );
  }
  if (number.isEmpty || number.length > 16) {
    throw const FormatException('Enter a reference of 1–16 characters.');
  }
  if (notes != booksStoredNotes(record) && notes.length > 4000) {
    throw const FormatException('Keep notes within 4,000 characters.');
  }
  final version = record.data['version'] ?? 0;
  if (version is! int || version < 0) {
    throw const FormatException('Reload this entry to verify its version.');
  }
  return BooksCommand(BooksOperation.amend, record.id, {
    'kind': record.kind,
    'name': record.party,
    'date': record.date,
    'amount': amount,
    'number': number,
    'data': {
      'version': version,
      if (notes != booksStoredNotes(record)) 'notes': notes,
    },
  });
}

class BooksEditDetails extends StatefulWidget {
  const BooksEditDetails({
    required this.posting,
    required this.record,
    required this.onBack,
    required this.onSaved,
    super.key,
  });
  final BooksPosting posting;
  final BooksRecord record;
  final VoidCallback onBack;
  final ValueChanged<BooksRecord> onSaved;

  @override
  State<BooksEditDetails> createState() => _BooksEditDetailsState();
}

class _BooksEditDetailsState extends State<BooksEditDetails> {
  late String _reference;
  late String _notes;
  String? _message;

  @override
  void initState() {
    super.initState();
    _reference = widget.record.number;
    _notes = booksStoredNotes(widget.record);
  }

  Future<void> _save() async {
    if (!widget.posting.canStart) return;
    try {
      final command = booksDetailAmendment(widget.record, _reference, _notes);
      final result = await widget.posting.submit(command);
      if (!mounted) return;
      if (result != null) {
        widget.onSaved(result);
      } else {
        setState(() => _message = widget.posting.message);
      }
    } on FormatException catch (error) {
      if (mounted) setState(() => _message = error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final record = widget.record;
    final busy = widget.posting.busy;
    final changed =
        _reference.trim() != record.number ||
        _notes != booksStoredNotes(record);
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: busy ? null : widget.onBack,
                icon: const Icon(Icons.arrow_back),
                label: const Text('Back to entry'),
              ),
            ),
            const SizedBox(height: 8),
            Text('Edit details', style: Apex.registerTitle),
            const SizedBox(height: 4),
            Text('${record.label} · ${record.party}', style: Apex.strong),
            Text(
              '${record.date} · ${booksMoney(record.json['amount'])}',
              style: Apex.note,
            ),
            const SizedBox(height: 16),
            TextFormField(
              initialValue: _reference,
              enabled: !busy,
              maxLength: 16,
              decoration: const InputDecoration(
                labelText: 'Document reference',
              ),
              onChanged: (value) => setState(() {
                _reference = value;
                _message = null;
              }),
            ),
            const SizedBox(height: 8),
            TextFormField(
              initialValue: _notes,
              enabled: !busy,
              maxLength: 4000,
              minLines: 2,
              maxLines: 5,
              decoration: const InputDecoration(labelText: 'Notes'),
              onChanged: (value) => setState(() {
                _notes = value;
                _message = null;
              }),
            ),
            const SizedBox(height: 8),
            if (_message case final message?)
              Semantics(
                liveRegion: true,
                child: Text(
                  message,
                  style: const TextStyle(color: Apex.red, fontSize: 13),
                ),
              ),
            if (busy)
              const LinearProgressIndicator(
                semanticsLabel: 'Saving entry details',
              )
            else
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton(
                  onPressed:
                      changed &&
                          _reference.trim().isNotEmpty &&
                          widget.posting.canStart
                      ? _save
                      : null,
                  child: const Text('Save details'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
