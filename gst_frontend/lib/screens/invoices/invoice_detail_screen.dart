import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/core/models/invoice.dart';
import 'package:gst_frontend/core/models/gl_entry.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

/// Invoice detail with line items, GL entries, and action buttons
class InvoiceDetailScreen extends ConsumerStatefulWidget {
  final String invoiceId;
  final String kind; // 'sales' or 'purchase'

  const InvoiceDetailScreen({
    super.key,
    required this.invoiceId,
    required this.kind,
  });

  @override
  ConsumerState<InvoiceDetailScreen> createState() =>
      _InvoiceDetailScreenState();
}

class _InvoiceDetailScreenState extends ConsumerState<InvoiceDetailScreen> {
  @override
  Widget build(BuildContext context) {
    final invoiceAsync = ref.watch(_invoiceDetailProvider(widget.invoiceId));
    final glEntriesAsync = ref.watch(_glEntriesProvider(widget.invoiceId));

    return AppScaffold(
      title: '${widget.kind == 'sales' ? 'Sales' : 'Purchase'} Invoice',
      currentIndex: 1,
      actions: [
        PopupMenuButton<String>(
          onSelected: (action) => _handleAction(action),
          itemBuilder: (_) => [
            const PopupMenuItem(
              value: 'submit',
              child: Text('Submit'),
            ),
            const PopupMenuItem(
              value: 'void',
              child: Text('Void'),
            ),
            const PopupMenuItem(
              value: 'pdf',
              child: Text('Generate PDF'),
            ),
            const PopupMenuItem(
              value: 'einvoice',
              child: Text('E-Invoice'),
            ),
            const PopupMenuItem(
              value: 'share',
              child: Text('Share'),
            ),
            const PopupMenuItem(
              value: 'duplicate',
              child: Text('Duplicate'),
            ),
          ],
        ),
      ],
      body: invoiceAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (invoice) {
          if (invoice == null) {
            return const Center(child: Text('Invoice not found'));
          }
          return _buildInvoiceDetail(invoice, glEntriesAsync);
        },
      ),
    );
  }

  Widget _buildInvoiceDetail(Invoice inv, AsyncValue<List<GLEntry>> glAsync) {
    final f = NumberFormat.currency(locale: 'en_IN', symbol: currencySymbol);
    final statusColor = inv.isSubmitted
        ? Colors.green
        : inv.isCancelled
            ? Colors.red
            : inv.isVoided
                ? Colors.grey
                : inv.isPartPaid
                    ? Colors.blue
                    : Colors.orange;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        inv.invoiceNumber,
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.bold),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: statusColor.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(inv.status,
                            style: TextStyle(
                                fontSize: 12,
                                color: statusColor,
                                fontWeight: FontWeight.w600)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _detailRow('Date',
                      DateFormat('dd MMM yyyy').format(inv.invoiceDate)),
                  _detailRow('Party', inv.partyId),
                  if (inv.partyGstin != null)
                    _detailRow('GSTIN', inv.partyGstin!),
                  _detailRow('Place of Supply', inv.placeOfSupply),
                  _detailRow('Supply Type', inv.supplyType),
                  _detailRow('Invoice Type', inv.invoiceType),
                  if (inv.dueDate != null)
                    _detailRow(
                        'Due Date', DateFormat('dd MMM yyyy').format(inv.dueDate!)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Line Items
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Line Items',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  ...inv.lines.map((line) => Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Expanded(
                                    child: Text(line.itemName,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w600)),
                                  ),
                                  Text(f.format(line.totalAmount),
                                      style: const TextStyle(
                                          fontWeight: FontWeight.bold)),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                      '${line.quantity} × ${f.format(line.unitPrice)}'),
                                  Text(
                                      'GST ${line.gstRate}%',
                                      style: TextStyle(
                                          color: Colors.grey[600])),
                                ],
                              ),
                              if (line.hsnCode != null)
                                Row(
                                  children: [
                                    Text('HSN: ${line.hsnCode}',
                                        style: TextStyle(
                                            fontSize: 11,
                                            color: Colors.grey[500])),
                                  ],
                                ),
                              if (line.cgstAmount > 0 ||
                                  line.sgstAmount > 0 ||
                                  line.igstAmount > 0)
                                Padding(
                                  padding:
                                      const EdgeInsets.only(top: 4),
                                  child: Row(
                                    children: [
                                      if (line.cgstAmount > 0)
                                        Text(
                                            'CGST: ${f.format(line.cgstAmount)}',
                                            style: TextStyle(
                                                fontSize: 11,
                                                color: Colors.green[700])),
                                      if (line.sgstAmount > 0)
                                        Padding(
                                          padding: const EdgeInsets.only(
                                              left: 8),
                                          child: Text(
                                              'SGST: ${f.format(line.sgstAmount)}',
                                              style: TextStyle(
                                                  fontSize: 11,
                                                  color: Colors.green[700])),
                                        ),
                                      if (line.igstAmount > 0)
                                        Padding(
                                          padding: const EdgeInsets.only(
                                              left: 8),
                                          child: Text(
                                              'IGST: ${f.format(line.igstAmount)}',
                                              style: TextStyle(
                                                  fontSize: 11,
                                                  color: Colors.green[700])),
                                        ),
                                    ],
                                  ),
                                ),
                            ],
                          ),
                        ),
                      )),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Tax Summary
          Card(
            color: const Color(0xFFF0FDF4),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Tax Breakdown',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  _summaryRow('Subtotal', f.format(inv.subtotal)),
                  if (inv.totalDiscount > 0)
                    _summaryRow(
                        'Discount', '-${f.format(inv.totalDiscount)}'),
                  _summaryRow('CGST', f.format(inv.totalCgst)),
                  _summaryRow('SGST', f.format(inv.totalSgst)),
                  _summaryRow('IGST', f.format(inv.totalIgst)),
                  if (inv.totalCess > 0)
                    _summaryRow('Cess', f.format(inv.totalCess)),
                  if (inv.roundOff != 0)
                    _summaryRow('Round Off', f.format(inv.roundOff)),
                  const Divider(),
                  _summaryRow('Grand Total', f.format(inv.grandTotal),
                      isBold: true),
                  if (inv.paymentStatus != 'Unpaid') ...[
                    const SizedBox(height: 4),
                    _summaryRow('Amount Paid',
                        f.format(inv.amountPaid)),
                    _summaryRow('Outstanding',
                        f.format(inv.outstandingAmount)),
                  ],
                ],
              ),
            ),
          ),

          // GL Entries (Submitted invoices only)
          if (inv.isSubmitted || inv.isPartPaid || inv.isPaid) ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Ledger Entries',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 8),
                    glAsync.when(
                      loading: () =>
                          const Center(child: CircularProgressIndicator()),
                      error: (e, _) => Text('Error loading entries: $e'),
                      data: (entries) {
                        if (entries.isEmpty) {
                          return const Text('No ledger entries');
                        }
                        return Column(
                          children: entries.map((entry) {
                            final isDebit = entry.debit > 0;
                            return Padding(
                              padding:
                                  const EdgeInsets.symmetric(vertical: 4),
                              child: Row(
                                children: [
                                  Icon(
                                    isDebit
                                        ? Icons.arrow_downward
                                        : Icons.arrow_upward,
                                    size: 16,
                                    color: isDebit
                                        ? Colors.green
                                        : Colors.red,
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                      child: Text(entry.account)),
                                  if (entry.partyId != null &&
                                      entry.partyId!.isNotEmpty)
                                    Text(
                                      '(${entry.partyId})',
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                  Text(
                                    '${isDebit ? 'Dr' : 'Cr'} ${f.format(isDebit ? entry.debit : entry.credit)}',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w600,
                                        color: isDebit
                                            ? Colors.green
                                            : Colors.red),
                                  ),
                                ],
                              ),
                            );
                          }).toList(),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  void _handleAction(String action) {
    final api = ref.read(apiProvider);
    switch (action) {
      case 'submit':
        _submitInvoice();
        break;
      case 'void':
        _voidInvoice();
        break;
      case 'pdf':
        _generatePdf();
        break;
      case 'einvoice':
        _pushEInvoice();
        break;
      case 'share':
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Share feature coming soon')),
        );
        break;
      case 'duplicate':
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Duplicate feature coming soon')),
        );
        break;
    }
  }

  Future<void> _submitInvoice() async {
    try {
      final api = ref.read(apiProvider);
      await api.submitInvoice(widget.invoiceId, widget.kind);
      ref.invalidate(_invoiceDetailProvider(widget.invoiceId));
      ref.invalidate(invoiceListProvider(widget.kind));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Invoice submitted!')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _voidInvoice() async {
    final reason = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Void Invoice'),
        content: TextField(
          autofocus: true,
          decoration:
              const InputDecoration(hintText: 'Reason for voiding'),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, 'User'),
              child: const Text('Void',
                  style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (reason == null) return;
    try {
      final api = ref.read(apiProvider);
      await api.voidInvoice(widget.invoiceId, {'reason': reason});
      ref.invalidate(_invoiceDetailProvider(widget.invoiceId));
      ref.invalidate(invoiceListProvider(widget.kind));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Invoice voided')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _generatePdf() async {
    try {
      final api = ref.read(apiProvider);
      final response = await api.getInvoicePdf(widget.invoiceId);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('PDF generation started')),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _pushEInvoice() async {
    try {
      final api = ref.read(apiProvider);
      final response = await api.pushEinvoice(widget.invoiceId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('E-Invoice: ${response.data}')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.grey)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }

  Widget _summaryRow(String label, String value, {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: TextStyle(
                  fontWeight: isBold ? FontWeight.bold : FontWeight.normal)),
          Text(value,
              style: TextStyle(
                  fontWeight: isBold ? FontWeight.bold : FontWeight.normal)),
        ],
      ),
    );
  }
}

// Providers for this screen
final _invoiceDetailProvider =
    FutureProvider.autoDispose.family<Invoice?, String>((ref, invoiceId) async {
  final api = ref.read(apiProvider);
  final kind = 'sales';
  try {
    final response = await api.getInvoice(invoiceId, kind);
    final data = response.data as Map<String, dynamic>;
    return Invoice.fromJson(data);
  } catch (_) {
    // Try purchase
    try {
      final response = await api.getInvoice(invoiceId, 'purchase');
      final data = response.data as Map<String, dynamic>;
      return Invoice.fromJson(data);
    } catch (_) {
      return null;
    }
  }
});

final _glEntriesProvider =
    FutureProvider.autoDispose.family<List<GLEntry>, String>((ref, invoiceId) async {
  // GL entries would come from a dedicated endpoint or be embedded in invoice
  // For now, return empty — the invoice dict API includes GL summary
  return [];
});