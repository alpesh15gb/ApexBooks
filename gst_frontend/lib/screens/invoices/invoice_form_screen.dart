import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/core/models/invoice.dart';
import 'package:gst_frontend/core/models/party.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:intl/intl.dart';

class InvoiceFormScreen extends ConsumerStatefulWidget {
  final Invoice? existing;
  final String kind; // 'sales' or 'purchase'
  final Party? selectedParty;

  const InvoiceFormScreen({
    super.key,
    this.existing,
    required this.kind,
    this.selectedParty,
  });

  @override
  ConsumerState<InvoiceFormScreen> createState() => _InvoiceFormScreenState();
}

class _InvoiceFormScreenState extends ConsumerState<InvoiceFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _partyCtrl = TextEditingController();
  final _placeCtrl = TextEditingController(text: '27');
  final _lineNameCtrl = TextEditingController();
  final _lineQtyCtrl = TextEditingController();
  final _linePriceCtrl = TextEditingController();
  final _lineGstCtrl = TextEditingController();

  String _supplyType = 'B2B';
  String _invoiceType = 'Regular';
  DateTime _invoiceDate = DateTime.now();
  List<Map<String, dynamic>> _lines = [];

  double get _subtotal => _lines.fold(
      0.0, (sum, l) => sum + (l['quantity'] as double) * (l['unit_price'] as double));
  double get _totalCgst => _lines.fold(0.0,
      (sum, l) => sum + (l['cgst_amount'] as double? ?? 0));
  double get _totalSgst => _lines.fold(0.0,
      (sum, l) => sum + (l['sgst_amount'] as double? ?? 0));
  double get _totalIgst => _lines.fold(0.0,
      (sum, l) => sum + (l['igst_amount'] as double? ?? 0));
  double get _grandTotal => _lines.fold(
      0.0, (sum, l) => sum + (l['total_amount'] as double? ?? 0));

  @override
  void initState() {
    super.initState();
    if (widget.selectedParty != null) {
      _partyCtrl.text = widget.selectedParty!.partyName;
    }
    if (widget.existing != null) {
      final inv = widget.existing!;
      _placeCtrl.text = inv.placeOfSupply;
      _supplyType = inv.supplyType;
      _invoiceType = inv.invoiceType;
      _invoiceDate = inv.invoiceDate;
      _lines = inv.lines.map((l) => {
        'item_name': l.itemName,
        'quantity': l.quantity,
        'unit_price': l.unitPrice,
        'gst_rate': l.gstRate,
        'taxable_value': l.taxableValue,
        'cgst_amount': l.cgstAmount,
        'sgst_amount': l.sgstAmount,
        'igst_amount': l.igstAmount,
        'total_amount': l.totalAmount,
      }).toList();
    }
  }

  void _addLine() {
    final qty = double.tryParse(_lineQtyCtrl.text) ?? 0;
    final price = double.tryParse(_linePriceCtrl.text) ?? 0;
    final rate = double.tryParse(_lineGstCtrl.text) ?? 0;
    if (qty <= 0 || price <= 0) return;

    final taxable = qty * price;
    final isInterstate = _placeCtrl.text != '27';
    final cgst = isInterstate ? 0.0 : (taxable * rate / 100) / 2;
    final sgst = isInterstate ? 0.0 : (taxable * rate / 100) / 2;
    final igst = isInterstate ? taxable * rate / 100 : 0.0;
    final total = taxable + cgst + sgst + igst;

    setState(() {
      _lines.add({
        'item_name': _lineNameCtrl.text,
        'quantity': qty,
        'unit_price': price,
        'gst_rate': rate,
        'taxable_value': taxable,
        'cgst_amount': cgst,
        'sgst_amount': sgst,
        'igst_amount': igst,
        'total_amount': total,
      });
      _lineNameCtrl.clear();
      _lineQtyCtrl.clear();
      _linePriceCtrl.clear();
      _lineGstCtrl.clear();
    });
  }

  void _removeLine(int i) {
    setState(() => _lines.removeAt(i));
  }

  Future<void> _saveInvoice() async {
    if (!_formKey.currentState!.validate()) return;
    if (_lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Add at least one line item')));
      return;
    }

    try {
      final api = ref.read(apiProvider);
final payload = {
         'invoice_date': _invoiceDate.toIso8601String().split('T')[0],
         'place_of_supply': _placeCtrl.text,
         'supply_type': _supplyType,
         'invoice_type': _invoiceType,
         'party_id': widget.selectedParty?.partyId ?? '',
         'line_items': _lines,
       };

      if (widget.existing != null) {
        await api.updateInvoice(
            widget.existing!.invoiceId, widget.kind, payload);
      } else {
        await api.createInvoice(payload..['kind'] = widget.kind);
      }

      ref.invalidate(invoiceListProvider(widget.kind));
      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(widget.existing != null
                  ? 'Invoice updated'
                  : 'Invoice created')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.existing != null ? 'Edit Invoice' : 'New ${widget.kind == 'sales' ? 'Sales' : 'Purchase'} Invoice'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Date & Type
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      readOnly: true,
                      decoration: const InputDecoration(labelText: 'Date'),
                      controller: TextEditingController(
                          text: '${_invoiceDate.year}-${_invoiceDate.month.toString().padLeft(2, '0')}-${_invoiceDate.day.toString().padLeft(2, '0')}'),
                      onTap: () async {
                        final d = await showDatePicker(
                          context: context,
                          initialDate: _invoiceDate,
                          firstDate: DateTime(2020),
                          lastDate: DateTime(2030),
                        );
                        if (d != null) setState(() => _invoiceDate = d);
                      },
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: _supplyType,
                      items: supplyTypes
                          .map((e) =>
                              DropdownMenuItem(value: e, child: Text(e)))
                          .toList(),
                      onChanged: (v) => setState(() => _supplyType = v!),
                      decoration:
                          const InputDecoration(labelText: 'Supply Type'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: _invoiceType,
                items: invoiceTypes
                    .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                    .toList(),
                onChanged: (v) => setState(() => _invoiceType = v!),
                decoration: const InputDecoration(labelText: 'Invoice Type'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _partyCtrl,
                decoration: const InputDecoration(labelText: 'Party Name'),
                validator: (v) =>
                    v == null || v.isEmpty ? 'Required' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _placeCtrl,
                decoration: const InputDecoration(labelText: 'Place of Supply (State Code)'),
                keyboardType: TextInputType.number,
              ),

              // Line Items
              const Divider(height: 32),
              const Text('Line Items',
                  style:
                      TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              ..._lines.asMap().entries.map((entry) {
                final i = entry.key;
                final l = entry.value;
                return Card(
                  margin: const EdgeInsets.symmetric(vertical: 4),
                  child: ListTile(
                    title: Text(l['item_name']),
                    subtitle: Text(
                      '${l['quantity']} × \u20B9${l['unit_price']} = \u20B9${l['total_amount']}',
                    ),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete, color: Colors.red),
                      onPressed: () => _removeLine(i),
                    ),
                  ),
                );
              }),

              // Add Line Form
              Card(
                color: const Color(0xFFF0FDF4),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Add Line Item',
                          style: TextStyle(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _lineNameCtrl,
                        decoration: const InputDecoration(
                            labelText: 'Item Name', border: InputBorder.none),
                      ),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _lineQtyCtrl,
                              decoration: const InputDecoration(
                                  labelText: 'Qty', border: InputBorder.none),
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: TextField(
                              controller: _linePriceCtrl,
                              decoration: const InputDecoration(
                                  labelText: 'Price', border: InputBorder.none),
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: TextField(
                              controller: _lineGstCtrl,
                              decoration: const InputDecoration(
                                  labelText: 'GST%', border: InputBorder.none),
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          onPressed: _addLine,
                          icon: const Icon(Icons.add),
                          label: const Text('Add to Invoice'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // Summary
              const Divider(height: 32),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      _summaryRow('Subtotal', _subtotal),
                      _summaryRow('CGST', _totalCgst),
                      _summaryRow('SGST', _totalSgst),
                      _summaryRow('IGST', _totalIgst),
                      const Divider(),
                      _summaryRow('Grand Total', _grandTotal, isBold: true),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // Submit Button
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton.icon(
                  onPressed: _saveInvoice,
                  icon: const Icon(Icons.save),
                  label: Text(widget.existing != null
                      ? 'Update Invoice'
                      : 'Create Invoice'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _summaryRow(String label, double value, {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: TextStyle(
                  fontWeight: isBold ? FontWeight.bold : FontWeight.normal)),
          Text('\u20B9${value.toStringAsFixed(2)}',
              style: TextStyle(
                  fontWeight: isBold ? FontWeight.bold : FontWeight.normal)),
        ],
      ),
    );
  }
}