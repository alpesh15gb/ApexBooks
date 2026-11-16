import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';

Future<bool> saveApexFile(String name, Uint8List bytes, String mimeType) async {
  final safeName = name.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '-');
  final destination = await FilePicker.saveFile(
    fileName: safeName,
    bytes: bytes,
    mimeType: mimeType,
  );
  // The default web picker starts a browser download and has no filesystem URI.
  return kIsWeb || destination != null;
}

typedef ApexPickedFile = ({String name, Uint8List bytes});

Future<ApexPickedFile?> pickApexFile(
  List<String> extensions,
  int maximumBytes,
) async {
  final file = await FilePicker.pickFile(
    type: FileType.custom,
    allowedExtensions: extensions,
  );
  if (file == null) return null;
  final size = await file.length();
  final label = maximumBytes >= 1024 * 1024
      ? '${maximumBytes ~/ (1024 * 1024)} MB'
      : '${maximumBytes ~/ 1000} KB';
  if (size != null && size > maximumBytes) {
    throw FormatException('Choose a file under $label.');
  }
  final buffer = BytesBuilder(copy: false);
  await for (final part in file.readAsByteStream()) {
    if (buffer.length + part.length > maximumBytes) {
      throw FormatException('Choose a file under $label.');
    }
    buffer.add(part);
  }
  return (name: file.name, bytes: buffer.takeBytes());
}
