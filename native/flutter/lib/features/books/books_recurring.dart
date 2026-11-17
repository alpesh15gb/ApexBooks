import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'books_entry_draft.dart';
import 'books_entry_picker.dart';
import 'books_entry_posting.dart';

class _Recurring {
  const _Recurring(this.templates, this.due, this.asOf);
  final List<BooksJson> templates;
  final List<BooksJson> due;
  final String asOf;
}

class BooksRecurring extends StatefulWidget {
  const BooksRecurring({
    required this.posting,
    required this.onBack,
    required this.onGenerated,
    this.showBack = true,
    this.source,
    super.key,
  });

  final BooksPosting posting;
  final VoidCallback onBack;
  final ValueChanged<BooksRecord> onGenerated;

  /// False when Recurring drafts was opened from the menu, where there is no list to go back to.
  final bool showBack;
  final BooksRecord? source;

  @override
  State<BooksRecurring> createState() => _BooksRecurringState();
}

class _BooksRecurringState extends State<BooksRecurring> {
  late Future<_Recurring> _future;
  String? _message;
  final _search = TextEditingController();

  BooksPosting get posting => widget.posting;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_Recurring> _load() async {
    final api = posting.workspace.api;
    final library = booksObject(
      await api.get('${posting.root}/recurring-templates'),
    );
    // The library stays usable when only the due worklist cannot be loaded.
    var worklist = <String, dynamic>{};
    try {
      worklist = booksObject(
        await api.get('${posting.root}/recurring-templates/due'),
      );
    } catch (_) {}
    final asOf = booksText(worklist['business_date'])
        .ifEmpty(booksText(worklist['as_of']))
        .ifEmpty(businessDate());
    return _Recurring(
      booksRows(library['templates']),
      worklist['rows'] is List
          ? booksRows(worklist['rows'])
          : const <BooksJson>[],
      asOf,
    );
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _refresh() => setState(() => _future = _load());

  Future<void> _save(BooksCommand command) async {
    if (!posting.canStart) return;
    final result = await posting.submit(command);
    if (!mounted) return;
    if (result != null && result.kind != 'recurring_template') {
      widget.onGenerated(result);
    } else if (result != null) {
      setState(() {
        _message = '${result.party} saved.';
        _future = _load();
      });
    } else {
      setState(() => _message = posting.message);
    }
  }

  Future<void> _new() async {
    if (!posting.canStart) return;
    final source = widget.source ?? await _source(booksDraftKinds.toList());
    if (!mounted || source == null || !posting.canStart) return;
    final command = await showDialog<BooksCommand>(
      context: context,
      builder: (context) => _ScheduleForm(
        title: 'New recurring draft template',
        source: source,
        chooseOther: null,
      ),
    );
    if (mounted && command != null) await _save(command);
  }

  Future<BooksRecord?> _source(List<String> kinds) => pickBooksRecord(
    context,
    posting.workspace,
    title: 'Choose a reviewed draft',
    kinds: kinds,
    accept: (row) =>
        row.json['posted'] != true &&
        row.json['cancelled'] != true &&
        booksText(row.json['converted_to']).isEmpty &&
        row.data['purchase_order_receiving_started'] != true,
    detail: (row) => '${row.date} · ${booksMoney(row.json['amount'])}',
  );

  Future<void> _edit(BooksJson schedule) async {
    if (!posting.canStart || posting.workspace.api is! ApexWriteApi) return;
    final command = await showDialog<BooksCommand>(
      context: context,
      builder: (context) => _ScheduleForm(
        title: 'Edit recurring template',
        schedule: schedule,
        chooseOther: () => _source([booksText(schedule['draft_kind'])]),
      ),
    );
    if (mounted && command != null) await _save(command);
  }

  Future<void> _generate(BooksJson schedule) async {
    if (!posting.canStart) return;
    final day = booksText(schedule['next_due']);
    if (day.isEmpty ||
        day.compareTo(businessDate()) > 0 ||
        schedule['is_active'] != true) {
      return;
    }
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Create one scheduled draft'),
        content: Text(
          '${booksKindLabel(booksText(schedule['draft_kind']))} for ${booksText(schedule['party_name'])} dated $day. The draft opens for review.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Back'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Create draft'),
          ),
        ],
      ),
    );
    if (mounted && accepted == true) {
      await _save(
        BooksCommand(
          BooksOperation.scheduleOccurrence,
          booksText(schedule['id']),
          {'occurrence_date': day},
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<_Recurring>(
    future: _future,
    builder: (context, snapshot) {
      final canWrite = posting.workspace.company.canWrite;
      final loaded = snapshot.connectionState == ConnectionState.done;
      final rows = snapshot.data?.templates ?? const <BooksJson>[];
      final dueRows = snapshot.data?.due ?? const <BooksJson>[];
      final asOf = snapshot.data?.asOf ?? businessDate();
      final visible = rows
          .where(
            (row) => '${row['name']} ${row['party_name'] ?? ''}'
                .toLowerCase()
                .contains(_search.text.trim().toLowerCase()),
          )
          .toList();
      return ApexPage(
        maxWidth: 1100,
        children: [
          if (widget.showBack)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: posting.busy ? null : widget.onBack,
                icon: const Icon(Icons.arrow_back, size: 18),
                label: const Text('Back to transactions'),
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size(0, 40),
                  foregroundColor: Apex.link,
                ),
              ),
            ),
          const SizedBox(height: 8),
          const Text(
            'PLANNED, NEVER AUTO-POSTED',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: .8,
              color: Apex.greenText,
            ),
          ),
          const SizedBox(height: 6),
          ApexRegisterHeading(
            'Recurring drafts',
            subtitle: 'Prepare repeat quotations, orders and purchase orders on a schedule. Every occurrence needs your review; nothing automatically invoices, moves stock or charges money.',
            actions: [
              OutlinedButton.icon(
                onPressed: posting.busy ? null : _refresh,
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('Refresh'),
              ),
              if (canWrite)
                FilledButton.icon(
                  onPressed: posting.canStart ? _new : null,
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('New template'),
                ),
            ],
          ),
          const SizedBox(height: 18),
          if (widget.source case final source?)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(
                'Source draft ${source.label} · ${source.party}',
                style: Apex.lead,
              ),
            ),
          if (_message case final message?)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Semantics(
                liveRegion: true,
                child: Text(message, style: Apex.strong),
              ),
            ),
          if (posting.busy || !loaded)
            const LinearProgressIndicator(
              semanticsLabel: 'Working on recurring drafts',
            )
          else if (!snapshot.hasData)
            const Text(
              'Could not load recurring schedules.',
              style: TextStyle(color: Apex.red),
            )
          else ...[
            ApexPanel(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ApexPanelHeading(
                    'Due for review',
                    note:
                        'Earliest ungenerated occurrence per active template · through $asOf · India business date (IST)',
                    trailing: Text('${dueRows.length} due', style: Apex.strong),
                  ),
                  const SizedBox(height: 14),
                  if (dueRows.isEmpty)
                    const ApexEmptyState(
                      icon: Icons.calendar_today_outlined,
                      title: 'No drafts due today',
                      note: 'Active schedules will appear here when their next date arrives. Paused schedules never generate drafts.',
                    )
                  else
                    for (final row in dueRows) _dueRow(row),
                ],
              ),
            ),
            const SizedBox(height: 16),
            ApexPanel(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ApexPanelHeading(
                    'Template library',
                    note:
                        '${rows.length} of 100 templates · generated drafts remain in their normal registers',
                  ),
                  const SizedBox(height: 14),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: ApexSearchField(
                      controller: _search,
                      hint: 'Find template or party',
                      onChanged: (_) => setState(() {}),
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (visible.isEmpty)
                    ApexEmptyState(
                      icon: Icons.event_repeat_outlined,
                      title: rows.isEmpty
                          ? 'Start from a reviewed draft'
                          : 'No matching templates',
                      note: rows.isEmpty
                          ? 'Create an estimate, pro forma, sales order or purchase order first, then save its inputs as a repeatable template. Expenses and posted invoices are not automatically repeated.'
                          : null,
                    )
                  else
                    for (final schedule in visible) _schedule(schedule),
                ],
              ),
            ),
          ],
        ],
      );
    },
  );

  Widget _dueRow(BooksJson row) {
    final overdue = int.tryParse(booksText(row['overdue_days'])) ?? 0;
    final canWrite = posting.workspace.company.canWrite;
    final info = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 3,
      children: [
        Text(booksText(row['name']), style: Apex.strong),
        Text(
          '${booksText(row['party_name']).ifEmpty('Party not selected')} · ${booksKindLabel(booksText(row['draft_kind']))}',
          style: Apex.note,
        ),
      ],
    );
    final when = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 3,
      children: [
        Text(booksText(row['next_due']), style: Apex.strong),
        Text(
          overdue > 0 ? '$overdue days overdue' : 'Due today',
          style: Apex.note,
        ),
      ],
    );
    final action = canWrite
        ? FilledButton.icon(
            onPressed: posting.canStart ? () => _generate(row) : null,
            icon: const Icon(Icons.arrow_forward, size: 15),
            iconAlignment: IconAlignment.end,
            label: const Text('Create draft & review'),
          )
        : const Text('Read-only');
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Apex.tint,
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
      child: LayoutBuilder(
        builder: (context, box) => box.maxWidth >= 640
            ? Row(
                spacing: 16,
                children: [
                  Expanded(flex: 3, child: info),
                  Expanded(flex: 2, child: when),
                  action,
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: 10,
                children: [info, when, action],
              ),
      ),
    );
  }

  Widget _schedule(BooksJson schedule) {
    final active = schedule['is_active'] == true;
    final due = booksText(schedule['next_due']);
    final canGenerate =
        active && due.isNotEmpty && due.compareTo(businessDate()) <= 0;
    final generated = booksText(schedule['generated_count']).ifEmpty('0');
    final last = booksText(schedule['last_generated_date']);
    final party = booksText(schedule['party_name']).ifEmpty('No party');
    final interval = booksText(schedule['interval']).ifEmpty('1');
    final monthly = booksText(schedule['frequency']) == 'monthly';
    final end = booksText(schedule['end_date']);
    final write =
        posting.workspace.company.canWrite &&
        posting.workspace.api is ApexWriteApi;
    final info = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 3,
      children: [
        Text(booksText(schedule['name']), style: Apex.strong),
        Text(
          '${booksKindLabel(booksText(schedule['draft_kind']))} · $party',
          style: Apex.note,
        ),
        Text(
          'Every $interval ${monthly ? 'month(s)' : 'week(s)'} · starts ${booksText(schedule['start_date'])}${end.isEmpty ? '' : ' · ends $end'}',
          style: Apex.note,
        ),
      ],
    );
    final status = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      spacing: 4,
      children: [
        ApexStatusBadge(
          active ? 'Active' : 'Paused',
          tone: active ? ApexBadgeTone.posted : ApexBadgeTone.neutral,
        ),
        Text(
          'Next: ${due.isEmpty ? 'Schedule complete' : due}',
          style: Apex.note,
        ),
        Text(
          '$generated generated${last.isEmpty ? '' : ' · last $last'}',
          style: Apex.note,
        ),
      ],
    );
    final actions = Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        if (canGenerate && posting.workspace.company.canWrite)
          FilledButton.tonal(
            onPressed: posting.canStart ? () => _generate(schedule) : null,
            child: const Text('Create due draft'),
          ),
        if (write)
          OutlinedButton(
            onPressed: posting.canStart ? () => _edit(schedule) : null,
            child: const Text('Review / edit'),
          ),
      ],
    );
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Apex.tint,
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
      child: LayoutBuilder(
        builder: (context, box) => box.maxWidth >= 640
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                spacing: 16,
                children: [
                  Expanded(flex: 3, child: info),
                  Expanded(flex: 2, child: status),
                  actions,
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: 10,
                children: [info, status, actions],
              ),
      ),
    );
  }
}

class _ScheduleForm extends StatefulWidget {
  const _ScheduleForm({
    required this.title,
    this.source,
    this.schedule,
    required this.chooseOther,
  });
  final String title;
  final BooksRecord? source;
  final BooksJson? schedule;
  final Future<BooksRecord?> Function()? chooseOther;

  @override
  State<_ScheduleForm> createState() => _ScheduleFormState();
}

class _ScheduleFormState extends State<_ScheduleForm> {
  late String _name;
  late String _start;
  String _end = '';
  String _frequency = 'monthly';
  int _interval = 1;
  late bool _active;
  BooksRecord? _replacement;

  bool get _editing => widget.schedule != null;
  bool get _valid =>
      _name.trim().isNotEmpty &&
      (_editing || _end.isEmpty || _end.compareTo(_start) >= 0);

  @override
  void initState() {
    super.initState();
    _name = booksText(widget.schedule?['name'])
        .ifEmpty(widget.source?.party ?? '');
    _start = businessDate();
    _active = widget.schedule?['is_active'] != false;
  }

  Future<void> _date({required bool start}) async {
    final today = DateTime.parse(businessDate());
    final old = DateTime.tryParse(start ? _start : _end) ?? today;
    final picked = await showDatePicker(
      context: context,
      initialDate: old,
      firstDate: DateTime(1900),
      lastDate: DateTime(today.year + 20, 12, 31),
      currentDate: today,
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (start) {
        _start = booksDate(picked);
      } else {
        _end = booksDate(picked);
      }
    });
  }

  void _finish() {
    final schedule = widget.schedule;
    final command = schedule != null
        ? BooksCommand(
            BooksOperation.scheduleUpdate,
            booksText(schedule['id']),
            {
              'name': _name.trim(),
              'version': schedule['version'],
              'is_active': _active,
              if (_replacement case final source?)
                'source_record_id': source.id,
            },
          )
        : BooksCommand(BooksOperation.scheduleCreate, '', {
            'name': _name.trim(),
            'source_record_id': widget.source!.id,
            'is_active': true,
            'start_date': _start,
            'frequency': _frequency,
            'interval': _interval,
            if (_end.isNotEmpty) 'end_date': _end,
          });
    Navigator.of(context).pop(command);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.title),
    scrollable: true,
    content: SizedBox(
      width: 460,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            initialValue: _name,
            maxLength: 120,
            onChanged: (value) => setState(() => _name = value),
            decoration: const InputDecoration(labelText: 'Template name'),
          ),
          if (_editing) ...[
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _active,
              title: const Text('Active schedule'),
              onChanged: (value) => setState(() => _active = value),
            ),
            if (_replacement case final source?)
              Text('Refresh from ${source.label}'),
            OutlinedButton(
              onPressed: () async {
                final selected = await widget.chooseOther?.call();
                if (mounted && selected != null) {
                  setState(() => _replacement = selected);
                }
              },
              child: const Text(
                'Refresh future inputs from a different reviewed draft (optional)',
              ),
            ),
          ] else ...[
            const SizedBox(height: 8),
            Text('Source ${widget.source!.label} · ${widget.source!.party}'),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              initialValue: _frequency,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Repeat'),
              items: const [
                DropdownMenuItem(value: 'weekly', child: Text('Weekly')),
                DropdownMenuItem(value: 'monthly', child: Text('Monthly')),
              ],
              onChanged: (value) =>
                  setState(() => _frequency = value ?? 'monthly'),
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<int>(
              initialValue: _interval,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Every'),
              items: [
                for (var interval = 1; interval <= 12; interval++)
                  DropdownMenuItem(
                    value: interval,
                    child: Text(
                      '$interval ${_frequency == 'weekly' ? 'week' : 'month'}${interval == 1 ? '' : 's'}',
                    ),
                  ),
              ],
              onChanged: (value) => setState(() => _interval = value ?? 1),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => _date(start: true),
              child: Text('First occurrence $_start'),
            ),
            OutlinedButton(
              onPressed: () => _date(start: false),
              child: Text(_end.isEmpty ? 'End date (optional)' : 'End $_end'),
            ),
            if (_end.isNotEmpty)
              TextButton(
                onPressed: () => setState(() => _end = ''),
                child: const Text('Clear end date'),
              ),
            if (_end.isNotEmpty && _end.compareTo(_start) < 0)
              const Text('End date must follow the start date.'),
          ],
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Back'),
      ),
      FilledButton(
        onPressed: _valid ? _finish : null,
        child: Text(_editing ? 'Save changes' : 'Save template'),
      ),
    ],
  );
}
