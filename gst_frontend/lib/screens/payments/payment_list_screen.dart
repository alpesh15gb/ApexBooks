import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/core/models/payment.dart';
import 'package:gst_frontend/core/models/party.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class PaymentListScreen extends ConsumerStatefulWidget {
  const PaymentListScreen({super.key});

  @override
  ConsumerState<PaymentListScreen> createState() => _PaymentListScreenState();
}

class _PaymentListScreenState extends ConsumerState<PaymentListScreen> {
  String _searchQuery = '';

  @override
  Widget build(BuildContext context) {
    final paymentsAsync = ref.watch(paymentListProvider);

    return AppScaffold(
      title: 'Payments',
      currentIndex: 3,
      actions: [
        IconButton(
          icon: const Icon(Icons.add),
          onPressed: () => _showPaymentForm(context),
        ),
      ],
      body: paymentsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (payments) {
          if (payments.isEmpty) {
            return const Center(child: Text('No payments recorded'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(8),
            itemCount: payments.length,
            itemBuilder: (ctx, i) {
              final p = payments[i];
              return Card(
                margin: const EdgeInsets.symmetric(vertical: 4),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: p.isReceived
                        ? const Color(0xFF10B981)
                        : const Color(0xFFEF4444),
                    child: Icon(
                      p.isReceived ? Icons.arrow_downward : Icons.arrow_upward,
                      color: Colors.white,
                    ),
                  ),
                  title: Text(
                    '${p.paymentType} — \u20B9${p.amount.toStringAsFixed(2)}',
                  ),
                  subtitle: Text(
                    '${p.paymentMode} • ${p.paymentDate.toLocal()}'.split(' ')[0],
                  ),
                  trailing: Chip(
                    label: Text(p.status),
                    color: WidgetStateColor.resolveWith((states) {
                      if (p.isReconciled) return Colors.green;
                      if (p.isVoided) return Colors.grey;
                      return Colors.orange;
                    }),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  void _showPaymentForm(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => const _NewPaymentForm(),
    );
  }
}

class _NewPaymentForm extends ConsumerStatefulWidget {
  const _NewPaymentForm();

  @override
  ConsumerState<_NewPaymentForm> createState() => _NewPaymentFormState();
}

class _NewPaymentFormState extends ConsumerState<_NewPaymentForm> {
  final _formKey = GlobalKey<FormState>();
  String _type = 'Receive';
  String _mode = 'Cash';
  final _amountCtrl = TextEditingController();
  final _refCtrl = TextEditingController();
  final _narrationCtrl = TextEditingController();

  @override
  void dispose() {
    _amountCtrl.dispose();
    _refCtrl.dispose();
    _narrationCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: 16,
        right: 16,
        top: 16,
      ),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('New Payment',
                style:
                    TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              value: _type,
              items: ['Receive', 'Make']
                  .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                  .toList(),
              onChanged: (v) => setState(() => _type = v!),
              decoration: const InputDecoration(labelText: 'Type'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _amountCtrl,
              decoration: const InputDecoration(
                  labelText: 'Amount', prefixText: '\u20B9'),
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              validator: (v) =>
                  v == null || v.isEmpty ? 'Required' : null,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: _mode,
              items: ['Cash', 'Bank Transfer', 'UPI', 'Cheque', 'Card']
                  .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                  .toList(),
              onChanged: (v) => setState(() => _mode = v!),
              decoration: const InputDecoration(labelText: 'Mode'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _refCtrl,
              decoration: const InputDecoration(labelText: 'Reference No'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _narrationCtrl,
              decoration: const InputDecoration(labelText: 'Narration'),
              maxLines: 2,
            ),
            const SizedBox(height: 20),
SizedBox(
               width: double.infinity,
               height: 48,
               child: ElevatedButton(
                 onPressed: () async {
                   if (_formKey.currentState!.validate()) {
                     final api = ref.read(apiProvider);
                     final payload = {
                       'payment_type': _type == 'Receive' ? 'Receive' : 'Make',
                       'payment_mode': _mode,
                       'payment_date': DateTime.now().toIso8601String().split('T')[0],
                       'party_id': '',
                       'amount': double.parse(_amountCtrl.text),
                       'reference_no': _refCtrl.text,
                       'narration': _narrationCtrl.text,
                     };
                     try {
                       await api.createPayment(payload);
                       ref.invalidate(paymentListProvider);
                       if (mounted) {
                         ScaffoldMessenger.of(context).showSnackBar(
                           const SnackBar(content: Text('Payment saved')),
                         );
                       }
                       Navigator.pop(context);
                     } catch (e) {
                       if (mounted) {
                         ScaffoldMessenger.of(context).showSnackBar(
                           SnackBar(content: Text('Error: $e')),
                         );
                       }
                     }
                   }
                 },
                 child: const Text('SAVE PAYMENT'),
               ),
             ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}