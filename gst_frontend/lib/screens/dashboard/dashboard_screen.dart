import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:syncfusion_flutter_charts/charts.dart';
import 'package:intl/intl.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/core/models/invoice.dart';
import 'package:gst_frontend/core/models/system_info.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final salesAsync = ref.watch(invoiceListProvider('sales'));
    final purchaseAsync = ref.watch(invoiceListProvider('purchase'));

    return AppScaffold(
      title: 'Dashboard',
      currentIndex: 0,
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(invoiceListProvider('sales'));
          ref.invalidate(invoiceListProvider('purchase'));
          ref.invalidate(partyListProvider);
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Greeting
              _buildGreeting(),
              const SizedBox(height: 20),

              // Quick Stats Cards (Khatabook/Vyapar style)
              _buildQuickStats(context, salesAsync, purchaseAsync),
              const SizedBox(height: 20),

              // Revenue Chart (Zoho style)
              _buildRevenueChart(context, salesAsync),
              const SizedBox(height: 20),

              // Receivables / Payables (Tally style)
              _buildReceivablesPayables(context, salesAsync, purchaseAsync),
              const SizedBox(height: 20),

              // Quick Actions (Tally Gateway style)
              _buildQuickActions(context),
              const SizedBox(height: 20),

              // Recent Transactions (Busy/Vyapar style)
              _buildRecentTransactions(context, salesAsync),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildGreeting() {
    final hour = DateTime.now().hour;
    final greeting = hour < 12
        ? 'Good Morning'
        : hour < 17
            ? 'Good Afternoon'
            : 'Good Evening';
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(greeting,
                style: const TextStyle(
                    fontSize: 24, fontWeight: FontWeight.bold)),
            const Text('Here\'s your business summary',
                style: TextStyle(color: Colors.grey)),
          ],
        ),
        CircleAvatar(
          radius: 24,
          backgroundColor: const Color(0xFFFF6B35).withOpacity(0.1),
          child: const Icon(Icons.person, color: Color(0xFFFF6B35)),
        ),
      ],
    );
  }

  Widget _buildQuickStats(
    BuildContext context,
    AsyncValue<List<Invoice>> salesAsync,
    AsyncValue<List<Invoice>> purchaseAsync,
  ) {
    double salesTotal = 0, purchaseTotal = 0, receivables = 0, payables = 0;

    if (salesAsync.hasValue) {
      for (final inv in salesAsync.value!) {
        if (inv.isSubmitted || inv.isPartPaid) {
          salesTotal += inv.grandTotal;
          if (inv.isPartPaid) receivables += inv.outstandingAmount;
          else receivables += inv.grandTotal;
        }
      }
    }
    if (purchaseAsync.hasValue) {
      for (final inv in purchaseAsync.value!) {
        if (inv.isSubmitted || inv.isPartPaid) {
          purchaseTotal += inv.grandTotal;
          if (inv.isPartPaid) payables += inv.outstandingAmount;
          else payables += inv.grandTotal;
        }
      }
    }

    final f = NumberFormat.currency(locale: 'en_IN', symbol: '\u20B9');
    final stats = [
      {'label': 'Sales', 'value': f.format(salesTotal), 'icon': Icons.trending_up, 'color': const Color(0xFF10B981)},
      {'label': 'Purchases', 'value': f.format(purchaseTotal), 'icon': Icons.shopping_cart, 'color': const Color(0xFF6366F1)},
      {'label': 'Receivables', 'value': f.format(receivables), 'icon': Icons.account_balance_wallet, 'color': const Color(0xFFF59E0B)},
      {'label': 'Payables', 'value': f.format(payables), 'icon': Icons.payment, 'color': const Color(0xFFEF4444)},
    ];

    return SizedBox(
      height: 140,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        itemCount: stats.length,
        itemBuilder: (ctx, i) {
          final s = stats[i];
          return Container(
            width: 155,
            margin: const EdgeInsets.only(right: 12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  (s['color'] as Color).withOpacity(0.15),
                  (s['color'] as Color).withOpacity(0.05),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: (s['color'] as Color).withOpacity(0.2)),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(s['icon'] as IconData, color: s['color'] as Color, size: 28),
                const SizedBox(height: 8),
                Text(s['value'] as String,
                    style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                        overflow: TextOverflow.ellipsis)),
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

  Widget _buildRevenueChart(
      BuildContext context, AsyncValue<List<Invoice>> salesAsync) {
    // Monthly data (last 6 months)
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
    final values = [42000, 55000, 38000, 62000, 48000, 51000];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Sales Overview',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            SizedBox(
              height: 180,
              child: SfCartesianChart(
                primaryXAxis: CategoryAxis(
                  majorGridLines: const MajorGridLines(width: 0),
                ),
                primaryYAxis: NumericAxis(
                  labelFormat: '{value}k',
                  axisLine: const AxisLine(width: 0),
                  majorTickLines: const MajorTickLines(size: 0),
                ),
                series: <CartesianSeries>[
                  AreaSeries<Map<String, dynamic>, String>(
                    dataSource: List.generate(6, (i) => {
                      'month': months[i],
                      'sales': values[i],
                    }),
                    xValueMapper: (data, _) => data['month'],
                    yValueMapper: (data, _) => data['sales'],
                    gradient: LinearGradient(colors: [
                      const Color(0xFFFF6B35),
                      const Color(0xFFFF6B35).withOpacity(0.1),
                    ]),
                    borderColor: const Color(0xFFFF6B35),
                    borderWidth: 2,
                  ),
                ],
                tooltipBehavior: TooltipBehavior(enable: true),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildReceivablesPayables(
    BuildContext context,
    AsyncValue<List<Invoice>> salesAsync,
    AsyncValue<List<Invoice>> purchaseAsync,
  ) {
    return Row(
      children: [
        Expanded(
          child: Card(
            color: const Color(0xFFF0FDF4),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  const Icon(Icons.account_balance_wallet,
                      color: Color(0xFF10B981), size: 32),
                  const SizedBox(height: 8),
                  const Text('You Receive',
                      style: TextStyle(color: Colors.grey, fontSize: 12)),
                  const SizedBox(height: 4),
                  const Text('\u20B945,200',
                      style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF10B981))),
                  const SizedBox(height: 4),
                  GestureDetector(
onTap: () => Navigator.pushNamed(context, '/payments'),
                     child: const Text('3 pending →',
                        style: TextStyle(
                            color: Color(0xFF10B981), fontSize: 12)),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Card(
            color: const Color(0xFFFEF2F2),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  const Icon(Icons.payment, color: Color(0xFFEF4444), size: 32),
                  const SizedBox(height: 8),
                  const Text('You Pay',
                      style: TextStyle(color: Colors.grey, fontSize: 12)),
                  const SizedBox(height: 4),
                  const Text('\u20B912,500',
                      style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFFEF4444))),
                  const SizedBox(height: 4),
                  GestureDetector(
onTap: () => Navigator.pushNamed(context, '/payments'),
                     child: const Text('1 pending →',
                        style: TextStyle(
                            color: Color(0xFFEF4444), fontSize: 12)),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    final actions = [
      {'icon': Icons.receipt_long, 'label': 'New Sale', 'color': const Color(0xFF10B981)},
      {'icon': Icons.shopping_cart, 'label': 'New Purchase', 'color': const Color(0xFF6366F1)},
      {'icon': Icons.payment, 'label': 'Receive', 'color': const Color(0xFFF59E0B)},
      {'icon': Icons.file_upload, 'label': 'File GST', 'color': const Color(0xFFFF6B35)},
      {'icon': Icons.add_card, 'label': 'New Party', 'color': const Color(0xFF3B82F6)},
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Quick Actions',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: actions.map((a) {
                return InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: () {
                    switch (a['label']) {
case 'New Sale':
                         Navigator.pushNamed(context, '/invoices');
                         break;
                       case 'New Purchase':
                         Navigator.pushNamed(context, '/invoices', arguments: 'purchase');
                         break;
                    }
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(
                      color: (a['color'] as Color).withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        Icon(a['icon'] as IconData,
                            color: a['color'] as Color, size: 24),
                        const SizedBox(height: 4),
                        Text(a['label'] as String,
                            style: TextStyle(
                                fontSize: 11,
                                color: a['color'] as Color,
                                fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRecentTransactions(
      BuildContext context, AsyncValue<List<Invoice>> salesAsync) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Recent Transactions',
                    style: TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
                TextButton(
                  onPressed: () => Navigator.pushNamed(context, '/invoices'),
                  child: const Text('View All'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            salesAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text('Error: $e'),
              data: (invoices) {
                final recent = invoices.take(5).toList();
                if (recent.isEmpty) {
                  return const Center(
                      child: Padding(
                    padding: EdgeInsets.all(32),
                    child: Text('No transactions yet'),
                  ));
                }
                return ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: recent.length,
                  itemBuilder: (ctx, i) {
                    final inv = recent[i];
                    final statusColor = inv.isSubmitted
                        ? Colors.green
                        : inv.isCancelled
                            ? Colors.red
                            : Colors.orange;
                    return ListTile(
                      leading: CircleAvatar(
                        backgroundColor:
                            const Color(0xFFFF6B35).withOpacity(0.1),
                        child: Icon(
                          inv.isSales
                              ? Icons.arrow_circle_up
                              : Icons.arrow_circle_down,
                          color: const Color(0xFFFF6B35),
                        ),
                      ),
                      title: Text(inv.invoiceNumber),
                      subtitle: Text(
                          '${inv.invoiceKind.toUpperCase()} • ${inv.status} • ${DateFormat('dd MMM yyyy').format(inv.invoiceDate)}'),
                      trailing: Text(
                          '\u20B9${inv.grandTotal.toStringAsFixed(2)}',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold)),
                    );
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}