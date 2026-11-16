import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import '../inventory/inventory_setup.dart';
import 'master_form_widgets.dart';

/// Web wording for the part grade (`GRADE_LABELS` in inventorySetup.js).
const itemGradeLabels = {
  'oem': 'OEM',
  'aftermarket': 'Aftermarket',
  'used': 'Used',
  'refurbished': 'Refurbished',
};

class ItemSetupFields extends StatefulWidget {
  const ItemSetupFields({
    required this.workspace,
    required this.itemData,
    required this.enabled,
    required this.onPatch,
    super.key,
  });
  final WorkspaceContext workspace;
  final Json itemData;
  final bool enabled;
  final void Function(String field, Object value) onPatch;

  @override
  State<ItemSetupFields> createState() => ItemSetupFieldsState();
}

class _FitRow {
  _FitRow({this.make = '', this.model = '', String from = '', String to = ''})
    : from = TextEditingController(text: from),
      to = TextEditingController(text: to);

  String make;
  String model;
  final TextEditingController from;
  final TextEditingController to;

  void dispose() {
    from.dispose();
    to.dispose();
  }
}

class ItemSetupFieldsState extends State<ItemSetupFields>
    with AutomaticKeepAliveClientMixin {
  late Future<InventorySetup> _setup = InventorySetup.load(widget.workspace);
  late List<String> _shelves = switch (widget.itemData['location_ids']) {
    List values => values.whereType<String>().toList(),
    _ => [],
  };
  late final List<_FitRow> _fits = [
    for (final fit in inventoryRows(widget.itemData['vehicle_fitment']).map(VehicleFitment.fromJson))
      _FitRow(
        make: fit.make,
        model: fit.model,
        from: fit.from?.toString() ?? '',
        to: fit.to?.toString() ?? '',
      ),
  ];
  late final _oem = TextEditingController(text: inventoryText(widget.itemData['oem_number']));
  late final _brand = TextEditingController(text: inventoryText(widget.itemData['part_brand']));
  late String _grade = inventoryText(widget.itemData['part_grade']);
  bool _fitsTouched = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _oem.dispose();
    _brand.dispose();
    for (final row in _fits) {
      row.dispose();
    }
    super.dispose();
  }

  void _refresh() {
    final setup = InventorySetup.load(widget.workspace);
    setState(() {
      _setup = setup;
    });
  }

  /// A message when an edited vehicle list cannot be saved, otherwise null.
  String? validate() {
    if (!_fitsTouched) return null;
    for (final row in _fits) {
      final make = row.make.trim();
      final model = row.model.trim();
      if (make.isEmpty && model.isEmpty) continue;
      if (make.isEmpty) return 'Enter a vehicle make.';
      final from = _year(row.from);
      final to = _year(row.to);
      if (from == _bad || to == _bad) return 'Use years between 1950 and 2100.';
      if (from != null && to != null && from > to) {
        return 'The first model year must come before the last.';
      }
    }
    return null;
  }

  static const _bad = -1;

  int? _year(TextEditingController field) {
    final text = field.text.trim();
    if (text.isEmpty) return null;
    final year = int.tryParse(text);
    return year == null || year < 1950 || year > 2100 ? _bad : year;
  }

  String _tidy(String value) => value.trim().replaceAll(RegExp(r'\s+'), ' ');

  void _storeFits() {
    _fitsTouched = true;
    widget.onPatch('vehicle_fitment', [
      for (final row in _fits)
        if (_tidy(row.make).isNotEmpty || _tidy(row.model).isNotEmpty)
          {
            'make': _tidy(row.make),
            'model': _tidy(row.model),
            'year_from': switch (_year(row.from)) { null || _bad => null, final year => year },
            'year_to': switch (_year(row.to)) { null || _bad => null, final year => year },
          },
    ]);
  }

  void _toggleShelf(String id, bool on) {
    setState(() {
      if (on) {
        _shelves = [..._shelves, id];
      } else {
        _shelves = _shelves.where((value) => value != id).toList();
      }
    });
    widget.onPatch('location_ids', List<String>.of(_shelves));
  }

  bool get _hasVehicleData =>
      _oem.text.isNotEmpty || _brand.text.isNotEmpty || _grade.isNotEmpty || _fits.isNotEmpty;

  Widget _suggest({
    required Key key,
    required String label,
    required String value,
    required Iterable<String> Function() options,
    required int maxLength,
    required ValueChanged<String> onChanged,
  }) => Autocomplete<String>(
    key: key,
    initialValue: TextEditingValue(text: value),
    optionsMaxHeight: 220,
    optionsBuilder: (input) {
      final typed = input.text.trim().toLowerCase();
      if (typed.isEmpty) return const [];
      return options().where((item) => item.toLowerCase().contains(typed)).take(20);
    },
    onSelected: onChanged,
    fieldViewBuilder: (context, controller, focus, submit) => TextField(
      controller: controller,
      focusNode: focus,
      enabled: widget.enabled,
      onChanged: onChanged,
      onSubmitted: (_) => submit(),
      maxLength: maxLength,
      decoration: InputDecoration(labelText: label, counterText: ''),
    ),
  );

  Widget _yearField(TextEditingController controller, String label, int index) => TextField(
    controller: controller,
    enabled: widget.enabled,
    keyboardType: TextInputType.number,
    maxLength: 4,
    onChanged: (_) => _storeFits(),
    decoration: InputDecoration(labelText: label, hintText: 'Year', counterText: ''),
  );

  Widget _fitRow(InventorySetup setup, int index, _FitRow row) {
    List<String> models() {
      final make = setup.modelsByMake.keys
          .where((name) => name.toLowerCase() == row.make.trim().toLowerCase())
          .firstOrNull;
      return setup.modelsByMake[make] ?? const [];
    }

    final makeField = _suggest(
      key: ObjectKey(row),
      label: 'Make',
      value: row.make,
      options: () => setup.modelsByMake.keys,
      maxLength: 40,
      onChanged: (value) {
        row.make = value;
        _storeFits();
      },
    );
    final modelField = _suggest(
      key: ValueKey(('model', row)),
      label: 'Model',
      value: row.model,
      options: models,
      maxLength: 60,
      onChanged: (value) {
        row.model = value;
        _storeFits();
      },
    );
    final remove = IconButton(
      tooltip: 'Remove vehicle ${index + 1}',
      icon: const Icon(Icons.delete_outline_rounded, size: 18),
      onPressed: widget.enabled
          ? () {
              setState(() => _fits.removeAt(index).dispose());
              _storeFits();
            }
          : null,
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: LayoutBuilder(
        builder: (context, limits) => limits.maxWidth < 560
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  makeField,
                  const SizedBox(height: 10),
                  modelField,
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(child: _yearField(row.from, 'From', index)),
                      const SizedBox(width: 10),
                      Expanded(child: _yearField(row.to, 'To', index)),
                      remove,
                    ],
                  ),
                ],
              )
            : Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 3, child: makeField),
                  const SizedBox(width: 10),
                  Expanded(flex: 3, child: modelField),
                  const SizedBox(width: 10),
                  Expanded(flex: 2, child: _yearField(row.from, 'From', index)),
                  const SizedBox(width: 10),
                  Expanded(flex: 2, child: _yearField(row.to, 'To', index)),
                  remove,
                ],
              ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return FutureBuilder<InventorySetup>(
      future: _setup,
      builder: (context, state) {
        if (state.connectionState != ConnectionState.done) {
          return const LinearProgressIndicator();
        }
        if (state.hasError) {
          return ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Shelf and vehicle settings could not be loaded.'),
            subtitle: Text(inventoryError(state.error!)),
            trailing: TextButton(onPressed: _refresh, child: const Text('Retry')),
          );
        }
        final setup = state.data ?? const InventorySetup();
        final chosen = _shelves;
        final options = <ShelfLocation>[
          for (final shelf in setup.shelves)
            if (shelf.active || chosen.contains(shelf.id)) shelf,
          for (final id in chosen)
            if (!setup.shelves.any((shelf) => shelf.id == id))
              ShelfLocation(id: id, name: 'Unknown shelf', active: false),
        ];
        final atLimit = chosen.length >= setup.shelfLimit;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            MasterFormSection(
              title: 'Where it is kept',
              icon: Icons.place_outlined,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (options.isEmpty)
                    const Text(
                      'No locations yet. The owner can add them in Settings → Stock & modules.',
                      style: TextStyle(fontSize: 12, color: Apex.muted),
                    )
                  else
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final shelf in options)
                          FilterChip(
                            label: Text(shelf.label),
                            selected: chosen.contains(shelf.id),
                            onSelected: widget.enabled && (chosen.contains(shelf.id) || !atLimit)
                                ? (on) => _toggleShelf(shelf.id, on)
                                : null,
                          ),
                      ],
                    ),
                  if (atLimit) MasterHint('An item can be filed under up to ${setup.shelfLimit} locations.'),
                ],
              ),
            ),
            if (setup.automobileEnabled) ...[
              const SizedBox(height: 16),
              MasterFormSection(
                title: 'Vehicle details',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    MasterFormGrid([
                      MasterFormCell(
                        TextField(
                          controller: _oem,
                          enabled: widget.enabled,
                          maxLength: 40,
                          onChanged: (value) => widget.onPatch('oem_number', value.trim()),
                          decoration: const InputDecoration(labelText: 'Part number (OEM)', counterText: ''),
                        ),
                      ),
                      MasterFormCell(
                        TextField(
                          controller: _brand,
                          enabled: widget.enabled,
                          maxLength: 40,
                          onChanged: (value) => widget.onPatch('part_brand', value.trim()),
                          decoration: const InputDecoration(labelText: 'Brand', counterText: ''),
                        ),
                      ),
                      MasterFormCell(
                        DropdownButtonFormField<String>(
                          initialValue: itemGradeLabels.containsKey(_grade) ? _grade : '',
                          isExpanded: true,
                          decoration: const InputDecoration(labelText: 'Part grade'),
                          items: [
                            const DropdownMenuItem(value: '', child: Text('Not specified')),
                            for (final entry in itemGradeLabels.entries)
                              DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                          ],
                          onChanged: widget.enabled
                              ? (value) {
                                  if (value != null) {
                                    setState(() => _grade = value);
                                    widget.onPatch('part_grade', value);
                                  }
                                }
                              : null,
                        ),
                      ),
                    ]),
                    const SizedBox(height: 18),
                    const Text('Fits these vehicles', style: Apex.strong),
                    if (_fits.isEmpty)
                      const MasterHint(
                        'Add each make and model this part fits. Leave the model blank if it fits every model of that make.',
                      ),
                    const SizedBox(height: 10),
                    for (final (index, row) in _fits.indexed) _fitRow(setup, index, row),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton.icon(
                        onPressed: widget.enabled && _fits.length < 60
                            ? () {
                                setState(() => _fits.add(_FitRow()));
                                _fitsTouched = true;
                              }
                            : null,
                        icon: const Icon(Icons.add, size: 16),
                        label: const Text('Add vehicle'),
                      ),
                    ),
                  ],
                ),
              ),
            ] else if (_hasVehicleData)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text(
                  'Saved vehicle details are kept while Automobile is off.',
                  style: TextStyle(fontSize: 12, color: Apex.muted),
                ),
              ),
          ],
        );
      },
    );
  }
}
