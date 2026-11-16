import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/session.dart';
import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import '../books/books_data.dart';
import '../commerce/commerce_screen.dart';
import 'backup_panel.dart';
import 'opening_party_panel.dart';
import 'settings_blocks.dart';
import 'settings_forms.dart';
import 'vyapar_panel.dart';

/// Left-rail categories, in the web app's order.
enum _Tab {
  company(
    'Company',
    'Your business identity and tax profile',
    Icons.business_outlined,
    'business address gst gstin tax phone email',
  ),
  documents(
    'Documents & branding',
    'Consistent documents, made yours',
    Icons.description_outlined,
    'logo signature branding pdf templates format prefix invoice bank upi notes terms',
  ),
  accounting(
    'Accounting',
    'Opening balances and accounting periods',
    Icons.tune_outlined,
    'opening balances stock period lock financial year',
  ),
  data(
    'Data & migration',
    'Import, export and protect your books',
    Icons.storage_outlined,
    'vyapar import export csv xlsx backup restore migration',
  ),
  access(
    'People & access',
    'Manage company roles and permissions',
    Icons.group_outlined,
    'team users roles permissions members',
  ),
  security(
    'Account security',
    'Protect your account and review changes',
    Icons.lock_outline,
    'password recovery sessions revoke audit history',
  ),
  inventory(
    'Stock & modules',
    'Item locations and optional industry modules such as Automobile',
    Icons.inventory_2_outlined,
    'stock locations rack shelf bin warehouse automobile vehicle make model spare parts garage workshop',
  ),
  commerce(
    'Ecommerce',
    'Connect your online store and review orders',
    Icons.shopping_bag_outlined,
    'online store ecommerce bagisto channels orders sync reconciliation',
  );

  const _Tab(this.title, this.description, this.icon, this.keywords);
  final String title;
  final String description;
  final IconData icon;
  final String keywords;
}

/// Server data a block needs; blocks that share one kind share one request.
enum _Data { documents, period, access, recovery, audit, inventory }

/// One titled block inside a tab's panel. [ownerOnly] blocks are hidden from
/// everyone else, as in the web app.
enum _Block {
  company(_Tab.company),
  branding(_Tab.documents, data: _Data.documents),
  prefixes(_Tab.documents, data: _Data.documents),
  formats(_Tab.documents, data: _Data.documents),
  openings(_Tab.accounting, ownerOnly: true),
  period(_Tab.accounting, data: _Data.period),
  vyapar(_Tab.data, ownerOnly: true),
  backup(_Tab.data),
  access(_Tab.access, data: _Data.access),
  account(_Tab.security),
  recovery(_Tab.security, data: _Data.recovery),
  audit(_Tab.security, data: _Data.audit, ownerOnly: true),
  locations(_Tab.inventory, data: _Data.inventory),
  automobile(_Tab.inventory, data: _Data.inventory),
  vehicles(_Tab.inventory, data: _Data.inventory),
  commerce(_Tab.commerce);

  const _Block(this.tab, {this.data, this.ownerOnly = false});
  final _Tab tab;
  final _Data? data;
  final bool ownerOnly;
}

/// Quick links under each tab heading: label, block to scroll to.
const _jumpLinks = <_Tab, List<(String, _Block)>>{
  _Tab.documents: [
    ('Logo & signature', _Block.branding),
    ('Transaction prefixes', _Block.prefixes),
    ('Document layouts', _Block.formats),
  ],
  _Tab.accounting: [
    ('Opening balances', _Block.openings),
    ('Period lock', _Block.period),
  ],
  _Tab.data: [
    ('Vyapar import', _Block.vyapar),
    ('Export data', _Block.backup),
    ('Backup & restore', _Block.backup),
  ],
  _Tab.inventory: [
    ('Item locations', _Block.locations),
    ('Automobile module', _Block.automobile),
    ('Vehicle makes & models', _Block.vehicles),
  ],
  _Tab.security: [
    ('Account security', _Block.account),
    ('Recovery codes', _Block.recovery),
    ('Audit history', _Block.audit),
  ],
};

const _layoutNames = {
  'modern': 'Modern',
  'vintage': 'Vintage',
  'mrp_discount': 'MRP + Discount',
  'elegant': 'Elegant',
  'evergreen': 'Evergreen',
  'classic': 'Classic',
  'compact': 'Compact',
  'bold': 'Bold',
  'minimal': 'Minimal',
};

String _titleCase(String value) =>
    value.isEmpty ? value : value[0].toUpperCase() + value.substring(1);

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    required this.workspace,
    required this.session,
    super.key,
  });
  final WorkspaceContext workspace;
  final ApexSession session;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _search = TextEditingController();
  final _anchors = {for (final block in _Block.values) block: GlobalKey()};
  final _restoreAnchor = GlobalKey();
  final _futures = <_Data, Future<dynamic>>{};
  final _visited = <_Tab>{_Tab.company};
  _Tab _tab = _Tab.company;
  bool _commerceOpen = false;
  bool _busy = false;
  String? _message;
  WorkspaceContext get _workspace => widget.workspace;
  ApexApi get _api => _workspace.api;
  String get _path => _workspace.path;
  bool get _owner => _workspace.company.role == 'owner';

  List<_Tab> get _availableTabs => [
    for (final tab in _Tab.values)
      if (tab != _Tab.inventory ||
          _workspace.features.contains('inventory_setup'))
        tab,
  ];

  List<_Block> _blocks(_Tab tab) => [
    for (final block in _Block.values)
      if (block.tab == tab && (_owner || !block.ownerOnly)) block,
  ];

  Future<dynamic> _load(_Data data) {
    final request = Future.sync(() => _request(data));
    // The block's FutureBuilder reports a failure; this only stops it being
    // treated as unhandled before the next frame subscribes.
    request.ignore();
    return request;
  }

  Future<dynamic> _request(_Data data) => switch (data) {
    _Data.documents => Future.wait([
      _api.get('$_path/preferences'),
      _api.get('$_path/document-branding'),
      _api.get('$_path/number-series'),
    ]),
    _Data.period => _api.get('$_path/period-lock'),
    _Data.access => _api.get('$_path/members'),
    _Data.recovery => widget.session.accountApi.get(
      '/api/auth/recovery-codes/status',
    ),
    _Data.audit => _api.get('$_path/audit-events', query: {'limit': '100'}),
    _Data.inventory => _api.get('$_path/inventory-setup'),
  };

  @override
  void initState() {
    super.initState();
    _ensureLoaded(_tab);
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _ensureLoaded(_Tab tab) {
    for (final block in _blocks(tab)) {
      final data = block.data;
      if (data != null) _futures.putIfAbsent(data, () => _load(data));
    }
  }

  void _select(_Tab tab) {
    if (_tab == tab && _search.text.isEmpty) return;
    setState(() {
      _tab = tab;
      _message = null;
      _search.clear();
      _visited.add(tab);
      _ensureLoaded(tab);
    });
  }

  void _reload(_Data data) {
    if (mounted) setState(() => _futures[data] = _load(data));
  }

  /// Reloads the server data behind the tab that is open.
  void _refresh() {
    if (!mounted) return;
    setState(() {
      for (final block in _blocks(_tab)) {
        final data = block.data;
        if (data != null) _futures[data] = _load(data);
      }
    });
  }

  void _jump(String label, _Block block) {
    final context =
        (label == 'Backup & restore' ? _restoreAnchor : _anchors[block]!)
            .currentContext;
    if (context == null) return;
    Scrollable.ensureVisible(
      context,
      duration: MediaQuery.of(context).disableAnimations
          ? Duration.zero
          : const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
  }

  Future<void> _action(Future<void> Function() work, {String? done}) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await work();
      if (mounted) setState(() => _message = done);
    } catch (failure) {
      if (mounted) {
        setState(
          () => _message = failure is ApexApiException
              ? failure.message
              : failure is FormatException
              ? failure.message
              : 'The operation could not be completed.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_commerceOpen) {
      return CommerceScreen(
        workspace: _workspace,
        onBack: () => setState(() => _commerceOpen = false),
      );
    }
    return ApexPage(
      children: [
        const _Kicker(),
        const SizedBox(height: 9),
        ApexRegisterHeading(
          'Settings',
          subtitle: 'Set up your company, documents and the way you work.',
          actions: [
            OutlinedButton.icon(
              onPressed: () => showCompanyEditor(context, widget.session),
              icon: const Icon(Icons.apartment_outlined, size: 16),
              label: const Text('Add company'),
            ),
          ],
        ),
        const SizedBox(height: 28),
        LayoutBuilder(
          builder: (context, limits) {
            final phone = limits.maxWidth < 700;
            final content = _content(phone);
            if (phone) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _rail(phone, 0),
                  const SizedBox(height: 22),
                  content,
                ],
              );
            }
            final railWidth = MediaQuery.sizeOf(context).width <= 1100
                ? 190.0
                : 225.0;
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(width: railWidth, child: _rail(phone, railWidth)),
                SizedBox(width: railWidth <= 190 ? 17 : 22),
                Expanded(child: content),
              ],
            );
          },
        ),
      ],
    );
  }

  List<_Tab> get _visibleTabs {
    final query = _search.text.trim().toLowerCase();
    return [
      for (final tab in _availableTabs)
        if ('${tab.title} ${tab.description} ${tab.keywords}'
            .toLowerCase()
            .contains(query))
          tab,
    ];
  }

  Widget _rail(bool phone, double width) {
    final company = _workspace.company;
    final visible = _visibleTabs;
    final search = Container(
      height: 46,
      padding: const EdgeInsets.symmetric(horizontal: 9),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: Apex.lineStrong),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        children: [
          const Icon(Icons.search_rounded, size: 16, color: Color(0xff798190)),
          const SizedBox(width: 10),
          Expanded(
            child: Semantics(
              label: 'Find a setting',
              child: TextField(
                controller: _search,
                onChanged: (_) => setState(() {}),
                style: const TextStyle(fontSize: 11),
                decoration: const InputDecoration(
                  hintText: 'Find a setting…',
                  hintStyle: TextStyle(fontSize: 11, color: Color(0xff798190)),
                  isDense: true,
                  filled: false,
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ),
          ),
        ],
      ),
    );
    final tabs = [
      for (final tab in visible)
        _RailTab(
          tab: tab,
          selected: tab == _tab,
          wide: !phone,
          onTap: () => _select(tab),
        ),
    ];
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: Apex.lineStrong),
        borderRadius: BorderRadius.circular(phone ? 6 : 7),
      ),
      child: Padding(
        padding: EdgeInsets.all(phone ? 6 : 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (!phone) ...[
              Container(
                color: Apex.paper,
                padding: const EdgeInsets.fromLTRB(5, 11, 5, 19),
                child: Row(
                  children: [
                    Container(
                      width: 33,
                      height: 35,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: const Color(0xffe4f1e9),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        company.name.isEmpty
                            ? 'A'
                            : company.name.characters.first,
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: Color(0xff17623b),
                        ),
                      ),
                    ),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            company.name.isEmpty
                                ? 'Your company'
                                : company.name,
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              height: 1.6,
                              color: Color(0xff27313d),
                            ),
                          ),
                          Text(
                            switch (company.taxMode) {
                              'regular' => 'GST registered',
                              'composition' => 'Composition',
                              _ => 'Non-GST business',
                            },
                            style: const TextStyle(
                              fontSize: 10,
                              color: Apex.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),
            ],
            search,
            SizedBox(height: phone ? 10 : 12),
            if (phone)
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    for (final tab in tabs) ...[tab, const SizedBox(width: 3)],
                  ],
                ),
              )
            else
              for (final tab in tabs) ...[tab, const SizedBox(height: 4)],
            if (visible.isEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 12, 4, 12),
                child: Semantics(
                  liveRegion: true,
                  child: const Text(
                    'No matching settings. Try logo, prefix, backup or GST.',
                    style: TextStyle(
                      fontSize: 11,
                      height: 1.7,
                      color: Color(0xff9c6b27),
                    ),
                  ),
                ),
              ),
            if (!phone)
              const Padding(
                padding: EdgeInsets.fromLTRB(4, 12, 4, 12),
                child: Text(
                  'Changes apply to this company. Account security applies to your sign-in.',
                  style: TextStyle(
                    fontSize: 11,
                    height: 1.7,
                    color: Apex.muted,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _content(bool phone) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final tab in _availableTabs)
        if (_visited.contains(tab))
          Visibility(
            visible: tab == _tab,
            maintainState: true,
            child: _tabPanel(tab, phone),
          ),
    ],
  );

  Widget _tabPanel(_Tab tab, bool phone) {
    final blocks = _blocks(tab);
    final jumps = [
      for (final (label, block)
          in _jumpLinks[tab] ?? const <(String, _Block)>[])
        if (blocks.contains(block)) (label, block),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(0, 4, 0, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Semantics(
                header: true,
                child: Text(
                  tab.title,
                  style: TextStyle(
                    fontSize: phone ? 18 : 20,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -.5,
                    color: Apex.ink,
                  ),
                ),
              ),
              const SizedBox(height: 5),
              Text(tab.description, style: Apex.note),
            ],
          ),
        ),
        if (jumps.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 18),
            child: Wrap(
              spacing: phone ? 6 : 8,
              runSpacing: phone ? 6 : 8,
              children: [
                for (final (label, block) in jumps)
                  SettingsJumpLink(label, onTap: () => _jump(label, block)),
              ],
            ),
          ),
        if (_busy)
          const Padding(
            padding: EdgeInsets.only(bottom: 10),
            child: LinearProgressIndicator(),
          ),
        if (_message case final status?)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: SettingsNotice(status),
          ),
        SettingsCard(
          padding: phone
              ? 18
              : MediaQuery.sizeOf(context).width <= 1100
              ? 20
              : 24,
          children: [for (final block in blocks) _blockView(block)],
        ),
      ],
    );
  }

  Widget _blockView(_Block block) {
    final data = block.data;
    if (data == null) {
      return KeyedSubtree(key: _anchors[block], child: _blockBody(block, null));
    }
    return KeyedSubtree(
      key: _anchors[block],
      child: FutureBuilder(
        future: _futures[data],
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const LinearProgressIndicator();
          }
          if (snapshot.hasError) {
            return SettingsNotice(
              'Couldn’t load these settings.',
              error: true,
              action: TextButton(
                onPressed: () => _reload(data),
                child: const Text('Retry'),
              ),
            );
          }
          return _blockBody(block, snapshot.data);
        },
      ),
    );
  }

  Widget _blockBody(_Block block, dynamic data) => switch (block) {
    _Block.company => _company(),
    _Block.branding => _branding(data as List),
    _Block.prefixes => _prefixes(data as List),
    _Block.formats => _formats(data as List),
    _Block.openings => SettingsBlock(
      title: 'Opening balances',
      children: [OpeningPartyPanel(workspace: _workspace)],
    ),
    _Block.period => _period(booksObject(data)),
    _Block.vyapar => VyaparPanel(workspace: _workspace),
    _Block.backup => BackupPanel(
      workspace: _workspace,
      session: widget.session,
      restoreAnchor: _restoreAnchor,
    ),
    _Block.access => _people(booksRows(data)),
    _Block.account => _account(),
    _Block.recovery => _recovery(booksObject(data)),
    _Block.audit => _audit(booksRows(data)),
    _Block.locations => _locations(booksObject(data)),
    _Block.automobile => _automobile(booksObject(data)),
    _Block.vehicles => _vehicles(booksObject(data)),
    _Block.commerce => SettingsBlock(
      title: 'Bagisto integration',
      note: 'Connect independent store channels and stock pools to this company. Review orders, deliveries and accounting reconciliation.',
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton(
            onPressed: () => setState(() => _commerceOpen = true),
            child: const Text('Open ecommerce workspace'),
          ),
        ),
      ],
    ),
  };

  Widget _company() {
    final company = _workspace.company;
    final mode = switch (company.taxMode) {
      'regular' => 'GST regular',
      'composition' => 'Composition',
      _ => 'Not GST registered',
    };
    return SettingsBlock(
      title: 'Business profile',
      children: [
        SettingsDetails([
          ('Company name', company.name.isEmpty ? '—' : company.name),
          ('Tax profile', mode),
          ('GSTIN', company.gstin.isEmpty ? 'Not registered' : company.gstin),
          ('State code', company.stateCode.isEmpty ? '—' : company.stateCode),
          (
            'Address',
            company.address.isEmpty ? 'Not provided' : company.address,
          ),
        ]),
        const SizedBox(height: 26),
        Text.rich(
          TextSpan(
            style: const TextStyle(fontSize: 13, color: Apex.muted),
            children: [
              const TextSpan(
                text: 'Book label: ',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              TextSpan(
                text: company.bookLabel.isEmpty ? 'Not set' : company.bookLabel,
              ),
              const TextSpan(
                text: ' · workspace label only, not printed on invoices',
                style: TextStyle(fontSize: 11),
              ),
            ],
          ),
        ),
        if (_owner) ...[
          const SizedBox(height: 10),
          _button(
            'Edit company details',
            () => showCompanyEditor(context, widget.session, company: company),
          ),
        ],
      ],
    );
  }

  Widget _period(Json rule) {
    final lockedThrough = booksText(rule['locked_through']);
    return SettingsBlock(
      title: 'Accounting period lock',
      note: 'Posted entries dated on or before the lock date cannot be added. The date can only move forward.',
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
                text: lockedThrough.isEmpty
                    ? 'No date set'
                    : apexDate(lockedThrough),
              ),
            ],
          ),
        ),
        if (_owner) ...[
          const SizedBox(height: 12),
          _button('Lock through date', () async {
            final today = DateTime.parse(businessDate());
            final earliest = DateTime.tryParse(lockedThrough) ?? DateTime(1900);
            final date = await showDatePicker(
              context: context,
              initialDate: earliest.isAfter(today) ? earliest : today,
              firstDate: earliest,
              lastDate: DateTime(
                (earliest.isAfter(today) ? earliest : today).year + 2,
                12,
                31,
              ),
            );
            if (!mounted || date == null) return;
            final value = booksDate(date);
            if (await _confirm(
                  'Lock all entries through ${apexDate(value)}?',
                  'This includes ${apexDate(value)}. You cannot move this lock backwards. Complete and review all entries for this period before confirming.',
                  action: 'Confirm period lock',
                ) !=
                true) {
              return;
            }
            await _action(() async {
              await _api.put(
                '$_path/period-lock',
                body: {'locked_through': value},
              );
              _reload(_Data.period);
            }, done: 'Period locked through ${apexDate(value)}.');
          }),
        ],
      ],
    );
  }

  Widget _people(List<Json> rows) => SettingsBlock(
    title: 'Team access',
    note: 'Registered users can be given editor or view-only access to this company.',
    children: [
      for (final row in rows)
        SettingsRow(
          title: booksText(row['email']),
          subtitle: _titleCase(booksText(row['role'])),
          trailing: !_owner || row['role'] == 'owner'
              ? null
              : ApexRowIconButton(
                  tooltip: 'Remove access for ${row['email']}',
                  icon: Icons.person_remove_outlined,
                  onPressed: _busy
                      ? null
                      : () async {
                          if (await _confirm(
                                'Remove company access?',
                                '${row['email']} will lose access to this company.',
                                action: 'Remove access',
                              ) !=
                              true) {
                            return;
                          }
                          await _action(() async {
                            await _api.delete(
                              '$_path/members/${Uri.encodeComponent(booksText(row['email']))}',
                            );
                            _refresh();
                          });
                        },
                ),
        ),
      if (_owner) ...[
        const SizedBox(height: 12),
        _button('Add a member', () async {
          final success = await showSettingsForm(
            context,
            title: 'Add a member',
            note: 'The person must already have an Apex Books account.',
            fields: [
              setting('email', 'Email address', maximum: 254),
              setting('role', 'Role', value: 'viewer'),
            ],
            choices: const {
              'role': [('viewer', 'Viewer'), ('editor', 'Editor')],
            },
            action: 'Grant access',
            save: (body) async {
              await _api.post('$_path/members', body: body);
            },
          );
          if (success == true) _refresh();
        }),
      ],
    ],
  );

  Widget _audit(List<Json> rows) => SettingsBlock(
    title: 'Activity log',
    note: 'Recent changes in this company, including who made them.',
    trailing: OutlinedButton(
      onPressed: _busy ? null : () => _reload(_Data.audit),
      child: const Text('Refresh'),
    ),
    children: [
      if (rows.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 6),
          child: Text('No activity yet.', style: Apex.note),
        ),
      for (final row in rows)
        Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            shape: const Border(top: BorderSide(color: Apex.lineSoft)),
            collapsedShape: const Border(top: BorderSide(color: Apex.lineSoft)),
            title: Text(
              _titleCase(
                booksText(row['action']).replaceAll(RegExp(r'[._]'), ' '),
              ),
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
            subtitle: Text(
              '${row['actor']} · ${row['occurred_at']}',
              style: Apex.note.copyWith(height: 1.4),
            ),
            children: [
              if (row['details'] case final Json details)
                for (final entry in details.entries)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(entry.key.replaceAll('_', ' ')),
                    subtitle: SelectableText('${entry.value}'),
                  ),
            ],
          ),
        ),
    ],
  );

  Widget _account() => SettingsBlock(
    title: 'Account security',
    note: 'Change your password to end every existing sign-in session. You will sign in again.',
    children: [
      _button('Change password', () async {
        final success = await showSettingsForm(
          context,
          title: 'Change password',
          fields: [
            setting(
              'current_password',
              'Current password',
              maximum: 128,
              secret: true,
            ),
            setting('new_password', 'New password', maximum: 128, secret: true),
          ],
          action: 'Change password',
          save: (data) async {
            if (data['new_password']!.length < 8) {
              throw const FormatException('Use at least eight characters.');
            }
            await widget.session.accountApi.post(
              '/api/auth/change-password',
              body: data,
            );
          },
        );
        if (success == true) await widget.session.signOut();
      }),
      const SizedBox(height: 16),
      const Text(
        'End other sign-ins if you no longer use those devices.',
        style: Apex.note,
      ),
      const SizedBox(height: 8),
      _button('Sign out other sessions', () async {
        if (await _confirm(
              'Sign out other sessions?',
              'This device will keep its current session.',
            ) !=
            true) {
          return;
        }
        await _action(() async {
          await widget.session.accountApi.post(
            '/api/auth/logout-other-sessions',
            body: {},
          );
        }, done: 'Other sessions signed out.');
      }),
    ],
  );

  Widget _recovery(Json status) {
    final remaining = status['remaining'];
    return SettingsBlock(
      title: 'Account recovery',
      note:
          '${remaining == null || remaining == 0 ? 'Generate recovery codes so you can regain access if you forget your password.' : '$remaining unused recovery codes available.'} Keep codes private and separate from company backups. Generating a set invalidates earlier codes.',
      children: [
        _button('Generate recovery codes', () async {
          List<String> codes = [];
          final success = await showSettingsForm(
            context,
            title: 'Generate recovery codes',
            note: 'Generating codes replaces any previous set. Each new code can be used once.',
            action: 'Generate codes',
            fields: [
              setting(
                'current_password',
                'Current password',
                maximum: 128,
                secret: true,
              ),
            ],
            save: (data) async {
              final value = booksObject(
                await widget.session.accountApi.post(
                  '/api/auth/recovery-codes',
                  body: data,
                ),
              );
              codes = (value['codes'] as List).cast<String>();
            },
          );
          if (!mounted || success != true) return;
          await showDialog<void>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('Save your recovery codes'),
              scrollable: true,
              content: SelectableText(codes.join('\n')),
              actions: [
                TextButton(
                  onPressed: () =>
                      Clipboard.setData(ClipboardData(text: codes.join('\n'))),
                  child: const Text('Copy codes'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Done'),
                ),
              ],
            ),
          );
          _reload(_Data.recovery);
        }),
      ],
    );
  }

  Widget _branding(List values) {
    final brand = booksObject(values[1]);
    String text(String key, String empty) =>
        booksText(brand[key]).isEmpty ? empty : booksText(brand[key]);
    return SettingsBlock(
      title: 'Company logo and document branding',
      note: 'Logo, signature and payment details appear on your PDF documents.',
      children: [
        SettingsDetails([
          ('Phone', text('phone', '—')),
          ('Email', text('email', '—')),
          ('Bank', text('bank_name', '—')),
          ('Logo', booksText(brand['logo']).isEmpty ? 'Not added' : 'Uploaded'),
          (
            'Signature',
            booksText(brand['signature']).isEmpty ? 'Not added' : 'Uploaded',
          ),
        ]),
        if (_owner) ...[
          const SizedBox(height: 18),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _button('Edit branding details', () => _editBrand(brand)),
              _button('Upload company logo', () => _uploadBrandAsset('logo')),
              _button('Upload signature', () => _uploadBrandAsset('signature')),
              if (booksText(brand['logo']).isNotEmpty)
                _button('Remove logo', () => _removeBrandAsset('logo')),
              if (booksText(brand['signature']).isNotEmpty)
                _button(
                  'Remove signature',
                  () => _removeBrandAsset('signature'),
                ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _prefixes(List values) {
    final series = booksRows(values[2]);
    return SettingsBlock(
      title: 'Transaction prefixes',
      note: 'Financial year numbering',
      children: [
        for (final row in series.take(100))
          SettingsRow(
            title: booksKindLabel(booksText(row['kind'])),
            subtitle:
                '${row['financial_year']} · ${row['prefix']} · Next ${row['next_number']}',
          ),
        if (_owner) ...[
          const SizedBox(height: 12),
          _button('Set document prefix', _editSeries),
        ],
      ],
    );
  }

  Widget _formats(List values) {
    final layout = booksText(booksObject(values[0])['document_template']);
    return SettingsBlock(
      title: 'Document PDF layout',
      note: 'Previews use synthetic sample details. Logos, signature images and bank details come from Document branding.',
      children: [
        SettingsDetails([
          ('Layout', _layoutNames[layout] ?? _titleCase(layout)),
        ]),
        if (_owner) ...[
          const SizedBox(height: 14),
          _button('Change layout', () async {
            final done = await showSettingsForm(
              context,
              title: 'Document PDF layout',
              fields: [setting('document_template', 'Layout', value: layout)],
              choices: {
                'document_template': [
                  for (final entry in _layoutNames.entries)
                    (entry.key, entry.value),
                ],
              },
              save: (body) async {
                await _api.put('$_path/preferences', body: body);
              },
            );
            if (done == true) _refresh();
          }),
        ],
      ],
    );
  }

  Widget _locations(Json setup) {
    final locations = booksRows(setup['locations']);
    return SettingsBlock(
      title: 'Item locations',
      icon: Icons.place_outlined,
      note: 'Name the places you keep stock, such as Rack 1, Shelf B or Counter drawer. Items can then be filed under one or more of them, and shown and searched by location.',
      children: [
        if (locations.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 6),
            child: Text('No locations yet', style: Apex.note),
          ),
        for (final location in locations)
          SettingsRow(
            title: booksText(location['name']),
            subtitle: location['active'] == false ? 'Archived' : 'Active',
            onTap: _owner && !_busy ? () => _location(setup, location) : null,
            trailing: _owner
                ? const Icon(Icons.edit_outlined, size: 18, color: Apex.muted)
                : null,
          ),
        if (_owner) ...[
          const SizedBox(height: 12),
          _button('Add a location', () => _location(setup, null)),
        ],
      ],
    );
  }

  Widget _automobile(Json setup) {
    final enabled = setup['automobile_enabled'] == true;
    return SettingsBlock(
      title: 'Automobile module',
      icon: Icons.directions_car_outlined,
      note: 'Turn this on for a parts counter, workshop, dealer, or tyre and battery shop. Items then get vehicle details: the makes and models a part fits, a part number, brand and grade. Turning it off hides those details but keeps what you entered.',
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Automobile'),
          subtitle: const Text('Vehicle fitment and part information on items'),
          value: enabled,
          onChanged: !_owner || _busy
              ? null
              : (value) => _action(() async {
                  await _saveSetup(setup, {'automobile_enabled': value});
                  _reload(_Data.inventory);
                }),
        ),
      ],
    );
  }

  Widget _vehicles(Json setup) {
    final enabled = setup['automobile_enabled'] == true;
    return SettingsBlock(
      title: 'Vehicle makes and models',
      icon: Icons.directions_car_outlined,
      note: 'These lists fill the pickers when you describe which vehicles a part fits. Add your own makes and models.',
      children: [
        for (final make in booksRows(setup['vehicle_added']))
          SettingsRow(
            title: booksText(make['make']),
            subtitle: (make['models'] as List).join(', '),
          ),
        if (enabled && _owner) ...[
          const SizedBox(height: 12),
          _button('Add a vehicle make or model', () => _vehicle(setup)),
        ],
      ],
    );
  }

  Future<void> _editBrand(Json brand) async {
    final done = await showSettingsForm(
      context,
      title: 'Branding & payment details',
      fields: [
        for (final (key, label, maximum) in const [
          ('phone', 'Phone', 32),
          ('email', 'Email', 254),
          ('bank_name', 'Bank', 120),
          ('account_number', 'Account number', 64),
          ('ifsc', 'IFSC', 20),
          ('branch', 'Branch', 120),
          ('upi_id', 'UPI ID', 120),
          ('notes', 'Default notes', 1500),
          ('terms', 'Default terms', 3000),
        ])
          setting(key, label, value: booksText(brand[key]), maximum: maximum),
      ],
      save: (body) async {
        await _api.patch('$_path/document-branding', body: body);
      },
    );
    if (done == true) _refresh();
  }

  Future<void> _editSeries() async {
    final today = DateTime.parse(businessDate());
    final year = today.year - (today.month < 4 ? 1 : 0);
    final fiscal =
        '${(year % 100).toString().padLeft(2, '0')}-${((year + 1) % 100).toString().padLeft(2, '0')}';
    final done = await showSettingsForm(
      context,
      title: 'Set document prefix',
      fields: [
        setting('kind', 'Document type', value: 'sales_invoice'),
        setting(
          'financial_year',
          'Financial year (YY-YY)',
          value: fiscal,
          maximum: 5,
        ),
        setting('prefix', 'Prefix', maximum: 5),
      ],
      choices: {
        'kind': [
          for (final kind in const [
            'sales_invoice',
            'purchase_bill',
            'pos',
            'credit_note',
            'debit_note',
            'estimate',
            'proforma',
            'sales_order',
            'purchase_order',
            'payment_in',
            'payment_out',
            'expense',
          ])
            (kind, booksKindLabel(kind)),
        ],
      },
      save: (body) async {
        await _api.put('$_path/number-series', body: body);
      },
    );
    if (done == true) _refresh();
  }

  Future<void> _uploadBrandAsset(String field) => _action(() async {
    final source = await pickApexFile(['png', 'jpg', 'jpeg'], 250000);
    if (source == null || !mounted) return;
    final mime = source.name.toLowerCase().endsWith('.png')
        ? 'image/png'
        : 'image/jpeg';
    await _api.patch(
      '$_path/document-branding',
      body: {field: 'data:$mime;base64,${base64Encode(source.bytes)}'},
    );
    _refresh();
  });

  Future<void> _removeBrandAsset(String field) async {
    if (await _confirm(
          'Remove $field?',
          'New documents will use the updated branding.',
        ) !=
        true) {
      return;
    }
    await _action(() async {
      await _api.patch('$_path/document-branding', body: {field: ''});
      _refresh();
    });
  }

  Future<void> _location(Json setup, Json? location) async {
    final changed = await showSettingsForm(
      context,
      title: location == null ? 'Add location' : 'Edit location',
      fields: [
        setting(
          'name',
          'Shelf or location name',
          maximum: 40,
          value: booksText(location?['name']),
        ),
        setting(
          'status',
          'Status',
          value: location?['active'] == false ? 'archived' : 'active',
        ),
      ],
      choices: const {
        'status': [('active', 'Active'), ('archived', 'Archived')],
      },
      save: (body) async {
        if (body['name']!.isEmpty) {
          throw const FormatException('Enter a location name.');
        }
        final edited = <String, dynamic>{
          if (location != null) 'id': location['id'],
          'name': body['name'],
          'active': body['status'] == 'active',
        };
        final locations = [
          for (final row in booksRows(setup['locations']))
            if (row['id'] == location?['id'])
              edited
            else
              {'id': row['id'], 'name': row['name'], 'active': row['active']},
          if (location == null) edited,
        ];
        await _saveSetup(setup, {'locations': locations});
      },
    );
    if (changed == true) _refresh();
  }

  Future<void> _vehicle(Json setup) async {
    final changed = await showSettingsForm(
      context,
      title: 'Add a vehicle make or model',
      fields: [
        setting('make', 'Make', maximum: 40),
        setting('model', 'Model (optional)', maximum: 60),
        setting('type', 'Vehicle type', value: 'car'),
      ],
      choices: const {
        'type': [
          ('car', 'Car'),
          ('two_wheeler', 'Two wheeler'),
          ('commercial', 'Commercial'),
          ('three_wheeler', 'Three wheeler'),
        ],
      },
      save: (body) async {
        final name = body['make']!;
        final model = body['model']!;
        if (name.isEmpty) throw const FormatException('Enter a vehicle make.');
        final entries = booksRows(setup['vehicle_added']).toList();
        final index = entries.indexWhere(
          (row) => booksText(row['make']).toLowerCase() == name.toLowerCase(),
        );
        if (index < 0) {
          entries.add({
            'make': name,
            'type': body['type'],
            'models': [if (model.isNotEmpty) model],
          });
        } else if (model.isNotEmpty) {
          final models = (entries[index]['models'] as List).cast<String>();
          if (!models.any(
            (entry) => entry.toLowerCase() == model.toLowerCase(),
          )) {
            entries[index] = {
              ...entries[index],
              'models': [...models, model],
            };
          }
        }
        await _saveSetup(setup, {'vehicle_added': entries});
      },
    );
    if (changed == true) _refresh();
  }

  Future<void> _saveSetup(Json setup, Json changes) async {
    await _api.put(
      '$_path/inventory-setup',
      body: {
        'version': setup['version'],
        'automobile_enabled': setup['automobile_enabled'],
        'locations': [
          for (final row in booksRows(setup['locations']))
            {'id': row['id'], 'name': row['name'], 'active': row['active']},
        ],
        'vehicle_added': setup['vehicle_added'],
        'vehicle_hidden_makes': setup['vehicle_hidden_makes'],
        'vehicle_hidden_models': setup['vehicle_hidden_models'],
        ...changes,
      },
    );
    await _workspace.refresh();
  }

  Widget _button(String title, VoidCallback action) => Align(
    alignment: Alignment.centerLeft,
    child: OutlinedButton(onPressed: _busy ? null : action, child: Text(title)),
  );

  Future<bool?> _confirm(
    String title,
    String message, {
    String action = 'Confirm',
  }) => showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          child: Text(action),
        ),
      ],
    ),
  );
}

/// "YOUR WORKSPACE" kicker with its green dot.
class _Kicker extends StatelessWidget {
  const _Kicker();

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 5,
        height: 5,
        decoration: const BoxDecoration(
          color: Apex.green,
          shape: BoxShape.circle,
        ),
      ),
      const SizedBox(width: 7),
      const Text(
        'YOUR WORKSPACE',
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w700,
          letterSpacing: .96,
          color: Color(0xff596472),
        ),
      ),
    ],
  );
}

/// One category button in the settings rail.
class _RailTab extends StatelessWidget {
  const _RailTab({
    required this.tab,
    required this.selected,
    required this.wide,
    required this.onTap,
  });

  final _Tab tab;
  final bool selected;
  final bool wide;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? const Color(0xff075e34) : Apex.muted;
    return Semantics(
      button: true,
      selected: selected,
      label: tab.title,
      excludeSemantics: true,
      onTap: onTap,
      child: Material(
        color: selected ? const Color(0xffeaf5ee) : Colors.white,
        borderRadius: BorderRadius.circular(7),
        child: InkWell(
          borderRadius: BorderRadius.circular(7),
          onTap: onTap,
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: wide ? 10 : 12,
              vertical: wide ? 12 : 11,
            ),
            child: Row(
              mainAxisSize: wide ? MainAxisSize.max : MainAxisSize.min,
              children: [
                Icon(tab.icon, size: wide ? 17 : 15, color: color),
                SizedBox(width: wide ? 11 : 8),
                if (wide) Expanded(child: _label(color)) else _label(color),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _label(Color color) => Text(
    tab.title,
    maxLines: 1,
    overflow: TextOverflow.ellipsis,
    style: TextStyle(
      fontSize: 11,
      fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
      color: color,
    ),
  );
}
