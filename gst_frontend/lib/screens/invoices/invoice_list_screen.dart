import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/core/models/invoice.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class InvoiceListScreen extends ConsumerStatefulWidget {
  const InvoiceListScreen({super.key});

  @override
  ConsumerState<InvoiceListScreen> createState() => _InvoiceListScreenState();
}

class _InvoiceListScreenState extends ConsumerState<InvoiceListScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Invoices',
      currentIndex: 1,
      actions: [
        IconButton(
          icon: const Icon(Icons.add),
          onPressed: () => _showCreateInvoice(context),
          tooltip: 'New Invoice',
        ),
      ],
      body: Column(
        children: [
          TabBar(
            controller: _tabCtrl,
            indicatorColor: const Color(0xFFFF6B35),
            labelColor: Colors.black87,
            unselectedLabelColor: Colors.grey,
            tabs: const [
              Tab(text: 'Sales'),
              Tab(text: 'Purchase'),
            ],
          ),
          Expanded(
            child: TabBarView(
              controller: _tabCtrl,
              children: [
                _buildInvoiceList(ref, 'sales'),
                _buildInvoiceList(ref, 'purchase'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInvoiceList(WidgetRef ref, String kind) {
    final provider = invoiceListProvider(kind);
    return Consumer(
      builder: (ctx, ref, _) {
        final async = ref.watch(provider);
        return async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, st) => Center(child: Text('Error: $e')),
          data: (invoices) {
            if (invoices.isEmpty) {
              return const Center(child: Text('No invoices'));
            }
            return ListView.builder(
              padding: const EdgeInsets.all(8),
              itemCount: invoices.length,
              itemBuilder: (ctx, i) {
                final inv = invoices[i];
                final statusColor = inv.isSubmitted
                    ? Colors.green
                    : inv.isCancelled
                        ? Colors.red
                        : inv.isVoided
                            ? Colors.grey
                            : Colors.orange;
                return Card(
                  margin: const EdgeInsets.symmetric(vertical: 4),
                  child: ListTile(
                    title: Text(inv.invoiceNumber),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Date: ${inv.invoiceDate.toLocal()}'.split(' ')[0]),
                        Text('Status: ${inv.status}',
                            style: TextStyle(color: statusColor)),
                        Text('\u20B9${inv.grandTotal.toStringAsFixed(2)}'),
                      ],
                    ),
                    trailing: PopupMenuButton<String>(
                      onSelected: (action) {
                        switch (action) {
                          case 'view':
                            _viewInvoice(context, inv);
                            break;
                          case 'submit':
                            _submitInvoice(ctx, ref, inv);
                            break;
                          case 'void':
                            _voidInvoice(ctx, ref, inv);
                            break;
                          case 'delete':
                            _deleteInvoice(ctx, ref, inv);
                            break;
                        }
                      },
                      itemBuilder: (_) => [
                        const PopupMenuItem(
                            value: 'view', child: Text('View')),
                        if (inv.isDraft)
                          const PopupMenuItem(
                              value: 'submit', child: Text('Submit')),
                        if (inv.isSubmitted || inv.isPartPaid)
                          const PopupMenuItem(
                              value: 'void', child: Text('Void')),
                        if (inv.isDraft)
                          const PopupMenuItem(
                              value: 'delete', child: Text('Delete')),
                      ],
                    ),
                  ),
                );
              },
            );
          },
        );
      },
    );
  }

  void _showCreateInvoice(BuildContext context) {
    // TODO: Navigate to invoice creation form
  }

  void _viewInvoice(BuildContext context, Invoice inv) {
    // TODO: Navigate to invoice detail
  }

  Future<void> _submitInvoice(
      BuildContext ctx, WidgetRef ref, Invoice inv) async {
    try {
      final api = ref.read(apiProvider);
      await api.submitInvoice(inv.invoiceId, inv.invoiceKind);
      ref.invalidate(invoiceListProvider(inv.invoiceKind));
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx)
            .showSnackBar(const SnackBar(content: Text('Submitted!')));
      }
    } catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _voidInvoice(
      BuildContext ctx, WidgetRef ref, Invoice inv) async {
    final reason = await showDialog<String>(
      context: ctx,
      builder: (ctx) => AlertDialog(
        title: const Text('Void Invoice'),
        content: TextField(
          autofocus: true,
          decoration: const InputDecoration(hintText: 'Reason for voiding'),
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, 'Voided by user'),
              child: const Text('Void',
                  style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (reason == null) return;
    try {
      final api = ref.read(apiProvider);
      await api.voidInvoice(inv.invoiceId, {'reason': reason});
      ref.invalidate(invoiceListProvider(inv.invoiceKind));
    } catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx)
            .showSnackBar(SnackBar(content: Text('Error: $e')));
      }
    }
  }

  Future<void> _deleteInvoice(
      BuildContext ctx, WidgetRef ref, Invoice inv) async {
    final confirmed = await showDialog<bool>(
      context: ctx,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete'),
        content: const Text('Delete this draft invoice?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete',
                  style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (confirmed != true) return;
    // TODO: implement delete via API
  }
}