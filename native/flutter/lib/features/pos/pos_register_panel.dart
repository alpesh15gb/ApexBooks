import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'pos_models.dart';
import 'pos_register_controller.dart';
import 'pos_register_models.dart';
import 'pos_widgets.dart';

class PosRegisterPanel extends StatefulWidget {
  const PosRegisterPanel({
    required this.register,
    required this.checkoutBusy,
    super.key,
  });

  final PosRegisterController register;
  final bool checkoutBusy;

  @override
  State<PosRegisterPanel> createState() => _PosRegisterPanelState();
}

class _PosRegisterPanelState extends State<PosRegisterPanel> {
  final _amount = TextEditingController();
  final _reason = TextEditingController();
  RegisterOperation? _form;
  String _direction = 'in';
  PosRegisterController get register => widget.register;
  bool get writable => register.writable && !widget.checkoutBusy;

  @override
  void dispose() {
    _amount.dispose();
    _reason.dispose();
    super.dispose();
  }

  void _select(RegisterOperation? action) {
    setState(() {
      _amount.clear();
      _reason.clear();
      _form = action;
    });
  }

  @override
  Widget build(BuildContext context) {
    final active = register.active;
    final overview = register.overview;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _section([
          Wrap(
            spacing: 12,
            runSpacing: 10,
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.start,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 12,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        const Text(
                          'Register session',
                          style: TextStyle(
                            fontFamily: Apex.display,
                            fontSize: 22,
                            fontWeight: FontWeight.w600,
                            letterSpacing: -.5,
                            color: Apex.ink,
                          ),
                        ),
                        if (overview != null)
                          ApexStatusBadge(
                            active == null ? 'Closed' : 'Open',
                            tone: active == null
                                ? ApexBadgeTone.neutral
                                : ApexBadgeTone.posted,
                          ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'One shared drawer for this company. POS sales and linked refunds posted while it is open enter this session.',
                      style: TextStyle(
                        fontSize: 13,
                        height: 1.5,
                        color: PosColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
              OutlinedButton.icon(
                onPressed: register.busy || register.refreshing
                    ? null
                    : register.refresh,
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('Refresh register'),
              ),
            ],
          ),
          if (register.refreshing || register.busy)
            const LinearProgressIndicator(),
          if (register.message case final message?) _notice(message),
          if (register.loadError case final error?) _notice(error),
          if (register.recoveryError case final error?) ...[
            _notice(error),
            OutlinedButton(
              onPressed: register.recover,
              child: const Text('Check saved activity'),
            ),
          ],
          if (register.pending case final pending?) ...[
            _notice(switch (pending.action) {
              RegisterOperation.open =>
                'Confirm the original opening before opening another register.',
              RegisterOperation.movement =>
                'Confirm the original cash movement before recording it again.',
              RegisterOperation.close => 'Confirm the original closing count before closing the register again.',
            }),
            FilledButton.icon(
              onPressed: register.canWrite && !register.busy
                  ? register.retry
                  : null,
              icon: const Icon(Icons.replay),
              label: const Text('Retry original action'),
            ),
          ],
          if (!register.canWrite)
            _notice('View-only access to register activity.'),
          if (widget.checkoutBusy && register.canWrite)
            _notice(
              'Resolve the saved checkout or return before changing the register.',
            ),
          if (overview != null && active == null) ...[
            Text(
              'No register session is open',
              style: theme.textTheme.titleMedium,
            ),
            if (register.canWrite && register.pending == null) _openForm(),
          ],
          if (active != null) ...[
            _activeSummary(active),
            if (register.canWrite && register.pending == null)
              _activeActions(active),
          ],
        ]),
        if (overview != null && overview.closed.isNotEmpty) ...[
          const SizedBox(height: 14),
          _section([
            const PosPanelHeading('Recent closes'),
            for (final closed in overview.closed) _closedSummary(closed),
          ]),
        ],
      ],
    );
  }

  Widget _section(List<Widget> children) =>
      PosPanel(spacing: 12, children: children);

  Widget _notice(String message) =>
      Semantics(liveRegion: true, child: Text(message));

  Widget _openForm() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      _moneyField('Opening float (₹)'),
      const SizedBox(height: 12),
      FilledButton(
        onPressed: writable && register.validateOpen(_amount.text) == null
            ? () => register.open(_amount.text)
            : null,
        child: const Text('Open register'),
      ),
    ],
  );

  Widget _activeSummary(PosRegisterSession active) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Register open · ${active.date}',
          style: theme.textTheme.titleMedium,
        ),
        const SizedBox(height: 10),
        DecoratedBox(
          decoration: BoxDecoration(
            color: PosColors.wash,
            border: Border.all(color: PosColors.totalBorder),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Expected cash',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: PosColors.totalText,
                  ),
                ),
                Text(
                  registerMoneyText(active.expected),
                  style: const TextStyle(
                    fontFamily: Apex.display,
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -.7,
                    color: PosColors.totalText,
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        _total('Opening cash', active.opening),
        _total('Cash sales', active.total('cash_sales')),
        _total('Cash refunds', active.total('cash_refunds')),
        _total('Cash added', active.total('cash_in')),
        _total('Cash removed', active.total('cash_out')),
        _total('Bank / UPI / card sales', active.total('bank_sales')),
        if (active.movementRows.isNotEmpty)
          ExpansionTile(
            title: const Text('Drawer movements'),
            tilePadding: EdgeInsets.zero,
            children: [
              for (final movement in active.movementRows)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(posText(posObject(movement['data'])['reason'])),
                  subtitle: Text(
                    posObject(movement['data'])['direction'] == 'in'
                        ? 'Cash in'
                        : 'Cash out',
                  ),
                  trailing: Text(
                    registerMoneyText(registerPaise(movement['amount'])),
                  ),
                ),
            ],
          ),
      ],
    );
  }

  Widget _total(String title, BigInt value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: Text(title)),
        const SizedBox(width: 8),
        Flexible(
          child: Text(registerMoneyText(value), textAlign: TextAlign.end),
        ),
      ],
    ),
  );

  Widget _activeActions(PosRegisterSession active) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (_form == null)
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            OutlinedButton(
              onPressed: writable
                  ? () => _select(RegisterOperation.movement)
                  : null,
              child: const Text('Record cash movement'),
            ),
            FilledButton.tonal(
              onPressed: writable
                  ? () => _select(RegisterOperation.close)
                  : null,
              child: const Text('Count & close register'),
            ),
          ],
        ),
      if (_form == RegisterOperation.movement) _movement(active),
      if (_form == RegisterOperation.close) _close(active),
    ],
  );

  Widget _movement(PosRegisterSession active) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        'Record cash movement',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const SizedBox(height: 10),
      DropdownButtonFormField<String>(
        initialValue: _direction,
        onChanged: writable
            ? (value) => setState(() => _direction = value ?? 'in')
            : null,
        decoration: const InputDecoration(labelText: 'Direction'),
        items: const [
          DropdownMenuItem(value: 'in', child: Text('Cash in')),
          DropdownMenuItem(value: 'out', child: Text('Cash out')),
        ],
      ),
      const SizedBox(height: 10),
      _moneyField('Cash movement amount (₹)'),
      const SizedBox(height: 10),
      _reasonField(required: true),
      _formActions(
        'Post cash movement',
        writable &&
                register.validateMovement(_amount.text, _reason.text) == null
            ? () => register.move(
                active.id,
                _direction,
                _amount.text,
                _reason.text,
              )
            : null,
      ),
    ],
  );

  Widget _close(PosRegisterSession active) {
    final amount = parsePosMoney(_amount.text);
    final difference = amount == null
        ? null
        : BigInt.from(amount) - active.expected;
    final mismatch = difference != null && difference != BigInt.zero;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Close register', style: Theme.of(context).textTheme.titleMedium),
        _total('Expected cash', active.expected),
        const SizedBox(height: 8),
        _moneyField('Counted cash (₹)'),
        if (difference != null) _total('Cash difference', difference),
        const SizedBox(height: 8),
        _reasonField(required: mismatch),
        _formActions(
          'Post closing count',
          writable &&
                  register.validateClose(
                        _amount.text,
                        _reason.text,
                        active.snapshot,
                      ) ==
                      null
              ? () => register.close(
                  active.id,
                  _amount.text,
                  _reason.text,
                  active.snapshot,
                )
              : null,
        ),
      ],
    );
  }

  Widget _moneyField(String label) => TextField(
    controller: _amount,
    enabled: writable,
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
    onChanged: (_) => setState(() {}),
    decoration: InputDecoration(labelText: label),
  );

  Widget _reasonField({required bool required}) => TextField(
    controller: _reason,
    enabled: writable,
    maxLength: 200,
    onChanged: (_) => setState(() {}),
    decoration: InputDecoration(
      labelText: required ? 'Reason (required)' : 'Reason (optional)',
    ),
  );

  Widget _formActions(String submitLabel, VoidCallback? submit) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        FilledButton(onPressed: submit, child: Text(submitLabel)),
        TextButton(
          onPressed: register.busy ? null : () => _select(null),
          child: const Text('Cancel'),
        ),
      ],
    ),
  );

  Widget _closedSummary(PosRegisterSession closed) {
    final timestamp = DateTime.tryParse(posText(closed.data['closed_at']));
    final day = timestamp == null ? closed.date : businessDate(timestamp);
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text('Closed $day'),
      subtitle: Text('Counted ${registerMoneyText(closed.counted)}'),
      children: [
        _total('Expected cash', closed.expected),
        _total('Counted cash', closed.counted),
        _total('Cash difference', closed.variance),
        if (closed.reason.isNotEmpty)
          Align(alignment: Alignment.centerLeft, child: Text(closed.reason)),
      ],
    );
  }
}
