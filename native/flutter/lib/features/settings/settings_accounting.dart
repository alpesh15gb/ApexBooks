import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import 'settings_blocks.dart';
import 'settings_fields.dart';

const _recoveryMessage =
    'Recovery is kept only while this screen is open. Do not leave it or sign out until the result is confirmed. After interruption, verify the original result before trying again.';

/// Web "Accounting period lock": the date form, review step and confirmation.
class PeriodLockForm extends StatefulWidget {
  const PeriodLockForm({
    required this.workspace,
    required this.lockedThrough,
    super.key,
  });

  final WorkspaceContext workspace;

  /// `yyyy-mm-dd` from the server, or empty when no date is set.
  final String lockedThrough;

  @override
  State<PeriodLockForm> createState() => _PeriodLockFormState();
}

class _PeriodLockFormState extends State<PeriodLockForm> {
  late String _locked = widget.lockedThrough;
  late String _next = widget.lockedThrough;
  String _review = '';
  String _error = '';
  bool _busy = false;
  bool _saved = false;
  bool _pending = false;

  bool get _owner => widget.workspace.company.role == 'owner';
  String get _path => '${widget.workspace.path}/period-lock';
  bool get _movable =>
      _next.isNotEmpty && (_locked.isEmpty || _next.compareTo(_locked) > 0);

  Future<void> _pick() async {
    final today = DateTime.parse(businessDate());
    final earliest = DateTime.tryParse(_locked) ?? DateTime(2000);
    final initial = DateTime.tryParse(_next) ?? today;
    final date = await showDatePicker(
      context: context,
      initialDate: initial.isBefore(earliest) ? earliest : initial,
      firstDate: earliest,
      lastDate: DateTime(today.year + 2, 12, 31),
      helpText: 'New lock date',
    );
    if (date != null && mounted) {
      setState(() {
        _next = booksDate(date);
        _saved = false;
      });
    }
  }

  void _begin() {
    if (!_owner || _pending || _busy || !_movable) return;
    setState(() {
      _saved = false;
      _error = '';
      _review = _next;
    });
  }

  Future<void> _save() async {
    if (_busy || _review.isEmpty || !_owner) return;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final data = booksObject(
        await widget.workspace.api.put(_path, body: {'locked_through': _review}),
      );
      final value = booksText(data['locked_through']);
      if (!mounted) return;
      setState(() {
        _pending = false;
        _locked = value.isEmpty ? _review : value;
        _next = _locked;
        _review = '';
        _saved = true;
      });
    } catch (failure) {
      if (!mounted) return;
      final uncertain = failure is! ApexApiException || failure.uncertain || failure.status == 409;
      setState(() {
        if (_pending || uncertain) _pending = true;
        _error = settingsFailure(failure);
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _check() async {
    if (!_pending || _busy) return;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final data = booksObject(await widget.workspace.api.get(_path));
      final value = booksText(data['locked_through']);
      if (!mounted) return;
      if (value.isEmpty || value.compareTo(_review) < 0) {
        setState(
          () => _error =
              'The requested lock is not visible yet. This does not prove the save failed; check again or retry the original date.',
        );
        return;
      }
      setState(() {
        _pending = false;
        _locked = value;
        _next = value;
        _review = '';
        _saved = true;
      });
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => SettingsBlock(
    title: 'Accounting period lock',
    note:
        'Posted entries dated on or before the lock date cannot be added. The date can only move forward.',
    children: [
      Text.rich(
        TextSpan(
          style: const TextStyle(fontSize: 13, color: Apex.inkSoft),
          children: [
            const TextSpan(
              text: 'Locked through: ',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
            TextSpan(
              text: _pending
                  ? 'Not verified after save'
                  : _locked.isEmpty
                  ? 'No date set'
                  : apexDate(_locked),
            ),
          ],
        ),
      ),
      if (_pending)
        SettingsInfoBox(
          children: [
            const Text(
              'Period-lock result not confirmed.',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              'The original date ${apexDate(_review)} is frozen until the current lock is verified. $_recoveryMessage',
              style: const TextStyle(fontSize: 13, height: 1.6),
            ),
            const SizedBox(height: 10),
            SettingsButton(
              'Check current lock',
              onPressed: _busy ? null : _check,
            ),
          ],
        ),
      if (_owner) ...[
        const SizedBox(height: 14),
        LayoutBuilder(
          builder: (context, limits) {
            final field = SettingsLabeled(
              label: 'New lock date',
              child: InkWell(
                onTap: _busy || _review.isNotEmpty ? null : _pick,
                borderRadius: BorderRadius.circular(4),
                child: InputDecorator(
                  decoration: InputDecoration(
                    suffixIcon: const Icon(
                      Icons.calendar_today_outlined,
                      size: 17,
                    ),
                    enabled: !_busy && _review.isEmpty,
                  ),
                  child: Text(
                    _next.isEmpty ? 'Choose a date' : _next,
                    style: const TextStyle(fontSize: 13),
                  ),
                ),
              ),
            );
            final button = SettingsButton(
              'Lock through date',
              onPressed: _busy || _review.isNotEmpty || !_movable
                  ? null
                  : _begin,
            );
            if (limits.maxWidth < 420) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [field, const SizedBox(height: 12), button],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                SizedBox(width: 200, child: field),
                const SizedBox(width: 12),
                button,
              ],
            );
          },
        ),
      ],
      if (_review.isNotEmpty && _owner)
        SettingsInfoBox(
          children: [
            Text(
              'Lock all entries through ${apexDate(_review)}?',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              'This includes ${apexDate(_review)}. You cannot move this lock backwards. Complete and review all entries for this period before confirming.',
              style: const TextStyle(fontSize: 13, height: 1.6),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton(
                  onPressed: _busy || _pending
                      ? null
                      : () => setState(() => _review = ''),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: _busy ? null : _save,
                  child: Text(
                    _busy
                        ? 'Saving…'
                        : _pending
                        ? 'Retry original lock'
                        : 'Confirm period lock',
                  ),
                ),
              ],
            ),
          ],
        ),
      if (_saved) ...[
        const SizedBox(height: 12),
        Text(
          'Period locked through ${apexDate(_locked)}.',
          style: const TextStyle(fontSize: 13, color: Apex.inkSoft),
        ),
      ],
      if (_error.isNotEmpty) ...[
        const SizedBox(height: 12),
        SettingsMessage(_error, error: true),
      ],
    ],
  );
}
