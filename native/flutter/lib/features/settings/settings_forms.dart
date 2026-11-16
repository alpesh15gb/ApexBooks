import 'package:material_ui/material_ui.dart';

import '../../core/session.dart';
import '../../core/workspace.dart';

typedef SettingField = ({
  String key,
  String label,
  String value,
  int maximum,
  bool secret,
});

SettingField setting(
  String key,
  String label, {
  String value = '',
  int maximum = 120,
  bool secret = false,
}) => (key: key, label: label, value: value, maximum: maximum, secret: secret);

Future<bool?> showSettingsForm(
  BuildContext context, {
  required String title,
  required List<SettingField> fields,
  required Future<void> Function(Map<String, String>) save,
  Map<String, List<(String, String)>> choices = const {},
  String action = 'Save',
  String? note,
}) => showDialog<bool>(
  context: context,
  builder: (context) => _SettingsForm(
    title: title,
    fields: fields,
    save: save,
    choices: choices,
    action: action,
    note: note,
  ),
);

Future<void> showCompanyEditor(
  BuildContext context,
  ApexSession session, {
  ApexCompany? company,
}) async {
  String? companyId;
  final result = await showSettingsForm(
    context,
    title: company == null ? 'Add company' : 'Company details',
    action: company == null ? 'Create company' : 'Save details',
    fields: [
      setting('name', 'Legal company name', value: company?.name ?? ''),
      setting(
        'book_label',
        'Book label (optional)',
        value: company?.bookLabel ?? '',
        maximum: 80,
      ),
      if (company == null)
        setting('tax_mode', 'Tax profile', value: 'unregistered'),
      setting('gstin', 'GSTIN', value: company?.gstin ?? '', maximum: 15),
      setting(
        'state_code',
        'State code',
        value: company?.stateCode ?? '',
        maximum: 2,
      ),
      setting(
        'address',
        'Address',
        value: company?.address ?? '',
        maximum: 500,
      ),
    ],
    choices: {
      if (company == null)
        'tax_mode': const [
          ('unregistered', 'Unregistered'),
          ('regular', 'Regular GST'),
          ('composition', 'Composition'),
        ],
    },
    save: (data) async {
      if (data['name']!.isEmpty) {
        throw const FormatException('Enter the company name.');
      }
      final api = session.accountApi;
      final saved = company == null
          ? await api.post('/api/companies', body: data)
          : await api.patch('/api/companies/${company.id}', body: data);
      companyId = (saved as Json)['id'] as String;
    },
  );
  if (result == true) await session.refreshCompanies(select: companyId);
}

class _SettingsForm extends StatefulWidget {
  const _SettingsForm({
    required this.title,
    required this.fields,
    required this.save,
    required this.choices,
    required this.action,
    this.note,
  });

  final String title;
  final List<SettingField> fields;
  final Future<void> Function(Map<String, String>) save;
  final Map<String, List<(String, String)>> choices;
  final String action;
  final String? note;

  @override
  State<_SettingsForm> createState() => _SettingsFormState();
}

class _SettingsFormState extends State<_SettingsForm> {
  late final _values = {
    for (final field in widget.fields) field.key: field.value,
  };
  bool _busy = false;
  String? _error;

  Future<void> _save() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final body = {
        for (final field in widget.fields)
          field.key: field.secret
              ? _values[field.key]!
              : _values[field.key]!.trim(),
      };
      await widget.save(body);
      if (mounted) Navigator.pop(context, true);
    } catch (failure) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = switch (failure) {
            ApexApiException() => failure.message,
            FormatException() => failure.message,
            _ => 'The operation could not be completed.',
          };
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy,
    child: AlertDialog(
      title: Text(widget.title),
      scrollable: true,
      content: SizedBox(
        width: 520,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (widget.note case final note?) ...[
              Text(note),
              const SizedBox(height: 12),
            ],
            for (final field in widget.fields) ...[
              if (widget.choices[field.key] case final options?)
                DropdownButtonFormField<String>(
                  isExpanded: true,
                  initialValue: _values[field.key],
                  decoration: InputDecoration(labelText: field.label),
                  items: [
                    for (final (key, label) in options)
                      DropdownMenuItem(value: key, child: Text(label)),
                  ],
                  onChanged: _busy
                      ? null
                      : (value) => _values[field.key] = value!,
                )
              else
                TextFormField(
                  initialValue: field.value,
                  maxLength: field.maximum,
                  enabled: !_busy,
                  obscureText: field.secret,
                  enableSuggestions: !field.secret,
                  autocorrect: !field.secret,
                  maxLines: field.maximum >= 500 ? 3 : 1,
                  onChanged: (value) => _values[field.key] = value,
                  decoration: InputDecoration(labelText: field.label),
                ),
              const SizedBox(height: 9),
            ],
            if (_error case final error?)
              Semantics(
                liveRegion: true,
                child: Text(
                  error,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
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
          child: Text(_busy ? 'Working…' : widget.action),
        ),
      ],
    ),
  );
}
