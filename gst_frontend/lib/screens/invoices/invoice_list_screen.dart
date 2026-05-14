import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/core/models/invoice.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

/// Invoice list with Tally-style voucher view
/// Supports Sales & Purchase with tab switching
class InvoiceListScreen extends ConsumerStatefulWidget {
  const InvoiceListScreen({super.key});

  @override
  ConsumerState<InvoiceListScreen> createState() => _InvoiceListScreenState();
}

class _InvoiceListScreenState extends ConsumerState<InvoiceListScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabCtrl;
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this)
      ..addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  String get _currentKind => _tabCtrl.index == 0 ? 'sales' : 'purchase';

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Invoices',
      currentIndex: 1,
      actions: [
        IconButton(
          icon: const Icon(Icons.add),
          onPressed: () => _createInvoice(context),
          tooltip: 'New Invoice',
        ),
        IconButton(
          icon: const Icon(Icons.search),
          onPressed: () => _showSearch(),
          tooltip: 'Search',
        ),
      ],
      body: Column(
        children: [
          // Filter bar (Vyapar style)
          _buildFilterBar(),
          // Tab bar
          TabBar(
            controller: _tabCtrl,
            indicatorColor: const Color(0xFFFF6B35),
            indicatorWeight: 3,
            labelColor: Colors.black87,
            unselectedLabelColor: Colors.grey,
            tabs: const [
              Tab(text: 'Sales', icon: Icon(Icons.arrow_circle_up)),
              Tab(text: 'Purchase', icon: Icon(Icons.arrow_circle_down)),
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

  Widget _buildFilterBar() {
    return Container(
      color: const Color(0xFFFFF7ED),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              onChanged: (v) => setState(() => _searchQuery = v),
              decoration: InputDecoration(
                hintText: 'Search invoices...',
                prefixIcon: const Icon(Icons.search, size: 20),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide.none,
                ),
                filled: true,
                fillColor: Colors.white,
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              ),
            ),
          ),
          PopupMenuButton<String>(
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.filter_list, size: 18),
                SizedBox(width: 4),
                Text('Filter'),
              ],
            ),
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'all', child: Text('All')),
              const PopupMenuItem(value: 'Draft', child: Text('Draft')),
              const PopupMenuItem(
                  value: 'Submitted', child: Text('Submitted')),
              const PopupMenuItem(value: 'Paid', child: Text('Paid')),
              const PopupMenuItem(
                  value: 'Part Paid', child: Text('Part Paid')),
              const PopupMenuItem(
                  value: 'Cancelled', child: Text('Cancelled')),
              const PopupMenuItem(value: 'Voided', child: Text('Voided')),
            ],
            onSelected: (_) {
              // TODO: Apply status filter
            },
          ),
          const SizedBox(width: 8),
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
            // Filter
            var list = invoices;
            if (_searchQuery.isNotEmpty) {
              list = list
                  .where((inv) =>
                      inv.invoiceNumber
                          .toLowerCase()
                          .contains(_searchQuery.toLowerCase()) ||
                      inv.partyId.toLowerCase().contains(
                          _searchQuery.toLowerCase()))
                  .toList();
            }

            if (list.isEmpty) {
              return Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.receipt_long,
                        size: 64, color: Colors.grey[400]),
                    const SizedBox(height: 12),
                    Text('No ${kind == 'sales' ? 'sales' : 'purchase'} invoices',
                        style: TextStyle(color: Colors.grey[600])),
                    const SizedBox(height: 8),
                    ElevatedButton(
                      onPressed: _createInvoice,
                      child: const Text('Create One'),
                    ),
                  ],
                ),
              );
            }

            // Summary header (Vyapar style)
            final total = list.fold(
                0.0, (sum, inv) => sum + inv.grandTotal);

            return Column(
              children: [
                Container(
                  color: const Color(0xFFFFF7ED),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        '${list.length} invoices — \u20B9${total.toStringAsFixed(2)}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w600, fontSize: 13),
                      ),
                      Text(
                        '${_currentKind == 'sales' ? 'Total Sales' : 'Total Purchases'}',
                        style: const TextStyle(
                            color: Colors.grey, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.all(8),
                    itemCount: list.length,
                    itemBuilder: (ctx, i) {
                      final inv = list[i];
                      return _buildInvoiceCard(ctx, inv, kind);
                    },
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }

  Widget _buildInvoiceCard(
      BuildContext ctx, Invoice inv, String kind) {
    final statusColor = inv.isSubmitted
        ? Colors.green
        : inv.isCancelled
            ? Colors.red
            : inv.isVoided
                ? Colors.grey
                : inv.isPartPaid
                    ? Colors.blue
                    : Colors.orange;

    final f = NumberFormat.currency(locale: 'en_IN', symbol: '\u20B9');

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
onTap: () {
           Navigator.push(
             context,
             MaterialPageRoute(
               builder: (_) => InvoiceDetailScreen(
                 invoiceId: inv.invoiceId,
                 kind: _currentKind,
               ),
             ),
           );
         },
         onLongPress: () {
          // Show action menu
          showModalBottomSheet(
            context: ctx,
            builder: (_) => _InvoiceActionsMenu(
              invoice: inv,
              kind: kind,
              onAction: (action) {
                Navigator.pop(ctx);
                if (action == 'submit') _submitInvoice(ctx, inv);
                if (action == 'void') _voidInvoice(ctx, inv);
              },
            ),
          );
        },
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    inv.invoiceNumber,
                    style: const TextStyle(
                        fontWeight: FontWeight.bold, fontSize: 15),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: statusColor.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(inv.status,
                        style: TextStyle(
                            fontSize: 11, color: statusColor, fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.person_outline, size: 16, color: Colors.grey[600]),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      inv.partyId,
                      style: const TextStyle(fontSize: 13),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text(
                    DateFormat('dd MMM yyyy')
                        .format(inv.invoiceDate),
                    style:
                        const TextStyle(fontSize: 12, color: Colors.grey),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    f.format(inv.grandTotal),
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  if (inv.isPartPaid)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'Due: ${f.format(inv.outstandingAmount)}',
                        style: const TextStyle(
                            fontSize: 11, color: Colors.blue),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _createInvoice([String? kind]) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => InvoiceFormScreen(
          kind: kind ?? _currentKind,
        ),
      ),
    );
  }

  Future<void> _submitInvoice(BuildContext ctx, Invoice inv) async {
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

  Future<void> _voidInvoice(BuildContext ctx, Invoice inv) async {
    final reason = await showDialog<String>(
      context: ctx,
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
}

class _InvoiceActionsMenu extends StatelessWidget {
  final Invoice invoice;
  final String kind;
  final Function(String action) onAction;

  const _InvoiceActionsMenu({
    required this.invoice,
    required this.kind,
    required this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Actions',
              style:
                  TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 12),
          if (invoice.isDraft)
            _menuItem('Submit', Icons.send, () => onAction('submit')),
if (widget.existing != null)
             _menuItem('Edit', Icons.edit, () {
               Navigator.push(
                 ctx,
                 MaterialPageRoute(
                   builder: (_) => InvoiceFormScreen(
                     existing: widget.invoice,
                     kind: kind,
                   ),
                 ),
               );
             })
          if (invoice.isSubmitted || invoice.isPartPaid)
            _menuItem('Void', Icons.block, () => onAction('void')),
          if (invoice.isDraft)
            _menuItem(
                'Delete', Icons.delete, () => onAction('delete')),
          _menuItem('Share', Icons.share, () {}),
          _menuItem('Print / PDF', Icons.print, () {}),
          _menuItem('Duplicate', Icons.copy, () {}),
        ],
      ),
    );
  }

  Widget _menuItem(String label, IconData icon, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            Icon(icon, size: 20, color: Colors.grey[700]),
            const SizedBox(width: 12),
            Text(label),
          ],
        ),
      ),
    );
  }
}