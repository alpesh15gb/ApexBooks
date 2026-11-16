import 'dart:typed_data';

import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/pdf_output.dart';
import '../../core/workspace.dart';
import 'books_data.dart';

typedef BooksSaveFile = Future<bool> Function(
  String name,
  Uint8List bytes,
  String mimeType,
);

bool canOutputBooksDocument(BooksRecord record) =>
    record.json['cancelled'] != true &&
    const {
      'sales_invoice',
      'purchase_bill',
      'estimate',
      'proforma',
      'sales_order',
      'purchase_order',
      'credit_note',
      'debit_note',
      'expense',
      'payment_in',
      'payment_out',
      'pos',
      'customer_refund',
      'supplier_refund',
      'advance_refund',
    }.contains(record.kind);

class BooksDocumentOutput extends StatefulWidget {
  const BooksDocumentOutput({
    required this.workspace,
    required this.record,
    this.saveFile = saveApexFile,
    this.printer = const PlatformPdfOutput(),
    super.key,
  });

  final WorkspaceContext workspace;
  final BooksRecord record;
  final BooksSaveFile saveFile;
  final PdfOutput printer;

  @override
  State<BooksDocumentOutput> createState() => _BooksDocumentOutputState();
}

class _BooksDocumentOutputState extends State<BooksDocumentOutput> {
  bool _busy = false;
  String? _message;

  Future<void> _deliver({required bool print}) async {
    if (_busy || !canOutputBooksDocument(widget.record)) return;
    final api = widget.workspace.api;
    final record = widget.record;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final bytes = await api.download(
        '${widget.workspace.path}/documents/${Uri.encodeComponent(record.id)}.pdf',
      );
      if (!mounted ||
          api != widget.workspace.api ||
          record.id != widget.record.id) {
        return;
      }
      final pdf = ApexPdf(bytes: bytes, name: record.label);
      final complete = print
          ? await widget.printer.print(pdf)
          : await widget.saveFile(pdf.name, pdf.bytes, 'application/pdf');
      if (mounted && complete) {
        setState(() => _message = print ? 'Sent to print.' : 'PDF saved.');
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _message = error is ApexApiException
              ? error.message
              : error is UnsupportedError
              ? 'Printing is unavailable on this device.'
              : 'Could not open the document PDF.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => canOutputBooksDocument(widget.record)
      ? Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _deliver(print: false),
                  icon: const Icon(Icons.download_outlined),
                  label: const Text('Save PDF'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _deliver(print: true),
                  icon: const Icon(Icons.print_outlined),
                  label: const Text('Print document'),
                ),
              ],
            ),
            if (_busy)
              const LinearProgressIndicator(
                semanticsLabel: 'Opening document PDF',
              ),
            if (_message case final message?)
              Semantics(liveRegion: true, child: Text(message)),
          ],
        )
      : const SizedBox.shrink();
}
