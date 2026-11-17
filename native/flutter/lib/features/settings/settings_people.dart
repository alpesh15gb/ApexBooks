import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/session.dart';
import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import '../books/books_data.dart';
import 'settings_blocks.dart';
import 'settings_fields.dart';

String _titleCase(String value) =>
    value.isEmpty ? value : value[0].toUpperCase() + value.substring(1);

/// Web "Team access": the member list with Remove, and the add-member form.
class MembersPanel extends StatefulWidget {
  const MembersPanel({
    required this.workspace,
    required this.members,
    required this.onChanged,
    super.key,
  });

  final WorkspaceContext workspace;
  final List<Json> members;
  final Future<void> Function() onChanged;

  @override
  State<MembersPanel> createState() => _MembersPanelState();
}

class _MembersPanelState extends State<MembersPanel> {
  final _email = TextEditingController();
  String _role = 'viewer';
  String _error = '';
  bool _busy = false;

  bool get _owner => widget.workspace.company.role == 'owner';
  String get _path => '${widget.workspace.path}/members';

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    if (_busy) return;
    final email = _email.text.trim();
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
      setState(() => _error = 'Enter the registered user’s email address.');
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await widget.workspace.api.post(_path, body: {'email': email, 'role': _role});
      _email.clear();
      await widget.onChanged();
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _remove(Json member) async {
    final email = booksText(member['email']);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove company access?'),
        content: Text(
          'Remove $email (${booksText(member['role'])}) from ${widget.workspace.company.name.isEmpty ? 'this company' : widget.workspace.company.name}? They will lose access to this company. Their posted records remain unchanged. You can add them again later.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep member'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove access'),
          ),
        ],
      ),
    );
    if (confirmed != true || _busy || !mounted) return;
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await widget.workspace.api.delete('$_path/${Uri.encodeComponent(email)}');
      await widget.onChanged();
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => SettingsBlock(
    title: 'Team access',
    note:
        'Registered users can be given editor or view-only access to this company.',
    children: [
      if (_error.isNotEmpty) SettingsMessage(_error, error: true),
      for (final row in widget.members)
        SettingsRow(
          title: booksText(row['email']),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                booksText(row['role']),
                style: const TextStyle(fontSize: 13, color: Apex.inkSoft),
              ),
              if (_owner && row['role'] != 'owner') ...[
                const SizedBox(width: 6),
                SettingsLinkButton(
                  'Remove',
                  onPressed: _busy ? null : () => _remove(row),
                ),
              ],
            ],
          ),
        ),
      if (_owner)
        Padding(
          padding: const EdgeInsets.only(top: 18),
          child: LayoutBuilder(
            builder: (context, limits) {
              final email = SettingsTextField(
                label: 'User email',
                controller: _email,
                enabled: !_busy,
                hint: 'Registered user’s email',
                keyboardType: TextInputType.emailAddress,
              );
              final role = SettingsSelect(
                label: 'Role',
                value: _role,
                options: const [('viewer', 'Viewer'), ('editor', 'Editor')],
                onChanged: _busy ? null : (value) => setState(() => _role = value),
              );
              final button = SettingsButton(
                _busy ? 'Working…' : 'Add member',
                primary: true,
                onPressed: _busy ? null : _add,
              );
              if (limits.maxWidth < 560) {
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    email,
                    const SizedBox(height: 14),
                    role,
                    const SizedBox(height: 14),
                    button,
                  ],
                );
              }
              return Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(flex: 2, child: email),
                  const SizedBox(width: 12),
                  Expanded(child: role),
                  const SizedBox(width: 12),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 1),
                    child: button,
                  ),
                ],
              );
            },
          ),
        ),
    ],
  );
}

/// Web "Account security": change password and sign out other sessions.
class AccountSecurityPanel extends StatefulWidget {
  const AccountSecurityPanel({required this.session, super.key});

  final ApexSession session;

  @override
  State<AccountSecurityPanel> createState() => _AccountSecurityPanelState();
}

class _AccountSecurityPanelState extends State<AccountSecurityPanel> {
  final _current = TextEditingController();
  final _new = TextEditingController();
  bool _busy = false;
  String _error = '';
  String _notice = '';

  @override
  void dispose() {
    _current.dispose();
    _new.dispose();
    super.dispose();
  }

  Future<void> _change() async {
    if (_busy) return;
    if (_current.text.isEmpty) {
      setState(() => _error = 'Enter your current password.');
      return;
    }
    if (_new.text.length < 8) {
      setState(() => _error = 'Use at least eight characters.');
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
      _notice = '';
    });
    try {
      await widget.session.accountApi.post(
        '/api/auth/change-password',
        body: {
          'current_password': _current.text,
          'new_password': _new.text,
        },
      );
      _current.clear();
      _new.clear();
      await widget.session.signOut();
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _signOutOthers() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = '';
      _notice = '';
    });
    try {
      final result = await widget.session.accountApi.post(
        '/api/auth/logout-other-sessions',
        body: {},
      );
      final revoked = result is Map ? result['revoked'] : null;
      if (mounted) {
        setState(
          () => _notice = revoked is int
              ? '$revoked other session${revoked == 1 ? '' : 's'} signed out.'
              : 'Other sessions signed out.',
        );
      }
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => SettingsBlock(
    title: 'Account security',
    note:
        'Change your password to end every existing sign-in session. You will sign in again.',
    children: [
      LayoutBuilder(
        builder: (context, limits) {
          final current = SettingsTextField(
            label: 'Current password',
            controller: _current,
            obscure: true,
            enabled: !_busy,
          );
          final next = SettingsTextField(
            label: 'New password',
            controller: _new,
            obscure: true,
            maxLength: 128,
            enabled: !_busy,
          );
          final button = SettingsButton(
            _busy ? 'Saving…' : 'Change password',
            onPressed: _busy ? null : _change,
          );
          if (limits.maxWidth < 620) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                current,
                const SizedBox(height: 14),
                next,
                const SizedBox(height: 14),
                button,
              ],
            );
          }
          return Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(child: current),
              const SizedBox(width: 12),
              Expanded(child: next),
              const SizedBox(width: 12),
              Padding(padding: const EdgeInsets.only(bottom: 1), child: button),
            ],
          );
        },
      ),
      const SizedBox(height: 18),
      const Text(
        'End other sign-ins if you no longer use those devices.',
        style: TextStyle(fontSize: 13, color: Apex.inkSoft),
      ),
      const SizedBox(height: 10),
      SettingsButton(
        'Sign out other sessions',
        onPressed: _busy ? null : _signOutOthers,
      ),
      if (_notice.isNotEmpty) ...[
        const SizedBox(height: 12),
        Text(_notice, style: const TextStyle(fontSize: 13, color: Apex.inkSoft)),
      ],
      if (_error.isNotEmpty) ...[
        const SizedBox(height: 12),
        SettingsMessage(_error, error: true),
      ],
    ],
  );
}

/// Web "Account recovery": verify the password, generate and save codes.
class RecoveryCodesPanel extends StatefulWidget {
  const RecoveryCodesPanel({
    required this.session,
    required this.remaining,
    super.key,
  });

  final ApexSession session;
  final Object? remaining;

  @override
  State<RecoveryCodesPanel> createState() => _RecoveryCodesPanelState();
}

class _RecoveryCodesPanelState extends State<RecoveryCodesPanel> {
  final _password = TextEditingController();
  late Object? _remaining = widget.remaining;
  List<String> _codes = const [];
  bool _busy = false;
  String _error = '';

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  Future<void> _generate() async {
    if (_busy) return;
    if (_password.text.isEmpty) {
      setState(() => _error = 'Enter your current password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      final result = booksObject(
        await widget.session.accountApi.post(
          '/api/auth/recovery-codes',
          body: {'current_password': _password.text},
        ),
      );
      final codes = (result['codes'] as List).cast<String>();
      _password.clear();
      if (mounted) {
        setState(() {
          _codes = codes;
          _remaining = codes.length;
        });
      }
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _download() async {
    final text =
        'Apex Books account recovery codes\nKeep these private and separate from your company backups.\nA password reset invalidates the entire set.\n\n${_codes.join('\n')}';
    try {
      await saveApexFile(
        'apex-recovery-codes.txt',
        Uint8List.fromList(utf8.encode(text)),
        'text/plain',
      );
    } catch (failure) {
      if (mounted) setState(() => _error = settingsFailure(failure));
    }
  }

  @override
  Widget build(BuildContext context) {
    final remaining = _remaining;
    return SettingsBlock(
      title: 'Account recovery',
      note:
          '${remaining == null ? 'Checking recovery setup…' : remaining != 0 ? '$remaining unused recovery codes available.' : 'Generate recovery codes so you can regain access if you forget your password.'} Keep codes private and separate from company backups. Generating a set invalidates earlier codes.',
      children: [
        SettingsTextField(
          label: 'Verify current password for recovery codes',
          controller: _password,
          obscure: true,
          enabled: !_busy,
        ),
        const SizedBox(height: 14),
        SettingsButton(
          _busy ? 'Generating…' : 'Generate recovery codes',
          onPressed: _busy ? null : _generate,
        ),
        if (_codes.isNotEmpty)
          SettingsInfoBox(
            children: [
              const Text(
                'Save these codes now. They are displayed only in this session.',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              for (final code in _codes)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: SelectableText(
                    code,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 13,
                    ),
                  ),
                ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton(
                    onPressed: _download,
                    child: const Text('Download recovery codes'),
                  ),
                  OutlinedButton(
                    onPressed: () => Clipboard.setData(
                      ClipboardData(text: _codes.join('\n')),
                    ),
                    child: const Text('Copy codes'),
                  ),
                ],
              ),
            ],
          ),
        if (_error.isNotEmpty) ...[
          const SizedBox(height: 12),
          SettingsMessage(_error, error: true),
        ],
      ],
    );
  }
}

/// Web "Activity log": WHEN / ACTION / BY / DETAIL, as a table or cards.
class AuditPanel extends StatelessWidget {
  const AuditPanel({
    required this.events,
    required this.onRefresh,
    this.busy = false,
    super.key,
  });

  final List<Json> events;
  final VoidCallback onRefresh;
  final bool busy;

  static const _entityLabels = {
    'bank_match_allocation': 'Bank statement allocation',
    'bank_statement_line': 'Bank statement entry',
    'bank_reconciliation_review': 'Bank reconciliation review',
  };

  static String friendly(Object? value) {
    final text = booksText(value).replaceAll('_', ' ').replaceAll('.', ' · ');
    return _titleCase(text);
  }

  static String when(Object? value) {
    final parsed = DateTime.tryParse(booksText(value));
    if (parsed == null) return booksText(value);
    final local = parsed.isUtc ? parsed.toLocal() : parsed;
    String two(int number) => number.toString().padLeft(2, '0');
    final hour = local.hour % 12 == 0 ? 12 : local.hour % 12;
    return '${two(local.day)}/${two(local.month)}/${local.year}, $hour:${two(local.minute)}:${two(local.second)} ${local.hour < 12 ? 'am' : 'pm'}';
  }

  static String detail(Json event) {
    final details = event['details'] is Map<String, dynamic>
        ? event['details'] as Map<String, dynamic>
        : const <String, dynamic>{};
    for (final key in const ['number', 'reference', 'code']) {
      if (booksText(details[key]).isNotEmpty) return booksText(details[key]);
    }
    final kind = booksText(details['kind']).isNotEmpty
        ? booksText(details['kind'])
        : booksText(event['entity_type']);
    return _entityLabels[kind] ?? friendly(kind);
  }

  Widget _technical(Json event) => Theme(
    data: ThemeData(
      dividerColor: Colors.transparent,
      splashColor: Colors.transparent,
    ),
    child: ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      dense: true,
      visualDensity: VisualDensity.compact,
      expandedAlignment: Alignment.centerLeft,
      expandedCrossAxisAlignment: CrossAxisAlignment.start,
      title: const Text('Technical identifiers', style: Apex.small),
      children: [
        Text('Action: ${event['action']}', style: Apex.small),
        Text('Type: ${event['entity_type']}', style: Apex.small),
        if (booksText(event['entity_id']).isNotEmpty)
          SelectableText('ID: ${event['entity_id']}', style: Apex.small),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => SettingsBlock(
    title: 'Activity log',
    note: 'Recent changes in this company, including who made them.',
    trailing: OutlinedButton(
      onPressed: busy ? null : onRefresh,
      child: Text(busy ? 'Loading…' : 'Refresh'),
    ),
    children: [
      LayoutBuilder(
        builder: (context, limits) {
          if (events.isEmpty) {
            return const Text('No activity yet.', style: Apex.note);
          }
          if (limits.maxWidth < 620) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final event in events)
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    decoration: const BoxDecoration(
                      border: Border(top: BorderSide(color: Apex.lineSoft)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          friendly(event['action']),
                          style: Apex.strong,
                        ),
                        Text(
                          '${when(event['occurred_at'])} · ${event['actor']}',
                          style: Apex.small,
                        ),
                        const SizedBox(height: 3),
                        Text(detail(event), style: const TextStyle(fontSize: 12)),
                        _technical(event),
                      ],
                    ),
                  ),
              ],
            );
          }
          const head = TextStyle(
            fontSize: 11,
            letterSpacing: .5,
            color: Apex.muted,
            fontWeight: FontWeight.w600,
          );
          Widget cell(double? width, Widget child) => width == null
              ? Expanded(child: child)
              : SizedBox(width: width, child: child);
          return DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: Apex.line),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Column(
              children: [
                Container(
                  color: Apex.paper,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 10,
                  ),
                  child: Row(
                    children: [
                      cell(190, const Text('WHEN', style: head)),
                      cell(180, const Text('ACTION', style: head)),
                      cell(190, const Text('BY', style: head)),
                      cell(null, const Text('DETAIL', style: head)),
                    ],
                  ),
                ),
                for (final event in events)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 9,
                    ),
                    decoration: const BoxDecoration(
                      border: Border(top: BorderSide(color: Apex.lineSoft)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        cell(
                          190,
                          Text(
                            when(event['occurred_at']),
                            style: const TextStyle(fontSize: 12),
                          ),
                        ),
                        cell(
                          180,
                          Text(
                            friendly(event['action']),
                            style: const TextStyle(fontSize: 12),
                          ),
                        ),
                        cell(
                          190,
                          Text(
                            booksText(event['actor']),
                            style: const TextStyle(fontSize: 12),
                          ),
                        ),
                        cell(
                          null,
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                detail(event),
                                style: const TextStyle(fontSize: 12),
                              ),
                              _technical(event),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    ],
  );
}
