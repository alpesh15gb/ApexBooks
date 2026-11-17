import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../inventory/inventory_models.dart';

/// One customer with overdue invoices (the web app's `overdueByParty` group).
class OverdueGroup {
  OverdueGroup(this.name, this.phone);
  final String name;
  String phone;
  final invoices = <Json>[];
  num total = 0;
  String get key => name.trim().toLowerCase();
}

const _titles = {
  'sales_invoice': 'Invoice',
  'pos': 'Bill',
  'estimate': 'Estimate',
  'proforma': 'Proforma invoice',
  'sales_order': 'Sales order',
  'credit_note': 'Credit note',
  'payment_in': 'Payment receipt',
  'purchase_order': 'Purchase order',
  'purchase_bill': 'Bill',
  'payment_out': 'Payment',
  'debit_note': 'Debit note',
};

String _rupees(Object? value) => apexMoney(apexNumber(value) ?? 0);

/// Digits WhatsApp accepts, or '' when the saved phone is not usable.
String whatsappPhone(Object? value) {
  final digits = inventoryText(value).replaceAll(RegExp(r'\D'), '').replaceFirst(RegExp(r'^0+'), '');
  if (digits.length == 10) return '91$digits';
  return digits.length >= 11 && digits.length <= 15 ? digits : '';
}

String _partyPhone(Json record, List<Json> records) {
  final data = inventoryObject(record['data']);
  final id = inventoryText(data['party_id']);
  final name = inventoryText(record['name']).trim().toLowerCase();
  for (final row in records) {
    if (row['kind'] != 'party') continue;
    if (id.isNotEmpty ? row['id'] == id : inventoryText(row['name']).trim().toLowerCase() == name) {
      final phone = inventoryText(inventoryObject(row['data'])['phone']);
      if (phone.isNotEmpty) return phone;
      break;
    }
  }
  return inventoryText(data['phone']).isNotEmpty ? inventoryText(data['phone']) : inventoryText(data['party_phone']);
}

bool _canRemind(Json record) =>
    (record['kind'] == 'sales_invoice' || record['kind'] == 'pos') &&
    record['posted'] == true &&
    record['cancelled'] != true &&
    (apexNumber(record['outstanding']) ?? 0) > 0;

/// Customers with a posted invoice past its due date and a balance, largest balance first.
List<OverdueGroup> overdueByParty(List<Json> records, String today) {
  final groups = <String, OverdueGroup>{};
  for (final record in records) {
    final due = inventoryText(inventoryObject(record['data'])['due_date']);
    if (!_canRemind(record) || due.isEmpty || due.compareTo(today) >= 0) continue;
    final key = inventoryText(record['name']).trim().toLowerCase();
    final group = groups.putIfAbsent(
      key,
      () => OverdueGroup(inventoryText(record['name']), _partyPhone(record, records)),
    );
    group.invoices.add(record);
    group.total += apexNumber(record['outstanding']) ?? 0;
    if (group.phone.isEmpty) group.phone = _partyPhone(record, records);
  }
  return groups.values.toList()..sort((a, b) => b.total.compareTo(a.total));
}

String partyReminderMessage(OverdueGroup group, String companyName, String upi) {
  final lines = [
    'Dear ${group.name.isEmpty ? 'Customer' : group.name},',
    'This is a gentle reminder that ${_rupees(group.total)} is overdue:',
    for (final invoice in group.invoices)
      '• ${_titles[invoice['kind']] ?? 'Invoice'} ${invoice['number']} dated ${invoice['date']}: ${_rupees(invoice['outstanding'])} (due ${inventoryObject(invoice['data'])['due_date']})',
    if (upi.isNotEmpty) 'You can pay by UPI: $upi',
    'Please ignore if already paid.\n– $companyName',
  ];
  return lines.join('\n');
}

String whatsappUrl(String phone, String text) =>
    'https://wa.me/${whatsappPhone(phone)}?text=${Uri.encodeComponent(text)}';

/// Opens WhatsApp with the message filled in. Where the platform cannot open a link from here the
/// message is copied instead, so it can be pasted into the chat. Nothing is sent from the app.
Future<bool> openWhatsApp(String url, String message) async {
  try {
    if (!kIsWeb) {
      if (Platform.isWindows) {
        await Process.start('rundll32', ['url.dll,FileProtocolHandler', url]);
        return true;
      }
      if (Platform.isMacOS) {
        await Process.start('open', [url]);
        return true;
      }
      if (Platform.isLinux) {
        await Process.start('xdg-open', [url]);
        return true;
      }
    }
  } catch (_) {}
  await Clipboard.setData(ClipboardData(text: message));
  return false;
}

/// "Remind overdue customers": WhatsApp opens one customer at a time; nothing is sent until you press
/// send there.
class OverdueRemindersDialog extends StatefulWidget {
  const OverdueRemindersDialog({required this.workspace, required this.records, this.opener = openWhatsApp, super.key});
  final WorkspaceContext workspace;
  final List<Json> records;
  final Future<bool> Function(String url, String message) opener;

  @override
  State<OverdueRemindersDialog> createState() => _OverdueRemindersDialogState();
}

class _OverdueRemindersDialogState extends State<OverdueRemindersDialog> {
  String _upi = '';
  final _sent = <String>{};
  late final List<OverdueGroup> _groups;

  @override
  void initState() {
    super.initState();
    _groups = overdueByParty(widget.records, businessDate());
    _loadBranding();
  }

  Future<void> _loadBranding() async {
    try {
      final branding = inventoryObject(await widget.workspace.api.get('${widget.workspace.path}/document-branding'));
      if (mounted) setState(() => _upi = inventoryText(branding['upi_id']));
    } catch (_) {}
  }

  Future<void> _remind(OverdueGroup group) async {
    final message = partyReminderMessage(group, widget.workspace.company.name, _upi);
    final opened = await widget.opener(whatsappUrl(group.phone, message), message);
    if (!mounted) return;
    setState(() => _sent.add(group.key));
    if (!opened) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Reminder copied. Paste it into WhatsApp to send.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final phone = MediaQuery.sizeOf(context).width < 600;
    final total = _groups.fold<num>(0, (sum, group) => sum + group.total);
    final count = _groups.length;
    return Dialog(
      insetPadding: phone ? const EdgeInsets.all(12) : const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(phone ? 18 : 26, 22, phone ? 10 : 18, 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Remind overdue customers', style: Apex.panelTitle.copyWith(fontSize: 21)),
                        const SizedBox(height: 4),
                        Text(
                          '$count ${count == 1 ? 'customer' : 'customers'} · ${apexMoney(total)} overdue · one WhatsApp message each',
                          style: const TextStyle(fontSize: 13, color: Apex.muted),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close_rounded, size: 20),
                  ),
                ],
              ),
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: EdgeInsets.fromLTRB(phone ? 18 : 26, 10, phone ? 18 : 26, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_groups.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 26),
                        child: Column(
                          children: [
                            Text('No overdue invoices', style: Apex.strong),
                            SizedBox(height: 4),
                            Text('Invoices past their due date with a balance appear here.', style: Apex.note),
                          ],
                        ),
                      ),
                    for (final group in _groups) _row(group),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(phone ? 18 : 26, 6, phone ? 18 : 26, 22),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Apex.tint,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Apex.line),
                ),
                child: const Padding(
                  padding: EdgeInsets.all(14),
                  child: Text(
                    'WhatsApp opens with the message filled in. Customers without a saved phone open WhatsApp so you can pick the chat.',
                    style: TextStyle(fontSize: 13, height: 1.5, color: Apex.muted),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(OverdueGroup group) {
    final sent = _sent.contains(group.key);
    final numbers = group.invoices.map((invoice) => inventoryText(invoice['number'])).join(', ');
    final info = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(group.name, style: Apex.strong.copyWith(fontSize: 14)),
        const SizedBox(height: 2),
        Text(
          '$numbers${whatsappPhone(group.phone).isEmpty ? ' · no phone saved' : ''}',
          style: Apex.small.copyWith(fontSize: 12),
        ),
      ],
    );
    final button = sent
        ? OutlinedButton.icon(
            onPressed: () => _remind(group),
            icon: const Icon(Icons.check_circle_outline, size: 15),
            label: const Text('Opened'),
          )
        : FilledButton.icon(
            onPressed: () => _remind(group),
            icon: const Icon(Icons.notifications_active_outlined, size: 15),
            label: const Text('Remind'),
          );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Apex.lineSoft))),
      child: Row(
        children: [
          Expanded(child: info),
          const SizedBox(width: 10),
          Text(
            apexMoney(group.total),
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Apex.ink),
          ),
          const SizedBox(width: 12),
          button,
        ],
      ),
    );
  }
}
