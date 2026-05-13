import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/models/party.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/widgets/app_scaffold.dart';

/// Party list with Tally-style ledger cards
/// Shows party name, GSTIN, outstanding balance at a glance
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
        IconButton(
          icon: const Icon(Icons.search),
          onPressed: () {}, // TODO: search
        ),
      ],
      body: partiesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
        data: (parties) {
          if (parties.isEmpty) {
            return const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.people_outline, size: 64, color: Colors.grey),
                  SizedBox(height: 12),
                  Text('No parties yet'),
                  SizedBox(height: 8),
                ],
              ),
            );
          }

          // Summary bar (Vyapar style)
          final totalCredit =
              parties.fold(0.0, (s, p) => s + p.creditLimit);

          return Column(
            children: [
              Container(
                color: const Color(0xFFF0FDF4),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('${parties.length} parties',
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    Text('Total Credit: \u20B9${totalCredit.toStringAsFixed(2)}',
                        style: const TextStyle(
                            color: Color(0xFF10B981),
                            fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.all(8),
                  itemCount: parties.length,
                  itemBuilder: (ctx, i) => _buildPartyCard(ctx, parties[i]),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildPartyCard(BuildContext context, Party p) {
    final f = NumberFormat.currency(locale: 'en_IN', symbol: '\u20B9');
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: () => _showPartyForm(context, p),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              CircleAvatar(
                radius: 22,
                backgroundColor: p.isCustomer
                    ? const Color(0xFF10B981).withOpacity(0.15)
                    : const Color(0xFF6366F1).withOpacity(0.15),
                child: Text(
                  p.partyName[0].toUpperCase(),
                  style: TextStyle(
                    color: p.isCustomer
                        ? const Color(0xFF10B981)
                        : const Color(0xFF6366F1),
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(p.partyName,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Icon(Icons.badge, size: 12, color: Colors.grey[400]),
                        const SizedBox(width: 3),
                        Text(
                          '${p.partyType}${p.gstin != null ? " • ${p.gstin}" : ""}',
                          style: const TextStyle(
                              fontSize: 11, color: Colors.grey),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                    if (p.creditLimit > 0) ...[
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Icon(Icons.account_balance_wallet,
                              size: 12, color: Colors.grey[400]),
                          const SizedBox(width: 3),
                          Text('Limit: ${f.format(p.creditLimit)}  •  ${p.creditDays} days',
                              style: const TextStyle(
                                  fontSize: 11, color: Colors.grey)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(f.format(p.openingBalance),
                      style: const TextStyle(
                          fontWeight: FontWeight.bold, fontSize: 14)),
                  Text(
                    p.isCustomer ? 'Receive' : 'Pay',
                    style: TextStyle(
                        fontSize: 10,
                        color: p.isCustomer ? Colors.green : Colors.red),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showPartyForm(BuildContext context, Party? party) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      enableDrag: true,
      showDragHandle: true,
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
  final _creditDaysCtrl = TextEditingController();
  String _type = 'Customer';

  @override
  void initState() {
    super.initState();
    if (widget.party != null) {
      _nameCtrl.text = widget.party!.partyName;
      _gstinCtrl.text = widget.party!.gstin ?? '';
      _panCtrl.text = widget.party!.pan ?? '';
      _creditLimitCtrl.text =
          widget.party!.creditLimit > 0
              ? widget.party!.creditLimit.toString()
              : '';
      _creditDaysCtrl.text =
          widget.party!.creditDays > 0
              ? widget.party!.creditDays.toString()
              : '';
      _type = widget.party!.partyType;
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _gstinCtrl.dispose();
    _panCtrl.dispose();
    _creditLimitCtrl.dispose();
    _creditDaysCtrl.dispose();
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
            const SizedBox(height: 20),
            DropdownButtonFormField<String>(
              value: _type,
              items: ['Customer', 'Supplier']
                  .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                  .toList(),
              onChanged: (v) => setState(() => _type = v!),
              decoration: const InputDecoration(
                  labelText: 'Party Type', border: InputBorder.none),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _nameCtrl,
              decoration: const InputDecoration(
                  labelText: 'Party Name *',
                  prefixIcon: Icon(Icons.person),
                  border: InputBorder.none),
              validator: (v) =>
                  v == null || v.isEmpty ? 'Required' : null,
            ),
            Container(
              height: 1,
              color: Colors.grey[200],
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _gstinCtrl,
              decoration: const InputDecoration(
                  labelText: 'GSTIN (optional)',
                  prefixIcon: Icon(Icons.badge),
                  border: InputBorder.none),
              maxLength: 15,
              textCapitalization: TextCapitalization.characters,
            ),
            Container(
              height: 1,
              color: Colors.grey[200],
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _panCtrl,
              decoration: const InputDecoration(
                  labelText: 'PAN (optional)',
                  prefixIcon: Icon(Icons.credit_card),
                  border: InputBorder.none),
              maxLength: 10,
              textCapitalization: TextCapitalization.characters,
            ),
            Container(
              height: 1,
              color: Colors.grey[200],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _creditLimitCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Credit Limit',
                        prefixText: '\u20B9',
                        prefixIcon:
                            Icon(Icons.account_balance_wallet),
                        border: InputBorder.none),
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _creditDaysCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Credit Days',
                        suffixText: 'days',
                        prefixIcon: Icon(Icons.calendar_today),
                        border: InputBorder.none),
                    keyboardType: TextInputType.number,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: () {
                  if (_formKey.currentState!.validate()) {
                    // TODO: Submit party
                    Navigator.pop(context);
                  }
                },
                child: Text(
                    widget.party != null ? 'UPDATE PARTY' : 'CREATE PARTY'),
              ),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}