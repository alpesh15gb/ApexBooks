import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppScaffold(
      title: 'Admin Panel',
      currentIndex: 6,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('System Overview',
                style:
                    TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),

            // System Info Cards
            _buildSystemInfoRow(context),
            const SizedBox(height: 20),

            // Queue Monitor
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Background Jobs',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 12),
                    _buildJobStatusRow('Pending', 0, Colors.orange),
                    _buildJobStatusRow('Processing', 0, Colors.blue),
                    _buildJobStatusRow('Completed', 0, Colors.green),
                    _buildJobStatusRow('Failed', 0, Colors.red),
                    const Divider(),
                    _buildJobStatusRow('Total', 0, Colors.black,
                        isBold: true),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Recent Audit Logs
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Recent Audit Logs',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.bold)),
                        TextButton(
                          onPressed: () {
                            // TODO: Navigate to full audit log viewer
                          },
                          child: const Text('View All'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    _buildAuditLogItem('INVOICE_CREATED', 'INV-001',
                        'admin@example.com', '2 min ago'),
                    _buildAuditLogItem('INVOICE_SUBMITTED', 'INV-002',
                        'accountant@example.com', '15 min ago'),
                    _buildAuditLogItem('SETTINGS_UPDATED', 'gst',
                        'admin@example.com', '1 hour ago'),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSystemInfoRow(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _buildInfoCard('Tenants', '0', Icons.apartment),
        ),
        const SizedBox(width: 12),
        Expanded(
          child:
              _buildInfoCard('Invoices', '0', Icons.receipt_long),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildInfoCard('GL Entries', '0', Icons.account_balance),
        ),
      ],
    );
  }

  Widget _buildInfoCard(String label, String value, IconData icon) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Icon(icon, color: const Color(0xFFFF6B35), size: 28),
            const SizedBox(height: 8),
            Text(value,
                style: const TextStyle(
                    fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(label,
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ],
        ),
      ),
    );
  }

  Widget _buildJobStatusRow(
      String label, int count, Color color,
      {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: TextStyle(
                  fontWeight: isBold ? FontWeight.bold : FontWeight.normal)),
          Text('$count',
              style: TextStyle(
                  fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
                  color: color)),
        ],
      ),
    );
  }

  Widget _buildAuditLogItem(
      String action, String resource, String actor, String time) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 8,
            height: 8,
            margin: const EdgeInsets.only(top: 6, right: 12),
            decoration: const BoxDecoration(
                color: Color(0xFF10B981), shape: BoxShape.circle),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                RichText(
                  text: TextSpan(
                    style: const TextStyle(fontSize: 13),
                    children: [
                      TextSpan(
                          text: '$action ',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      TextSpan(
                          text: 'on $resource',
                          style: TextStyle(color: Colors.grey[600])),
                    ],
                  ),
                ),
                const SizedBox(height: 2),
                Text('$actor • $time',
                    style:
                        TextStyle(fontSize: 11, color: Colors.grey[500])),
              ],
            ),
          ),
        ],
      ),
    );
  }
}