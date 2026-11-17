import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'pos_controller.dart';
import 'pos_models.dart';
import 'pos_register_controller.dart';
import 'pos_register_models.dart';
import 'pos_widgets.dart';

typedef PosMovementsLoader = Future<List<PosJson>> Function(String registerId);

/// Register tab, laid out like the web `PosRegisterSession`: status heading,
/// tender totals, cash activity, and the open / cash movement / close forms
/// shown inline.
class PosRegisterPanel extends StatefulWidget {
  const PosRegisterPanel({
    required this.register,
    required this.checkoutBusy,
    this.loadMovements,
    super.key,
  });

  final PosRegisterController register;
  final bool checkoutBusy;
  final PosMovementsLoader? loadMovements;

  @override
  State<PosRegisterPanel> createState() => _PosRegisterPanelState();
}

class _PosRegisterPanelState extends State<PosRegisterPanel> {
  final _opening = TextEditingController();
  final _amount = TextEditingController();
  final _reason = TextEditingController();
  final _counted = TextEditingController();
  final _closeReason = TextEditingController();
  String _direction = 'in';
  RegisterOperation? _lastAction;
  PosRegisterController get register => widget.register;
  bool get writable => register.writable && !widget.checkoutBusy;

  @override
  void dispose() {
    _opening.dispose();
    _amount.dispose();
    _reason.dispose();
    _counted.dispose();
    _closeReason.dispose();
    super.dispose();
  }

  void _run(RegisterOperation action, Future<void> Function() send) {
    _lastAction = action;
    send();
  }

  @override
  Widget build(BuildContext context) {
    final active = register.active;
    final overview = register.overview;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PosPanel(
          spacing: 14,
          children: [
            _heading(overview != null, active != null),
            if (register.refreshing || register.busy)
              const LinearProgressIndicator(),
            if (register.loadError case final error?) _error(error),
            if (register.message case final message?)
              register.message!.endsWith('recorded.')
                  ? PosInfoBox(message)
                  : _error(message),
            if (register.recoveryError case final error?) ...[
              _error(error),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton(
                  onPressed: register.recover,
                  child: const Text('Check saved activity'),
                ),
              ),
            ],
            if (register.pending case final pending?)
              PosInfoBox(
                switch (pending.action) {
                  RegisterOperation.open =>
                    'Confirm the original opening before opening another register.',
                  RegisterOperation.movement =>
                    'Confirm the original cash movement before recording it again.',
                  RegisterOperation.close => 'Confirm the original closing count before closing the register again.',
                },
                child: Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton(
                      onPressed: register.canWrite && !register.busy
                          ? register.retry
                          : null,
                      child: Text(
                        'Retry ${switch (pending.action) {
                          RegisterOperation.open => 'open register',
                          RegisterOperation.movement => 'record cash movement',
                          RegisterOperation.close => 'close register',
                        }}',
                      ),
                    ),
                  ),
                ),
              ),
            if (!register.canWrite)
              const Text(
                'View-only access to register activity.',
                style: TextStyle(fontSize: 13, color: PosColors.muted),
              ),
            if (widget.checkoutBusy && register.canWrite)
              const Text(
                'Resolve the saved checkout or return before changing the register.',
                style: TextStyle(fontSize: 13, color: PosColors.muted),
              ),
            if (overview == null && register.loadError == null)
              const Text('Loading register…'),
            if (overview != null && active == null) ...[
              if (register.canWrite && register.pending == null) _openForm(),
            ],
            if (active != null) ..._activeSession(active),
            if (overview != null && overview.closed.isNotEmpty)
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 6, bottom: 4),
                    child: Text(
                      'Recent closes',
                      style: TextStyle(
                        fontFamily: Apex.display,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                        color: Apex.ink,
                      ),
                    ),
                  ),
                  for (final closed in overview.closed)
                    _ClosedRegister(
                      key: ValueKey(closed.id),
                      session: closed,
                      loadMovements: widget.loadMovements,
                    ),
                ],
              ),
          ],
        ),
      ],
    );
  }

  Widget _error(String message) => Semantics(
    liveRegion: true,
    child: Text(
      message,
      style: TextStyle(color: Theme.of(context).colorScheme.error),
    ),
  );

  Widget _heading(bool loaded, bool open) => Wrap(
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
                if (loaded)
                  ApexStatusBadge(
                    open ? 'Open' : 'Closed',
                    tone: open ? ApexBadgeTone.posted : ApexBadgeTone.neutral,
                  ),
              ],
            ),
            const SizedBox(height: 6),
            const Text(
              'One shared drawer for this company. POS sales and linked refunds posted while it is open enter this session.',
              style: TextStyle(fontSize: 13, height: 1.5, color: PosColors.muted),
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
  );

  Widget _moneyField(
    TextEditingController controller,
    String label, {
    String? hint,
  }) => TextField(
    controller: controller,
    enabled: writable,
    maxLength: 16,
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
    onChanged: (_) => setState(() {}),
    decoration: InputDecoration(
      labelText: label,
      hintText: hint,
      counterText: '',
    ),
  );

  Widget _textField(
    TextEditingController controller,
    String label, {
    bool required = false,
  }) => TextField(
    controller: controller,
    enabled: writable,
    maxLength: 200,
    onChanged: (_) => setState(() {}),
    decoration: InputDecoration(
      labelText: required ? '$label *' : label,
      counterText: '',
    ),
  );

  Widget _openForm() => PosFieldset(
    legend: null,
    children: [
      PosFieldRow([
        _moneyField(_opening, 'Opening float (₹)'),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton(
            onPressed: writable && register.validateOpen(_opening.text) == null
                ? () => _run(
                    RegisterOperation.open,
                    () => register.open(_opening.text),
                  )
                : null,
            child: Text(
              register.busy && _lastAction == RegisterOperation.open
                  ? 'Opening…'
                  : 'Open register',
            ),
          ),
        ),
      ]),
    ],
  );

  List<Widget> _activeSession(PosRegisterSession active) {
    final data = active.data;
    final totals = active.totals;
    int count(String field) => int.tryParse(posText(totals[field])) ?? 0;
    String plural(int value, String one, String many) =>
        '$value ${value == 1 ? one : many}';
    return [
      Text(
        'Opened ${posDateTime(posText(data['created_at']))} by ${posText(data['opened_by'])} with ${registerMoneyText(active.opening)}',
        style: const TextStyle(fontSize: 14, color: Apex.ink),
      ),
      PosResultsBox(registerTenderTotals(totals)),
      Text(
        '${plural(count('sales_count'), 'sale', 'sales')} · ${count('refund_count')} linked ${count('refund_count') == 1 ? 'refund' : 'refunds'} · ${count('movement_count')} cash ${count('movement_count') == 1 ? 'movement' : 'movements'}',
        style: const TextStyle(fontSize: 14, color: Apex.ink),
      ),
      PosDisclosure(
        title: 'Cash activity',
        children: [
          PosCashActivity(
            movements: active.movementRows,
            count: count('movement_count'),
          ),
        ],
      ),
      if (register.canWrite && register.pending == null) ...[
        _movementForm(active),
        _closeForm(active),
      ],
    ];
  }

  Widget _movementForm(PosRegisterSession active) => PosFieldset(
    legend: 'Record cash movement',
    children: [
      PosFieldRow([
        DropdownButtonFormField<String>(
          initialValue: _direction,
          onChanged: writable
              ? (value) => setState(() => _direction = value ?? 'in')
              : null,
          decoration: const InputDecoration(labelText: 'Movement'),
          items: const [
            DropdownMenuItem(value: 'in', child: Text('Add cash')),
            DropdownMenuItem(value: 'out', child: Text('Remove cash')),
          ],
        ),
        _moneyField(_amount, 'Amount (₹)'),
      ]),
      _textField(_reason, 'Reason'),
      const Text(
        'Record drawer movements here and enter any accounting transaction separately.',
        style: TextStyle(fontSize: 13, color: PosColors.muted),
      ),
      Align(
        alignment: Alignment.centerLeft,
        child: OutlinedButton(
          onPressed:
              writable &&
                  register.validateMovement(_amount.text, _reason.text) == null
              ? () => _run(
                  RegisterOperation.movement,
                  () => register.move(
                    active.id,
                    _direction,
                    _amount.text,
                    _reason.text,
                  ),
                )
              : null,
          child: Text(
            register.busy && _lastAction == RegisterOperation.movement
                ? 'Recording…'
                : 'Record cash movement',
          ),
        ),
      ),
    ],
  );

  Widget _closeForm(PosRegisterSession active) {
    final amount = parseDrawerPaise(_counted.text);
    final difference = amount == null ? null : amount - active.expected;
    final mismatch = difference != null && difference != BigInt.zero;
    return PosFieldset(
      legend: 'Close register',
      children: [
        PosFieldRow([
          _moneyField(_counted, 'Counted cash (₹)'),
          _textField(
            _closeReason,
            'Reason for any difference',
            required: mismatch,
          ),
        ]),
        if (difference != null)
          Semantics(
            liveRegion: true,
            child: Text(
              difference == BigInt.zero
                  ? 'Cash count matches.'
                  : 'Cash ${difference.isNegative ? 'short' : 'over'} by ${registerMoneyText(difference.abs())}.',
              style: const TextStyle(fontSize: 14, color: Apex.ink),
            ),
          ),
        const Text(
          "Closing saves the count and locks edits and cancellations for the session's sales.",
          style: TextStyle(fontSize: 13, color: PosColors.muted),
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton(
            onPressed:
                writable &&
                    register.validateClose(
                          _counted.text,
                          _closeReason.text,
                          active.snapshot,
                        ) ==
                        null
                ? () => _run(
                    RegisterOperation.close,
                    () => register.close(
                      active.id,
                      _counted.text,
                      _closeReason.text,
                      active.snapshot,
                    ),
                  )
                : null,
            child: Text(
              register.busy && _lastAction == RegisterOperation.close
                  ? 'Closing…'
                  : 'Close register',
            ),
          ),
        ),
      ],
    );
  }
}

BigInt? parseDrawerPaise(String value) {
  final cents = parsePosMoney(value);
  return cents == null ? null : BigInt.from(cents);
}

/// The six figures of the web `TenderTotals` block.
List<(String, String)> registerTenderTotals(PosJson totals) {
  BigInt amount(String field) =>
      totals[field] == null ? BigInt.zero : registerPaise(totals[field]);
  return [
    ('Expected cash', registerMoneyText(amount('expected_cash'))),
    ('Cash sales', registerMoneyText(amount('cash_sales'))),
    ('Cash refunds', registerMoneyText(amount('cash_refunds'))),
    (
      'Bank / UPI / card net',
      registerMoneyText(amount('bank_sales') - amount('bank_refunds')),
    ),
    ('Other cash added', registerMoneyText(amount('cash_in'))),
    ('Other cash removed', registerMoneyText(amount('cash_out'))),
  ];
}

/// Cash additions and drops, as listed under "Cash activity".
class PosCashActivity extends StatelessWidget {
  const PosCashActivity({
    required this.movements,
    required this.count,
    super.key,
  });

  final List<PosJson> movements;
  final int count;

  @override
  Widget build(BuildContext context) {
    if (movements.isEmpty) return const Text('No cash additions or drops.');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (count > movements.length)
          Text(
            'Showing the latest ${movements.length} of $count movements.',
            style: const TextStyle(fontSize: 13, color: PosColors.muted),
          ),
        for (final row in movements)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${posObject(row['data'])['direction'] == 'in' ? 'Added' : 'Removed'} ${registerMoneyText(registerPaise(row['amount']))}',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: Apex.ink,
                  ),
                ),
                Text(
                  '${posText(posObject(row['data'])['reason'])} · ${posText(posObject(row['data'])['actor'])} · ${posDateTime(posText(posObject(row['data'])['created_at']))}',
                  style: const TextStyle(fontSize: 12.8, color: PosColors.muted),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _ClosedRegister extends StatefulWidget {
  const _ClosedRegister({
    required this.session,
    required this.loadMovements,
    super.key,
  });

  final PosRegisterSession session;
  final PosMovementsLoader? loadMovements;

  @override
  State<_ClosedRegister> createState() => _ClosedRegisterState();
}

class _ClosedRegisterState extends State<_ClosedRegister> {
  List<PosJson>? _movements;
  String? _error;
  bool _loading = false;

  Future<void> _load() async {
    final loader = widget.loadMovements;
    if (loader == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await loader(widget.session.id);
      if (mounted) setState(() => _movements = rows);
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is PosFailure
              ? error.message
              : 'Could not load cash activity.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final closed = widget.session;
    final data = closed.data;
    final count = int.tryParse(posText(closed.totals['movement_count'])) ?? 0;
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Apex.line)),
      ),
      child: PosDisclosure(
        title:
            '${posDateTime(posText(data['closed_at']))} · Counted ${registerMoneyText(closed.counted)} · Variance ${registerMoneyText(closed.variance)}',
        children: [
          Text(
            'Opened by ${posText(data['opened_by'])} with ${registerMoneyText(closed.opening)} · Closed by ${posText(data['closed_by'])}',
          ),
          if (closed.reason.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(closed.reason),
          ],
          const SizedBox(height: 8),
          PosResultsBox(registerTenderTotals(closed.totals)),
          const SizedBox(height: 8),
          if (_movements case final rows?)
            PosCashActivity(movements: rows, count: count)
          else if (widget.loadMovements != null)
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                onPressed: _loading ? null : _load,
                child: Text(_loading ? 'Loading…' : 'View cash activity'),
              ),
            ),
          if (_error case final error?)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
    );
  }
}
