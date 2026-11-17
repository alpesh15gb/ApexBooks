import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../books/books_data.dart';
import 'settings_blocks.dart';
import 'settings_fields.dart';

/// Layouts the server accepts, in the web select's order.
const documentLayoutNames = <String, String>{
  'modern': 'Modern',
  'vintage': 'Vintage',
  'mrp_discount': 'MRP + Discount',
  'elegant': 'Elegant',
  'evergreen': 'Evergreen',
  'classic': 'Classic',
  'compact': 'Compact',
  'bold': 'Bold',
  'minimal': 'Minimal',
};

/// The five formats that have a preview image.
const documentGalleryLayouts = [
  'modern',
  'vintage',
  'mrp_discount',
  'elegant',
  'evergreen',
];

/// Prefix defaults and labels, in the web's order.
const documentPrefixDefaults = <String, (String, String)>{
  'sales_invoice': ('INV', 'Sales invoices'),
  'estimate': ('EST', 'Estimates'),
  'sales_order': ('SO', 'Sales orders'),
  'proforma': ('PF', 'Proforma invoices'),
  'payment_in': ('PIN', 'Payment in'),
  'credit_note': ('CN', 'Credit notes'),
  'pos': ('POS', 'POS'),
  'purchase_bill': ('BILL', 'Purchase bills'),
  'payment_out': ('POUT', 'Payment out'),
  'expense': ('EXP', 'Expenses'),
  'purchase_order': ('PO', 'Purchase orders'),
  'debit_note': ('DN', 'Debit notes'),
  'bank_transfer': ('TRF', 'Cash/bank transfer'),
};

/// April to March financial year that contains today's business date.
int settingsFinancialYear() {
  final today = DateTime.parse(businessDate());
  return today.year - (today.month < 4 ? 1 : 0);
}

const _imageLimit = 240000;

/// Reads a PNG or JPEG into a data URL the server accepts (at most 250 KB).
/// Large pictures are scaled down to 700 px first, like the web upload.
Future<String> brandImageDataUrl(ApexPickedFile file) async {
  final name = file.name.toLowerCase();
  final png = name.endsWith('.png');
  if (!png && !name.endsWith('.jpg') && !name.endsWith('.jpeg')) {
    throw const FormatException('Choose a PNG or JPEG below 15 MB');
  }
  ui.Codec codec;
  try {
    codec = await ui.instantiateImageCodec(file.bytes);
  } catch (_) {
    throw const FormatException('Image could not be read');
  }
  final frame = await codec.getNextFrame();
  final width = frame.image.width;
  final height = frame.image.height;
  frame.image.dispose();
  codec.dispose();
  String url(String mime, Uint8List bytes) =>
      'data:$mime;base64,${base64Encode(bytes)}';
  final longest = max(width, height);
  if (longest <= 700 && file.bytes.length <= _imageLimit) {
    return url(png ? 'image/png' : 'image/jpeg', file.bytes);
  }
  final scale = min(1.0, 700 / longest);
  final scaled = await ui.instantiateImageCodec(
    file.bytes,
    targetWidth: max(1, (width * scale).round()),
    targetHeight: max(1, (height * scale).round()),
  );
  final image = (await scaled.getNextFrame()).image;
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  scaled.dispose();
  if (data == null) throw const FormatException('Image could not be read');
  final bytes = data.buffer.asUint8List();
  if (bytes.length > _imageLimit) {
    throw const FormatException('Image is too detailed; choose a smaller crop');
  }
  return url('image/png', bytes);
}

Uint8List? _decodeDataUrl(String value) {
  final comma = value.indexOf(',');
  if (!value.startsWith('data:') || comma < 0) return null;
  try {
    return base64Decode(value.substring(comma + 1));
  } on FormatException {
    return null;
  }
}

/// Web "Company logo and document branding": the whole form inline.
class BrandingForm extends StatefulWidget {
  const BrandingForm({
    required this.workspace,
    required this.initial,
    this.pickFile,
    super.key,
  });

  final WorkspaceContext workspace;
  final Json initial;

  /// Replaceable in tests.
  final Future<ApexPickedFile?> Function()? pickFile;

  @override
  State<BrandingForm> createState() => _BrandingFormState();
}

class _BrandingFormState extends State<BrandingForm> {
  static const _fields = [
    ('phone', 'Phone', 32, 1),
    ('email', 'Email', 254, 1),
    ('bank_name', 'Bank name', 120, 1),
    ('account_number', 'Bank account number', 120, 1),
    ('ifsc', 'IFSC', 120, 1),
    ('branch', 'Branch', 120, 1),
    ('upi_id', 'UPI ID', 120, 1),
    ('notes', 'Notes', 1500, 4),
    ('terms', 'Terms and conditions', 3000, 4),
  ];

  late final Map<String, TextEditingController> _controllers = {
    for (final (key, _, _, _) in _fields) key: TextEditingController(),
  };
  String _logo = '';
  String _signature = '';
  String _logoFile = '';
  String _signatureFile = '';
  bool _busy = false;
  String _error = '';
  String _message = '';

  WorkspaceContext get _workspace => widget.workspace;
  String get _path => '${_workspace.path}/document-branding';

  @override
  void initState() {
    super.initState();
    _apply(widget.initial);
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _apply(Json data) {
    for (final entry in _controllers.entries) {
      entry.value.text = booksText(data[entry.key]);
    }
    _logo = data['logo'] is String ? data['logo'] as String : '';
    _signature = data['signature'] is String ? data['signature'] as String : '';
  }

  Future<void> _perform(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = '';
      _message = '';
    });
    try {
      await action();
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _saveLogo(String value) async {
    final result = booksObject(await _workspace.api.patch(_path, body: {'logo': value}));
    if (!mounted) return;
    setState(() {
      _logo = result['logo'] is String ? result['logo'] as String : value;
      _logoFile = '';
      _message = value.isEmpty
          ? 'Company logo removed from document output.'
          : 'Company logo saved. It will appear on newly downloaded documents, including older invoices.';
    });
  }

  Future<void> _upload(String key) => _perform(() async {
    final picked = await (widget.pickFile ?? () => pickApexFile(['png', 'jpg', 'jpeg'], 15 * 1024 * 1024))();
    if (picked == null || !mounted) return;
    final value = await brandImageDataUrl(picked);
    if (!mounted) return;
    if (key == 'logo') {
      await _saveLogo(value);
      if (mounted) setState(() => _logoFile = picked.name);
    } else {
      setState(() {
        _signature = value;
        _signatureFile = picked.name;
        _message =
            'Signature selected. Save document details to apply it to new documents.';
      });
    }
  });

  Future<void> _remove(String key) async {
    if (_busy) return;
    if (key == 'logo') {
      await _perform(() => _saveLogo(''));
    } else {
      setState(() {
        _signature = '';
        _signatureFile = '';
        _error = '';
        _message =
            'Signature removed from this draft. Save document details to apply the change.';
      });
    }
  }

  Future<void> _submit() => _perform(() async {
    final body = <String, dynamic>{
      for (final (key, _, _, _) in _fields) key: _controllers[key]!.text,
      'signature': _signature,
    };
    final result = booksObject(await _workspace.api.put(_path, body: body));
    if (!mounted) return;
    setState(() {
      _apply(result);
      _message =
          'Saved. Your company logo appears on all documents; other details are saved with new document snapshots.';
    });
  });

  Widget _asset(String key, String label, String value, String fileName) {
    final bytes = value.isEmpty ? null : _decodeDataUrl(value);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SettingsLabeled(
          label: label,
          child: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border.all(color: Apex.lineStrong),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Row(
              children: [
                OutlinedButton(
                  onPressed: _busy ? null : () => _upload(key),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size(0, 36),
                    backgroundColor: const Color(0xffeef1f5),
                  ),
                  child: const Text('Choose file'),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    fileName.isEmpty ? 'No file chosen' : fileName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, color: Apex.inkSoft),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (bytes != null) ...[
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: Image.memory(
              bytes,
              semanticLabel: key,
              width: 140,
              height: 90,
              fit: BoxFit.contain,
              alignment: Alignment.centerLeft,
              errorBuilder: (_, _, _) => Text('Preview unavailable', style: Apex.note),
            ),
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: SettingsLinkButton(
              'Remove $key',
              onPressed: _busy ? null : () => _remove(key),
            ),
          ),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) => SettingsPanelBox(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          header: true,
          child: const Text(
            'Company logo and document branding',
            style: settingsBlockTitle,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Your logo saves immediately after upload and appears on all newly downloaded documents, including existing invoices. Configure the signature, bank details, UPI QR code, notes and terms saved with new documents.',
          style: TextStyle(fontSize: 13, height: 1.6, color: Apex.inkSoft),
        ),
        const SizedBox(height: 14),
        if (_error.isNotEmpty) SettingsMessage(_error, error: true),
        if (_message.isNotEmpty) SettingsMessage(_message),
        SettingsGrid([
          SettingsCell(
            _asset(
              'logo',
              'Company logo · upload saves immediately',
              _logo,
              _logoFile,
            ),
          ),
          SettingsCell(
            _asset(
              'signature',
              'Authorized signature image',
              _signature,
              _signatureFile,
            ),
          ),
          for (final (key, label, maximum, lines) in _fields)
            SettingsCell(
              SettingsTextField(
                label: label,
                controller: _controllers[key]!,
                maxLength: maximum,
                maxLines: lines,
                enabled: !_busy,
              ),
            ),
          SettingsCell(
            SettingsButton(
              _busy ? 'Saving…' : 'Save document details',
              primary: true,
              onPressed: _busy ? null : _submit,
            ),
            full: true,
          ),
        ]),
      ],
    ),
  );
}

/// Web "Transaction prefixes": select, prefix field and Save prefix, inline.
class PrefixesForm extends StatefulWidget {
  const PrefixesForm({
    required this.workspace,
    required this.series,
    required this.onSaved,
    super.key,
  });

  final WorkspaceContext workspace;
  final List<Json> series;
  final Future<void> Function() onSaved;

  @override
  State<PrefixesForm> createState() => _PrefixesFormState();
}

class _PrefixesFormState extends State<PrefixesForm> {
  final _prefix = TextEditingController();
  late final int _year = settingsFinancialYear();
  String _kind = 'sales_invoice';
  bool _busy = false;
  String _error = '';
  String _saved = '';

  bool get _owner => widget.workspace.company.role == 'owner';

  @override
  void initState() {
    super.initState();
    _resetPrefix();
  }

  @override
  void didUpdateWidget(PrefixesForm old) {
    super.didUpdateWidget(old);
    if (!identical(old.series, widget.series)) _resetPrefix();
  }

  @override
  void dispose() {
    _prefix.dispose();
    super.dispose();
  }

  void _resetPrefix() {
    String? current;
    for (final row in widget.series) {
      if (row['kind'] == _kind && row['financial_year'] == _year) {
        current = booksText(row['prefix']);
      }
    }
    _prefix.text = current ?? documentPrefixDefaults[_kind]!.$1;
  }

  Future<void> _save() async {
    if (_busy) return;
    final prefix = _prefix.text.trim();
    if (prefix.isEmpty || !RegExp(r'^[A-Z0-9-]+$').hasMatch(prefix)) {
      setState(() {
        _saved = '';
        _error = 'Use capital letters, numbers or hyphens for the prefix.';
      });
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
      _saved = '';
    });
    try {
      await widget.workspace.api.put(
        '${widget.workspace.path}/number-series',
        body: {'kind': _kind, 'financial_year': _year, 'prefix': prefix},
      );
      if (mounted) setState(() => _saved = 'Prefix saved');
      await widget.onSaved();
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => SettingsBlock(
    title: 'Transaction prefixes',
    note:
        'Numbers are assigned automatically within the April–March financial year. Year $_year–${_year + 1}.',
    children: [
      if (_error.isNotEmpty) SettingsMessage(_error, error: true),
      if (_owner)
        LayoutBuilder(
          builder: (context, limits) {
            final select = SettingsSelect(
              label: 'Document type',
              value: _kind,
              options: [
                for (final entry in documentPrefixDefaults.entries)
                  (entry.key, entry.value.$2),
              ],
              onChanged: _busy
                  ? null
                  : (value) => setState(() {
                      _kind = value;
                      _resetPrefix();
                    }),
            );
            final prefix = SettingsTextField(
              label: 'Prefix',
              controller: _prefix,
              maxLength: 6,
              enabled: !_busy,
              onChanged: (value) {
                final upper = value.toUpperCase();
                if (upper != value) {
                  _prefix.value = TextEditingValue(
                    text: upper,
                    selection: TextSelection.collapsed(offset: upper.length),
                  );
                }
              },
            );
            final button = SettingsButton(
              'Save prefix',
              primary: true,
              onPressed: _busy ? null : _save,
            );
            if (limits.maxWidth < 560) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  select,
                  const SizedBox(height: 14),
                  prefix,
                  const SizedBox(height: 14),
                  button,
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(flex: 2, child: select),
                const SizedBox(width: 12),
                Expanded(child: prefix),
                const SizedBox(width: 12),
                Padding(padding: const EdgeInsets.only(bottom: 1), child: button),
              ],
            );
          },
        ),
      if (_saved.isNotEmpty) ...[
        const SizedBox(height: 12),
        Text(_saved, style: const TextStyle(fontSize: 13, color: Apex.inkSoft)),
      ],
    ],
  );
}

/// Web "Document PDF layout": select, preview gallery and the note.
class LayoutGallery extends StatefulWidget {
  const LayoutGallery({
    required this.workspace,
    required this.layout,
    required this.onSaved,
    super.key,
  });

  final WorkspaceContext workspace;
  final String layout;
  final Future<void> Function() onSaved;

  @override
  State<LayoutGallery> createState() => _LayoutGalleryState();
}

class _LayoutGalleryState extends State<LayoutGallery> {
  late String _layout = widget.layout;
  String _error = '';
  bool _busy = false;

  bool get _owner => widget.workspace.company.role == 'owner';

  @override
  void didUpdateWidget(LayoutGallery old) {
    super.didUpdateWidget(old);
    if (old.layout != widget.layout) _layout = widget.layout;
  }

  Future<void> _choose(String value) async {
    if (_busy || value == _layout) return;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await widget.workspace.api.put(
        '${widget.workspace.path}/preferences',
        body: {'document_template': value},
      );
      if (mounted) setState(() => _layout = value);
      await widget.onSaved();
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _preview(String layout) => showDialog<void>(
    context: context,
    builder: (context) => Dialog(
      backgroundColor: Colors.white,
      insetPadding: const EdgeInsets.all(16),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720, maxHeight: 900),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 8, 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '${documentLayoutNames[layout]} sample preview',
                      style: Apex.strong,
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            Flexible(
              child: InteractiveViewer(
                maxScale: 4,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Image.asset(
                    'assets/document-templates/$layout.png',
                    semanticLabel:
                        '${layout.replaceAll('_', ' ')} synthetic layout preview',
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => Column(
    key: const ValueKey('document-layout'),
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (_error.isNotEmpty) SettingsMessage(_error, error: true),
      SettingsSelect(
        label: 'Document PDF layout',
        value: _layout,
        options: [
          for (final entry in documentLayoutNames.entries)
            (entry.key, entry.value),
        ],
        onChanged: _owner && !_busy ? _choose : null,
      ),
      LayoutBuilder(
        builder: (context, limits) {
          const gap = 14.0;
          final columns = max(1, ((limits.maxWidth + gap) / (145 + gap)).floor());
          final width = (limits.maxWidth - gap * (columns - 1)) / columns;
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Wrap(
              spacing: gap,
              runSpacing: gap,
              children: [
                for (final id in documentGalleryLayouts)
                  SizedBox(
                    width: width,
                    child: _LayoutCard(
                      id: id,
                      selected: id == _layout,
                      onOpen: () => _preview(id),
                    ),
                  ),
              ],
            ),
          );
        },
      ),
      const Text(
        'Previews use synthetic sample details. Logos, signature images and bank details come from Document branding.',
        style: TextStyle(fontSize: 13, height: 1.6, color: Apex.inkSoft),
      ),
    ],
  );
}

class _LayoutCard extends StatelessWidget {
  const _LayoutCard({
    required this.id,
    required this.selected,
    required this.onOpen,
  });

  final String id;
  final bool selected;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    selected: selected,
    label:
        '${documentLayoutNames[id]}${selected ? ', current layout' : ''}. Open sample preview',
    excludeSemantics: true,
    onTap: onOpen,
    child: Material(
      color: selected ? const Color(0xffeaf5ee) : const Color(0xfff7f8fa),
      shape: RoundedRectangleBorder(
        side: BorderSide(
          color: selected ? Apex.green : const Color(0xffdfe3e8),
          width: selected ? 2 : 1,
        ),
        borderRadius: BorderRadius.circular(5),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(5),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AspectRatio(
                aspectRatio: 715 / 1011,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border: Border.all(color: Apex.line),
                  ),
                  child: Image.asset(
                    'assets/document-templates/$id.png',
                    fit: BoxFit.cover,
                    alignment: Alignment.topCenter,
                    excludeFromSemantics: true,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Flexible(
                    child: Text(
                      documentLayoutNames[id]!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: Apex.ink,
                      ),
                    ),
                  ),
                  if (selected) ...[
                    const SizedBox(width: 5),
                    const Icon(Icons.check_circle, size: 15, color: Apex.green),
                  ],
                ],
              ),
              const SizedBox(height: 6),
              const Text('Open sample preview', style: Apex.small),
            ],
          ),
        ),
      ),
    ),
  );
}
