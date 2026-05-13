import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:syncfusion_flutter_charts/charts.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class GstDashboardScreen extends ConsumerWidget {
  const GstDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppScaffold(
      title: 'GST Compliance',
      currentIndex: 4,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Quick GSTR Cards
            _buildGstrQuickActions(context),
            const SizedBox(height: 20),

            // Monthly GST Chart
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Monthly GST Collection',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 12),
                    SizedBox(
                      height: 200,
                      child: _buildGstBarChart(),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // GSTR-3B Summary
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('GSTR-3B Summary',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 12),
                    _buildGstr3bRow('IGST', 0, Colors.blue),
                    _buildGstr3bRow('CGST', 0, Colors.green),
                    _buildGstr3bRow('SGST', 0, Colors.orange),
                    _buildGstr3bRow('Cess', 0, Colors.purple),
                    const Divider(),
                    _buildGstr3bRow('Total Tax', 0, Colors.black,
                        isBold: true),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildGstrQuickActions(BuildContext context) {
    final actions = [
      {
        'icon': Icons.file_upload,
        'label': 'GSTR-1',
        'color': const Color(0xFF6366F1),
      },
      {
        'icon': Icons.receipt_long,
        'label': 'GSTR-3B',
        'color': const Color(0xFF10B981),
      },
      {
        'icon': Icons.assessment,
        'label': 'Reconcile',
        'color': const Color(0xFFF59E0B),
      },
      {
        'icon': Icons.description,
        'label': 'GSTR-9',
        'color': const Color(0xFFEF4444),
      },
    ];

    return SizedBox(
      height: 100,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        itemCount: actions.length,
        itemBuilder: (ctx, i) {
          final a = actions[i];
          return Container(
            width: 100,
            margin: const EdgeInsets.only(right: 12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () {
                // TODO: Navigate to respective GSTR screens
              },
              child: Card(
                color: (a['color'] as Color).withOpacity(0.1),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(a['icon'] as IconData,
                        color: a['color'] as Color, size: 32),
                    const SizedBox(height: 6),
                    Text(a['label'] as String,
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildGstBarChart() {
    return SfCartesianChart(
      primaryXAxis: const CategoryAxis(),
      primaryYAxis: const NumericAxis(
        labelFormat: '{value}k',
        axisLine: AxisLine(width: 0),
      ),
      series: <CartesianSeries>[
        ColumnSeries<Map<String, dynamic>, String>(
          dataSource: [
            {'month': 'Jan', 'igst': 45, 'cgst': 22, 'sgst': 22},
            {'month': 'Feb', 'igst': 52, 'cgst': 26, 'sgst': 26},
            {'month': 'Mar', 'igst': 48, 'cgst': 24, 'sgst': 24},
            {'month': 'Apr', 'igst': 61, 'cgst': 30, 'sgst': 30},
            {'month': 'May', 'igst': 55, 'cgst': 27, 'sgst': 27},
            {'month': 'Jun', 'igst': 42, 'cgst': 21, 'sgst': 21},
          ],
          xValueMapper: (data, _) => data['month'],
          yValueMapper: (data, _) => data['igst'],
          name: 'IGST',
          color: Colors.blue,
          width: 0.6,
          spacing: 0.1,
        ),
        ColumnSeries<Map<String, dynamic>, String>(
          dataSource: [
            {'month': 'Jan', 'igst': 45, 'cgst': 22, 'sgst': 22},
            {'month': 'Feb', 'igst': 52, 'cgst': 26, 'sgst': 26},
            {'month': 'Mar', 'igst': 48, 'cgst': 24, 'sgst': 24},
            {'month': 'Apr', 'igst': 61, 'cgst': 30, 'sgst': 30},
            {'month': 'May', 'igst': 55, 'cgst': 27, 'sgst': 27},
            {'month': 'Jun', 'igst': 42, 'cgst': 21, 'sgst': 21},
          ],
          xValueMapper: (data, _) => data['month'],
          yValueMapper: (data, _) => data['cgst'],
          name: 'CGST',
          color: const Color(0xFF10B981),
          width: 0.6,
          spacing: 0.1,
        ),
        ColumnSeries<Map<String, dynamic>, String>(
          dataSource: [
            {'month': 'Jan', 'igst': 45, 'cgst': 22, 'sgst': 22},
            {'month': 'Feb', 'igst': 52, 'cgst': 26, 'sgst': 26},
            {'month': 'Mar', 'igst': 48, 'cgst': 24, 'sgst': 24},
            {'month': 'Apr', 'igst': 61, 'cgst': 30, 'sgst': 30},
            {'month': 'May', 'igst': 55, 'cgst': 27, 'sgst': 27},
            {'month': 'Jun', 'igst': 42, 'cgst': 21, 'sgst': 21},
          ],
          xValueMapper: (data, _) => data['month'],
          yValueMapper: (data, _) => data['sgst'],
          name: 'SGST',
          color: const Color(0xFFFF6B35),
          width: 0.6,
          spacing: 0.1,
        ),
      ],
      legend: const Legend(isVisible: true),
      tooltipBehavior: TooltipBehavior(enable: true),
    );
  }

  Widget _buildGstr3bRow(String label, double amount, Color color,
      {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
              fontSize: isBold ? 16 : 14,
            ),
          ),
          Text(
            '\u20B9${amount.toStringAsFixed(2)}',
            style: TextStyle(
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
              fontSize: isBold ? 16 : 14,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}