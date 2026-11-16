part of 'app.dart';

/// Every place the workspace can open. Mirrors the web app's navigation keys so
/// both clients are organised the same way.
enum _Route {
  dashboard('Dashboard', Icons.space_dashboard_outlined, _Destination.home),
  pos('POS', Icons.point_of_sale_outlined, _Destination.pointOfSale),
  items(
    'Items',
    Icons.inventory_2_outlined,
    _Destination.masters,
    master: MasterGroup.item,
  ),
  stock('Stock', Icons.warehouse_outlined, _Destination.stock),
  parties(
    'Parties',
    Icons.people_alt_outlined,
    _Destination.masters,
    master: MasterGroup.customer,
  ),
  salesInvoice(
    'Sales invoices',
    Icons.receipt_long_outlined,
    _Destination.books,
    kind: 'sales_invoice',
  ),
  estimate(
    'Estimates',
    Icons.request_quote_outlined,
    _Destination.books,
    kind: 'estimate',
  ),
  salesOrder(
    'Sales orders',
    Icons.assignment_outlined,
    _Destination.books,
    kind: 'sales_order',
  ),
  proforma(
    'Proforma invoices',
    Icons.description_outlined,
    _Destination.books,
    kind: 'proforma',
  ),
  paymentIn(
    'Payment in',
    Icons.south_west_rounded,
    _Destination.books,
    kind: 'payment_in',
  ),
  creditNote(
    'Credit notes',
    Icons.assignment_return_outlined,
    _Destination.books,
    kind: 'credit_note',
  ),
  purchaseBill(
    'Purchase bills',
    Icons.receipt_outlined,
    _Destination.books,
    kind: 'purchase_bill',
  ),
  paymentOut(
    'Payment out',
    Icons.north_east_rounded,
    _Destination.books,
    kind: 'payment_out',
  ),
  expense(
    'Expenses',
    Icons.account_balance_wallet_outlined,
    _Destination.books,
    kind: 'expense',
  ),
  purchaseOrder(
    'Purchase orders',
    Icons.shopping_bag_outlined,
    _Destination.books,
    kind: 'purchase_order',
  ),
  debitNote(
    'Debit notes',
    Icons.assignment_late_outlined,
    _Destination.books,
    kind: 'debit_note',
  ),
  allTransactions(
    'All transactions',
    Icons.list_alt_rounded,
    _Destination.books,
  ),
  bank('Cash & bank', Icons.account_balance_outlined, _Destination.banking),
  dayBook(
    'Day book',
    Icons.menu_book_outlined,
    _Destination.reports,
    report: BooksReport.dayBook,
  ),
  ledger('Ledger', Icons.article_outlined, _Destination.ledger),
  reports('Reports', Icons.bar_chart_rounded, _Destination.reports),
  recurring(
    'Recurring drafts',
    Icons.event_repeat_outlined,
    _Destination.books,
    opensRecurring: true,
  ),
  commerce('Ecommerce', Icons.storefront_outlined, _Destination.commerce),
  settings('Settings', Icons.settings_outlined, _Destination.settings);

  const _Route(
    this.label,
    this.icon,
    this.destination, {
    this.kind,
    this.master,
    this.report,
    this.opensRecurring = false,
  });

  final String label;
  final IconData icon;
  final _Destination destination;
  final String? kind;
  final MasterGroup? master;
  final BooksReport? report;
  final bool opensRecurring;

  /// The section a page belongs to, shown in the header breadcrumb.
  String? get section => switch (this) {
    salesInvoice || estimate || salesOrder || proforma || paymentIn || creditNote => 'Sales',
    purchaseBill || paymentOut || expense || purchaseOrder || debitNote => 'Purchases',
    _ => null,
  };
}

const _salesRoutes = [
  _Route.salesInvoice,
  _Route.estimate,
  _Route.salesOrder,
  _Route.proforma,
  _Route.paymentIn,
  _Route.creditNote,
];
const _purchaseRoutes = [
  _Route.purchaseBill,
  _Route.paymentOut,
  _Route.expense,
  _Route.purchaseOrder,
  _Route.debitNote,
];

/// Sidebar sections, in the web app's order.
const _navigation = <(String, List<Object>)>[
  ('Workspace', [_Route.dashboard, _Route.pos, _Route.items, _Route.stock, _Route.parties]),
  (
    'Transactions',
    [
      ('Sales', Icons.shopping_cart_outlined, _salesRoutes),
      ('Purchases', Icons.shopping_bag_outlined, _purchaseRoutes),
    ],
  ),
  ('Accounting', [_Route.bank, _Route.dayBook, _Route.ledger, _Route.reports]),
  ('Business tools', [_Route.recurring, _Route.commerce, _Route.settings]),
];

class _WorkspaceSidebar extends StatefulWidget {
  const _WorkspaceSidebar({
    required this.expanded,
    required this.active,
    required this.select,
    required this.newTransaction,
    required this.findWorkspace,
    required this.company,
    required this.addCompany,
    required this.signOut,
  });

  final bool expanded;
  final _Route active;
  final ValueChanged<_Route> select;
  final VoidCallback? newTransaction;
  final VoidCallback findWorkspace;
  final Widget company;
  final VoidCallback addCompany;
  final VoidCallback signOut;

  @override
  State<_WorkspaceSidebar> createState() => _WorkspaceSidebarState();
}

class _WorkspaceSidebarState extends State<_WorkspaceSidebar> {
  late final Set<String> _open = {
    if (_salesRoutes.contains(widget.active)) 'Sales',
    if (_purchaseRoutes.contains(widget.active)) 'Purchases',
  };

  @override
  void didUpdateWidget(covariant _WorkspaceSidebar old) {
    super.didUpdateWidget(old);
    // Like the web app, only the active page's group stays open after navigating.
    if (old.active != widget.active) {
      _open
        ..clear()
        ..addAll([
          if (_salesRoutes.contains(widget.active)) 'Sales',
          if (_purchaseRoutes.contains(widget.active)) 'Purchases',
        ]);
    }
  }

  bool get _expanded => widget.expanded;

  @override
  Widget build(BuildContext context) => Material(
    color: Apex.sidebar,
    child: SizedBox(
      width: _expanded ? 232 : 66,
      child: FocusTraversalGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(_expanded ? 12 : 9, 18, _expanded ? 12 : 9, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: EdgeInsets.only(left: _expanded ? 8 : 0),
                    child: Align(
                      alignment: _expanded ? Alignment.centerLeft : Alignment.center,
                      child: _Brand(onDark: true, compact: !_expanded),
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_expanded) widget.company,
                  if (_expanded) const SizedBox(height: 13),
                  if (widget.newTransaction case final action?)
                    _expanded
                        ? FilledButton.icon(
                            onPressed: action,
                            icon: const Icon(Icons.add, size: 18),
                            label: const Text('New transaction'),
                            style: FilledButton.styleFrom(
                              backgroundColor: Apex.sidebarCta,
                              foregroundColor: Apex.sidebarCtaText,
                              minimumSize: const Size(0, 40),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                          )
                        : IconButton.filled(
                            onPressed: action,
                            tooltip: 'New transaction',
                            style: IconButton.styleFrom(
                              backgroundColor: Apex.sidebarCta,
                              foregroundColor: Apex.sidebarCtaText,
                            ),
                            icon: const Icon(Icons.add),
                          ),
                  if (!_expanded)
                    IconButton(
                      onPressed: widget.findWorkspace,
                      tooltip: 'Search books',
                      color: Apex.sidebarText,
                      icon: const Icon(Icons.search),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            // The menu scrolls on its own so the account actions below stay reachable on short windows.
            Expanded(
              child: Semantics(
                label: 'Workspace navigation',
                container: true,
                explicitChildNodes: true,
                child: ListView(
                  padding: EdgeInsets.fromLTRB(_expanded ? 12 : 7, 8, _expanded ? 12 : 7, 12),
                  children: [
                    for (final (index, (title, entries)) in _navigation.indexed) ...[
                      if (index > 0) SizedBox(height: _expanded ? 14 : 8),
                      if (_expanded)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(13, 0, 10, 8),
                          child: ExcludeSemantics(
                            child: Text(title.toUpperCase(), style: Apex.eyebrow),
                          ),
                        )
                      else if (index > 0)
                        const Divider(color: Apex.sidebarBorder, indent: 8, endIndent: 8, height: 1),
                      for (final entry in entries)
                        if (entry is _Route)
                          _row(entry)
                        else if (entry case (final String name, final IconData icon, final List<_Route> routes))
                          ..._group(name, icon, routes),
                    ],
                  ],
                ),
              ),
            ),
            if (_expanded) ...[
              const Divider(color: Apex.sidebarBorder, height: 1, indent: 12, endIndent: 12),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 6, 12, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _footer(Icons.add, 'Add company', widget.addCompany),
                    _footer(Icons.logout_rounded, 'Sign out', widget.signOut),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    ),
  );

  Widget _footer(IconData icon, String label, VoidCallback onTap) => InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(10),
    hoverColor: const Color(0x16ffffff),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          Icon(icon, size: 16, color: Apex.sidebarFoot),
          const SizedBox(width: 10),
          Text(
            label,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: Apex.sidebarFoot),
          ),
        ],
      ),
    ),
  );

  Iterable<Widget> _group(String name, IconData icon, List<_Route> routes) sync* {
    final containsActive = routes.contains(widget.active);
    if (!_expanded) {
      // Collapsed rail: show each page as its own icon so nothing is hidden.
      for (final route in routes) {
        yield _row(route);
      }
      return;
    }
    final open = _open.contains(name);
    yield _item(
      label: name,
      icon: icon,
      selected: containsActive && !open,
      trailing: AnimatedRotation(
        turns: open ? .5 : 0,
        duration: const Duration(milliseconds: 150),
        child: Icon(Icons.expand_more_rounded, size: 18, color: Apex.sidebarText.withValues(alpha: .8)),
      ),
      expandedState: open,
      onTap: () => setState(() => open ? _open.remove(name) : _open.add(name)),
    );
    if (!open) return;
    yield Padding(
      padding: const EdgeInsets.fromLTRB(26, 2, 0, 6),
      child: DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(left: BorderSide(color: Apex.sidebarBorder)),
        ),
        child: Padding(
          padding: const EdgeInsets.only(left: 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [for (final route in routes) _row(route, child: true)],
          ),
        ),
      ),
    );
  }

  Widget _row(_Route route, {bool child = false}) => _item(
    label: route.label,
    icon: child ? null : route.icon,
    selected: route == widget.active,
    child: child,
    onTap: () => widget.select(route),
  );

  Widget _item({
    required String label,
    required IconData? icon,
    required bool selected,
    required VoidCallback onTap,
    bool child = false,
    Widget? trailing,
    bool? expandedState,
  }) {
    final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(7));
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Semantics(
        button: true,
        expanded: expandedState,
        label: label,
        selected: selected,
        onTap: onTap,
        child: Tooltip(
          message: _expanded ? '' : label,
          excludeFromSemantics: true,
          child: Ink(
            decoration: ShapeDecoration(
              shape: shape,
              color: selected ? Apex.sidebarActive : Colors.transparent,
              shadows: selected && !child && _expanded
                  ? const [BoxShadow(color: Apex.sidebarAccent, offset: Offset(-3, 0), spreadRadius: -0.5)]
                  : null,
            ),
            child: InkWell(
              onTap: onTap,
              excludeFromSemantics: true,
              customBorder: shape,
              hoverColor: const Color(0x14ffffff),
              focusColor: const Color(0x26ffffff),
              child: ExcludeSemantics(
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: child ? 34 : 37),
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: _expanded ? 12 : 0),
                    child: Row(
                      mainAxisAlignment: _expanded ? MainAxisAlignment.start : MainAxisAlignment.center,
                      children: [
                        if (icon != null) Icon(icon, size: 18, color: selected ? Colors.white : Apex.sidebarText),
                        if (_expanded) ...[
                          if (icon != null) const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              label,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 13,
                                color: selected ? Colors.white : Apex.sidebarText,
                                fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                              ),
                            ),
                          ),
                          ?trailing,
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _WorkspaceHeader extends StatelessWidget {
  const _WorkspaceHeader({
    required this.active,
    required this.profile,
    required this.findWorkspace,
    required this.showShortcut,
    required this.compact,
  });

  final _Route active;
  final Widget profile;
  final VoidCallback findWorkspace;
  final bool showShortcut;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final trail = ['Apex Books', ?active.section];
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(bottom: BorderSide(color: Apex.line)),
      ),
      child: SizedBox(
        height: 64,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: compact ? 18 : 28),
          child: Row(
            children: [
              Expanded(
                flex: 2,
                child: Semantics(
                  container: true,
                  label: [...trail, active.label].join(', '),
                  child: ExcludeSemantics(
                    child: Row(
                      children: [
                        for (final crumb in trail) ...[
                          Flexible(
                            child: Text(
                              crumb,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 12, color: Apex.crumb),
                            ),
                          ),
                          const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 9),
                            child: Icon(Icons.chevron_right_rounded, size: 15, color: Apex.crumb),
                          ),
                        ],
                        Flexible(
                          child: Text(
                            active.label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Apex.inkSoft),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              Flexible(
                flex: 3,
                child: Align(
                  alignment: Alignment.center,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: Material(
                      color: const Color(0xfff5f8f6),
                      shape: RoundedRectangleBorder(
                        side: const BorderSide(color: Color(0xffcbd9d0)),
                        borderRadius: BorderRadius.circular(Apex.radiusControl),
                      ),
                      child: InkWell(
                        onTap: findWorkspace,
                        borderRadius: BorderRadius.circular(Apex.radiusControl),
                        child: SizedBox(
                          height: 40,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 13),
                            child: Row(
                              children: [
                                const Icon(Icons.search_rounded, size: 18, color: Apex.muted),
                                const SizedBox(width: 10),
                                const Expanded(
                                  child: Text(
                                    'Search books',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(fontSize: 13, color: Apex.muted),
                                  ),
                                ),
                                if (showShortcut)
                                  ExcludeSemantics(
                                    child: DecoratedBox(
                                      decoration: BoxDecoration(
                                        color: Colors.white,
                                        borderRadius: BorderRadius.circular(4),
                                        border: Border.all(color: Apex.lineStrong),
                                      ),
                                      child: const Padding(
                                        padding: EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                                        child: Text('Ctrl K', style: TextStyle(fontSize: 10, color: Apex.muted)),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 18),
              profile,
            ],
          ),
        ),
      ),
    );
  }
}

/// Company switcher and account menu. The sidebar shows it as the web app's
/// "Workspace" box; the header shows it as the profile.
class _CompanyMenu extends StatelessWidget {
  const _CompanyMenu({
    required this.session,
    required this.company,
    required this.style,
    required this.maxWidth,
  });

  final ApexSession session;
  final ApexCompany company;
  final _CompanyMenuStyle style;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    final name = company.displayName(session.companies);
    final role = switch (company.role) {
      'owner' => 'Owner',
      'editor' => 'Editor',
      _ => 'View only',
    };
    final tax = switch (company.taxMode) {
      'regular' => 'GST registered',
      'composition' => 'Composition GST',
      _ => 'Non-GST',
    };
    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: maxWidth),
      child: PopupMenuButton<String>(
        tooltip: 'Company and account',
        position: PopupMenuPosition.under,
        onSelected: (value) async {
          if (value == ':sign-out') {
            await session.signOut();
          } else if (value == ':add-company') {
            await showCompanyEditor(context, session);
          } else {
            session.chooseCompany(value);
          }
        },
        itemBuilder: (context) => [
          for (final candidate in session.companies)
            CheckedPopupMenuItem(
              value: candidate.id,
              checked: candidate.id == company.id,
              child: Text(candidate.displayName(session.companies)),
            ),
          const PopupMenuDivider(),
          const PopupMenuItem(value: ':add-company', child: Text('Add company')),
          const PopupMenuItem(value: ':sign-out', child: Text('Sign out')),
        ],
        child: switch (style) {
          _CompanyMenuStyle.sidebar => DecoratedBox(
            decoration: BoxDecoration(
              color: Apex.sidebarRaised,
              borderRadius: BorderRadius.circular(9),
              border: Border.all(color: Apex.sidebarBorder),
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 10, 8, 10),
              child: Row(
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      color: const Color(0x1affffff),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Apex.sidebarBorder),
                    ),
                    child: const Icon(Icons.domain_rounded, size: 18, color: Apex.sidebarText),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('WORKSPACE', style: Apex.eyebrow.copyWith(fontSize: 11, color: Apex.sidebarLabel)),
                        const SizedBox(height: 3),
                        Text(
                          name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.white),
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.unfold_more_rounded, size: 17, color: Apex.sidebarText),
                ],
              ),
            ),
          ),
          _CompanyMenuStyle.header => Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircleAvatar(
                  radius: 19.5,
                  backgroundColor: const Color(0xffe4f3e9),
                  foregroundColor: Apex.greenDark,
                  child: Text(
                    name.isEmpty ? '?' : name.characters.first.toUpperCase(),
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
                  ),
                ),
                const SizedBox(width: 9),
                Flexible(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Apex.ink),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '$role · $tax',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 11, color: Apex.muted),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                const Icon(Icons.expand_more_rounded, size: 17, color: Apex.muted),
              ],
            ),
          ),
          _CompanyMenuStyle.compact => Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
                const SizedBox(width: 4),
                const Icon(Icons.expand_more_rounded, size: 17),
              ],
            ),
          ),
        },
      ),
    );
  }
}

enum _CompanyMenuStyle { sidebar, header, compact }

class _WorkspaceSearch extends StatefulWidget {
  const _WorkspaceSearch();

  @override
  State<_WorkspaceSearch> createState() => _WorkspaceSearchState();
}

class _WorkspaceSearchState extends State<_WorkspaceSearch> {
  static const _notes = {
    _Route.dashboard: 'Business overview and daily figures',
    _Route.pos: 'Checkout, receipts and register',
    _Route.items: 'Products, services, prices and locations',
    _Route.stock: 'Stock on hand, counts, movements and receiving',
    _Route.parties: 'Customers and suppliers',
    _Route.salesInvoice: 'Bill customers and collect payments',
    _Route.estimate: 'Quotations for customers',
    _Route.salesOrder: 'Confirmed customer orders',
    _Route.proforma: 'Advance invoices before delivery',
    _Route.paymentIn: 'Money received from customers',
    _Route.creditNote: 'Sales returns and customer credits',
    _Route.purchaseBill: 'Supplier bills',
    _Route.paymentOut: 'Money paid to suppliers',
    _Route.expense: 'Business spending',
    _Route.purchaseOrder: 'Orders placed with suppliers',
    _Route.debitNote: 'Purchase returns and supplier debits',
    _Route.allTransactions: 'Every transaction in one list',
    _Route.bank: 'Cash book, transfers and reconciliation',
    _Route.dayBook: "A day's transactions in one place",
    _Route.ledger: 'Accounts, journals and reversals',
    _Route.reports: 'Financial reports, ageing and GST',
    _Route.recurring: 'Repeat invoices and bills on a schedule',
    _Route.commerce: 'Online store orders and stock',
    _Route.settings: 'Company, documents, stock setup and access',
  };
  final _scroll = ScrollController();
  String _query = '';
  int _selected = 0;

  List<_Route> get _matches => [
    for (final entry in _notes.entries)
      if (_query
          .split(RegExp(r'\s+'))
          .every('${entry.key.label} ${entry.key.section ?? ''} ${entry.value}'.toLowerCase().contains))
        entry.key,
  ];

  void _move(int delta) {
    if (_matches.isEmpty) return;
    setState(() => _selected = (_selected + delta).clamp(0, _matches.length - 1));
    if (!_scroll.hasClients) return;
    final top = _selected * 56.0;
    final bottom = top + 56;
    final viewport = _scroll.position.viewportDimension;
    if (top < _scroll.offset) _scroll.jumpTo(top);
    if (bottom > _scroll.offset + viewport) {
      _scroll.jumpTo((bottom - viewport).clamp(0, _scroll.position.maxScrollExtent));
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final results = _matches;
    return Dialog(
      alignment: const Alignment(0, -.6),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520, maxHeight: 480),
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.arrowDown): () => _move(1),
            const SingleActivator(LogicalKeyboardKey.arrowUp): () => _move(-1),
          },
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.all(14),
                child: TextField(
                  autofocus: true,
                  decoration: const InputDecoration(
                    hintText: 'Search pages, e.g. invoices, stock or GST',
                    prefixIcon: Icon(Icons.search),
                  ),
                  onChanged: (value) => setState(() {
                    _query = value.trim().toLowerCase();
                    _selected = 0;
                    if (_scroll.hasClients) _scroll.jumpTo(0);
                  }),
                  onSubmitted: (_) {
                    final matches = _matches;
                    if (matches.isNotEmpty) Navigator.pop(context, matches[_selected]);
                  },
                ),
              ),
              if (results.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('No matching pages.'),
                )
              else
                Flexible(
                  child: ListView.builder(
                    controller: _scroll,
                    shrinkWrap: true,
                    padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                    itemExtent: 56,
                    itemCount: results.length,
                    itemBuilder: (context, index) {
                      final route = results[index];
                      return ListTile(
                        dense: true,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        selected: _selected == index,
                        selectedColor: Apex.forest,
                        selectedTileColor: Apex.mint,
                        leading: Icon(route.icon, size: 20),
                        title: Text(route.section == null ? route.label : '${route.label} · ${route.section}'),
                        subtitle: Text(_notes[route]!, maxLines: 1, overflow: TextOverflow.ellipsis),
                        onTap: () => Navigator.pop(context, route),
                      );
                    },
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
