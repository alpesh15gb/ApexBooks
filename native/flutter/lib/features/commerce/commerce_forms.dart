import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';

class CommerceField extends StatelessWidget {
  const CommerceField({
    required this.label,
    required this.controller,
    this.maxLength = 120,
    this.type,
    this.onChanged,
    super.key,
  });
  final String label;
  final TextEditingController controller;
  final int maxLength;
  final TextInputType? type;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: TextField(
      controller: controller,
      maxLength: maxLength,
      keyboardType: type,
      onChanged: onChanged,
      decoration: InputDecoration(labelText: label, counterText: ''),
    ),
  );
}

class CommerceDialog extends StatelessWidget {
  const CommerceDialog({
    required this.title,
    required this.fields,
    required this.primary,
    this.error,
    this.eyebrow,
    super.key,
  });
  final String title;
  final List<Widget> fields;
  final Widget primary;
  final String? error;
  final String? eyebrow;

  @override
  Widget build(BuildContext context) {
    // The web dialog is up to 800 px wide; phones get the screen minus the dialog inset.
    final room = MediaQuery.sizeOf(context).width - 96;
    final width = room < 800 ? room : 800.0;
    return AlertDialog(
      title: eyebrow == null
          ? Text(title)
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  eyebrow!,
                  style: const TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.8,
                    color: Apex.muted,
                  ),
                ),
                const SizedBox(height: 6),
                Text(title),
              ],
            ),
      scrollable: true,
      content: SizedBox(
        width: width,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ...fields,
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        primary,
      ],
    );
  }
}

class CommerceConnectionForm extends StatefulWidget {
  const CommerceConnectionForm({required this.banks, super.key});
  final List<Json> banks;

  @override
  State<CommerceConnectionForm> createState() => _CommerceConnectionFormState();
}

class _CommerceConnectionFormState extends State<CommerceConnectionForm> {
  final _name = TextEditingController();
  final _origin = TextEditingController();
  final _channel = TextEditingController(text: 'default');
  String _bank = 'default';
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _origin.dispose();
    _channel.dispose();
    super.dispose();
  }

  void _save() {
    final name = _name.text.trim();
    final channel = _channel.text.trim();
    final url = Uri.tryParse(_origin.text.trim());
    if (name.isEmpty ||
        channel.isEmpty ||
        url == null ||
        !url.hasAuthority ||
        url.host.isEmpty ||
        url.userInfo.isNotEmpty ||
        url.hasFragment ||
        url.hasQuery ||
        (url.path.isNotEmpty && url.path != '/') ||
        (url.scheme != 'https' &&
            !(url.scheme == 'http' &&
                const {'localhost', '127.0.0.1'}.contains(url.host)))) {
      setState(
        () => _error = 'Enter a store name, channel and HTTPS store origin without a path.',
      );
      return;
    }
    Navigator.pop(context, {
      'name': name,
      'base_url': url.origin,
      'channel': channel,
      'gateway_bank_id': _bank,
    });
  }

  @override
  Widget build(BuildContext context) => CommerceDialog(
    title: 'Connect a Bagisto store',
    error: _error,
    fields: [
      const Text(
        'ApexBridge uses a one-time setup secret. Have the store administrator ready before creating the connection.',
      ),
      CommerceField(label: 'Store name', controller: _name, maxLength: 100),
      CommerceField(
        label: 'Store origin',
        controller: _origin,
        maxLength: 500,
        type: TextInputType.url,
      ),
      CommerceField(
        label: 'Store channel',
        controller: _channel,
        maxLength: 100,
      ),
      DropdownButtonFormField<String>(
        initialValue: _bank,
        isExpanded: true,
        decoration: const InputDecoration(
          labelText: 'Gateway clearing account',
        ),
        items: [
          for (final bank in widget.banks)
            DropdownMenuItem(
              value: inventoryText(bank['id']),
              child: Text(
                inventoryText(bank['name']),
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) => setState(() => _bank = value ?? 'default'),
      ),
    ],
    primary: FilledButton(
      onPressed: _save,
      child: const Text('Create connection'),
    ),
  );
}

class CommerceMappingForm extends StatefulWidget {
  const CommerceMappingForm({
    required this.workspace,
    required this.storeProducts,
    super.key,
  });
  final WorkspaceContext workspace;
  final List<Json> storeProducts;

  @override
  State<CommerceMappingForm> createState() => _CommerceMappingFormState();
}

class _CommerceMappingFormState extends State<CommerceMappingForm> {
  final _identity = TextEditingController();
  final _sku = TextEditingController();
  String _entity = 'product';
  String? _record;
  String? _recordName;
  String? _error;
  String _search = '';
  late Future<List<Json>> _records = _load('item');

  Future<List<Json>> _load(String kind) async {
    final all = <String, Json>{};
    for (var offset = 0; ; offset += 200) {
      final page = inventoryRows(
        await widget.workspace.api.get(
          '${widget.workspace.path}/records',
          query: {
            'kind': kind,
            'compact': 'true',
            'limit': '200',
            'offset': '$offset',
          },
        ),
      );
      final oldLength = all.length;
      for (final row in page) {
        all[inventoryText(row['id'])] = row;
      }
      if (page.length < 200 || oldLength == all.length) break;
    }
    return all.values
        .where((row) => inventoryObject(row['data'])['is_active'] != false)
        .toList();
  }

  @override
  void dispose() {
    _identity.dispose();
    _sku.dispose();
    super.dispose();
  }

  void _save() {
    if (_identity.text.trim().isEmpty ||
        _record == null ||
        (_entity == 'product' && _sku.text.trim().isEmpty)) {
      setState(
        () => _error =
            'Enter the store identity and select a matching accounting record.'
            '${_entity == 'product' ? ' Product mappings also need the exact store SKU.' : ''}',
      );
      return;
    }
    Navigator.pop(context, {
      'entity_type': _entity,
      'external_id': _identity.text.trim(),
      'record_id': _record,
      if (_entity == 'product') 'sku': _sku.text.trim(),
    });
  }

  @override
  Widget build(BuildContext context) => CommerceDialog(
    title: 'Map store identity',
    error: _error,
    fields: [
      DropdownButtonFormField<String>(
        initialValue: _entity,
        decoration: const InputDecoration(labelText: 'Mapping type'),
        items: const [
          DropdownMenuItem(value: 'product', child: Text('Product to item')),
          DropdownMenuItem(
            value: 'customer',
            child: Text('Customer to contact'),
          ),
        ],
        onChanged: (value) {
          if (value == null || value == _entity) return;
          final records = _load(value == 'product' ? 'item' : 'party');
          setState(() {
            _entity = value;
            _record = null;
            _recordName = null;
            _search = '';
            _identity.clear();
            _sku.clear();
            _records = records;
          });
        },
      ),
      if (_entity == 'product' && widget.storeProducts.isNotEmpty)
        DropdownButtonFormField<String>(
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Scanned products'),
          items: [
            for (final product in widget.storeProducts)
              DropdownMenuItem(
                value: inventoryText(product['external_id']),
                child: Text(
                  '${product['sku']} · ${product['name']}',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
          onChanged: (value) {
            final product = widget.storeProducts
                .where((row) => row['external_id'] == value)
                .firstOrNull;
            if (product != null) {
              _identity.text = inventoryText(product['external_id']);
              _sku.text = inventoryText(product['sku']);
            }
          },
        ),
      CommerceField(
        label: 'Store identity',
        controller: _identity,
        maxLength: 160,
      ),
      if (_entity == 'product')
        CommerceField(
          label: 'Exact store SKU',
          controller: _sku,
          maxLength: 100,
        ),
      if (_recordName != null) Text('Selected: $_recordName'),
      TextField(
        key: ValueKey(_entity),
        onChanged: (value) =>
            setState(() => _search = value.trim().toLowerCase()),
        decoration: InputDecoration(
          labelText: _entity == 'product'
              ? 'Find accounting item'
              : 'Find accounting contact',
          prefixIcon: const Icon(Icons.search),
        ),
      ),
      FutureBuilder<List<Json>>(
        future: _records,
        builder: (context, state) {
          if (state.connectionState != ConnectionState.done) {
            return const LinearProgressIndicator();
          }
          if (state.hasError) return Text(inventoryError(state.error!));
          final matches = (state.data ?? [])
              .where(
                (row) =>
                    inventoryText(row['name']).toLowerCase().contains(_search),
              )
              .take(10);
          if (matches.isEmpty) {
            return const Text('No active accounting records match.');
          }
          return Column(
            children: [
              for (final row in matches)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  leading: Icon(
                    row['id'] == _record
                        ? Icons.check_circle
                        : Icons.circle_outlined,
                  ),
                  title: Text(inventoryText(row['name'])),
                  onTap: () => setState(() {
                    _record = inventoryText(row['id']);
                    _recordName = inventoryText(row['name']);
                  }),
                ),
            ],
          );
        },
      ),
    ],
    primary: FilledButton(onPressed: _save, child: const Text('Save mapping')),
  );
}
