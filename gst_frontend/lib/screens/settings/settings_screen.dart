import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppScaffold(
      title: 'Settings',
      currentIndex: 5,
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildSettingsCard(
            context,
            'Business',
            Icons.business,
            '/settings/business',
          ),
          _buildSettingsCard(
            context,
            'GST Configuration',
            Icons.receipt_long,
            '/settings/gst',
          ),
          _buildSettingsCard(
            context,
            'E-Invoice',
            Icons.cloud_upload,
            '/settings/einvoice',
          ),
          _buildSettingsCard(
            context,
            'E-Way Bill',
            Icons.local_shipping,
            '/settings/ewaybill',
          ),
          _buildSettingsCard(
            context,
            'Invoice Numbering',
            Icons.format_list_numbered,
            '/settings/numbering',
          ),
          _buildSettingsCard(
            context,
            'Notifications',
            Icons.notifications,
            '/settings/notifications',
          ),
          _buildSettingsCard(
            context,
            'Integrations',
            Icons.extension,
            '/settings/integrations',
          ),
          const SizedBox(height: 20),
          _buildInfoCard(context),
        ],
      ),
    );
  }

  Widget _buildSettingsCard(
    BuildContext context,
    String title,
    IconData icon,
    String route,
  ) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFFF6B35).withOpacity(0.1),
          child: Icon(icon, color: const Color(0xFFFF6B35)),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        trailing: const Icon(Icons.chevron_right),
        onTap: () {
          // TODO: Navigate to detail forms
        },
      ),
    );
  }

  Widget _buildInfoCard(BuildContext context) {
    return Card(
      color: const Color(0xFFF0FDF4),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            const Icon(Icons.info_outline, color: Color(0xFF10B981)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('API Status',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(
                    'Connected to GST API Engine v0.2.0',
                    style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}