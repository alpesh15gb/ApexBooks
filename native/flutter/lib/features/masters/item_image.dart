import 'dart:convert';

import 'package:flutter/foundation.dart';
// The image package is already resolved through pdf and printing; it is the only JPEG encoder here.
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../ui/apex_theme.dart';

/// The web app's limits (frontend/src/imageInput.js): PNG, JPEG or WebP below 15 MB, scaled to fit
/// 600 px and re-encoded as JPEG of at most 64,000 bytes, plus a 160 px thumbnail of at most 15,000.
const itemImageSourceLimit = 15000000;
const itemImageSize = 600;
const itemImageBytes = 64000;
const itemThumbnailSize = 160;
const itemThumbnailBytes = 15000;
const itemImageChoiceError = 'Choose a PNG, JPEG or WebP below 15 MB';

typedef ItemImage = ({String image, String thumbnail});

/// Converts a picked file to the `data:image/jpeg;base64,…` pair the API stores.
/// Throws a [FormatException] carrying the web app's message when the file cannot be used.
Future<ItemImage> prepareItemImage(Uint8List bytes) async {
  if (bytes.length > itemImageSourceLimit) throw const FormatException(itemImageChoiceError);
  final result = await compute(_prepare, bytes);
  if (result == null) throw const FormatException(itemImageChoiceError);
  if (result.length == 1) throw const FormatException('Image is too detailed; choose a smaller crop');
  return (image: result[0], thumbnail: result[1]);
}

String? _encode(img.Image source, int size, int limit) {
  final scale = size / (source.width > source.height ? source.width : source.height);
  var image = source;
  if (scale < 1) {
    image = img.copyResize(
      source,
      width: (source.width * scale).round().clamp(1, size),
      height: (source.height * scale).round().clamp(1, size),
      interpolation: img.Interpolation.average,
    );
  }
  // JPEG has no alpha: flatten onto white like the web canvas does.
  final flat = img.Image(width: image.width, height: image.height, numChannels: 3);
  img.fill(flat, color: img.ColorRgb8(255, 255, 255));
  img.compositeImage(flat, image);
  for (final quality in const [90, 75, 60, 40]) {
    final jpeg = img.encodeJpg(flat, quality: quality);
    if (jpeg.length <= limit) return 'data:image/jpeg;base64,${base64Encode(jpeg)}';
  }
  return null;
}

/// Runs in a background isolate. Null: not a readable PNG/JPEG/WebP. A one-element list: too detailed.
List<String>? _prepare(Uint8List bytes) {
  final isImage = switch (bytes) {
    [0x89, 0x50, 0x4e, 0x47, ...] => true,
    [0xff, 0xd8, 0xff, ...] => true,
    [0x52, 0x49, 0x46, 0x46, _, _, _, _, 0x57, 0x45, 0x42, 0x50, ...] => true,
    _ => false,
  };
  if (!isImage) return null;
  final source = img.decodeImage(bytes);
  if (source == null) return null;
  final image = _encode(source, itemImageSize, itemImageBytes);
  final thumbnail = _encode(source, itemThumbnailSize, itemThumbnailBytes);
  if (image == null || thumbnail == null) return const [''];
  return [image, thumbnail];
}

Uint8List? _decodeDataUrl(String url) {
  final comma = url.indexOf(',');
  if (!url.startsWith('data:image/') || comma < 0) return null;
  try {
    return base64Decode(url.substring(comma + 1));
  } catch (_) {
    return null;
  }
}

/// "Item image" field of the item form: choose a file (or take a photo on Android), preview,
/// remove. [image] is the full image or, when only the thumbnail is known, the thumbnail.
class ItemImageField extends StatefulWidget {
  const ItemImageField({
    required this.image,
    required this.enabled,
    required this.onPicked,
    required this.onRemoved,
    this.pick,
    super.key,
  });

  final String image;
  final bool enabled;
  final ValueChanged<ItemImage> onPicked;
  final VoidCallback onRemoved;

  /// Replaces the file chooser (tests).
  final Future<ApexPickedFile?> Function()? pick;

  @override
  State<ItemImageField> createState() => _ItemImageFieldState();
}

class _ItemImageFieldState extends State<ItemImageField> {
  bool _busy = false;
  String? _error;

  bool get _camera => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  Future<ApexPickedFile?> _chooseFile() async {
    try {
      return await pickApexFile(['png', 'jpg', 'jpeg', 'webp'], itemImageSourceLimit);
    } on FormatException {
      throw const FormatException(itemImageChoiceError);
    }
  }

  Future<ApexPickedFile?> _takePhoto() async {
    final photo = await ImagePicker().pickImage(
      source: ImageSource.camera,
      maxWidth: 2600,
      maxHeight: 2600,
      requestFullMetadata: false,
    );
    if (photo == null) return null;
    return (name: photo.name, bytes: await photo.readAsBytes());
  }

  Future<void> _choose(Future<ApexPickedFile?> Function() source) async {
    if (_busy || !widget.enabled) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final file = await source();
      if (file == null) return;
      final image = await prepareItemImage(file.bytes);
      if (mounted) widget.onPicked(image);
    } catch (failure) {
      if (mounted) {
        setState(() => _error = failure is FormatException ? failure.message : 'Image could not be read');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bytes = widget.image.isEmpty ? null : _decodeDataUrl(widget.image);
    final editable = widget.enabled && !_busy;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Item image', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: Apex.label)),
        const SizedBox(height: 7),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Apex.radiusControl),
            border: Border.all(color: Apex.fieldBorder),
          ),
          child: Wrap(
            spacing: 10,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: editable ? () => _choose(widget.pick ?? _chooseFile) : null,
                icon: const Icon(Icons.image_outlined, size: 17),
                label: Text(bytes == null ? 'Choose file' : 'Replace file'),
              ),
              if (_camera)
                OutlinedButton.icon(
                  onPressed: editable ? () => _choose(_takePhoto) : null,
                  icon: const Icon(Icons.photo_camera_outlined, size: 17),
                  label: const Text('Take photo'),
                ),
              Text(
                _busy
                    ? 'Preparing image…'
                    : bytes == null
                    ? 'No file chosen'
                    : 'Image ready',
                style: const TextStyle(fontSize: 13, color: Apex.muted),
              ),
            ],
          ),
        ),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text(_error!, style: const TextStyle(fontSize: 13, color: Apex.red))),
        if (bytes != null) ...[
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerLeft,
            child: Image.memory(
              bytes,
              semanticLabel: 'Item preview',
              width: 150,
              height: 120,
              fit: BoxFit.contain,
              alignment: Alignment.centerLeft,
              errorBuilder: (_, _, _) => const SizedBox.shrink(),
            ),
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: editable ? widget.onRemoved : null,
              style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: const Size(0, 32)),
              child: const Text('Remove item image'),
            ),
          ),
        ],
      ],
    );
  }
}
