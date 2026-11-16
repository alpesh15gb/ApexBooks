import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:pdf/pdf.dart';
import 'package:printing/printing.dart';

class ApexPdf {
  ApexPdf({required this.bytes, required String name, this.rollWidthMm})
    : name = _fileName(name) {
    if (bytes.length < 5 ||
        ascii.decode(bytes.take(5).toList(), allowInvalid: true) != '%PDF-') {
      throw const FormatException('Apex Books did not return a PDF.');
    }
    if (rollWidthMm != null) {
      final format = _firstMediaBox(bytes);
      if (format == null ||
          (format.width - rollWidthMm! * PdfPageFormat.mm).abs() > 1) {
        throw const FormatException(
          'The PDF does not match the selected receipt roll.',
        );
      }
      _format = format;
    }
  }

  final Uint8List bytes;
  final String name;
  final int? rollWidthMm;
  PdfPageFormat _format = PdfPageFormat.standard;

  double get pageWidthPoints => _format.width;
  double get pageHeightPoints => _format.height;

  static String _fileName(String name) {
    final clean = name
        .replaceFirst(RegExp(r'\.pdf$', caseSensitive: false), '')
        .replaceAll(RegExp(r'[^a-zA-Z0-9_-]+'), '-');
    final limited = clean.length > 100 ? clean.substring(0, 100) : clean;
    return 'apex-${limited.isEmpty ? 'document' : limited}.pdf';
  }

  // Apex Books generates thermal PDFs with an explicit ReportLab media box.
  static PdfPageFormat? _firstMediaBox(Uint8List bytes) {
    final dictionary = latin1.decode(bytes);
    final box = RegExp(r'/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]')
        .firstMatch(dictionary);
    final width = double.tryParse(box?[1] ?? '');
    final height = double.tryParse(box?[2] ?? '');
    if (width == null ||
        height == null ||
        width <= 0 ||
        height <= 0 ||
        !width.isFinite ||
        !height.isFinite) {
      return null;
    }
    return PdfPageFormat(width, height);
  }
}

abstract interface class PdfOutput {
  Future<bool> print(ApexPdf document);
}

class PlatformPdfOutput implements PdfOutput {
  const PlatformPdfOutput();

  @override
  Future<bool> print(ApexPdf document) async {
    // Web hands the PDF directly to the browser. Printing.info() would load
    // the plugin's optional PDF.js rasterizer from a third-party CDN.
    if (!kIsWeb && !(await Printing.info()).canPrint) {
      throw UnsupportedError('Printing is unavailable on this device.');
    }
    return Printing.layoutPdf(
      onLayout: (_) async => document.bytes,
      name: document.name,
      format: document._format,
      dynamicLayout: false,
      usePrinterSettings:
          !kIsWeb && defaultTargetPlatform == TargetPlatform.windows,
    );
  }
}
