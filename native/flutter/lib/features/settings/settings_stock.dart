import 'dart:convert';

import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../books/books_data.dart';
import 'settings_blocks.dart';
import 'settings_fields.dart';

String _tidy(Object? text) =>
    '${text ?? ''}'.replaceAll(RegExp(r'\s+'), ' ').trim();
bool _same(Object? a, Object? b) => _tidy(a).toLowerCase() == _tidy(b).toLowerCase();

const _typeOrder = ['car', 'two_wheeler', 'commercial', 'three_wheeler'];

/// Editable copy of the server's inventory setup (the web `draft`).
class SetupDraft {
  SetupDraft({
    required this.automobile,
    required this.locations,
    required this.added,
    required this.hiddenMakes,
    required this.hiddenModels,
  });

  factory SetupDraft.from(Json setup) => SetupDraft(
    automobile: setup['automobile_enabled'] == true,
    locations: [
      for (final row in (setup['locations'] as List? ?? const []))
        {'id': (row as Map)['id'], 'name': row['name'], 'active': row['active']},
    ],
    added: [
      for (final row in (setup['vehicle_added'] as List? ?? const []))
        {
          'make': (row as Map)['make'],
          'type': row['type'],
          'models': [...(row['models'] as List)],
        },
    ],
    hiddenMakes: [...(setup['vehicle_hidden_makes'] as List? ?? const [])],
    hiddenModels: [
      for (final row in (setup['vehicle_hidden_models'] as List? ?? const []))
        {...(row as Map<String, dynamic>)},
    ],
  );

  bool automobile;
  List<Map<String, dynamic>> locations;
  List<Map<String, dynamic>> added;
  List<dynamic> hiddenMakes;
  List<Map<String, dynamic>> hiddenModels;

  SetupDraft copy() => SetupDraft(
    automobile: automobile,
    locations: [for (final row in locations) {...row}],
    added: [
      for (final row in added) {...row, 'models': [...row['models']]},
    ],
    hiddenMakes: [...hiddenMakes],
    hiddenModels: [for (final row in hiddenModels) {...row}],
  );

  Json payload(Object? version) => {
    'version': version,
    'automobile_enabled': automobile,
    'locations': [
      for (final row in locations)
        {
          if (row['id'] != null) 'id': row['id'],
          'name': _tidy(row['name']),
          'active': row['active'],
        },
    ],
    'vehicle_added': added,
    'vehicle_hidden_makes': hiddenMakes,
    'vehicle_hidden_models': hiddenModels,
  };
}

/// One make in the effective catalogue (built-in plus the owner's edits).
class CatalogEntry {
  CatalogEntry(this.make, this.type, this.custom, this.hidden, this.models);
  final String make;
  final String type;
  final bool custom;
  final bool hidden;
  final List<({String name, bool custom})> models;
}

List<CatalogEntry> effectiveCatalog(List<dynamic> defaults, SetupDraft draft) {
  String lower(Object? v) => _tidy(v).toLowerCase();
  final hiddenMakes = {for (final m in draft.hiddenMakes) lower(m)};
  final hiddenModels = {
    for (final r in draft.hiddenModels) '${lower(r['make'])}|${lower(r['model'])}',
  };
  final added = {for (final r in draft.added) lower(r['make']): r};
  final result = <CatalogEntry>[];
  final used = <String>{};
  int byName(({String name, bool custom}) a, ({String name, bool custom}) b) =>
      a.name.toLowerCase().compareTo(b.name.toLowerCase());
  for (final entry in defaults.cast<Map<String, dynamic>>()) {
    final key = lower(entry['make']);
    used.add(key);
    final models = [
      for (final name in (entry['models'] as List))
        if (!hiddenModels.contains('$key|${lower(name)}'))
          (name: '$name', custom: false),
    ];
    final seen = {for (final m in models) lower(m.name)};
    for (final name in (added[key]?['models'] as List? ?? const [])) {
      if (!seen.contains(lower(name))) models.add((name: '$name', custom: true));
    }
    models.sort(byName);
    result.add(CatalogEntry('${entry['make']}', '${entry['type']}', false, hiddenMakes.contains(key), models));
  }
  for (final item in added.entries) {
    if (used.contains(item.key)) continue;
    final models = [
      for (final name in (item.value['models'] as List? ?? const []))
        (name: '$name', custom: true),
    ]..sort(byName);
    result.add(CatalogEntry('${item.value['make']}', '${item.value['type'] ?? 'car'}', true, false, models));
  }
  return result;
}

/// Edit helpers return an error message, or null after changing [draft].
Map<String, dynamic>? _builtIn(List<dynamic> defaults, String make) {
  for (final e in defaults.cast<Map<String, dynamic>>()) {
    if (_same(e['make'], make)) return e;
  }
  return null;
}

int _addedIndex(SetupDraft d, String make) =>
    d.added.indexWhere((r) => _same(r['make'], make));

String? addMake(List<dynamic> defaults, SetupDraft d, String name, String type) {
  final make = _tidy(name);
  if (make.isEmpty) return 'Enter a make name.';
  if (make.length > 40) return 'Make names can be up to 40 characters.';
  final built = _builtIn(defaults, make);
  if (built != null) {
    if (d.hiddenMakes.any((n) => _same(n, make))) {
      d.hiddenMakes = d.hiddenMakes.where((n) => !_same(n, make)).toList();
      return null;
    }
    return '${built['make']} is already in the list.';
  }
  if (_addedIndex(d, make) >= 0) return '$make is already in the list.';
  d.added = [...d.added, {'make': make, 'type': type, 'models': <dynamic>[]}];
  return null;
}

String? addModel(List<dynamic> defaults, SetupDraft d, String make, String name) {
  final model = _tidy(name);
  if (model.isEmpty) return 'Enter a model name.';
  if (model.length > 60) return 'Model names can be up to 60 characters.';
  final built = _builtIn(defaults, make);
  final hidden = d.hiddenModels.where((r) => _same(r['make'], make) && _same(r['model'], model)).toList();
  if (hidden.isNotEmpty) {
    d.hiddenModels = d.hiddenModels.where((r) => r != hidden.first).toList();
    return null;
  }
  for (final entry in effectiveCatalog(defaults, d)) {
    if (_same(entry.make, make) && entry.models.any((r) => _same(r.name, model))) {
      return '$model is already listed under ${entry.make}.';
    }
  }
  final index = _addedIndex(d, make);
  final added = [...d.added];
  if (index >= 0) {
    added[index] = {...added[index], 'models': [...added[index]['models'], model]};
  } else {
    added.add({'make': built?['make'] ?? _tidy(make), 'type': built?['type'] ?? 'car', 'models': [model]});
  }
  d.added = added;
  return null;
}

void removeModel(List<dynamic> defaults, SetupDraft d, String make, String model) {
  final index = _addedIndex(d, make);
  if (index >= 0 && (d.added[index]['models'] as List).any((n) => _same(n, model))) {
    final added = [...d.added];
    added[index] = {
      ...added[index],
      'models': (added[index]['models'] as List).where((n) => !_same(n, model)).toList(),
    };
    d.added = added;
    return;
  }
  final built = _builtIn(defaults, make);
  if (built == null) return;
  d.hiddenModels = [...d.hiddenModels, {'make': built['make'], 'model': _tidy(model)}];
}

void removeMake(List<dynamic> defaults, SetupDraft d, String make) {
  final built = _builtIn(defaults, make);
  if (built == null) {
    d.added = d.added.where((r) => !_same(r['make'], make)).toList();
  } else {
    d.hiddenMakes = [...d.hiddenMakes.where((n) => !_same(n, make)), built['make']];
  }
}

void restoreMake(SetupDraft d, String make) =>
    d.hiddenMakes = d.hiddenMakes.where((n) => !_same(n, make)).toList();

({List<String>? names, String? error}) rangeNames(String prefix, String from, String to) {
  final start = int.tryParse(from.trim());
  final end = int.tryParse(to.trim());
  final label = _tidy(prefix);
  if (label.isEmpty) return (names: null, error: 'Enter a name such as Rack.');
  if (start == null || end == null || start < 0 || end < start) {
    return (names: null, error: 'Enter a start number that is not above the end number.');
  }
  if (end - start >= 200) return (names: null, error: 'Add at most 200 locations at a time.');
  return (names: [for (var i = start; i <= end; i++) '$label $i'], error: null);
}

String? addLocations(SetupDraft d, List<String> names) {
  final known = {for (final r in d.locations) _tidy(r['name']).toLowerCase()};
  final fresh = <Map<String, dynamic>>[];
  for (final name in names.map(_tidy).where((n) => n.isNotEmpty)) {
    if (name.length > 40) return 'Location names can be up to 40 characters.';
    if (known.add(name.toLowerCase())) fresh.add({'id': null, 'name': name, 'active': true});
  }
  if (fresh.isEmpty) return 'Those locations are already in the list.';
  if (d.locations.length + fresh.length > 300) return 'A company can have at most 300 locations.';
  d.locations = [...d.locations, ...fresh];
  return null;
}

/// The whole web "Stock & modules" editor with one Save changes bar.
class InventorySetupEditor extends StatefulWidget {
  const InventorySetupEditor({
    required this.workspace,
    required this.setup,
    required this.onReload,
    this.anchors = const {},
    super.key,
  });

  final WorkspaceContext workspace;
  final Json setup;
  final Future<void> Function() onReload;

  /// Anchor keys for 'locations', 'automobile' and 'vehicles'.
  final Map<String, GlobalKey> anchors;

  @override
  State<InventorySetupEditor> createState() => _InventorySetupEditorState();
}

class _InventorySetupEditorState extends State<InventorySetupEditor> {
  late Json _setup = widget.setup;
  late SetupDraft _draft = SetupDraft.from(_setup);
  final _name = TextEditingController();
  final _prefix = TextEditingController(text: 'Rack');
  final _from = TextEditingController(text: '1');
  final _to = TextEditingController(text: '10');
  final _query = TextEditingController();
  final _make = TextEditingController();
  final _models = <String, TextEditingController>{};
  final _locationNames = <int, TextEditingController>{};
  String _type = 'all';
  String _makeType = 'car';
  String _locMessage = '';
  String _vehMessage = '';
  String _error = '';
  String _saved = '';
  bool _busy = false;

  bool get _canEdit => widget.workspace.company.role == 'owner';
  List<dynamic> get _defaults => _setup['default_catalog'] as List? ?? const [];
  Map<String, dynamic> get _types => _setup['vehicle_types'] is Map<String, dynamic>
      ? _setup['vehicle_types'] as Map<String, dynamic>
      : const {};
  bool get _changed =>
      jsonEncode(_draft.payload(0)) != jsonEncode(SetupDraft.from(_setup).payload(0));

  @override
  void dispose() {
    for (final c in [_name, _prefix, _from, _to, _query, _make, ..._models.values, ..._locationNames.values]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (_busy || !_canEdit) return;
    setState(() {
      _busy = true;
      _error = '';
      _saved = '';
    });
    try {
      final result = booksObject(
        await widget.workspace.api.put(
          '${widget.workspace.path}/inventory-setup',
          body: _draft.payload(_setup['version']),
        ),
      );
      if (!mounted) return;
      setState(() {
        _setup = result;
        _draft = SetupDraft.from(result);
        _locationNames.clear();
        _saved = 'Saved. Items and the point of sale now use these settings.';
      });
      await widget.workspace.refresh();
    } catch (failure) {
      if (!mounted) return;
      final message = settingsFailure(failure);
      setState(() => _error = message);
      if (failure is ApexApiException && failure.status == 409 && !message.contains('used by')) {
        await widget.onReload();
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _discard() => setState(() {
    _draft = SetupDraft.from(_setup);
    _locationNames.clear();
    _error = '';
    _saved = '';
  });

  Widget _notice(String text, {bool error = false}) =>
      text.isEmpty ? const SizedBox.shrink() : Padding(
        padding: const EdgeInsets.only(top: 10),
        child: SettingsNotice(text, error: error),
      );

  Widget _inline(List<Widget> children) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Wrap(
      spacing: 12,
      runSpacing: 10,
      crossAxisAlignment: WrapCrossAlignment.end,
      children: children,
    ),
  );

  Widget _locations() => KeyedSubtree(
    key: widget.anchors['locations'],
    child: SettingsBlock(
      title: 'Item locations',
      icon: Icons.place_outlined,
      note:
          'Name the places you keep stock, such as Rack 1, Shelf B or Counter drawer. Items can then be filed under one or more of them, and shown and searched by location.',
      children: [
        if (_canEdit) ...[
          _inline([
            SizedBox(
              width: 280,
              child: SettingsTextField(
                label: 'New location',
                controller: _name,
                maxLength: 40,
                hint: 'e.g. Rack 1 · Shelf B',
                onSubmitted: (_) => _addOne(),
              ),
            ),
            SettingsButton('Add', icon: Icons.add, onPressed: _addOne),
          ]),
          _inline([
            SizedBox(
              width: 330,
              child: SettingsLabeled(
                label: 'Add a numbered series',
                child: Row(
                  children: [
                    Expanded(flex: 3, child: _small(_prefix, 'Series name', 30)),
                    const SizedBox(width: 8),
                    Expanded(flex: 2, child: _small(_from, 'First number', null)),
                    const SizedBox(width: 8),
                    const Text('to'),
                    const SizedBox(width: 8),
                    Expanded(flex: 2, child: _small(_to, 'Last number', null)),
                  ],
                ),
              ),
            ),
            SettingsButton('Add series', icon: Icons.add, onPressed: _addSeries),
          ]),
        ],
        _notice(_locMessage, error: true),
        if (_draft.locations.isEmpty)
          const Padding(
            padding: EdgeInsets.only(top: 10),
            child: Text('No locations yet. Add the first one above.', style: Apex.note),
          )
        else
          for (var i = 0; i < _draft.locations.length; i++) _locationRow(i),
        const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
            'Archived locations stay on the items that already use them but cannot be chosen for new items. A location that items use can be archived, not removed.',
            style: Apex.note,
          ),
        ),
      ],
    ),
  );

  Widget _small(TextEditingController c, String label, int? max) => Semantics(
    label: label,
    textField: true,
    child: TextField(
      controller: c,
      maxLength: max,
      enabled: !_busy,
      style: const TextStyle(fontSize: 13),
      keyboardType: max == null ? TextInputType.number : null,
      decoration: const InputDecoration(counterText: ''),
    ),
  );

  void _addOne() {
    final error = addLocations(_draft = _draft.copy(), [_name.text]);
    setState(() {
      _locMessage = error ?? '';
      if (error == null) _name.clear();
    });
  }

  void _addSeries() {
    final made = rangeNames(_prefix.text, _from.text, _to.text);
    final draft = _draft.copy();
    final error = made.error ?? addLocations(draft, made.names!);
    setState(() {
      _locMessage = error ?? '';
      if (error == null) _draft = draft;
    });
  }

  Widget _locationRow(int index) {
    final row = _draft.locations[index];
    final active = row['active'] == true;
    final isNew = row['id'] == null;
    final controller = _locationNames.putIfAbsent(
      index,
      () => TextEditingController(text: '${row['name']}'),
    );
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: active ? Colors.white : const Color(0xfff4f5f7),
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Wrap(
        spacing: 10,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SizedBox(
            width: 240,
            child: Semantics(
              label: 'Location ${index + 1} name',
              textField: true,
              child: TextField(
                controller: controller,
                maxLength: 40,
                enabled: _canEdit && !_busy,
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(counterText: ''),
                onChanged: (value) =>
                    setState(() => _draft.locations[index]['name'] = value),
              ),
            ),
          ),
          if (isNew) const ApexBadge('New', Color(0xffe7edf5), Apex.inkSoft),
          if (!isNew && !active)
            const ApexBadge('Archived', Color(0xfff4e1df), Color(0xffa4413d)),
          if (_canEdit) ...[
            OutlinedButton.icon(
              onPressed: () => setState(() => _draft.locations[index]['active'] = !active),
              icon: Icon(active ? Icons.archive_outlined : Icons.unarchive_outlined, size: 15),
              label: Text(active ? 'Archive' : 'Restore'),
            ),
            IconButton(
              tooltip: 'Remove ${row['name']}',
              onPressed: () => setState(() {
                _draft.locations = [
                  for (var i = 0; i < _draft.locations.length; i++)
                    if (i != index) _draft.locations[i],
                ];
                _locationNames.clear();
              }),
              icon: const Icon(Icons.delete_outline, size: 18),
            ),
          ],
        ],
      ),
    );
  }

  Widget _automobile() => KeyedSubtree(
    key: widget.anchors['automobile'],
    child: SettingsBlock(
      title: 'Automobile module',
      icon: Icons.directions_car_outlined,
      note:
          'Turn this on for a parts counter, workshop, dealer, or tyre and battery shop. Items then get vehicle details: the makes and models a part fits, a part number, brand and grade. Turning it off hides those details but keeps what you entered.',
      children: [
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          dense: true,
          value: _draft.automobile,
          title: const Text('Automobile shop — add vehicle details to items'),
          onChanged: !_canEdit || _busy
              ? null
              : (value) => setState(() => _draft.automobile = value ?? false),
        ),
      ],
    ),
  );

  Widget _vehicles() {
    final catalog = effectiveCatalog(_defaults, _draft);
    final needle = _tidy(_query.text).toLowerCase();
    final visible = [
      for (final e in catalog)
        if (!e.hidden &&
            (_type == 'all' || e.type == _type) &&
            (needle.isEmpty ||
                e.make.toLowerCase().contains(needle) ||
                e.models.any((m) => m.name.toLowerCase().contains(needle))))
          e,
    ];
    final hidden = [for (final e in catalog) if (e.hidden) e];
    final total = catalog.where((e) => !e.hidden).fold<int>(0, (s, e) => s + e.models.length);
    String typeLabel(String key) => '${_types[key] ?? key}';
    return KeyedSubtree(
      key: widget.anchors['vehicles'],
      child: SettingsBlock(
        title: 'Vehicle makes and models',
        icon: Icons.directions_car_outlined,
        note:
            'These lists fill the pickers when you describe which vehicles a part fits. They start with ${_defaults.length} makes and common models for cars, two-wheelers, trucks and three-wheelers. Add your own, and hide any you never sell for.',
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 280,
                child: TextField(
                  controller: _query,
                  onChanged: (_) => setState(() {}),
                  style: const TextStyle(fontSize: 13),
                  decoration: const InputDecoration(
                    hintText: 'Search a make or model',
                    prefixIcon: Icon(Icons.search_rounded, size: 17),
                  ),
                ),
              ),
              for (final key in ['all', ..._typeOrder.where(_types.containsKey)])
                ChoiceChip(
                  label: Text(key == 'all' ? 'All' : typeLabel(key)),
                  selected: _type == key,
                  onSelected: (_) => setState(() => _type = key),
                  showCheckmark: false,
                  selectedColor: const Color(0xffe0f2e7),
                  shape: const StadiumBorder(),
                ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Semantics(
              liveRegion: true,
              child: Text(
                '${visible.length} ${visible.length == 1 ? 'make' : 'makes'} shown · $total models in your list',
                style: Apex.note,
              ),
            ),
          ),
          if (_canEdit)
            _inline([
              SizedBox(
                width: 240,
                child: SettingsTextField(
                  label: 'Add a make',
                  controller: _make,
                  maxLength: 40,
                  hint: 'e.g. Local Coachworks',
                ),
              ),
              SizedBox(
                width: 200,
                child: SettingsSelect(
                  label: 'Type',
                  value: _makeType,
                  options: [for (final k in _typeOrder) (k, typeLabel(k))],
                  onChanged: (v) => setState(() => _makeType = v),
                ),
              ),
              SettingsButton('Add make', icon: Icons.add, onPressed: () {
                final draft = _draft.copy();
                final error = addMake(_defaults, draft, _make.text, _makeType);
                setState(() {
                  _vehMessage = error ?? '';
                  if (error == null) {
                    _draft = draft;
                    _make.clear();
                  }
                });
              }),
            ]),
          _notice(_vehMessage, error: true),
          const SizedBox(height: 8),
          for (final entry in visible) _makeTile(entry, needle, visible.length, typeLabel),
          if (visible.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: Text(
                'No makes match. Clear the search or add the make above.',
                style: Apex.note,
              ),
            ),
          if (hidden.isNotEmpty)
            Theme(
              data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: Text(
                  '${hidden.length} hidden make${hidden.length == 1 ? '' : 's'}',
                  style: const TextStyle(fontSize: 13),
                ),
                children: [
                  for (final e in hidden)
                    ListTile(
                      dense: true,
                      title: Text(e.make),
                      trailing: _canEdit
                          ? OutlinedButton.icon(
                              onPressed: () => setState(() => restoreMake(_draft, e.make)),
                              icon: const Icon(Icons.unarchive_outlined, size: 15),
                              label: const Text('Show again'),
                            )
                          : null,
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _makeTile(CatalogEntry entry, String needle, int shown, String Function(String) typeLabel) {
    final controller = _models.putIfAbsent(entry.make, () => TextEditingController());
    final open = needle.isNotEmpty &&
        entry.models.any((m) => m.name.toLowerCase().contains(needle)) &&
        shown < 6;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Material(
        color: Colors.transparent,
        child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          key: PageStorageKey('make-${entry.make}-$open'),
          initiallyExpanded: open,
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          title: Text(entry.make, style: Apex.strong),
          subtitle: Text(
            '${typeLabel(entry.type)} · ${entry.models.length} models${entry.custom ? ' · yours' : ''}',
            style: Apex.small,
          ),
          children: [
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final model in entry.models)
                  InputChip(
                    label: Text(model.name, style: const TextStyle(fontSize: 12)),
                    backgroundColor: model.custom ? const Color(0xffe0f2e7) : const Color(0xfff1f4f8),
                    side: BorderSide.none,
                    shape: const StadiumBorder(),
                    deleteIcon: const Icon(Icons.close, size: 13),
                    deleteButtonTooltipMessage:
                        '${model.custom ? 'Remove' : 'Hide'} ${entry.make} ${model.name}',
                    onDeleted: _canEdit
                        ? () => setState(() => removeModel(_defaults, _draft, entry.make, model.name))
                        : null,
                  ),
                if (entry.models.isEmpty) const Text('No models yet.', style: Apex.note),
              ],
            ),
            if (_canEdit)
              _inline([
                SizedBox(
                  width: 240,
                  child: SettingsTextField(
                    label: 'Add a model to ${entry.make}',
                    controller: controller,
                    maxLength: 60,
                  ),
                ),
                SettingsButton('Add model', icon: Icons.add, onPressed: () {
                  final draft = _draft.copy();
                  final error = addModel(_defaults, draft, entry.make, controller.text);
                  setState(() {
                    _vehMessage = error ?? '';
                    if (error == null) {
                      _draft = draft;
                      controller.clear();
                    }
                  });
                }),
                SettingsButton(
                  entry.custom ? 'Remove make' : 'Hide make',
                  icon: entry.custom ? Icons.delete_outline : Icons.archive_outlined,
                  onPressed: () => setState(() => removeMake(_defaults, _draft, entry.make)),
                ),
              ]),
          ],
        ),
      ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final changed = _changed;
    Widget gap() => const Padding(
      padding: EdgeInsets.symmetric(vertical: 14),
      child: SizedBox.shrink(),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!_canEdit)
          const SettingsNotice(
            'Only the owner can change item locations and business modules. You can see how they are set up.',
          ),
        _locations(),
        gap(),
        _automobile(),
        if (_draft.automobile) ...[gap(), _vehicles()],
        _notice(_error, error: true),
        _notice(_saved),
        if (_canEdit)
          Padding(
            padding: const EdgeInsets.only(top: 18),
            child: Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                FilledButton(
                  onPressed: _busy || !changed ? null : _save,
                  child: Text(_busy ? 'Saving…' : 'Save changes'),
                ),
                OutlinedButton(
                  onPressed: _busy || !changed ? null : _discard,
                  child: const Text('Discard changes'),
                ),
                if (changed)
                  const Text('You have unsaved changes.', style: Apex.note),
              ],
            ),
          ),
      ],
    );
  }
}

/// Small rounded tag, like the web `.status-badge`.
class ApexBadge extends StatelessWidget {
  const ApexBadge(this.text, this.background, this.color, {super.key});
  final String text;
  final Color background;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(10)),
    child: Text(text, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
  );
}
