import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import 'core/session.dart';
import 'core/workspace.dart';
import 'features/banking/banking_screen.dart';
import 'features/books/books_data.dart' show BooksReport;
import 'features/books/books_register.dart';
import 'features/books/books_reports.dart';
import 'features/home/home_screen.dart';
import 'features/inventory/inventory_screen.dart';
import 'features/ledger/ledger_screen.dart';
import 'features/commerce/commerce_screen.dart';
import 'features/masters/master_editor.dart' show MasterGroup;
import 'features/masters/masters_screen.dart';
import 'features/pos/pos_screen.dart';
import 'features/settings/settings_forms.dart';
import 'features/settings/settings_screen.dart';
import 'ui/apex_theme.dart';

part 'workspace_navigation.dart';

const forest = Apex.forest;
const mint = Apex.mint;
const paper = Apex.paper;
const border = Apex.line;

class ApexApp extends StatelessWidget {
  const ApexApp({required this.session, super.key});

  final ApexSession session;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Apex Books',
      debugShowCheckedModeBanner: false,
      theme: apexTheme(),
      home: ListenableBuilder(
        listenable: session,
        builder: (context, _) {
          if (!session.signedIn) return _SignIn(session: session);
          final workspace = session.workspace;
          if (workspace == null) return _ChooseCompany(session: session);
          return _Workspace(
            key: ObjectKey(workspace),
            session: session,
            workspace: workspace,
          );
        },
      ),
    );
  }
}

class _Brand extends StatelessWidget {
  const _Brand({this.onDark = false, this.compact = false});

  final bool onDark;
  final bool compact;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(9),
        child: Image.asset(
          'assets/brand/apexbooks-logo.png',
          width: 36,
          height: 36,
          excludeFromSemantics: true,
        ),
      ),
      if (!compact) const SizedBox(width: 9),
      if (!compact)
        Flexible(
          child: Text(
            'Apex Books',
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontFamily: Apex.display,
              fontWeight: FontWeight.w700,
              color: onDark ? Colors.white : forest,
              fontSize: onDark ? 22 : 20,
              letterSpacing: -.8,
            ),
          ),
        ),
    ],
  );
}

class _SignIn extends StatefulWidget {
  const _SignIn({required this.session});

  final ApexSession session;

  @override
  State<_SignIn> createState() => _SignInState();
}

class _SignInState extends State<_SignIn> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _showPassword = false;

  Future<void> _accountForm({required bool recovery}) async {
    final completed = await showSettingsForm(
      context,
      title: recovery ? 'Recover your account' : 'Create an account',
      action: recovery ? 'Reset password' : 'Create account',
      fields: [
        setting('email', 'Email address', value: _email.text, maximum: 254),
        if (recovery) setting('code', 'Recovery code', maximum: 128),
        setting(
          'password',
          recovery ? 'New password' : 'Password',
          maximum: 128,
          secret: true,
        ),
      ],
      save: (data) async {
        final email = data['email']!;
        final password = data['password']!;
        if (!email.contains('@') || password.length < 8) {
          throw const FormatException(
            'Enter a valid email address and at least eight password characters.',
          );
        }
        if (recovery) {
          await widget.session.recover(email, data['code']!, password);
        } else {
          await widget.session.register(email, password);
        }
        _email.text = email;
      },
    );
    if (mounted && completed == true) {
      _password.clear();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            recovery
                ? 'Password updated. Sign in to continue.'
                : 'Account created. Sign in to continue.',
          ),
        ),
      );
    }
  }

  void _submit() {
    if (widget.session.busy || !(_form.currentState?.validate() ?? false)) {
      return;
    }
    widget.session.signIn(_email.text, _password.text);
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final busy = widget.session.busy;
    final message = widget.session.message;
    const label = TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Apex.label);
    final form = Form(
      key: _form,
      child: AutofillGroup(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'WELCOME TO APEX BOOKS',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.2, color: Color(0xff4f5965)),
            ),
            const SizedBox(height: 14),
            const Text(
              'Good to see you again.',
              style: TextStyle(fontFamily: Apex.display, fontSize: 30, fontWeight: FontWeight.w700, letterSpacing: -1, color: Apex.inkSoft),
            ),
            const SizedBox(height: 12),
            const Text('Sign in to continue to your workspace.', style: TextStyle(fontSize: 13, color: Apex.muted)),
            const SizedBox(height: 32),
            const ExcludeSemantics(child: Text('Email address', style: label)),
            const SizedBox(height: 8),
            // The visible label sits above the field like the web form; screen readers get it on the field.
            Semantics(
              label: 'Email address',
              child: TextFormField(
              controller: _email,
              enabled: !busy,
              autofillHints: const [AutofillHints.username],
              textInputAction: TextInputAction.next,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(hintText: 'you@company.com'),
              validator: (value) => value == null || !value.trim().contains('@') ? 'Enter your email address.' : null,
              ),
            ),
            const SizedBox(height: 18),
            const ExcludeSemantics(child: Text('Password', style: label)),
            const SizedBox(height: 8),
            Semantics(
              label: 'Password',
              child: TextFormField(
              controller: _password,
              enabled: !busy,
              obscureText: !_showPassword,
              enableSuggestions: false,
              autocorrect: false,
              autofillHints: const [AutofillHints.password],
              onFieldSubmitted: (_) => _submit(),
              decoration: InputDecoration(
                hintText: 'Enter your password',
                suffixIcon: IconButton(
                  tooltip: _showPassword ? 'Hide password' : 'Show password',
                  onPressed: busy ? null : () => setState(() => _showPassword = !_showPassword),
                  icon: Icon(_showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 19),
                ),
              ),
              validator: (value) => value == null || value.isEmpty ? 'Enter your password.' : null,
              ),
            ),
            if (message != null) ...[
              const SizedBox(height: 12),
              Semantics(
                liveRegion: true,
                child: DecoratedBox(
                  decoration: BoxDecoration(color: const Color(0xfffcf1ef), borderRadius: BorderRadius.circular(6)),
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: Text(message, style: const TextStyle(fontSize: 12, color: Color(0xffa4413d))),
                  ),
                ),
              ),
            ],
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: busy ? null : _submit,
              iconAlignment: IconAlignment.end,
              style: FilledButton.styleFrom(minimumSize: const Size(0, 48)),
              icon: const Icon(Icons.chevron_right_rounded, size: 18),
              label: Text(busy ? 'Signing in…' : 'Sign in'),
            ),
            const SizedBox(height: 18),
            Wrap(
              alignment: WrapAlignment.center,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                const Text('New to Apex Books?', style: TextStyle(fontSize: 12, color: Apex.muted)),
                TextButton(
                  onPressed: busy ? null : () => _accountForm(recovery: false),
                  child: const Text('Create an account', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                ),
              ],
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: busy ? null : () => _accountForm(recovery: true),
                child: const Text('Forgot password? Use a recovery code', style: TextStyle(fontSize: 15)),
              ),
            ),
          ],
        ),
      ),
    );
    return Scaffold(
      backgroundColor: const Color(0xfff3f4f5),
      body: LayoutBuilder(
        builder: (context, limits) {
          final wide = limits.maxWidth >= 860;
          final panel = Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.symmetric(horizontal: 24, vertical: wide ? 40 : 28),
              child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 410), child: form),
            ),
          );
          if (wide) {
            return Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Expanded(child: _SignInIntro(compact: false)),
                Expanded(child: SafeArea(child: panel)),
              ],
            );
          }
          return SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const _SignInIntro(compact: true),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
                  child: form,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// The web app's sign-in story panel: wordmark, promise and a quiet ring motif.
class _SignInIntro extends StatelessWidget {
  const _SignInIntro({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    final wordmark = DecoratedBox(
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14)),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: compact ? 22 : 28, vertical: compact ? 18 : 26),
        child: Image.asset(
          'assets/brand/apexbooks-wordmark.png',
          height: compact ? 26 : 30,
          semanticLabel: 'Apex Books — Your books in balance',
        ),
      ),
    );
    final headline = Text.rich(
      const TextSpan(
        children: [
          TextSpan(text: 'Clarity for every\n'),
          TextSpan(text: 'business decision.', style: TextStyle(color: Color(0xffa8e6a3))),
        ],
      ),
      style: TextStyle(
        fontFamily: Apex.display,
        fontSize: compact ? 28 : 54,
        height: 1.18,
        fontWeight: FontWeight.w700,
        letterSpacing: compact ? -1 : -2.6,
        color: Colors.white,
      ),
    );
    const eyebrow = Text(
      'MADE FOR INDIAN BUSINESSES',
      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 1.1, color: Color(0xffd7ecd9)),
    );
    return ClipRect(
      child: Container(
        color: const Color(0xff183c2e),
        child: Stack(
          children: [
            Positioned(
              right: compact ? -120 : -220,
              bottom: compact ? -160 : -320,
              child: IgnorePointer(
                child: Container(
                  width: compact ? 360 : 700,
                  height: compact ? 360 : 700,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: const Color(0x14ffffff), width: compact ? 34 : 60),
                  ),
                ),
              ),
            ),
            SafeArea(
              bottom: false,
              child: Padding(
                padding: EdgeInsets.fromLTRB(compact ? 24 : 48, compact ? 24 : 48, compact ? 24 : 48, compact ? 26 : 48),
                child: compact
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          wordmark,
                          const SizedBox(height: 22),
                          eyebrow,
                          const SizedBox(height: 12),
                          headline,
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          wordmark,
                          const Spacer(),
                          eyebrow,
                          const SizedBox(height: 20),
                          headline,
                          const SizedBox(height: 26),
                          const SizedBox(
                            width: 400,
                            child: Text(
                              'Keep your books organised, your transactions in view, and your business moving forward.',
                              style: TextStyle(fontSize: 15, height: 1.9, color: Color(0xffe7f2ea)),
                            ),
                          ),
                          const Spacer(),
                          const Row(
                            children: [
                              Expanded(
                                child: Text(
                                  'Thoughtful accounting, made simple.',
                                  style: TextStyle(fontSize: 11, color: Color(0xffe7f2ea)),
                                ),
                              ),
                              Text('✳', style: TextStyle(fontSize: 11, color: Color(0xff8fd0a5))),
                            ],
                          ),
                        ],
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChooseCompany extends StatelessWidget {
  const _ChooseCompany({required this.session});

  final ApexSession session;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Image.asset('assets/brand/apexbooks-wordmark.png', height: 28, semanticLabel: 'Apex Books'),
                ),
                const SizedBox(height: 34),
                const Text(
                  'WELCOME TO APEX BOOKS',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.2, color: Color(0xff4f5965)),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Choose a company',
                  style: TextStyle(fontFamily: Apex.display, fontSize: 30, fontWeight: FontWeight.w700, letterSpacing: -1, color: Apex.inkSoft),
                ),
                const SizedBox(height: 8),
                Text(
                  session.companies.isEmpty
                      ? 'Add a company or ask an existing company owner to grant access.'
                      : 'Open the books you want to work in. You can switch at any time from the sidebar.',
                  style: const TextStyle(fontSize: 13, height: 1.6, color: Apex.muted),
                ),
                const SizedBox(height: 24),
                for (final company in session.companies)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Material(
                      color: Colors.white,
                      shape: RoundedRectangleBorder(
                        side: const BorderSide(color: Apex.line),
                        borderRadius: BorderRadius.circular(Apex.radiusPanel),
                      ),
                      child: InkWell(
                        onTap: () => session.chooseCompany(company.id),
                        borderRadius: BorderRadius.circular(Apex.radiusPanel),
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Row(
                            children: [
                              CircleAvatar(
                                radius: 20,
                                backgroundColor: const Color(0xffe4f3e9),
                                foregroundColor: Apex.greenDark,
                                child: Text(
                                  company.name.isEmpty ? '?' : company.name.characters.first.toUpperCase(),
                                  style: const TextStyle(fontWeight: FontWeight.w700),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(company.displayName(session.companies), style: Apex.strong.copyWith(fontSize: 14)),
                                    const SizedBox(height: 3),
                                    Text(
                                      '${switch (company.role) {
                                        'owner' => 'Owner',
                                        'editor' => 'Editor',
                                        _ => 'View only',
                                      }} · ${company.taxMode == 'regular' ? 'GST registered' : company.taxMode == 'composition' ? 'Composition GST' : 'Non-GST'}',
                                      style: Apex.small,
                                    ),
                                  ],
                                ),
                              ),
                              const Icon(Icons.chevron_right_rounded, color: Apex.muted),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilledButton.icon(
                      onPressed: () => showCompanyEditor(context, session),
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('Add company'),
                    ),
                    OutlinedButton.icon(
                      onPressed: session.signOut,
                      icon: const Icon(Icons.logout_rounded, size: 17),
                      label: const Text('Sign out'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

/// The screens the workspace keeps alive. Several routes can share one screen
/// (for example every document type opens the transaction register).
enum _Destination {
  home,
  pointOfSale,
  stock,
  books,
  reports,
  masters,
  banking,
  ledger,
  commerce,
  settings,
}

class _Workspace extends StatefulWidget {
  const _Workspace({required this.session, required this.workspace, super.key});

  final ApexSession session;
  final WorkspaceContext workspace;

  @override
  State<_Workspace> createState() => _WorkspaceState();
}

class _WorkspaceState extends State<_Workspace> {
  /// Phone bottom bar: the pages a counter or owner opens most.
  static const _phoneTabs = [
    _Route.dashboard,
    _Route.pos,
    _Route.salesInvoice,
    _Route.items,
  ];
  final _scaffold = GlobalKey<ScaffoldState>();
  _Route _active = _Route.dashboard;
  final _visited = {_Destination.home};
  int _entryRequest = 0;
  int _routeRequest = 0;
  int _filterRequest = 0;
  String _requestedTab = 'all';
  int _bankRequest = 0;
  String? _requestedBank;
  BooksReport? _dashboardReport;
  DateTimeRange? _dashboardRange;
  bool _searchOpen = false;

  void _open(
    _Route route, {
    String? tab,
    String? unmatchedBank,
    BooksReport? report,
    DateTimeRange? range,
  }) {
    _scaffold.currentState?.closeDrawer();
    if (_active == route && tab == null && unmatchedBank == null &&
        report == null && _dashboardReport == null) {
      return;
    }
    setState(() {
      _active = route;
      _routeRequest++;
      _visited.add(route.destination);
      if (tab != null) {
        _requestedTab = tab;
        _filterRequest++;
      }
      if (unmatchedBank != null) {
        _requestedBank = unmatchedBank;
        _bankRequest++;
      }
      if (route.destination == _Destination.reports) {
        _dashboardReport = report;
        _dashboardRange = range;
      }
    });
  }

  void _newTransaction([String? kind]) {
    if (!widget.workspace.company.canWrite) return;
    _scaffold.currentState?.closeDrawer();
    setState(() {
      if (kind != null) {
        _active = _routeForKey(kind);
        _routeRequest++;
      } else if (_active.destination != _Destination.books) {
        _active = _Route.allTransactions;
      }
      _visited.add(_Destination.books);
      _entryRequest++;
    });
  }

  Future<void> _findWorkspace() async {
    if (_searchOpen || ModalRoute.of(context)?.isCurrent != true) return;
    _searchOpen = true;
    try {
      final route = await showDialog<_Route>(
        context: context,
        builder: (_) => const _WorkspaceSearch(),
      );
      if (mounted && route != null) _open(route);
    } finally {
      _searchOpen = false;
    }
  }

  /// The route a shared screen shows. It keeps its last filter while hidden.
  final _lastRoute = <_Destination, _Route>{};

  _Route _routeFor(_Destination destination, _Route fallback) {
    if (_active.destination == destination) _lastRoute[destination] = _active;
    return _lastRoute[destination] ?? fallback;
  }

  _Route _routeForKey(String key) => _Route.values.firstWhere(
    (route) => route.kind == key || route.name == key,
    orElse: () => _Route.allTransactions,
  );

  Widget _page(_Destination destination) {
    if (!_visited.contains(destination)) return const SizedBox.shrink();
    final workspace = widget.workspace;
    final active = _active.destination == destination;
    switch (destination) {
      case _Destination.home:
        return HomeScreen(
          workspace: workspace,
          revision: widget.session.revision,
          openCheckout: () => _open(_Route.pos),
          openPage: (key) => _open(_routeForKey(key)),
          openRegister: (kind, tab) => _open(_routeForKey(kind), tab: tab),
          openBank: (bank) => _open(_Route.bank, unmatchedBank: bank),
          openReport: (report, range) => _open(_Route.reports, report: report, range: range),
          newEntry: workspace.company.canWrite ? _newTransaction : null,
          verifyPassword: widget.session.verifyPassword,
        );
      case _Destination.pointOfSale:
        return PosScreen(
          workspace: workspace,
          active: active,
          revision: widget.session.revision,
        );
      case _Destination.stock:
        return InventoryScreen(
          workspace: workspace,
          active: active,
          revision: widget.session.revision,
        );
      case _Destination.books:
        final route = _routeFor(destination, _Route.allTransactions);
        return BooksRegister(
          workspace: workspace,
          active: active,
          revision: widget.session.revision,
          entryRequest: _entryRequest,
          kind: route.kind ?? '',
          title: route.kind == null ? 'Transactions' : route.label,
          recurringRequest: route.opensRecurring ? _routeRequest : 0,
          filterRequest: _filterRequest,
          requestedTab: _requestedTab,
        );
      case _Destination.reports:
        final route = _routeFor(destination, _Route.reports);
        return BooksReports(
          workspace: workspace,
          active: active,
          revision: widget.session.revision,
          report: route.report ?? _dashboardReport,
          requestedRange: route.report == null ? _dashboardRange : null,
          reportRequest: _routeRequest,
        );
      case _Destination.masters:
        return MastersScreen(
          workspace: workspace,
          active: active,
          revision: widget.session.revision,
          group: _routeFor(destination, _Route.parties).master,
        );
      case _Destination.banking:
        return BankingScreen(
          workspace: workspace,
          active: active,
          revision: widget.session.revision,
          bankRequest: _bankRequest,
          requestedBank: _requestedBank,
        );
      case _Destination.ledger:
        return LedgerScreen(
          workspace: workspace,
          revision: widget.session.revision,
        );
      case _Destination.commerce:
        return CommerceScreen(workspace: workspace);
      case _Destination.settings:
        return SettingsScreen(workspace: workspace, session: widget.session);
    }
  }

  Future<void> _addCompany() async {
    _scaffold.currentState?.closeDrawer();
    await showCompanyEditor(context, widget.session);
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final workspace = widget.workspace;
    return LayoutBuilder(
      builder: (context, limits) {
        final desktop = limits.maxWidth >= 780 && limits.maxHeight >= 440;
        final expanded = limits.maxWidth >= 1080;
        final smallPhone = limits.maxWidth < 360;
        Widget sidebar({required bool expanded, VoidCallback? openMenu}) =>
            _WorkspaceSidebar(
              expanded: expanded,
              openMenu: openMenu,
              active: _active,
              select: _open,
              newTransaction: workspace.company.canWrite
                  ? () => _newTransaction()
                  : null,
              findWorkspace: _findWorkspace,
              company: _CompanyMenu(
                session: session,
                company: workspace.company,
                style: _CompanyMenuStyle.sidebar,
                maxWidth: 232,
              ),
              addCompany: _addCompany,
              signOut: session.signOut,
            );
        final phoneIndex = _phoneTabs.indexOf(_active);
        return CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.keyK, control: true):
                _findWorkspace,
            const SingleActivator(LogicalKeyboardKey.keyK, meta: true):
                _findWorkspace,
          },
          child: Focus(
            // Focused on phones too, so Ctrl K works with a tablet or phone keyboard.
            autofocus: true,
            child: Scaffold(
              key: _scaffold,
              drawer: desktop && expanded
                  ? null
                  : Drawer(
                      width: 280,
                      backgroundColor: Apex.sidebar,
                      shape: const RoundedRectangleBorder(),
                      child: SafeArea(child: sidebar(expanded: true)),
                    ),
              appBar: desktop
                  ? null
                  : AppBar(
                      backgroundColor: Colors.white,
                      surfaceTintColor: Colors.transparent,
                      titleSpacing: 0,
                      leading: IconButton(
                        tooltip: 'Open menu',
                        icon: const Icon(Icons.menu_rounded),
                        onPressed: () => _scaffold.currentState?.openDrawer(),
                      ),
                      title: Text(
                        _active.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: Apex.ink,
                        ),
                      ),
                      actions: [
                        IconButton(
                          tooltip: 'Search books',
                          onPressed: _findWorkspace,
                          icon: const Icon(Icons.search_rounded),
                        ),
                        _CompanyMenu(
                          session: session,
                          company: workspace.company,
                          style: _CompanyMenuStyle.compact,
                          maxWidth: smallPhone ? 110 : limits.maxWidth * .36,
                        ),
                        const SizedBox(width: 6),
                      ],
                      bottom: const PreferredSize(
                        preferredSize: Size.fromHeight(1),
                        child: Divider(height: 1, color: Apex.line),
                      ),
                    ),
              bottomNavigationBar: desktop
                  ? null
                  : DecoratedBox(
                      decoration: const BoxDecoration(
                        border: Border(top: BorderSide(color: Apex.line)),
                      ),
                      child: NavigationBar(
                        selectedIndex: phoneIndex < 0
                            ? _phoneTabs.length
                            : phoneIndex,
                        onDestinationSelected: (index) =>
                            index == _phoneTabs.length
                            ? _scaffold.currentState?.openDrawer()
                            : _open(_phoneTabs[index]),
                        destinations: [
                          for (final route in _phoneTabs)
                            NavigationDestination(
                              icon: Icon(route.icon),
                              label: route == _Route.salesInvoice
                                  ? 'Sales'
                                  : route.label,
                            ),
                          const NavigationDestination(
                            icon: Icon(Icons.grid_view_rounded),
                            label: 'More',
                          ),
                        ],
                      ),
                    ),
              body: SafeArea(
                top: desktop,
                bottom: desktop,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (desktop)
                      sidebar(
                        expanded: expanded,
                        openMenu: expanded
                            ? null
                            : () => _scaffold.currentState?.openDrawer(),
                      ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (desktop)
                            _WorkspaceHeader(
                              active: _active,
                              compact: !expanded,
                              showBreadcrumb: limits.maxWidth >= 1200,
                              findWorkspace: _findWorkspace,
                              showShortcut: expanded,
                              profile: _CompanyMenu(
                                session: session,
                                company: workspace.company,
                                style: _CompanyMenuStyle.header,
                                maxWidth: 240,
                              ),
                            ),
                          Expanded(
                            child: IndexedStack(
                              index: _active.destination.index,
                              children: [
                                for (final destination in _Destination.values)
                                  TickerMode(
                                    enabled:
                                        _active.destination == destination,
                                    child: _page(destination),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
