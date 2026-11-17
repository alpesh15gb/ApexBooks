import 'dart:typed_data';

import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/pdf_output.dart';
import '../../core/workspace.dart';
import '../masters/overdue_reminders.dart' show openWhatsApp, whatsappUrl;
import 'books_data.dart';
import 'books_entry_draft.dart' show BooksTextFallback;
import 'detail_share.dart';

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
    this.opener = openWhatsApp,
    super.key,
  });

  final WorkspaceContext workspace;
  final BooksRecord record;
  final BooksSaveFile saveFile;
  final PdfOutput printer;
  final Future<bool> Function(String url, String message) opener;

  @override
  State<BooksDocumentOutput> createState() => _BooksDocumentOutputState();
}

class _BooksDocumentOutputState extends State<BooksDocumentOutput> {
  bool _busy = false;
  String? _message;

  Future<void> _share({required bool reminder}) async {
    if (_busy) return;
    final record = widget.record;
    setState(() {
      _busy = true;
      _message = null;
    });
    var upi = '';
    try {
      final branding = await widget.workspace.api.get(
        '${widget.workspace.path}/document-branding',
      );
      if (branding is Map) upi = booksText(branding['upi_id']);
    } catch (_) {
      // The message still works without a UPI ID.
    }
    final company = widget.workspace.company.name;
    final text = reminder
        ? detailReminderMessage(record, company, upi, businessDate())
        : detailDocumentMessage(record, company, upi);
    final phone = booksText(record.data['party_phone']).ifEmpty(
      booksText(record.data['phone']),
    );
    final opened = await widget.opener(whatsappUrl(phone, text), text);
    if (mounted) {
      setState(() {
        _busy = false;
        _message = opened
            ? 'WhatsApp opened with the message filled in.'
            : 'Message copied. Paste it into WhatsApp to send.';
      });
    }
  }

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
                  label: const Text('Download PDF'),
                ),
                OutlinedButton.icon(
                  onPressed: _busy ? null : () => _deliver(print: true),
                  icon: const Icon(Icons.print_outlined),
                  label: const Text('Print document'),
                ),
                if (detailCanShare(widget.record))
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _share(reminder: false),
                    icon: const Icon(Icons.chat_outlined),
                    label: const Text('Share on WhatsApp'),
                  ),
                if (detailCanRemind(widget.record))
                  OutlinedButton.icon(
                    onPressed: _busy ? null : () => _share(reminder: true),
                    icon: const Icon(Icons.notifications_active_outlined),
                    label: const Text('Send reminder'),
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
