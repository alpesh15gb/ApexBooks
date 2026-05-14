import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/services/api_service.dart';
import 'package:gst_frontend/core/models/audit_log.dart';
import 'package:gst_frontend/core/models/background_job.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';
import 'package:intl/intl.dart';

class AdminDashboardScreen extends ConsumerStatefulWidget {
  const AdminDashboardScreen({super.key});

  @override
  ConsumerState<AdminDashboardScreen> createState() =>
      _AdminDashboardScreenState();
}

class _AdminDashboardScreenState extends ConsumerState<AdminDashboardScreen> {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final systemInfoAsync = ref.watch(systemInfoProvider);
    final auditLogsAsync = ref.watch(auditLogsProvider());
    final jobsAsync = ref.watch(backgroundJobsProvider());

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
            systemInfoAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text('Error: $e'),
              data: (info) => _buildSystemInfoRow(context, info),
            ),
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
                    jobsAsync.when(
                      loading: () =>
                          const Center(child: CircularProgressIndicator()),
                      error: (e, _) => Text('Error: $e'),
                      data: (jobs) {
                        final pending =
                            jobs.where((j) => j.status == 'pending').length;
                        final processing =
                            jobs.where((j) => j.status == 'processing').length;
                        final completed =
                            jobs.where((j) => j.status == 'completed').length;
                        final failed =
                            jobs.where((j) => j.status == 'failed').length;
                        return Column(
                          children: [
                            _buildJobStatusRow(
                                'Pending', pending, Colors.orange),
                            _buildJobStatusRow(
                                'Processing', processing, Colors.blue),
                            _buildJobStatusRow(
                                'Completed', completed, Colors.green),
                            _buildJobStatusRow(
                                'Failed', failed, Colors.red),
                            const Divider(),
                            _buildJobStatusRow('Total', jobs.length,
                                Colors.black, isBold: true),
                          ],
                        );
                      },
                    ),
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
                    auditLogsAsync.when(
                      loading: () =>
                          const Center(child: CircularProgressIndicator()),
                      error: (e, _) => Text('Error: $e'),
                      data: (logs) {
                        final recent = logs.take(5).toList();
                        return Column(
                          children: recent.map((log) => Padding(
                            padding:
                                const EdgeInsets.symmetric(vertical: 6),
                            child: Row(
                              crossAxisAlignment:
                                  CrossAxisAlignment.start,
                              children: [
                                Container(
                                  width: 8,
                                  height: 8,
                                  margin: const EdgeInsets.only(
                                      top: 6, right: 12),
                                  decoration: const BoxDecoration(
                                      color: Color(0xFF10B981),
                                      shape: BoxShape.circle),
                                ),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      RichText(
                                        text: TextSpan(
                                          style:
                                              const TextStyle(fontSize: 13),
                                          children: [
                                            TextSpan(
                                                text: '${log.action} ',
                                                style: const TextStyle(
                                                    fontWeight:
                                                        FontWeight.w600)),
                                            TextSpan(
                                                text:
                                                    'on ${log.resource}',
                                                style: TextStyle(
                                                    color: Colors.grey[600])),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                          '${log.actorId} • ${log.createdAt != null ? DateFormat('dd MMM yyyy HH:mm').format(log.createdAt!) : 'unknown'}',
                                          style: TextStyle(
                                              fontSize: 11,
                                              color: Colors.grey[500])),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          )).toList(),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSystemInfoRow(BuildContext context, SystemInfo info) {
    return Row(
      children: [
        Expanded(
          child: _buildInfoCard(
              '${info.totalTenants}', 'Tenants', Icons.apartment),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildInfoCard(
              '${info.totalInvoices}', 'Invoices', Icons.receipt_long),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildInfoCard(
              '${info.totalGlEntries}', 'GL Entries', Icons.account_balance),
        ),
      ],
    );
  }

  Widget _buildInfoCard(String value, String label, IconData icon) {
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
                style:
                    const TextStyle(fontSize: 12, color: Colors.grey)),
          ],
        ),
      ),
    );
  }

  Widget _buildJobStatusRow(String label, int count, Color color,
      {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: TextStyle(
                  fontWeight:
                      isBold ? FontWeight.bold : FontWeight.normal)),
          Text('$count',
              style: TextStyle(
                  fontWeight:
                      isBold ? FontWeight.bold : FontWeight.normal,
                  color: color)),
        ],
      ),
    );
  }
}