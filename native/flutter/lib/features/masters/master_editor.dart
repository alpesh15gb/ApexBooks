import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import 'item_setup_fields.dart';
import 'master_form_widgets.dart';

enum MasterGroup {
  customer('Customers', 'customer'),
  supplier('Suppliers', 'supplier'),
  item('Items', 'item');

  const MasterGroup(this.label, this.value);
  final String label;
  final String value;
}

/// The New / Edit party and item form, laid out like the web app's modal.
/// Show it with `showDialog`; it closes itself after a successful save.
class MasterEditorPage extends StatefulWidget {
  const MasterEditorPage({
    required this.group,
    required this.workspace,
    required this.record,
    required this.onSave,
    required this.canWrite,
    required this.canArchive,
    super.key,
  });

  final MasterGroup group;
  final WorkspaceContext workspace;
  final Json? record;
  final Future<void> Function(String? id, Json fields) onSave;
  final bool canWrite;
  final bool canArchive;

  @override
  State<MasterEditorPage> createState() => _MasterEditorPageState();
}

class _MasterEditorPageState extends State<MasterEditorPage> {
  final _fields = <String, TextEditingController>{};
  final _initial = <String, String>{};
  final _itemSetupPatch = <String, Object>{};
  final _setupKey = GlobalKey<ItemSetupFieldsState>();
  late final Json _original;
  late bool _tracked;
  late bool _active;
  late String _partyType;
  late String _itemType;
  late String _tax;
  bool _busy = false;
  bool _touched = false;
  bool _discard = false;
  String? _error;

  bool get _new => widget.record == null;
  bool get _item => widget.group == MasterGroup.item;
  bool get _editable => widget.canWrite && !_busy;
  String get _noun => _item ? 'item' : 'party';
  bool _supports(String feature) => widget.workspace.features.contains(feature);

  bool get _dirty =>
      _touched ||
      _itemSetupPatch.isNotEmpty ||
      _fields.entries.any((entry) => entry.value.text != _initial[entry.key]);

  @override
  void initState() {
    super.initState();
    _original = inventoryObject(widget.record?['data']);
    _tracked = _original['track_stock'] == true;
    _active = _original['is_active'] != false;
    _itemType = (_original['item_type'] as String?) ?? 'goods';
    _partyType = (_original['party_type'] as String?) ?? 'both';
    final rate = num.tryParse(inventoryText(_original['gst_rate']));
    _tax = (_original['tax_treatment'] as String?) ?? (rate != null && rate > 0 ? 'taxable' : 'nil_rated');
  }

  TextEditingController _controller(String key, {String fallback = ''}) => _fields.putIfAbsent(key, () {
    final text = key == 'name'
        ? inventoryText(widget.record?['name'])
        : _original[key] == null
        ? fallback
        : inventoryText(_original[key]);
    _initial[key] = text;
    return TextEditingController(text: text);
  });

  String _value(String key) => _controller(key).text.trim();

  String? _number(String name, int precision, {required String label, bool optional = false}) {
    final value = _value(name);
    if (value.isEmpty) return optional ? null : '0';
    if (inventoryDecimal(value, precision) == null) {
      throw FormatException('Enter a valid $label.');
    }
    return value;
  }

  Json _body() {
    final name = _value('name');
    if (name.isEmpty) throw FormatException('Enter a $_noun name.');
    final data = <String, dynamic>{'name': name};
    if (widget.canArchive || _new) data['is_active'] = _active;
    if (_item) {
      final gst = _tax == 'taxable' ? _number('gst_rate', 2, label: 'GST rate')! : '0';
      if (inventoryDecimal(gst, 2)! > BigInt.from(10000)) {
        throw const FormatException('GST rate cannot exceed 100%.');
      }
      if (_tracked &&
          _itemType == 'services' &&
          !(_original['track_stock'] == true && _original['item_type'] == 'services')) {
        throw const FormatException(
          'Stock tracking is supported for goods only. Turn off stock tracking for a new service, or keep this tracked item as goods.',
        );
      }
      final fitError = _setupKey.currentState?.validate();
      if (fitError != null) throw FormatException(fitError);
      return {
        ...data,
        'item_type': _itemType,
        'track_stock': _tracked,
        'tax_treatment': _tax,
        'gst_rate': gst,
        'hsn': _value('hsn'),
        'unit': _value('unit'),
        'barcode': _value('barcode'),
        'sale_rate': _number('sale_rate', 2, label: 'sale rate'),
        'purchase_rate': _number('purchase_rate', 2, label: 'purchase rate'),
        if (_supports('low_stock_reorder') &&
            ((_tracked && _itemType == 'goods') || _value('low_stock_threshold').isNotEmpty))
          'low_stock_threshold': _number('low_stock_threshold', 3, label: 'low-stock quantity', optional: true),
        ..._itemSetupPatch,
      };
    }
    final termsText = _value('payment_terms_days');
    final terms = int.tryParse(termsText);
    if (termsText.isNotEmpty && (terms == null || terms < 0 || terms > 3650)) {
      throw const FormatException('Enter payment terms from 0 to 3,650 days.');
    }
    final email = _value('email');
    final gstin = _value('gstin').toUpperCase();
    if (email.isNotEmpty && !RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
      throw const FormatException('Enter a valid email address.');
    }
    if (gstin.isNotEmpty && !RegExp(r'^\d{2}[A-Z0-9]{13}$').hasMatch(gstin) && gstin != _original['gstin']) {
      throw const FormatException('Enter a 15-character GSTIN.');
    }
    return {
      ...data,
      'party_type': _partyType,
      'email': email,
      'gstin': gstin,
      'phone': _value('phone'),
      'address': _value('address'),
      if (_supports('party_shipping_address')) 'shipping_address': _value('shipping_address'),
      if (_supports('party_payment_terms')) 'payment_terms_days': terms,
      if (_supports('party_credit_limits'))
        'credit_limit': _number('credit_limit', 2, label: 'credit limit', optional: true),
    };
  }

  Future<void> _save() async {
    if (!_editable) return;
    setState(() {
      _busy = true;
      _error = null;
      _discard = false;
    });
    try {
      await widget.onSave(widget.record?['id'] as String?, _body());
      if (!mounted) return;
      Navigator.of(context).pop();
    } catch (error) {
      if (!mounted) return;
      final message = inventoryError(error);
      setState(
        () => _error = error is ApexApiException && error.uncertain
            ? _new
                  ? '$message Return to the list to recover the original request.'
                  : '$message Refresh and check the saved details before editing again.'
            : message,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _requestClose() {
    if (_busy) return;
    if (_dirty && !_discard) {
      setState(() => _discard = true);
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  void dispose() {
    for (final controller in _fields.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Widget _field(
    String key,
    String title,
    int limit, {
    TextInputType? type,
    bool enabled = true,
    String? hint,
    String? note,
    String fallback = '',
    ValueChanged<String>? onChanged,
  }) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      TextField(
        controller: _controller(key, fallback: fallback),
        enabled: _editable && enabled,
        maxLength: limit,
        keyboardType: type,
        onChanged: onChanged,
        decoration: InputDecoration(labelText: title, hintText: hint, counterText: ''),
      ),
      if (note != null) MasterHint(note),
    ],
  );

  Widget _choice(
    String label,
    String value,
    Map<String, String> choices,
    ValueChanged<String> onChange, {
    bool enabled = true,
  }) => DropdownButtonFormField<String>(
    initialValue: choices.containsKey(value) ? value : choices.keys.first,
    isExpanded: true,
    decoration: InputDecoration(labelText: label),
    items: [for (final entry in choices.entries) DropdownMenuItem(value: entry.key, child: Text(entry.value))],
    onChanged: _editable && enabled
        ? (value) {
            if (value != null) {
              setState(() {
                _touched = true;
                onChange(value);
              });
            }
          }
        : null,
  );

  Widget _check(String title, bool value, ValueChanged<bool>? onChanged, {String? note}) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        dense: true,
        controlAffinity: ListTileControlAffinity.leading,
        title: Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
        value: value,
        onChanged: onChanged == null
            ? null
            : (checked) => setState(() {
                _touched = true;
                onChanged(checked ?? false);
              }),
      ),
      if (note != null) Padding(padding: const EdgeInsets.only(left: 4), child: MasterHint(note)),
    ],
  );

  static const _decimal = TextInputType.numberWithOptions(decimal: true);

  List<MasterFormCell> _partyCells() => [
    MasterFormCell(
      _choice('Party type', _partyType, const {
        'both': 'Customer and supplier',
        'customer': 'Customer',
        'supplier': 'Supplier',
      }, (value) => _partyType = value),
    ),
    MasterFormCell(_field('gstin', 'GSTIN', 15, hint: 'Optional')),
    MasterFormCell(_field('phone', 'Phone', 32, type: TextInputType.phone)),
    MasterFormCell(_field('email', 'Email', 254, type: TextInputType.emailAddress)),
    if (_supports('party_credit_limits'))
      MasterFormCell(
        full: true,
        _field(
          'credit_limit',
          'Customer credit limit (₹)',
          16,
          type: _decimal,
          hint: 'No limit warning',
          note:
              'Optional advisory only; does not block saving. Zero warns for any positive customer exposure. Unused customer credits and advances reduce exposure, not supplier payables.',
        ),
      ),
    if (_supports('party_payment_terms'))
      MasterFormCell(
        full: true,
        _field(
          'payment_terms_days',
          'Default payment terms (days)',
          4,
          type: TextInputType.number,
          hint: 'No default',
          note:
              'Optional. Net 0 means due on the document date. Existing documents keep their saved due dates.',
        ),
      ),
    if (_supports('party_shipping_address'))
      MasterFormCell(
        full: true,
        _field(
          'shipping_address',
          'Default delivery address',
          500,
          hint: 'Same as billing address when blank',
          note: 'Copied into new documents only; saved document addresses stay unchanged.',
        ),
      ),
    MasterFormCell(full: true, _field('address', 'Billing address', 500)),
  ];

  List<MasterFormCell> _itemCells() => [
    MasterFormCell(
      _choice('Item type', _itemType, const {'goods': 'Goods', 'services': 'Services'}, (value) {
        _itemType = value;
        if (_new && value == 'services') _tracked = false;
      }, enabled: _new || !_tracked),
    ),
    MasterFormCell(_field('barcode', 'Barcode', 80)),
    MasterFormCell(_field('hsn', 'HSN / SAC', 16)),
    MasterFormCell(_field('unit', 'Unit', 24, hint: 'e.g. pcs')),
    MasterFormCell(_field('sale_rate', 'Sale rate (₹)', 16, type: _decimal, fallback: '0')),
    MasterFormCell(_field('purchase_rate', 'Purchase rate (₹)', 16, type: _decimal, fallback: '0')),
    MasterFormCell(
      _choice('GST treatment', _tax, const {
        'taxable': 'Taxable',
        'nil_rated': 'Nil rated',
        'exempt': 'Exempt',
        'non_gst': 'Non-GST supply',
      }, (value) {
        _tax = value;
        if (value != 'taxable') _controller('gst_rate').text = '0';
      }),
    ),
    MasterFormCell(
      _field(
        'gst_rate',
        'GST rate (%)',
        6,
        type: _decimal,
        fallback: '0',
        enabled: _tax == 'taxable',
        onChanged: (value) {
          final rate = num.tryParse(value);
          setState(() {
            if (rate != null && rate > 0) {
              _tax = 'taxable';
            } else if (_tax == 'taxable') {
              _tax = 'nil_rated';
            }
          });
        },
      ),
    ),
    MasterFormCell(
      full: true,
      _check(
        'Track stock quantities for this item${_new ? '' : ' (fixed after creation)'}',
        _tracked,
        _new && _editable && _itemType == 'goods' ? (value) => _tracked = value : null,
        note: _itemType == 'services'
            ? 'Inventory tracking is supported for goods only. Existing service stock history requires review; it is not changed here.'
            : null,
      ),
    ),
    if (_supports('inventory_setup'))
      MasterFormCell(
        full: true,
        ItemSetupFields(
          key: _setupKey,
          workspace: widget.workspace,
          itemData: _original,
          enabled: _editable,
          onPatch: (field, value) => _itemSetupPatch[field] = value,
        ),
      ),
    if (_supports('low_stock_reorder') &&
        ((_tracked && _itemType == 'goods') || _value('low_stock_threshold').isNotEmpty))
      MasterFormCell(
        full: true,
        _field(
          'low_stock_threshold',
          'Low-stock threshold',
          16,
          type: _decimal,
          hint: 'Disabled',
          note:
              'Alerts when on-hand stock is at or below this quantity. Blank explicitly disables alerts. Clear this value before changing to a service or untracked item. Changing this never posts stock or accounting entries.',
        ),
      ),
  ];

  @override
  Widget build(BuildContext context) {
    final phone = MediaQuery.sizeOf(context).width < 600;
    final pad = phone ? 18.0 : 26.0;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _requestClose();
      },
      child: Dialog(
        insetPadding: phone ? const EdgeInsets.all(12) : const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
        clipBehavior: Clip.antiAlias,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(pad, 22, pad - 8, 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${_new ? 'New' : 'Edit'} $_noun', style: Apex.panelTitle.copyWith(fontSize: 21)),
                          const SizedBox(height: 4),
                          Text(
                            _new ? 'Add a reusable record to this company.' : 'Update details for this company.',
                            style: const TextStyle(fontSize: 13, color: Apex.muted),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: 'Close',
                      onPressed: _busy ? null : _requestClose,
                      icon: const Icon(Icons.close_rounded, size: 20),
                    ),
                  ],
                ),
              ),
              Flexible(
                child: SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(pad, 14, pad, 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (!widget.canWrite)
                        const Padding(
                          padding: EdgeInsets.only(bottom: 14),
                          child: Text(
                            'Read-only access: your draft is preserved, but saving requires editor access.',
                            style: TextStyle(fontSize: 13, color: Apex.muted),
                          ),
                        ),
                      if (!_supports('master_lifecycle'))
                        const Padding(
                          padding: EdgeInsets.only(bottom: 14),
                          child: Text(
                            'Advanced master settings need an updated connected API. Core details can still be saved; unsupported settings will not be submitted.',
                            style: TextStyle(fontSize: 13, color: Apex.muted),
                          ),
                        ),
                      if (_discard)
                        Container(
                          margin: const EdgeInsets.only(bottom: 14),
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: const Color(0xfffbf2e2),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Discard unsaved changes?', style: Apex.strong),
                              const SizedBox(height: 4),
                              Text('Your $_noun details have not been saved.', style: Apex.note),
                              const SizedBox(height: 10),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  OutlinedButton(
                                    onPressed: () => setState(() => _discard = false),
                                    child: const Text('Keep editing'),
                                  ),
                                  OutlinedButton(
                                    style: OutlinedButton.styleFrom(
                                      foregroundColor: Apex.red,
                                      side: const BorderSide(color: Apex.red),
                                    ),
                                    onPressed: () => Navigator.of(context).pop(),
                                    child: const Text('Discard changes'),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      MasterFormGrid([
                        MasterFormCell(
                          full: true,
                          _field(
                            'name',
                            _item ? 'Item name' : 'Party name',
                            120,
                            enabled: _new,
                            note: _new ? null : 'Names are fixed to preserve existing transaction links.',
                          ),
                        ),
                        if (_supports('master_lifecycle') && !_new)
                          MasterFormCell(
                            full: true,
                            _check(
                              'Active for new transactions',
                              _active,
                              _editable ? (value) => _active = value : null,
                              note:
                                  'Archive without deleting history. Existing invoices, balances and settlement remain available. Reactivate here any time.',
                            ),
                          ),
                        ...(_item ? _itemCells() : _partyCells()),
                      ]),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(pad, 8, pad, 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: Text(_error!, style: const TextStyle(color: Apex.red, fontSize: 13)),
                      ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        OutlinedButton(onPressed: _busy ? null : _requestClose, child: const Text('Cancel')),
                        const SizedBox(width: 10),
                        FilledButton(
                          onPressed: _editable ? _save : null,
                          child: Text(_busy ? 'Saving…' : 'Save $_noun'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
