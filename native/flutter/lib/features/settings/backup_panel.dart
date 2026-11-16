import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/portable_backup.dart';
import '../../core/session.dart';
import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../books/books_data.dart';
import 'settings_blocks.dart';

class BackupPanel extends StatefulWidget {
  const BackupPanel({
    required this.workspace,
    required this.session,
    this.restoreAnchor,
    super.key,
  });
  final WorkspaceContext workspace;
  final ApexSession session;

  /// Lets the settings jump link scroll to the restore block.
  final GlobalKey? restoreAnchor;

  @override
  State<BackupPanel> createState() => _BackupPanelState();
}

class _BackupPanelState extends State<BackupPanel> {
  static const _zipLimit = 64 * 1024 * 1024;
  final _name = TextEditingController();
  final _exportPassword = TextEditingController();
  final _restorePassword = TextEditingController();
  ApexPickedFile? _file;
  Uint8List? _validatedBytes;
  Json? _preview;
  Json? _export;
  String? _uploadId;
  String? _exportKey;
  String? _uploadKey;
  bool _busy = false;
  bool _consent = false;
  String? _status;
  double? _progress;

  WorkspaceContext get _workspace => widget.workspace;
  String get _root => _workspace.path;
  bool get _complete => _workspace.features.contains('chunked_backups');
  bool get _encrypted =>
      _file?.name.toLowerCase().endsWith('.apexbackup') == true;
  bool get _exportAllowed => _exportPassword.text.isEmpty
      ? _consent
      : _exportPassword.text.length >= 12;
  bool get _owner => _workspace.company.role == 'owner';

  String _key() {
    final secure = Random.secure();
    return List.generate(
      24,
      (_) => secure.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _status = null;
      _progress = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) {
        setState(
          () => _status = switch (error) {
            ApexApiException() => error.message,
            FormatException() => error.message,
            _ => 'The transfer could not be completed.',
          },
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _progress = null;
        });
      }
    }
  }

  void _notify(String status, {double? progress}) {
    if (mounted) {
      setState(() {
        _status = status;
        _progress = progress;
      });
    }
  }

  Future<bool> _saveBytes(String filename, Uint8List bytes, String mime) async {
    final password = _exportPassword.text;
    if (password.isEmpty) return saveApexFile(filename, bytes, mime);
    final protected = await encryptBackup(bytes, password);
    if (!mounted) return false;
    final base = filename.split('.').first;
    return saveApexFile('$base.apexbackup', protected, 'application/json');
  }

  Future<void> _saveExport({required bool full}) => _run(() async {
    final api = _workspace.api;
    final day = businessDate();
    if (!full) {
      final Uint8List bytes;
      try {
        bytes = await api.download('$_root/data-export.json');
      } on ApexApiException catch (error) {
        if (error.message.contains('COMPLETE_BACKUP_REQUIRED')) {
          throw const FormatException(
            'Save a complete ZIP to include this company’s receipts and import evidence.',
          );
        }
        rethrow;
      }
      if (mounted &&
          await _saveBytes('apex-books-$day.json', bytes, 'application/json')) {
        _notify(
          kIsWeb ? 'Company data download started.' : 'Company data saved.',
        );
      }
      return;
    }
    _exportKey ??= _key();
    final initial = _export ??= booksObject(
      await api.post(
        '$_root/backup-exports',
        body: {},
        idempotencyKey: _exportKey,
      ),
    );
    final path = '$_root/backup-exports/${initial['export_id']}';
    final Json manifest;
    try {
      manifest = booksObject(await api.get(path));
    } on ApexApiException catch (error) {
      if (error.status == 410 || error.status == 404) {
        _export = null;
        _exportKey = null;
        throw const FormatException(
          'The previous download expired. Start a new backup.',
        );
      }
      rethrow;
    }
    final size = manifest['byte_count'] as int;
    if (_exportPassword.text.isNotEmpty && size > encryptableBackupMaximum) {
      throw const FormatException('Encrypted backups support up to 8 MB.');
    }
    if (size < 1 || size > _zipLimit) {
      throw const FormatException(
        'This app can save a complete backup up to 64 MB.',
      );
    }
    final chunks = booksRows(manifest['chunks']).toList()
      ..sort(
        (left, right) =>
            (left['index'] as int).compareTo(right['index'] as int),
      );
    final assembled = BytesBuilder(copy: false);
    for (final chunk in chunks) {
      if (!mounted) return;
      final bytes = await api.download('$path/chunks/${chunk['index']}');
      if (bytes.length != chunk['size_bytes'] ||
          sha256.convert(bytes).toString() != chunk['sha256']) {
        throw const FormatException('A downloaded chunk failed verification.');
      }
      if (assembled.length + bytes.length > size) {
        throw const FormatException(
          'The downloaded size did not match the snapshot.',
        );
      }
      assembled.add(bytes);
      _notify(
        'Downloading complete backup…',
        progress: assembled.length / size,
      );
    }
    final archive = assembled.takeBytes();
    if (archive.length != size ||
        sha256.convert(archive).toString() != manifest['sha256']) {
      throw const FormatException('The downloaded backup failed verification.');
    }
    if (mounted &&
        await _saveBytes('apex-books-$day.zip', archive, 'application/zip')) {
      _notify(
        kIsWeb
            ? 'Verified complete backup download started.'
            : 'Verified complete backup saved.',
      );
      try {
        await api.delete(path);
      } on ApexApiException {
        // If the cleanup reply is lost, the staging snapshot expires server-side.
      }
      _export = null;
      _exportKey = null;
    }
  });

  Future<void> _selectFile() => _run(() async {
    final result = await pickApexFile([
      if (_complete) 'zip',
      'gz',
      'json',
      'apexbackup',
    ], _complete ? _zipLimit : encryptedBackupMaximum);
    if (!mounted || result == null) return;
    setState(() {
      _file = result;
      _preview = null;
      _validatedBytes = null;
      _restorePassword.clear();
      _uploadKey = null;
    });
  });

  Future<void> _validate() => _run(() async {
    final file = _file;
    final name = _name.text.trim();
    if (file == null || name.isEmpty) {
      throw const FormatException(
        'Choose a backup and enter the new company name.',
      );
    }
    final api = widget.session.accountApi;
    final bytes =
        _validatedBytes ??
        (_encrypted
            ? await decryptBackup(file.bytes, _restorePassword.text)
            : file.bytes);
    if (!mounted) return;
    final zip = bytes.length >= 4 && bytes[0] == 0x50 && bytes[1] == 0x4b;
    if (!zip) {
      if (bytes.length > 3000000) {
        throw const FormatException('Choose a legacy backup under 3 MB.');
      }
      final value = booksObject(
        await api.post(
          '/api/backups/restore/preview',
          body: {'company_name': name, 'backup_base64': base64Encode(bytes)},
        ),
      );
      if (mounted) {
        setState(() {
          _preview = value;
          _validatedBytes = bytes;
        });
      }
      return;
    }
    if (!_complete) {
      throw const FormatException(
        'The connected API does not support complete ZIP restore.',
      );
    }
    _uploadKey ??= _key();
    final digest = sha256.convert(bytes).toString();
    final start = booksObject(
      await api.post(
        '/api/backups/uploads',
        body: {
          'company_name': name,
          'byte_count': bytes.length,
          'sha256': digest,
        },
        idempotencyKey: _uploadKey,
      ),
    );
    final id = start['upload_id'] as String;
    _uploadId = id;
    _validatedBytes = bytes;
    final path = '/api/backups/uploads/$id';
    final chunkSize = start['chunk_size'] as int;
    if (chunkSize < 1 || chunkSize > 1024 * 1024) {
      throw const FormatException(
        'The API returned an invalid upload chunk size.',
      );
    }
    final received = (start['received_indices'] as List)
        .whereType<int>()
        .toSet();
    for (var offset = 0; offset < bytes.length; offset += chunkSize) {
      if (!mounted) return;
      final index = offset ~/ chunkSize;
      final end = min(offset + chunkSize, bytes.length);
      if (!received.contains(index)) {
        final chunk = Uint8List.sublistView(bytes, offset, end);
        final uploaded = booksObject(
          await api.uploadBytes('$path/chunks/$index', chunk),
        );
        if (uploaded['sha256'] != sha256.convert(chunk).toString()) {
          throw const FormatException('An uploaded chunk failed verification.');
        }
      }
      _notify('Uploading backup…', progress: end / bytes.length);
    }
    final value = booksObject(await api.post('$path/preview', body: {}));
    if (mounted) {
      setState(() {
        _preview = value;
        _status = null;
      });
    }
  });

  Future<void> _restore() => _run(() async {
    final bytes = _validatedBytes;
    final preview = _preview;
    if (bytes == null || preview == null || preview['ready'] != true) return;
    final api = widget.session.accountApi;
    final id = _uploadId;
    final value = id == null
        ? await api.post(
            '/api/backups/restore/commit',
            body: {
              'company_name': _name.text.trim(),
              'backup_base64': base64Encode(bytes),
              'digest': preview['digest'],
            },
          )
        : await api.post(
            '/api/backups/uploads/$id/commit',
            body: {'digest': preview['digest']},
          );
    final company = booksObject(value)['company_id'] as String;
    if (mounted) await widget.session.refreshCompanies(select: company);
  });

  Future<void> _resetRestore() => _run(() async {
    if (_uploadId case final id?) {
      try {
        await widget.session.accountApi.delete('/api/backups/uploads/$id');
      } on ApexApiException catch (error) {
        if (error.status != 404 && error.status != 410) rethrow;
      }
    }
    if (mounted) {
      setState(() {
        _file = null;
        _validatedBytes = null;
        _preview = null;
        _uploadId = null;
        _uploadKey = null;
        _restorePassword.clear();
      });
    }
  });

  Widget _restoreReview(Json preview) {
    final theme = Theme.of(context);
    final counts = preview['counts'] is Json
        ? preview['counts'] as Json
        : const <String, dynamic>{};
    final ready = preview['ready'] == true;
    return Semantics(
      container: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Apex.tint,
          border: Border.all(color: Apex.line),
          borderRadius: BorderRadius.circular(Apex.radiusPanel),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                ready ? 'Backup verified' : 'Review backup',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              Text(
                'Restore ${preview['company_name']} into ${_name.text.trim()}',
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 20,
                runSpacing: 10,
                children: [
                  for (final (label, count) in [
                    ('Records', counts['records']),
                    ('Journal entries', counts['journals']),
                    ('Stock movements', counts['stock_movements']),
                    ('Attachments', preview['attachment_count']),
                  ])
                    if (count != null)
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('$count', style: theme.textTheme.titleLarge),
                          Text(label),
                        ],
                      ),
                ],
              ),
              if (preview['warnings'] case final List warnings)
                for (final warning in warnings)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text('$warning'),
                  ),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: !_busy && ready ? _restore : null,
                child: const Text('Restore this backup'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _name.dispose();
    _exportPassword.dispose();
    _restorePassword.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_owner) ...[
          SettingsBlock(
            title: 'Export company data',
            children: [
              TextField(
                controller: _exportPassword,
                obscureText: true,
                enabled: !_busy,
                enableSuggestions: false,
                autocorrect: false,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  labelText: 'Backup password (optional)',
                  helperText: 'Use 12 or more characters for encryption',
                ),
              ),
              if (_exportPassword.text.isEmpty)
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: const Text(
                    'I am saving an unencrypted file containing company data.',
                  ),
                  value: _consent,
                  onChanged: _busy
                      ? null
                      : (value) => setState(() => _consent = value ?? false),
                ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton(
                    onPressed: _busy || !_exportAllowed
                        ? null
                        : () => _saveExport(full: false),
                    child: const Text('Save company JSON'),
                  ),
                  if (_complete)
                    FilledButton(
                      onPressed: _busy || !_exportAllowed
                          ? null
                          : () => _saveExport(full: true),
                      child: const Text('Save complete ZIP'),
                    ),
                ],
              ),
            ],
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Divider(height: 1, color: Apex.line),
          ),
        ],
        SettingsBlock(
          anchor: widget.restoreAnchor,
          title: 'Restore into a new company',
          children: [
            TextField(
              controller: _name,
              enabled: !_busy && _uploadId == null,
              maxLength: 120,
              onChanged: (_) => setState(() {
                _preview = null;
                _validatedBytes = null;
                _uploadKey = null;
              }),
              decoration: const InputDecoration(labelText: 'New company name'),
            ),
            if (_file case final file?) Text(file.name),
            if (_encrypted && _uploadId == null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: TextField(
                  controller: _restorePassword,
                  enabled: !_busy,
                  obscureText: true,
                  enableSuggestions: false,
                  autocorrect: false,
                  onChanged: (_) => setState(() {
                    _preview = null;
                    _validatedBytes = null;
                  }),
                  decoration: const InputDecoration(
                    labelText: 'Backup password',
                  ),
                ),
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _busy || _uploadId != null ? null : _selectFile,
                  child: const Text('Choose backup'),
                ),
                FilledButton(
                  onPressed: _busy || _file == null || _name.text.trim().isEmpty
                      ? null
                      : _validate,
                  child: Text(
                    _uploadId == null ? 'Validate backup' : 'Recheck backup',
                  ),
                ),
                if (_file != null)
                  TextButton(
                    onPressed: _busy ? null : _resetRestore,
                    child: const Text('Cancel transfer'),
                  ),
              ],
            ),
            if (_preview case final preview?) ...[
              const SizedBox(height: 12),
              _restoreReview(preview),
            ],
          ],
        ),
        if (_busy)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: LinearProgressIndicator(value: _progress),
          ),
        if (_status case final status?)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: SettingsNotice(status),
          ),
      ],
    );
  }
}
