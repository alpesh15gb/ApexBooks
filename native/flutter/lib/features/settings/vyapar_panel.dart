import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../books/books_data.dart';
import 'settings_blocks.dart';

enum VyaparScope {
  posting('vyapar-posting', 'Full transaction posting'),
  archive('vyapar', 'Masters and source archive');

  const VyaparScope(this.endpoint, this.label);
  final String endpoint;
  final String label;
}

class VyaparRequest {
  const VyaparRequest(this.scope, this.digest, this.name);

  factory VyaparRequest.fromJson(Json json) {
    final scope = VyaparScope.values.byName(booksText(json['scope']));
    final digest = booksText(json['digest']);
    final name = booksText(json['file']);
    if (!_digest(digest) || !name.toLowerCase().endsWith('.vyb')) {
      throw const FormatException(
        'The saved Vyapar import could not be opened.',
      );
    }
    return VyaparRequest(scope, digest, name);
  }

  static const maximumBytes = 3000000;
  static const storageKey = 'vyapar-import';

  final VyaparScope scope;
  final String digest;
  final String name;

  static bool _digest(String value) =>
      RegExp(r'^[a-f0-9]{64}$').hasMatch(value);

  static VyaparRequest fromFile(VyaparScope scope, ApexPickedFile file) {
    if (!file.name.toLowerCase().endsWith('.vyb') ||
        file.bytes.isEmpty ||
        file.bytes.length > maximumBytes) {
      throw const FormatException('Choose a nonempty .vyb backup up to 3 MB.');
    }
    return VyaparRequest(
      scope,
      sha256.convert(file.bytes).toString(),
      file.name,
    );
  }

  Json toJson() => {'scope': scope.name, 'digest': digest, 'file': name};

  Json payload(ApexPickedFile file, {required bool commit}) {
    final actual = VyaparRequest.fromFile(scope, file);
    if (actual.digest != digest) {
      throw const FormatException(
        'Choose the exact backup used for the original import.',
      );
    }
    return {
      'backup_base64': base64Encode(file.bytes),
      'digest': commit ? digest : '',
    };
  }

  bool matchesReport(Json report) => report['digest'] == digest;
}

class VyaparPanel extends StatefulWidget {
  const VyaparPanel({
    required this.workspace,
    this.pickFile = pickApexFile,
    this.saveFile = saveApexFile,
    super.key,
  });

  final WorkspaceContext workspace;
  final Future<ApexPickedFile?> Function(List<String>, int) pickFile;
  final Future<bool> Function(String, Uint8List, String) saveFile;

  @override
  State<VyaparPanel> createState() => _VyaparPanelState();
}

class _VyaparPanelState extends State<VyaparPanel> {
  VyaparScope _scope = VyaparScope.posting;
  VyaparRequest? _pending;
  ApexPickedFile? _file;
  Json? _report;
  String? _message;
  bool _busy = false;
  bool _loaded = false;
  bool _accepted = false;
  int _generation = 0;

  bool get _owner => widget.workspace.company.role == 'owner';
  bool get _imported =>
      _report?['imported'] == true || _report?['already_imported'] == true;
  List<dynamic> get _errors =>
      _report?['errors'] is List ? _report!['errors'] as List : const [];
  bool get _canCommit =>
      _owner &&
      _loaded &&
      !_busy &&
      _pending == null &&
      _accepted &&
      _report != null &&
      _file != null &&
      !_imported &&
      _errors.isEmpty &&
      (_scope == VyaparScope.archive || _report?['ready'] == true);
  bool _current(int generation) =>
      mounted && _owner && _generation == generation;

  @override
  void initState() {
    super.initState();
    if (_owner) _recover();
  }

  @override
  void didUpdateWidget(covariant VyaparPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workspace.api != widget.workspace.api ||
        oldWidget.workspace.company.id != widget.workspace.company.id ||
        oldWidget.workspace.company.role != widget.workspace.company.role) {
      _generation++;
      _pending = null;
      _file = null;
      _report = null;
      _message = null;
      _loaded = false;
      _busy = false;
      _accepted = false;
      _scope = VyaparScope.posting;
      if (_owner) _recover();
    }
  }

  Future<void> _recover() async {
    if (!_owner || _busy) return;
    final generation = _generation;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final data = await widget.workspace.pending.load(
        VyaparRequest.storageKey,
      );
      final pending = data == null ? null : VyaparRequest.fromJson(data);
      if (!_current(generation)) return;
      setState(() {
        _pending = pending;
        if (pending != null) _scope = pending.scope;
        _loaded = true;
      });
    } catch (error) {
      if (_current(generation)) {
        setState(() {
          _loaded = false;
          _message = _error(error, 'Could not check the saved import.');
        });
      }
    } finally {
      if (_current(generation)) setState(() => _busy = false);
    }
  }

  Future<void> _preview() async {
    if (!_owner || !_loaded || _pending != null || _busy) return;
    final generation = _generation;
    final workspace = widget.workspace;
    setState(() {
      _busy = true;
      _message = null;
      _accepted = false;
    });
    try {
      final picked = await widget.pickFile(const [
        'vyb',
      ], VyaparRequest.maximumBytes);
      if (picked == null || !_current(generation)) return;
      setState(() {
        _file = null;
        _report = null;
      });
      final request = VyaparRequest.fromFile(_scope, picked);
      final report = booksObject(
        await workspace.api.post(
          '${workspace.path}/imports/${request.scope.endpoint}/preview',
          body: request.payload(picked, commit: false),
        ),
      );
      if (!request.matchesReport(report)) {
        throw const FormatException(
          'The preview did not match the selected backup.',
        );
      }
      if (_current(generation)) {
        setState(() {
          _file = picked;
          _report = report;
        });
      }
    } catch (error) {
      if (_current(generation)) {
        setState(
          () => _message = _error(error, 'Could not review the Vyapar backup.'),
        );
      }
    } finally {
      if (_current(generation)) setState(() => _busy = false);
    }
  }

  Future<void> _commit({required bool retry}) async {
    if (!_owner ||
        !_loaded ||
        _busy ||
        (retry ? _pending == null : !_canCommit)) {
      return;
    }
    final generation = _generation;
    final workspace = widget.workspace;
    var enteredApi = false;
    final saved = _pending;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final file =
          _file ??
          await widget.pickFile(const ['vyb'], VyaparRequest.maximumBytes);
      if (file == null || !_current(generation)) return;
      final request = saved ?? VyaparRequest.fromFile(_scope, file);
      final body = request.payload(file, commit: true);
      if (!retry && !request.matchesReport(_report!)) {
        throw const FormatException('Review this exact backup first.');
      }
      if (!retry) {
        try {
          await workspace.pending.save(
            VyaparRequest.storageKey,
            request.toJson(),
          );
        } catch (_) {
          if (_current(generation)) setState(() => _loaded = false);
          throw const FormatException(
            'Could not save the recovery reference. Check saved imports before continuing.',
          );
        }
      }
      if (!_current(generation)) return;
      setState(() {
        _pending = request;
        _file = file;
      });
      enteredApi = true;
      final report = booksObject(
        await workspace.api.post(
          '${workspace.path}/imports/${request.scope.endpoint}/commit',
          body: body,
        ),
      );
      if (!request.matchesReport(report) ||
          (report['imported'] != true && report['already_imported'] != true)) {
        throw const FormatException(
          'The migration outcome could not be verified. Retry the original backup.',
        );
      }
      await workspace.pending.clear(VyaparRequest.storageKey);
      if (!_current(generation)) return;
      setState(() {
        _pending = null;
        _file = null;
        _report = report;
        _accepted = false;
      });
      try {
        await workspace.refresh();
      } catch (_) {
        if (_current(generation)) {
          setState(
            () => _message = 'Import confirmed. Refresh the company to see the imported records.',
          );
        }
      }
    } catch (error) {
      if (enteredApi &&
          !retry &&
          error is ApexApiException &&
          error.status != null &&
          !error.uncertain) {
        try {
          await workspace.pending.clear(VyaparRequest.storageKey);
          if (_current(generation)) setState(() => _pending = null);
        } catch (_) {}
      }
      if (_current(generation)) {
        setState(
          () => _message = _error(
            error,
            'Could not confirm the original migration.',
          ),
        );
      }
    } finally {
      if (_current(generation)) setState(() => _busy = false);
    }
  }

  Future<void> _saved({
    bool reconciliation = false,
    bool export = false,
  }) async {
    if (!_owner || _busy) return;
    final generation = _generation;
    final workspace = widget.workspace;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final path =
          '${workspace.path}/imports/${reconciliation ? 'vyapar-posting/reconciliation' : 'vyapar/archive.json'}';
      if (export) {
        final bytes = await workspace.api.download(path);
        if (!_current(generation)) return;
        if (await widget.saveFile(
              reconciliation
                  ? 'vyapar-posting-reconciliation.json'
                  : 'vyapar-source-archive.json',
              bytes,
              'application/json',
            ) &&
            _current(generation)) {
          setState(() => _message = 'Export saved.');
        }
      } else {
        final report = booksObject(await workspace.api.get(path));
        if (_current(generation)) {
          setState(() {
            _scope = VyaparScope.posting;
            _report = report;
            _file = null;
            _accepted = false;
          });
        }
      }
    } catch (error) {
      if (_current(generation)) {
        setState(
          () => _message = _error(error, 'Could not open migration records.'),
        );
      }
    } finally {
      if (_current(generation)) setState(() => _busy = false);
    }
  }

  String _error(Object error, String fallback) => error is ApexApiException
      ? error.message
      : error is FormatException
      ? error.message
      : fallback;

  @override
  Widget build(BuildContext context) {
    if (!_owner) return const SizedBox.shrink();
    return SettingsBlock(
      title: 'Import Vyapar backup',
      children: [
        Text('Destination: ${widget.workspace.company.name}'),
        const Text(
          'Use a new company for migration. Review the source totals and any blocked records before importing.',
        ),
        const SizedBox(height: 12),
        if (_busy)
          const LinearProgressIndicator(
            semanticsLabel: 'Working on Vyapar backup',
          ),
        if (_message case final message?)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: SettingsNotice(message),
          ),
        if (!_loaded && !_busy)
          OutlinedButton(
            onPressed: _recover,
            child: const Text('Check saved imports'),
          )
        else if (_pending case final pending?) ...[
          Text('Import awaiting confirmation · ${pending.scope.label}'),
          Text(pending.name),
          const Text('Confirm the original backup to recover the result.'),
          OutlinedButton(
            onPressed: _busy ? null : () => _commit(retry: true),
            child: Text(
              _file == null
                  ? 'Choose original backup and retry'
                  : 'Retry original import',
            ),
          ),
        ] else ...[
          DropdownButtonFormField<VyaparScope>(
            key: ValueKey(_scope),
            initialValue: _scope,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Import scope'),
            items: [
              for (final scope in VyaparScope.values)
                DropdownMenuItem(value: scope, child: Text(scope.label)),
            ],
            onChanged: _busy
                ? null
                : (scope) {
                    if (scope != null) {
                      setState(() {
                        _scope = scope;
                        _file = null;
                        _report = null;
                        _accepted = false;
                        _message = null;
                      });
                    }
                  },
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _busy || !_loaded ? null : _preview,
            icon: const Icon(Icons.upload_file_outlined),
            label: Text(_file?.name ?? 'Choose .vyb backup'),
          ),
          if (_report case final report?) _previewPanel(context, report),
        ],
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            OutlinedButton(
              onPressed: _busy || _pending != null
                  ? null
                  : () => _saved(reconciliation: true),
              child: const Text('View reconciliation'),
            ),
            OutlinedButton(
              onPressed: _busy ? null : () => _saved(export: true),
              child: const Text('Download source archive'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _saved(reconciliation: true, export: true),
              child: const Text('Download reconciliation'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _previewPanel(BuildContext context, Json report) {
    final theme = Theme.of(context);
    final title = booksText(report['company_name']);
    final totals = report['totals'] is Json
        ? report['totals'] as Json
        : const <String, dynamic>{};
    final masters = report['ready'] is Json
        ? report['ready'] as Json
        : const <String, dynamic>{};
    final checks = report['reconciliation'] is List
        ? booksRows(report['reconciliation'])
        : const <Json>[];
    final taxes = report['tax_rounding_by_party'] is List
        ? booksRows(report['tax_rounding_by_party'])
        : const <Json>[];
    final warnings = report['warnings'] is List
        ? report['warnings'] as List
        : const [];
    final counts = report['document_counts'] is Json
        ? report['document_counts'] as Json
        : const <String, dynamic>{};
    return Material(
      color: Apex.tint,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        side: const BorderSide(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusPanel),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title.isEmpty ? 'Backup review' : title,
              style: theme.textTheme.titleMedium,
            ),
            if (_scope == VyaparScope.posting) ...[
              if (report['source_transaction_count'] != null)
                Text(
                  '${booksText(report['source_transaction_count'])} source transactions',
                ),
              for (final entry in counts.entries)
                Text('${booksKindLabel(entry.key)}  ${booksText(entry.value)}'),
              for (final (key, label) in [
                ('sales', 'Source sales'),
                ('purchases', 'Purchase bills'),
                ('receivable', 'Receivables'),
              ])
                if (totals[key] != null)
                  Text('$label  ${booksMoney(totals[key])}'),
              for (final (key, label) in [
                ('payment_count', 'Payment entries'),
                ('supplier_advance_count', 'Supplier advances'),
                ('stock_items', 'Stock items'),
                ('negative_stock_items', 'Source negative stock'),
              ])
                if (report[key] != null)
                  Text('$label  ${booksText(report[key])}'),
            ] else if (masters.isNotEmpty)
              Text(
                '${booksText(masters['parties'])} parties and ${booksText(masters['items'])} items ready',
              ),
            for (final warning in warnings)
              if (booksText(warning).isNotEmpty) Text(booksText(warning)),
            if (_errors.isNotEmpty)
              ExpansionTile(
                initiallyExpanded: true,
                tilePadding: EdgeInsets.zero,
                title: Text('Import blocked · ${_errors.length} source checks'),
                children: [
                  for (final error in _errors)
                    ListTile(
                      title: Text(
                        error is Json
                            ? [
                                booksText(error['name']),
                                booksText(error['error']),
                              ].where((part) => part.isNotEmpty).join(' · ')
                            : booksText(error),
                      ),
                    ),
                ],
              ),
            if (taxes.isNotEmpty)
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text('GST rounding differences'),
                children: [
                  for (final row in taxes)
                    ListTile(
                      title: Text(booksText(row['party'])),
                      subtitle: Text(
                        'Source ${booksText(row['source_report_tax'])} · Posted ${booksText(row['posted_tax'])} · Difference ${booksText(row['difference'])}',
                      ),
                    ),
                ],
              ),
            if (checks.isNotEmpty)
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: Text(
                  '${checks.where((row) => row['passed'] == true).length} of ${checks.length} reconciliation checks matched',
                ),
                children: [
                  for (final row in checks)
                    ListTile(
                      title: Text(booksText(row['check'])),
                      subtitle: Text(
                        'Source ${booksText(row['expected'])} · Posted ${booksText(row['actual'])}',
                      ),
                      trailing: Text(
                        row['passed'] == true ? 'Matched' : 'Difference',
                      ),
                    ),
                ],
              ),
            if (_imported)
              Text(
                report['already_imported'] == true
                    ? 'This exact backup is already imported.'
                    : _scope == VyaparScope.posting
                    ? 'Migration posted and reconciled.'
                    : 'Masters and source archive imported.',
              ),
            if (_file != null && !_imported) ...[
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: _accepted,
                title: Text(
                  _scope == VyaparScope.posting
                      ? 'I reviewed the preview and want to post these transactions.'
                      : 'I reviewed the masters and source archive preview.',
                ),
                onChanged: _busy
                    ? null
                    : (value) => setState(() => _accepted = value ?? false),
              ),
              FilledButton(
                onPressed: _canCommit ? () => _commit(retry: false) : null,
                child: Text(
                  _scope == VyaparScope.posting
                      ? 'Post and reconcile migration'
                      : 'Import masters and source archive',
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
