import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import 'books_data.dart';

const _maximumBytes = 5000000;

Future<Json?> scanPurchaseBill(
  BuildContext context,
  WorkspaceContext workspace, {
  Future<ApexPickedFile?> Function()? capture,
}) => showDialog<Json>(
  context: context,
  builder: (_) =>
      _PurchaseScan(workspace: workspace, capture: capture ?? _cameraPhoto),
);

Future<ApexPickedFile?> _cameraPhoto() async {
  final photo = await ImagePicker().pickImage(
    source: ImageSource.camera,
    maxWidth: 2600,
    maxHeight: 2600,
    imageQuality: 94,
    requestFullMetadata: false,
  );
  if (photo == null) return null;
  if (await photo.length() > _maximumBytes) {
    throw const FormatException(
      'The photo exceeds 5 MB. Choose a smaller image.',
    );
  }
  return (name: photo.name, bytes: await photo.readAsBytes());
}

class _PurchaseScan extends StatefulWidget {
  const _PurchaseScan({required this.workspace, required this.capture});

  final WorkspaceContext workspace;
  final Future<ApexPickedFile?> Function() capture;

  @override
  State<_PurchaseScan> createState() => _PurchaseScanState();
}

class _PurchaseScanState extends State<_PurchaseScan> {
  late Future<Json> _status;
  ApexPickedFile? _file;
  String? _message;
  bool _busy = false;
  bool _takingPhoto = false;

  bool get _canTakePhoto =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;
  bool get _working => _busy || _takingPhoto;

  @override
  void initState() {
    super.initState();
    _status = _check();
  }

  Future<Json> _check() async =>
      booksObject(await widget.workspace.api.get('/api/ocr/status'));

  Future<void> _choose() async {
    try {
      final file = await pickApexFile([
        'jpg',
        'jpeg',
        'png',
        'webp',
      ], _maximumBytes);
      if (mounted && file != null) {
        setState(() {
          _file = file;
          _message = null;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is FormatException
              ? error.message
              : 'Could not open this image.',
        );
      }
    }
  }

  Future<void> _takePhoto() async {
    if (_working) return;
    setState(() {
      _takingPhoto = true;
      _message = null;
    });
    try {
      final photo = await widget.capture();
      if (mounted && photo != null) setState(() => _file = photo);
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is FormatException
              ? error.message
              : 'Camera unavailable. You can choose a saved image.',
        );
      }
    } finally {
      if (mounted) setState(() => _takingPhoto = false);
    }
  }

  Future<void> _extract() async {
    final file = _file;
    if (file == null || _working) return;
    final type = switch (file.bytes) {
      [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, ...] => 'png',
      [0xff, 0xd8, 0xff, ...] => 'jpeg',
      [0x52, 0x49, 0x46, 0x46, _, _, _, _, 0x57, 0x45, 0x42, 0x50, ...] =>
        'webp',
      _ => '',
    };
    if (type.isEmpty) {
      setState(() => _message = 'Choose a PNG, JPEG or WebP photo.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final workspace = widget.workspace;
      final response = booksObject(
        await workspace.api.post(
          '${workspace.path}/ocr/purchase-draft',
          body: {
            'image_data_url':
                'data:image/$type;base64,${base64Encode(file.bytes)}',
          },
        ),
      );
      if (response['status'] != 'review_required') {
        throw const FormatException();
      }
      final draft = booksObject(response['draft']);
      if (mounted) Navigator.pop(context, draft);
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is ApexApiException && !error.uncertain
              ? error.message
              : 'Could not extract this bill. Try another photo or enter it manually.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_working,
    child: FutureBuilder(
      future: _status,
      builder: (context, snapshot) {
        final ready = snapshot.data?['ready'] == true;
        return AlertDialog(
          title: const Text('Scan a supplier bill'),
          scrollable: true,
          content: SizedBox(
            width: 440,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (snapshot.connectionState != ConnectionState.done)
                  const LinearProgressIndicator(
                    semanticsLabel: 'Checking scan availability',
                  )
                else if (!ready)
                  Text(
                    booksText(snapshot.data?['message']).isEmpty
                        ? 'Could not check scanning availability.'
                        : booksText(snapshot.data?['message']),
                  )
                else ...[
                  const Text(
                    'Scanning sends your invoice image to the configured provider and replaces supplier and line details in this entry.',
                  ),
                  const SizedBox(height: 12),
                  if (_file case final file?) ...[
                    Image.memory(
                      file.bytes,
                      height: 184,
                      fit: BoxFit.contain,
                      errorBuilder: (_, _, _) =>
                          const Text('Image preview unavailable.'),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      file.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      OutlinedButton.icon(
                        onPressed: _working ? null : _choose,
                        icon: const Icon(Icons.image_outlined),
                        label: Text(
                          _file == null ? 'Choose image' : 'Change image',
                        ),
                      ),
                      if (_canTakePhoto)
                        OutlinedButton.icon(
                          onPressed: _working ? null : _takePhoto,
                          icon: const Icon(Icons.photo_camera_outlined),
                          label: const Text('Take photo'),
                        ),
                    ],
                  ),
                ],
                if (_busy)
                  const LinearProgressIndicator(
                    semanticsLabel: 'Extracting bill details',
                  ),
                if (_message case final message?)
                  Semantics(liveRegion: true, child: Text(message)),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: _working ? null : () => Navigator.pop(context),
              child: const Text('Back'),
            ),
            if (snapshot.hasError)
              TextButton(
                onPressed: () => setState(() => _status = _check()),
                child: const Text('Retry status'),
              ),
            if (ready)
              FilledButton(
                onPressed: _file == null || _working ? null : _extract,
                child: const Text('Extract draft'),
              ),
          ],
        );
      },
    ),
  );
}
