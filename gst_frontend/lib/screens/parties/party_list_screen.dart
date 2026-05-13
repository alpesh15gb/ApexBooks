import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/models/party.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

class PartyListScreen extends ConsumerWidget {
  const PartyListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final partiesAsync = ref.watch(partyListProvider);

    return AppScaffold(
      title: 'Parties',
      currentIndex: 2,
      actions: [
        IconButton(
          icon: const Icon(Icons.add),
          onPressed: () => _showPartyForm(context, null),
        ),
      ],
      body: partiesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (parties) {
          if (parties.isEmpty) {
            return const Center(child: Text('No parties yet. Add one!'));
          }
          return ListView.builder(
            padding: const EdgeInsets.all(8),
            itemCount: parties.length,
            itemBuilder: (ctx, i) {
              final p = parties[i];
              return Card(
                margin: const EdgeInsets.symmetric(vertical: 4),
                child: ListTile(
                  leading: CircleAvatar(
                    child: Text(
                      p.partyName[0].toUpperCase(),
                      style: const TextStyle(color: Colors.white),
                    ),
                    backgroundColor: p.isCustomer
                        ? const Color(0xFF10B981)
                        : const Color(0xFF6366F1),
                  ),
                  title: Text(p.partyName),
                  subtitle: Text(
                    '${p.partyType}${p.gstin != null ? " • ${p.gstin}" : ""}',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _showPartyForm(context, p),
                ),
              );
            },
          );
        },
      ),
    );
  }

  void _showPartyForm(BuildContext context, Party? party) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => _PartyForm(party: party),
    );
  }
}

class _PartyForm extends StatefulWidget {
  final Party? party;

  const _PartyForm({this.party});

  @override
  State<_PartyForm> createState() => _PartyFormState();
}

class _PartyFormState extends State<_PartyForm> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _gstinCtrl = TextEditingController();
  final _panCtrl = TextEditingController();
  final _creditLimitCtrl = TextEditingController();
  String _type = 'Customer';

  @override
  void initState() {
    super.initState();
    if (widget.party != null) {
      _nameCtrl.text = widget.party!.partyName;
      _gstinCtrl.text = widget.party!.gstin ?? '';
      _panCtrl.text = widget.party!.pan ?? '';
      _creditLimitCtrl.text = widget.party!.creditLimit.toString();
      _type = widget.party!.partyType;
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _gstinCtrl.dispose();
    _panCtrl.dispose();
    _creditLimitCtrl.dispose();
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
            Text(
              widget.party != null ? 'Edit Party' : 'New Party',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              value: _type,
              items: ['Customer', 'Supplier']
                  .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                  .toList(),
              onChanged: (v) => setState(() => _type = v!),
              decoration: const InputDecoration(labelText: 'Party Type'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _nameCtrl,
              decoration:
                  const InputDecoration(labelText: 'Party Name'),
              validator: (v) =>
                  v == null || v.isEmpty ? 'Required' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _gstinCtrl,
              decoration:
                  const InputDecoration(labelText: 'GSTIN'),
              maxLength: 15,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _panCtrl,
              decoration:
                  const InputDecoration(labelText: 'PAN'),
              maxLength: 10,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _creditLimitCtrl,
              decoration: const InputDecoration(
                  labelText: 'Credit Limit', prefixText: '\u20B9'),
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: () {
                  if (_formKey.currentState!.validate()) {
                    // TODO: Submit party via API
                    Navigator.pop(context);
                  }
                },
                child: Text(widget.party != null ? 'UPDATE' : 'CREATE'),
              ),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}