import 'dart:convert';
import 'dart:math';

import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../inventory/inventory_models.dart';
import '../inventory/inventory_posting.dart';
import 'master_csv.dart';

class MasterImportPage extends StatefulWidget {
  const MasterImportPage({
    required this.workspace,
    required this.initialKind,
    super.key,
  });
  final WorkspaceContext workspace;
  final String initialKind;

  @override
  State<MasterImportPage> createState() => _MasterImportPageState();
}

class _MasterImportPageState extends State<MasterImportPage> {
  static const _operation = 'master-import';
  final _csv = TextEditingController();
  late String _kind = widget.initialKind;
  Json? _command;
  Json? _preview;
  Json? _receipt;
  MasterCsv? _parsed;
  String? _filename;
  String? _error;
  bool _loading = true;
  bool _busy = false;
  bool _recoveryFault = false;

  WorkspaceContext get _workspace => widget.workspace;
  String get _root => '${_workspace.path}/masters';
  bool get _supported => _workspace.features.contains('master_import_receipts');
  bool get _changeable =>
      !_busy &&
      !_loading &&
      _command == null &&
      !_recoveryFault &&
      _workspace.company.canWrite;

  @override
  void initState() {
    super.initState();
    _loadRecovery();
  }

  @override
  void dispose() {
    _csv.dispose();
    super.dispose();
  }

  Future<void> _loadRecovery() async {
    try {
      final saved = await _workspace.pending.load(_operation);
      if (saved != null &&
          (saved['key'] is! String ||
              saved['body'] is! Map ||
              !const {
                'item',
                'party',
              }.contains(inventoryObject(saved['body'])['kind']))) {
        throw const FormatException('Invalid master import recovery.');
      }
      if (!mounted) return;
      setState(() {
        _command = saved;
        if (saved != null) {
          _kind = inventoryObject(saved['body'])['kind'] as String;
        }
        _loading = false;
        _recoveryFault = false;
        _error = null;
      });
    } catch (_) {
      if (mounted) {
        setState(() {
          _loading = false;
          _recoveryFault = true;
          _error = 'The previous import could not be loaded from this device.';
        });
      }
    }
  }

  void _changed() {
    _preview = null;
    _parsed = null;
    _receipt = null;
    _error = null;
  }

  Future<void> _pick() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final selected = await pickApexFile(['csv'], 1024 * 1024);
      if (!mounted || selected == null) return;
      final parsed = utf8.decode(selected.bytes);
      setState(() {
        _changed();
        _csv.text = parsed;
        _filename = selected.name;
      });
    } on FormatException {
      if (mounted) {
        setState(() => _error = 'Choose a valid UTF-8 CSV below 1 MB.');
      }
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _prepare() async {
    if (!_changeable) return;
    setState(() {
      _busy = true;
      _changed();
    });
    try {
      final parsed = masterCsv(_csv.text, _kind);
      final result = inventoryObject(
        await _workspace.api.post(
          '$_root/import',
          body: {'kind': _kind, 'dry_run': true, 'rows': parsed.rows},
        ),
      );
      if (result['dry_run'] != true ||
          result['ready'] is! int ||
          result['errors'] is! List) {
        throw const FormatException(
          'The server did not return an import preview.',
        );
      }
      if (mounted) {
        setState(() {
          _parsed = parsed;
          _preview = result;
        });
      }
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  bool get _canCommit =>
      _changeable &&
      _supported &&
      _parsed != null &&
      (_preview?['ready'] as int? ?? 0) > 0 &&
      inventoryRows(_preview?['errors']).isEmpty;

  Future<void> _commit({bool retry = false}) async {
    if (_busy || !_workspace.company.canWrite || (!retry && !_canCommit)) {
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      var command = _command;
      if (!retry) {
        final rng = Random.secure();
        final key = List.generate(
          20,
          (_) => rng.nextInt(256).toRadixString(16).padLeft(2, '0'),
        ).join();
        command = {
          'key': 'flutter-master-import-$key',
          'body': {'kind': _kind, 'dry_run': false, 'rows': _parsed!.rows},
        };
        await _workspace.pending.save(_operation, command);
        _command = command;
      }
      if (command == null) return;
      final key = command['key'] as String;
      final result = inventoryObject(
        await _workspace.api.post(
          '$_root/import',
          body: inventoryObject(command['body']),
          idempotencyKey: key,
        ),
      );
      await _recordReceipt(result, key);
    } on ApexApiException catch (failure) {
      if (!retry && !failure.uncertain && _command != null) {
        try {
          await _workspace.pending.clear(_operation);
          _command = null;
        } catch (_) {
          if (mounted) {
            setState(
              () =>
                  _error = 'The previous import remains saved on this device.',
            );
          }
          return;
        }
      }
      if (mounted) setState(() => _error = inventoryError(failure));
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _lookup() async {
    final key = _command?['key'] as String?;
    if (key == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final result = inventoryObject(
        await _workspace.api.get(
          '$_root/import-receipts/${Uri.encodeComponent(key)}',
        ),
      );
      await _recordReceipt(result, key);
    } on ApexApiException catch (failure) {
      if (mounted) {
        setState(
          () => _error = failure.status == 404
              ? 'No receipt yet. Check again or retry the original import.'
              : failure.message,
        );
      }
    } catch (failure) {
      if (mounted) setState(() => _error = inventoryError(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _recordReceipt(Json result, String key) async {
    if (result['operation_key'] != key ||
        result['created'] is! int ||
        result['record_ids'] is! List) {
      throw const FormatException(
        'The server did not confirm the original import receipt.',
      );
    }
    await _workspace.pending.clear(_operation);
    if (mounted) {
      setState(() {
        _command = null;
        _changed();
        _receipt = result;
        _filename = null;
        _csv.clear();
      });
    }
    await _workspace.refresh();
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy,
    child: Scaffold(
      appBar: AppBar(title: const Text('Import contacts or items')),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 800),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_loading || _busy) const LinearProgressIndicator(),
                if (_error != null)
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                if (_recoveryFault)
                  TextButton(
                    onPressed: _busy ? null : _loadRecovery,
                    child: const Text('Try loading again'),
                  ),
                if (_receipt != null)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.check_circle_outline),
                      title: Text(
                        '${_receipt!['created']} ${_receipt!['created'] == 1 ? 'record' : 'records'} imported',
                      ),
                      subtitle: Text(
                        '${_receipt!['duplicates']} existing or repeated names skipped',
                      ),
                    ),
                  ),
                if (_command != null) ...[
                  const Text('The original import is awaiting confirmation.'),
                  Wrap(
                    spacing: 8,
                    children: [
                      OutlinedButton(
                        onPressed: _busy || !_workspace.company.canWrite
                            ? null
                            : _lookup,
                        child: const Text('Check receipt'),
                      ),
                      FilledButton(
                        onPressed: _busy || !_workspace.company.canWrite
                            ? null
                            : () => _commit(retry: true),
                        child: const Text('Retry original import'),
                      ),
                    ],
                  ),
                ] else ...[
                  Wrap(
                    spacing: 8,
                    children: [
                      ChoiceChip(
                        label: const Text('Contacts'),
                        selected: _kind == 'party',
                        onSelected: _changeable
                            ? (_) => setState(() {
                                _kind = 'party';
                                _changed();
                              })
                            : null,
                      ),
                      ChoiceChip(
                        label: const Text('Items'),
                        selected: _kind == 'item',
                        onSelected: _changeable
                            ? (_) => setState(() {
                                _kind = 'item';
                                _changed();
                              })
                            : null,
                      ),
                    ],
                  ),
                  Text(
                    _kind == 'party'
                        ? 'Use a Name column. Optional columns include Type, Phone, Email, GSTIN and Address.'
                        : 'Use a Name column. Optional columns include Unit, Barcode, Sale rate, Purchase rate, GST rate and Stock tracked.',
                  ),
                  const Text(
                    'Use UTF-8 CSV with up to 500 rows. Existing names are skipped.',
                  ),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      onPressed: _changeable ? _pick : null,
                      label: const Text('Choose CSV file'),
                      icon: const Icon(Icons.attach_file),
                    ),
                  ),
                  if (_filename != null) Text(_filename!),
                  TextField(
                    controller: _csv,
                    enabled: _changeable,
                    maxLength: 1024 * 1024,
                    minLines: 4,
                    maxLines: 8,
                    keyboardType: TextInputType.multiline,
                    decoration: const InputDecoration(
                      labelText: 'CSV contents',
                      counterText: '',
                    ),
                    onChanged: (_) => setState(() {
                      _changed();
                      _filename = null;
                    }),
                  ),
                  if (_preview != null) ...[
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text('${_preview!['ready']} ready to import'),
                      subtitle: Text(
                        '${_preview!['duplicates']} existing or repeated names skipped',
                      ),
                    ),
                    for (final error in inventoryRows(_preview!['errors']))
                      Text(
                        'CSV row ${_csvLine(error['row'])}: ${error['message']}',
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                  ],
                  if (!_supported)
                    const Text(
                      'This server can preview the file. Update it to post imports with a recoverable receipt.',
                    ),
                  Wrap(
                    spacing: 8,
                    children: [
                      OutlinedButton(
                        onPressed: _changeable ? _prepare : null,
                        child: const Text('Preview import'),
                      ),
                      FilledButton(
                        onPressed: _canCommit ? _commit : null,
                        child: const Text('Import records'),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    ),
  );

  Object? _csvLine(Object? row) {
    final lines = _parsed?.lines;
    final index = row is int ? row - 2 : -1;
    return lines != null && index >= 0 && index < lines.length
        ? lines[index]
        : row;
  }
}
