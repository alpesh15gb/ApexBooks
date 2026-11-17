import 'package:material_ui/material_ui.dart';

import '../../core/session.dart';
import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../books/books_data.dart';
import '../commerce/commerce_screen.dart';
import '../masters/master_import.dart';
import 'backup_panel.dart';
import 'opening_party_panel.dart';
import 'settings_about.dart';
import 'settings_accounting.dart';
import 'settings_blocks.dart';
import 'settings_documents.dart';
import 'settings_fields.dart';
import 'settings_forms.dart';
import 'settings_people.dart';
import 'settings_stock.dart';
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
  branding(_Tab.documents, data: _Data.documents, ownerOnly: true),
  prefixes(_Tab.documents, data: _Data.documents),
  formats(_Tab.documents, data: _Data.documents),
  openings(_Tab.accounting, ownerOnly: true),
  period(_Tab.accounting, data: _Data.period),
  vyapar(_Tab.data, ownerOnly: true),
  masters(_Tab.data),
  backup(_Tab.data),
  access(_Tab.access, data: _Data.access),
  account(_Tab.security),
  recovery(_Tab.security, data: _Data.recovery),
  audit(_Tab.security, data: _Data.audit, ownerOnly: true),
  locations(_Tab.inventory, data: _Data.inventory),
  automobile(_Tab.inventory, data: _Data.inventory, hidden: true),
  vehicles(_Tab.inventory, data: _Data.inventory, hidden: true),
  commerce(_Tab.commerce);

  const _Block(
    this.tab, {
    this.data,
    this.ownerOnly = false,
    this.hidden = false,
  });
  final bool hidden;
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
    ('CSV import', _Block.masters),
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
  final _exportAnchor = GlobalKey();
  final _futures = <_Data, Future<dynamic>>{};
  final _visited = <_Tab>{_Tab.company};
  _Tab _tab = _Tab.company;
  bool _commerceOpen = false;
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
      if (block.tab == tab && !block.hidden && (_owner || !block.ownerOnly))
        block,
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
    _Data.audit => _api.get('$_path/audit-events', query: {'limit': '50'}),
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
      _search.clear();
      _visited.add(tab);
      _ensureLoaded(tab);
    });
  }

  void _reload(_Data data) {
    if (mounted) setState(() => _futures[data] = _load(data));
  }

  void _jump(String label, _Block block) {
    final context =
        (label == 'Backup & restore'
                ? _restoreAnchor
                : label == 'Export data'
                ? _exportAnchor
                : _anchors[block]!)
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
            if (!phone) ...[
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
              const Divider(height: 1, color: Apex.lineSoft),
            ],
            SettingsAbout(api: _api),
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
        if (blocks.contains(block) || (block.hidden && block.tab == tab))
          (label, block),
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
          if (!snapshot.hasData && !snapshot.hasError) {
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
    _Block.branding => BrandingForm(
      workspace: _workspace,
      initial: booksObject((data as List)[1]),
    ),
    _Block.prefixes => PrefixesForm(
      workspace: _workspace,
      series: booksRows((data as List)[2]),
      onSaved: () async => _reload(_Data.documents),
    ),
    _Block.formats => LayoutGallery(
      workspace: _workspace,
      layout: booksText(booksObject((data as List)[0])['document_template']),
      onSaved: () async => _reload(_Data.documents),
    ),
    _Block.openings => SettingsBlock(
      title: 'Opening balances',
      note:
          'Set balances before the first transaction for that party or cash/bank account. Opening stock is available in Items.',
      children: [OpeningPartyPanel(workspace: _workspace)],
    ),
    _Block.period => PeriodLockForm(
      workspace: _workspace,
      lockedThrough: booksText(booksObject(data)['locked_through']),
    ),
    _Block.vyapar => VyaparPanel(workspace: _workspace),
    _Block.masters => _masters(),
    _Block.backup => BackupPanel(
      workspace: _workspace,
      session: widget.session,
      restoreAnchor: _restoreAnchor,
      exportAnchor: _exportAnchor,
    ),
    _Block.access => MembersPanel(
      workspace: _workspace,
      members: booksRows(data),
      onChanged: () async => _reload(_Data.access),
    ),
    _Block.account => AccountSecurityPanel(session: widget.session),
    _Block.recovery => RecoveryCodesPanel(
      session: widget.session,
      remaining: booksObject(data)['remaining'],
    ),
    _Block.audit => AuditPanel(
      events: booksRows(data),
      onRefresh: () => _reload(_Data.audit),
    ),
    _Block.locations => InventorySetupEditor(
      workspace: _workspace,
      setup: booksObject(data),
      onReload: () async => _reload(_Data.inventory),
      anchors: {
        'automobile': _anchors[_Block.automobile]!,
        'vehicles': _anchors[_Block.vehicles]!,
      },
    ),
    _Block.automobile || _Block.vehicles => const SizedBox.shrink(),
    _Block.commerce => SettingsBlock(
      title: 'Bagisto integration',
      note:
          'Connect independent store channels and stock pools to this company. Review orders, deliveries and accounting reconciliation.',
      children: [
        SettingsButton(
          'Open ecommerce workspace',
          primary: true,
          onPressed: () => setState(() => _commerceOpen = true),
        ),
      ],
    ),
  };

  Widget _masters() => SettingsBlock(
    title: 'Import parties or items',
    note:
        'Preview a CSV before adding records. Duplicate names in this company are skipped.',
    children: [
      const Text(
        'Party columns: name, party_type, gstin, address, phone, email. Item columns: name, hsn, unit, sale_rate, purchase_rate, gst_rate, track_stock (true/false).',
        style: Apex.note,
      ),
      const SizedBox(height: 12),
      Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final (kind, label) in const [
            ('party', 'Import parties from CSV'),
            ('item', 'Import items from CSV'),
          ])
            OutlinedButton(
              onPressed: _workspace.company.canWrite
                  ? () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => MasterImportPage(
                          workspace: _workspace,
                          initialKind: kind,
                        ),
                      ),
                    )
                  : null,
              child: Text(label),
            ),
        ],
      ),
    ],
  );

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
          SettingsButton(
            'Edit company details',
            onPressed: () =>
                showCompanyEditor(context, widget.session, company: company),
          ),
        ],
      ],
    );
  }
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
