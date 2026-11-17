import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/http_api.dart';
import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'books_document_output.dart';

const _media = {
  'pdf': 'application/pdf',
  'png': 'image/png',
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
};

String? booksAttachmentType(String name) =>
    _media[name.split('.').last.toLowerCase()];

class BooksAttachmentCommand {
  const BooksAttachmentCommand(this.key, this.values);

  factory BooksAttachmentCommand.fromJson(Json json) {
    final key = booksText(json['key']);
    final values = booksObject(json['values']);
    final type = values['type'];
    if (!RegExp(r'^flutter-attachment-[a-f0-9]{32}$').hasMatch(key) ||
        (type != 'upload' && type != 'archive')) {
      throw const FormatException('Invalid retained receipt request');
    }
    if (type == 'upload' &&
        (booksText(values['filename']).isEmpty ||
            !RegExp(r'^[a-f0-9]{64}$').hasMatch(booksText(values['sha256'])) ||
            !_media.containsValue(values['media_type']))) {
      throw const FormatException('Invalid retained receipt upload');
    }
    if (type == 'archive' &&
        (booksText(values['id']).isEmpty ||
            values['version'] is! int ||
            values['is_archived'] is! bool)) {
      throw const FormatException('Invalid retained receipt update');
    }
    return BooksAttachmentCommand(key, values);
  }

  factory BooksAttachmentCommand.create(Json values) {
    final random = Random.secure();
    final key = List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    return BooksAttachmentCommand.fromJson({
      'key': 'flutter-attachment-$key',
      'values': values,
    });
  }

  final String key;
  final Json values;

  bool get upload => values['type'] == 'upload';
  Json toJson() => {'key': key, 'values': values};

  bool confirms(BooksJson metadata, String recordId) {
    if (metadata['record_id'] != recordId ||
        booksText(metadata['id']).isEmpty) {
      return false;
    }
    return upload
        ? metadata['sha256'] == values['sha256'] &&
              metadata['media_type'] == values['media_type']
        : metadata['id'] == values['id'] &&
              metadata['is_archived'] == values['is_archived'] &&
              (metadata['version'] is int &&
                  metadata['version'] > (values['version'] as int));
  }
}

class BooksAttachments extends StatefulWidget {
  const BooksAttachments({
    required this.workspace,
    required this.record,
    this.saveFile = saveApexFile,
    this.pickFile = pickApexFile,
    super.key,
  });
  final WorkspaceContext workspace;
  final BooksRecord record;
  final BooksSaveFile saveFile;
  final Future<ApexPickedFile?> Function(List<String>, int) pickFile;

  @override
  State<BooksAttachments> createState() => _BooksAttachmentsState();
}

class _BooksAttachmentsState extends State<BooksAttachments> {
  List<BooksJson> _rows = const [];
  BooksAttachmentCommand? _pending;
  bool _loaded = false;
  bool _busy = false;
  String? _message;
  int _limit = 2 * 1024 * 1024;

  String get _root => widget.workspace.path;
  String get _recordPath =>
      '$_root/records/${Uri.encodeComponent(widget.record.id)}/attachments';
  String get _storage =>
      'books-attachment-${Uri.encodeComponent(widget.record.id)}';
  bool get _canWrite => widget.workspace.company.canWrite;
  bool get _canUpload => widget.workspace.api is HttpApexApi;

  @override
  void initState() {
    super.initState();
    // The web shows receipts inline on the document, so they load with it.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && !_loaded) _load();
    });
  }

  Future<void> _load() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final bundle = booksObject(await widget.workspace.api.get(_recordPath));
      final rows = booksRows(bundle['attachments']);
      if (rows.any(
        (row) =>
            row['record_id'] != widget.record.id ||
            booksText(row['id']).isEmpty ||
            row['version'] is! int ||
            row['is_archived'] is! bool ||
            !_media.containsValue(row['media_type']) ||
            !RegExp(r'^[a-f0-9]{64}$').hasMatch(booksText(row['sha256'])),
      )) {
        throw const FormatException('Unexpected receipt identity');
      }
      final saved = _canWrite
          ? await widget.workspace.pending.load(_storage)
          : null;
      if (!mounted) return;
      final options = booksObject(bundle['storage']);
      setState(() {
        _pending = saved == null
            ? null
            : BooksAttachmentCommand.fromJson(saved);
        _limit = options['max_file_bytes'] is int
            ? options['max_file_bytes'] as int
            : _limit;
        _rows = rows;
        _loaded = true;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          _loaded = false;
          _message = _error(error, 'Could not load the retained receipts.');
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _choose({BooksAttachmentCommand? retry}) async {
    if (_busy || !_loaded || !_canWrite || !_canUpload) return;
    final api = widget.workspace.api as HttpApexApi;
    final pendingStore = widget.workspace.pending;
    final path = _recordPath;
    final recordId = widget.record.id;
    final storage = _storage;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final file = await widget.pickFile(
        _media.keys.toList(growable: false),
        _limit,
      );
      if (!mounted || file == null) return;
      final media = booksAttachmentType(file.name);
      if (media == null ||
          file.name.length > 120 ||
          file.name.contains(RegExp(r'[/\\\x00-\x1f\x7f]')) ||
          file.bytes.isEmpty) {
        throw const FormatException(
          'Choose a PDF, PNG or JPEG with a filename of up to 120 characters.',
        );
      }
      final hash = sha256.convert(file.bytes).toString();
      final command =
          retry ??
          BooksAttachmentCommand.create({
            'type': 'upload',
            'filename': file.name,
            'sha256': hash,
            'media_type': media,
          });
      if (hash != command.values['sha256'] ||
          media != command.values['media_type']) {
        throw const FormatException(
          'Choose the original receipt file to retry this upload.',
        );
      }
      if (retry == null) await _persist(pendingStore, storage, command);
      if (!mounted) return;
      _pending = command;
      final response = await api.uploadBytes(
        path,
        file.bytes,
        method: 'POST',
        query: {'filename': command.values['filename'] as String},
        contentType: media,
        idempotencyKey: command.key,
      );
      await _complete(command, response, recordId, pendingStore, storage);
    } catch (error) {
      await _failed(
        error,
        retry: retry != null,
        pendingStore: pendingStore,
        storage: storage,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _archive({BooksJson? row, BooksAttachmentCommand? retry}) async {
    if (_busy || !_loaded || !_canWrite) return;
    final command =
        retry ??
        BooksAttachmentCommand.create({
          'type': 'archive',
          'id': row!['id'],
          'version': row['version'],
          'is_archived': row['is_archived'] != true,
        });
    final pendingStore = widget.workspace.pending;
    final recordId = widget.record.id;
    final storage = _storage;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      if (retry == null) await _persist(pendingStore, storage, command);
      if (!mounted) return;
      _pending = command;
      final id = Uri.encodeComponent(command.values['id'] as String);
      final response = await widget.workspace.api.put(
        '$_root/attachments/$id',
        idempotencyKey: command.key,
        body: {
          'version': command.values['version'],
          'is_archived': command.values['is_archived'],
        },
      );
      await _complete(command, response, recordId, pendingStore, storage);
    } catch (error) {
      await _failed(
        error,
        retry: retry != null,
        pendingStore: pendingStore,
        storage: storage,
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _persist(
    PendingStore store,
    String key,
    BooksAttachmentCommand command,
  ) async {
    try {
      await store.save(key, command.toJson());
    } catch (_) {
      if (mounted) setState(() => _loaded = false);
      throw const FormatException(
        'Could not save a retry copy. Refresh receipts before continuing.',
      );
    }
  }

  Future<void> _complete(
    BooksAttachmentCommand command,
    Object? response,
    String recordId,
    PendingStore storage,
    String key,
  ) async {
    final row = booksObject(booksObject(response)['attachment']);
    if (!command.confirms(row, recordId)) {
      throw const FormatException(
        'The retained receipt could not be verified.',
      );
    }
    await storage.clear(key);
    if (!mounted) return;
    setState(() {
      _pending = null;
      _rows = [..._rows.where((old) => old['id'] != row['id']), row];
      _message = command.upload
          ? 'Receipt retained.'
          : row['is_archived'] == true
          ? 'Receipt archived.'
          : 'Receipt restored.';
    });
  }

  Future<void> _failed(
    Object error, {
    required bool retry,
    required PendingStore pendingStore,
    required String storage,
  }) async {
    if (!mounted) return;
    if (!retry &&
        _pending != null &&
        error is ApexApiException &&
        error.status != null &&
        !error.uncertain) {
      try {
        await pendingStore.clear(storage);
        _pending = null;
      } catch (_) {}
    }
    if (mounted) {
      setState(() {
        _message = _error(error, 'Could not confirm the receipt request.');
      });
    }
  }

  Future<void> _download(BooksJson row) async {
    if (_busy) return;
    final api = widget.workspace.api;
    final recordId = widget.record.id;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final id = Uri.encodeComponent(booksText(row['id']));
      final bytes = await api.download('$_root/attachments/$id/download');
      if (!mounted ||
          recordId != widget.record.id ||
          api != widget.workspace.api) {
        return;
      }
      if (sha256.convert(bytes).toString() != row['sha256']) {
        throw const FormatException(
          'The receipt download could not be verified.',
        );
      }
      final saved = await widget.saveFile(
        booksText(row['filename']),
        bytes,
        booksText(row['media_type']),
      );
      if (mounted && saved) setState(() => _message = 'Receipt saved.');
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = _error(
            error,
            'Could not download the retained receipt.',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _error(Object error, String fallback) => error is ApexApiException
      ? error.message
      : error is FormatException
      ? error.message
      : fallback;

  @override
  Widget build(BuildContext context) => ApexPanel(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 8,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text('Receipts & evidence', style: Apex.panelTitle),
              ),
              Text('${_rows.length} retained files', style: Apex.note),
            ],
          ),
          const Text(
            'PDF, PNG or JPEG · up to 2 MiB each. Files download only; Apex Books does not preview or certify their safety.',
            style: Apex.note,
          ),
          const Text(
            'Archiving hides a receipt from active use; it does not delete evidence or release storage. Complete backups retain archived files.',
            style: Apex.note,
          ),
          if (_busy)
            const LinearProgressIndicator(
              semanticsLabel: 'Working on receipt attachment',
            ),
          if (_message case final message?)
            Semantics(liveRegion: true, child: Text(message)),
          if (_pending case final saved?)
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                onPressed: _busy
                    ? null
                    : () => saved.upload
                          ? _choose(retry: saved)
                          : _archive(retry: saved),
                child: Text(
                  saved.upload
                      ? 'Retry with original receipt file'
                      : 'Retry original receipt update',
                ),
              ),
            ),
          for (final row in _rows)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(booksText(row['filename'])),
              subtitle: Text(
                row['is_archived'] == true ? 'Archived · retained' : 'Active',
              ),
              trailing: PopupMenuButton<String>(
                tooltip: 'Receipt actions',
                enabled: !_busy,
                onSelected: (value) =>
                    value == 'download' ? _download(row) : _archive(row: row),
                itemBuilder: (context) => [
                  const PopupMenuItem(
                    value: 'download',
                    child: Text('Save receipt'),
                  ),
                  if (_loaded &&
                      _canWrite &&
                      _pending == null &&
                      widget.workspace.api is ApexWriteApi)
                    PopupMenuItem(
                      value: 'archive',
                      child: Text(
                        row['is_archived'] == true
                            ? 'Restore receipt'
                            : 'Archive receipt',
                      ),
                    ),
                ],
              ),
            ),
          if (_loaded && _rows.isEmpty)
            const Text(
              'No receipt attached yet. Your accounting entry is unchanged.',
              style: Apex.note,
            ),
          if (!_canWrite)
            const Text(
              'Read-only access: you can download receipts, but cannot upload, archive or reactivate them.',
              style: Apex.note,
            ),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              OutlinedButton(
                onPressed: _busy ? null : _load,
                child: const Text('Refresh receipts'),
              ),
              if (_canWrite && _canUpload && _pending == null)
                FilledButton(
                  onPressed: _loaded && !_busy ? _choose : null,
                  child: const Text('Attach receipt'),
                ),
            ],
          ),
        ],
      ),
    ),
  );
}
