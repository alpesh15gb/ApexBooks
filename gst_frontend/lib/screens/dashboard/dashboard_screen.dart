import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppScaffold(
      title: 'Dashboard',
      currentIndex: 0,
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(invoiceListProvider('sales'));
          ref.invalidate(partyListProvider);
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Quick Stats
              _buildQuickStats(context),
              const SizedBox(height: 20),

              // Financial Overview Chart Placeholder
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Financial Overview',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 12),
                      _buildMiniChart(context),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 20),

              // Recent Invoices
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Recent Invoices',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold)),
                  TextButton(
                    onPressed: () => Navigator.pushNamed(context, '/invoices'),
                    child: const Text('View All'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              _buildRecentInvoices(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildQuickStats(BuildContext context) {
    final stats = [
      {'label': 'Total Sales', 'value': '\u20B94,52,000', 'icon': Icons.trending_up, 'color': const Color(0xFF10B981)},
      {'label': 'Pending', 'value': '\u20B912,500', 'icon': Icons.pending, 'color': const Color(0xFFFF6B35)},
      {'label': 'GST Payable', 'value': '\u20B98,200', 'icon': Icons.receipt_long, 'color': const Color(0xFF6366F1)},
      {'label': 'Parties', 'value': '156', 'icon': Icons.people, 'color': const Color(0xFFF59E0B)},
    ];

    return SizedBox(
      height: 120,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        itemCount: stats.length,
        itemBuilder: (ctx, i) {
          final s = stats[i];
          return Container(
            width: 140,
            margin: const EdgeInsets.only(right: 12),
            decoration: BoxDecoration(
              color: (s['color'] as Color).withOpacity(0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(s['icon'] as IconData, color: s['color'], size: 28),
                const SizedBox(height: 6),
                Text(s['value'] as String,
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.bold)),
                const SizedBox(height: 2),
                Text(s['label'] as String,
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildMiniChart(BuildContext context) {
    return Container(
      height: 150,
      alignment: Alignment.center,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: List.generate(12, (i) {
                final h = (i + 1) * 5.0 + 10;
                return Container(
                  width: 20,
                  height: h,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFF6B35).withOpacity(0.3 + i * 0.05),
                    borderRadius: BorderRadius.circular(4),
                  ),
                );
              }),
            ),
          ),
          const SizedBox(height: 4),
          const Text('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec',
              style: TextStyle(fontSize: 8, color: Colors.grey)),
        ],
      ),
    );
  }

  Widget _buildRecentInvoices(BuildContext context) {
    return Consumer(
      builder: (ctx, ref, _) {
        final invoicesAsync = ref.watch(invoiceListProvider('sales'));
        return invoicesAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Text('Error: $e'),
          data: (invoices) {
            if (invoices.isEmpty) {
              return const Center(child: Text('No invoices yet'));
            }
            return ListView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: invoices.length > 5 ? 5 : invoices.length,
              itemBuilder: (ctx, i) {
                final inv = invoices[i];
                return ListTile(
                  title: Text(inv.invoiceNumber),
                  subtitle: Text(
                      '${inv.invoiceKind.toUpperCase()} • ${inv.status} • ${inv.grandTotal}'),
                  trailing: Text('\u20B9${inv.grandTotal}'),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                );
              },
            );
          },
        );
      },
    );
  }
}