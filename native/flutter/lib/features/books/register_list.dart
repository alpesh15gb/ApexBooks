import 'package:material_ui/material_ui.dart';

import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'books_document_output.dart';
import 'register_query.dart';

enum RegisterActionStyle { tonal, outlined, text }

/// One action a register row offers. [label] is the web register's wording;
/// [detailLabel] is the wording used on the record detail screen.
class RegisterRowAction {
  const RegisterRowAction({
    required this.label,
    required this.run,
    this.detailLabel,
    this.style = RegisterActionStyle.outlined,
  });

  final String label;
  final String? detailLabel;
  final VoidCallback run;
  final RegisterActionStyle style;
}

String _rowDate(String iso) =>
    DateTime.tryParse(iso) == null ? iso : apexDate(iso);

String _rowMoney(Object? value) => booksMoney(value);

/// The list view of the transaction register: heading, summary cards, status
/// tabs and the panel with its filters and table (cards on phones).
class BooksRegisterList extends StatelessWidget {
  const BooksRegisterList({
    required this.kind,
    required this.title,
    required this.addLabel,
    required this.allRecords,
    required this.scoped,
    required this.visible,
    required this.query,
    required this.today,
    required this.search,
    required this.page,
    required this.expandedFilters,
    required this.loading,
    required this.failed,
    required this.canWrite,
    required this.onQuery,
    required this.onSearch,
    required this.onPage,
    required this.onExpandFilters,
    required this.onReset,
    required this.onOpen,
    required this.onRefresh,
    required this.onRetry,
    required this.actionsFor,
    this.onAdd,
    this.onRecurring,
    this.onKind,
    this.onOpenParty,
    super.key,
  });

  final String kind;
  final String title;
  final String addLabel;
  final List<BooksRecord> allRecords;
  final List<BooksRecord> scoped;
  final List<BooksRecord> visible;
  final BooksRegisterQuery query;
  final String today;
  final TextEditingController search;
  final int page;
  final bool expandedFilters;
  final bool loading;
  final bool failed;
  final bool canWrite;
  final ValueChanged<BooksRegisterQuery> onQuery;
  final VoidCallback onSearch;
  final ValueChanged<int> onPage;
  final ValueChanged<bool> onExpandFilters;
  final VoidCallback onReset;
  final ValueChanged<String> onOpen;
  final VoidCallback? onRefresh;
  final VoidCallback onRetry;
  final List<RegisterRowAction> Function(BooksRecord) actionsFor;
  final VoidCallback? onAdd;
  final VoidCallback? onRecurring;

  /// Set only on the "All transactions" page, which keeps a type filter.
  final ValueChanged<String>? onKind;

  /// Opens a party from its name in the register (the web app's party link). The register page
  /// passes this; the name stays plain text when it is null.
  final void Function(String partyId, String name)? onOpenParty;

  List<Widget> _headingActions() => [
    OutlinedButton.icon(
      onPressed: onRefresh,
      icon: const Icon(Icons.refresh, size: 17),
      label: const Text('Refresh'),
    ),
    if (onRecurring != null)
      OutlinedButton.icon(
        onPressed: onRecurring,
        icon: const Icon(Icons.event_repeat_outlined, size: 17),
        label: const Text('Recurring drafts'),
      ),
    if (canWrite)
      FilledButton.icon(
        onPressed: onAdd,
        icon: const Icon(Icons.add, size: 18),
        label: Text(addLabel),
      ),
  ];

  @override
  Widget build(BuildContext context) {
    final stats = registerStats(kind, scoped);
    final tabs = registerTabs(kind, scoped, today);
    final tab = tabs.any((t) => t.$1 == query.tab) ? query.tab : 'all';
    final pages = (visible.length / registerPageSize).ceil().clamp(1, 1 << 30);
    final current = page.clamp(1, pages);
    final start = (current - 1) * registerPageSize;
    final shown = visible.sublist(
      start,
      (start + registerPageSize).clamp(0, visible.length),
    );
    final count = visible.length;
    return ApexPage(
      children: [
        ApexRegisterHeading(
          title,
          subtitle: registerSubtitles[kind],
          actions: _headingActions(),
        ),
        const SizedBox(height: 22),
        if (stats.isNotEmpty) ...[
          ApexStatGrid([
            for (final stat in stats)
              ApexStatCard(
                label: stat.label,
                value: stat.value,
                icon: stat.icon,
              ),
          ]),
          const SizedBox(height: 18),
        ],
        ApexFilterTabs<String>(
          label: 'Transaction status',
          tabs: tabs,
          selected: tab,
          onSelected: (value) => onQuery(query.copyWith(tab: value)),
        ),
        const SizedBox(height: 18),
        ApexRegisterPanel(
          title: 'Transactions',
          subtitle: '$count ${count == 1 ? 'record' : 'records'} in this view',
          search: ApexSearchField(
            controller: search,
            hint: 'Search party or reference',
            width: 320,
            onChanged: (_) => onSearch(),
          ),
          filters: _filters(context),
          child: _body(context, shown, count, current, pages),
        ),
      ],
    );
  }

  Widget _filters(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final phone = limits.maxWidth < 700;
      final names =
          {
            for (final r in allRecords)
              if (r.party.isNotEmpty) r.party,
            if (query.party.isNotEmpty) query.party,
          }.toList()..sort(
            (a, b) => a.toLowerCase().compareTo(b.toLowerCase()),
          );
      final active = query.hasFilters;
      final expanded = !phone || expandedFilters;
      final period = ApexFilterSelect<String>(
        label: 'Period',
        value: query.period,
        width: phone ? 200 : 180,
        items: const [
          ('all', 'All dates'),
          ('today', 'Today'),
          ('month', 'This month'),
          ('last_month', 'Last month'),
          ('year', 'This financial year'),
          ('custom', 'Custom dates'),
        ],
        onChanged: (value) {
          if (value == 'custom') {
            onQuery(query.copyWith(period: 'custom'));
          } else {
            final dates = registerPeriodDates(value);
            onQuery(
              query.copyWith(period: value, from: dates.from, to: dates.to),
            );
          }
        },
      );
      final reset = TextButton.icon(
        onPressed: active ? onReset : null,
        icon: const Icon(Icons.tune_rounded, size: 16),
        label: const Text('Reset filters'),
      );
      return Wrap(
        spacing: 14,
        runSpacing: 12,
        crossAxisAlignment: WrapCrossAlignment.end,
        children: [
          if (!phone)
            const Padding(
              padding: EdgeInsets.only(bottom: 11),
              child: Icon(
                Icons.calendar_month_outlined,
                size: 17,
                color: Apex.muted,
              ),
            ),
          period,
          if (query.period == 'custom') ..._customDates(context),
          if (phone)
            TextButton.icon(
              onPressed: () => onExpandFilters(!expandedFilters),
              icon: const Icon(Icons.tune_rounded, size: 16),
              label: Text(
                '${expandedFilters ? 'Fewer filters' : 'More filters'}'
                '${query.extraFilters > 0 ? ' · ${query.extraFilters} active' : ''}',
              ),
            ),
          if (onKind != null && expanded)
            ApexFilterSelect<String>(
              label: 'Transaction type',
              value: kind,
              width: 200,
              items: [
                ('', 'All transaction types'),
                for (final MapEntry(:key, :value) in booksKinds.entries)
                  (key, value),
              ],
              onChanged: onKind!,
            ),
          if (expanded)
            ApexFilterSelect<String>(
              label: 'Party',
              value: query.party,
              width: 200,
              items: [
                ('', 'All parties'),
                for (final name in names) (name, name),
              ],
              onChanged: (value) => onQuery(query.copyWith(party: value)),
            ),
          if (expanded)
            ApexFilterSelect<String>(
              label: 'Sort by',
              value: query.sort,
              width: 200,
              items: const [
                ('newest', 'Date · newest first'),
                ('oldest', 'Date · oldest first'),
                ('amount', 'Amount · high to low'),
                ('balance', 'Balance · high to low'),
              ],
              onChanged: (value) => onQuery(query.copyWith(sort: value)),
            ),
          if (!phone || active || expandedFilters) reset,
        ],
      );
    },
  );

  List<Widget> _customDates(BuildContext context) {
    Future<void> pick(bool from) async {
      final current = DateTime.tryParse(from ? query.from : query.to);
      final first = from ? DateTime(2000) : DateTime.tryParse(query.from);
      final last = from ? DateTime.tryParse(query.to) : DateTime(2100);
      final initial = current ?? DateTime.now();
      final picked = await showDatePicker(
        context: context,
        initialDate: initial,
        firstDate: first == null || first.isAfter(initial) ? DateTime(2000) : first,
        lastDate: last == null || last.isBefore(initial) ? DateTime(2100) : last,
      );
      if (picked == null) return;
      final day = booksDate(picked);
      onQuery(
        query.copyWith(
          period: 'custom',
          from: from ? day : null,
          to: from ? null : day,
        ),
      );
    }

    Widget button(String label, String value, bool from) => SizedBox(
      width: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Apex.muted,
            ),
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 40,
            child: OutlinedButton(
              onPressed: () => pick(from),
              style: OutlinedButton.styleFrom(
                alignment: Alignment.centerLeft,
                padding: const EdgeInsets.symmetric(horizontal: 11),
                backgroundColor: Colors.white,
                side: const BorderSide(color: Apex.fieldBorder),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(Apex.radiusChip),
                ),
              ),
              child: Text(
                value.isEmpty ? 'Any date' : _rowDate(value),
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  color: Color(0xff27313d),
                ),
              ),
            ),
          ),
        ],
      ),
    );

    return [
      Semantics(
        label: 'From date',
        container: true,
        child: button('From', query.from, true),
      ),
      Semantics(
        label: 'To date',
        container: true,
        child: button('To', query.to, false),
      ),
      ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 260),
        child: Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text(
            '${query.from.isEmpty ? 'All earlier dates' : _rowDate(query.from)} to '
            '${query.to.isEmpty ? 'all later dates' : _rowDate(query.to)}.',
            style: Apex.small,
          ),
        ),
      ),
    ];
  }

  Widget _body(
    BuildContext context,
    List<BooksRecord> shown,
    int count,
    int current,
    int pages,
  ) {
    if (allRecords.isEmpty && loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 46),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              SizedBox(height: 12),
              Text('Loading transactions…'),
            ],
          ),
        ),
      );
    }
    if (allRecords.isEmpty && failed) {
      return ApexEmptyState(
        icon: Icons.error_outline,
        title: 'Could not load transactions.',
        action: OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
      );
    }
    if (shown.isEmpty) {
      final filtered = query.hasFilters;
      return ApexEmptyState(
        icon: Icons.description_outlined,
        title: filtered ? 'No matching records' : 'No transactions in this view',
        note: filtered
            ? 'Change the search or filters to find your records.'
            : canWrite
            ? 'Create your first document to start this register.'
            : 'There are no records here yet. Your company owner can add them.',
        action: filtered
            ? OutlinedButton(
                onPressed: onReset,
                child: const Text('Clear filters'),
              )
            : canWrite && onAdd != null && addLabel != 'New entry'
            ? FilledButton.icon(
                onPressed: onAdd,
                icon: const Icon(Icons.add, size: 17),
                label: Text(addLabel),
              )
            : null,
      );
    }
    final byId = {for (final r in allRecords) r.id: r};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ApexTable(
          cardBreakpoint: 1060,
          columns: const [
            ApexColumn('Date', width: 112),
            ApexColumn('Document / party', flex: 2),
            ApexColumn('Status', width: 140),
            ApexColumn('Amount', width: 120, alignEnd: true),
            ApexColumn('Balance', width: 120, alignEnd: true),
            ApexColumn('Actions', width: 260, alignEnd: true),
          ],
          rowCount: shown.length,
          onRowTap: (row) => onOpen(shown[row].id),
          cell: (row, column) {
            final r = shown[row];
            return switch (column) {
              0 => Text(_rowDate(r.date), style: _muted),
              1 => _reference(r, byId),
              2 => _status(r),
              3 => Text(_rowMoney(r.json['amount']), style: _amount),
              4 => _balance(r),
              _ => _actions(context, r),
            };
          },
          card: (row) {
            final r = shown[row];
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _reference(r, byId),
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _labelled('Date', Text(_rowDate(r.date), style: _muted))),
                    Expanded(child: _labelled('Status', _status(r))),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: _labelled(
                        'Amount',
                        Text(_rowMoney(r.json['amount']), style: _amount),
                      ),
                    ),
                    Expanded(child: _labelled('Balance', _balance(r))),
                  ],
                ),
                const Divider(color: Apex.lineSoft, height: 22),
                Align(
                  alignment: Alignment.centerLeft,
                  child: _actions(context, r),
                ),
              ],
            );
          },
        ),
        if (pages > 1 || loading) _footer(count, current, pages),
      ],
    );
  }

  Widget _footer(int count, int current, int pages) {
    final first = (current - 1) * registerPageSize + 1;
    final last = (current * registerPageSize).clamp(0, count);
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Apex.lineSoft)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
        child: Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 12,
          runSpacing: 8,
          children: [
            Text(
              loading
                  ? 'Loading transactions…'
                  : '$first–$last of $count',
              style: Apex.small,
            ),
            if (pages > 1)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  OutlinedButton(
                    onPressed: current > 1 ? () => onPage(current - 1) : null,
                    child: const Text('Previous'),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Text('Page $current of $pages', style: Apex.small),
                  ),
                  OutlinedButton(
                    onPressed: current < pages
                        ? () => onPage(current + 1)
                        : null,
                    child: const Text('Next'),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  static const _muted = TextStyle(fontSize: 13, color: Apex.muted);
  static const _amount = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w700,
    color: Apex.ink,
  );

  Widget _labelled(String label, Widget child) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        label.toUpperCase(),
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: .6,
          color: Apex.label,
        ),
      ),
      const SizedBox(height: 4),
      child,
    ],
  );

  Widget _reference(BooksRecord r, Map<String, BooksRecord> byId) {
    final destination = byId[booksText(r.json['converted_to'])];
    final due = booksText(r.data['due_date']);
    final allocations = r.data['allocations'] is List
        ? (r.data['allocations'] as List).length
        : booksText(r.data['applied_to']).isNotEmpty
        ? 1
        : 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ApexLink(
          r.number.isEmpty ? 'No reference' : r.number,
          strong: true,
          onTap: () => onOpen(r.id),
        ),
        if (r.party.isNotEmpty) ...[
          const SizedBox(height: 3),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 2),
            child: onOpenParty == null
                ? Text(
                    r.party,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: Apex.inkSoft,
                    ),
                  )
                : InkWell(
                    onTap: () =>
                        onOpenParty!(booksText(r.data['party_id']), r.party),
                    borderRadius: BorderRadius.circular(4),
                    child: Text(
                      r.party,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: Apex.link,
                      ),
                    ),
                  ),
          ),
        ],
        if (kind.isEmpty)
          Padding(
            padding: const EdgeInsets.only(left: 2, top: 3),
            child: Text(booksKindLabel(r.kind), style: Apex.small),
          ),
        if (due.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(left: 2, top: 3),
            child: Text('Due $due', style: Apex.small),
          ),
        if (allocations > 0)
          Padding(
            padding: const EdgeInsets.only(left: 2, top: 3),
            child: Text(
              '$allocations allocated document${allocations == 1 ? '' : 's'}',
              style: Apex.small,
            ),
          ),
        if (destination != null)
          Padding(
            padding: const EdgeInsets.only(left: 2, top: 3),
            child: Text(
              'Converted to ${destination.number.isEmpty ? destination.party : destination.number}',
              style: Apex.small,
            ),
          ),
      ],
    );
  }

  Widget _status(BooksRecord r) {
    final status = registerStatusLabel(r);
    final settlement = registerSettlement(r);
    final tone = status == 'Cancelled'
        ? ApexBadgeTone.cancelled
        : status == 'Posted' || status == 'Converted'
        ? ApexBadgeTone.posted
        : ApexBadgeTone.draft;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ApexStatusBadge(status, tone: tone),
        if (settlement.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 5, left: 2),
            child: Text(settlement, style: _muted.copyWith(fontSize: 12)),
          ),
      ],
    );
  }

  Widget _balance(BooksRecord r) {
    final invoice = const {
      'sales_invoice',
      'purchase_bill',
      'pos',
    }.contains(r.kind);
    if (!invoice || r.json['posted'] != true) {
      return const Text('—', style: _muted);
    }
    final owing = (double.tryParse(booksText(r.json['outstanding'])) ?? 0) > 0;
    return Text(
      _rowMoney(r.json['outstanding'] ?? '0'),
      style: TextStyle(
        fontSize: 13,
        fontWeight: owing ? FontWeight.w700 : FontWeight.w500,
        color: owing ? const Color(0xff606a77) : Apex.muted,
      ),
    );
  }

  Widget _actions(BuildContext context, BooksRecord r) {
    final actions = actionsFor(r);
    final primary = actions.isEmpty ? null : actions.first;
    final menu = actions.skip(1).toList();
    final label = r.number.isEmpty ? r.party : r.number;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (primary != null)
          Flexible(
            child: TextButton(
              onPressed: primary.run,
              style: TextButton.styleFrom(
                foregroundColor: Apex.link,
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                minimumSize: const Size(0, 36),
                textStyle: const TextStyle(fontFamily: Apex.body, 
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              child: Text(
                primary.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        if (canOutputBooksDocument(r))
          ApexRowIconButton(
            icon: Icons.download_outlined,
            tooltip: 'Download $label PDF',
            onPressed: () => onOpen(r.id),
          ),
        if (menu.isNotEmpty)
          PopupMenuButton<int>(
            tooltip: 'More actions for $label',
            icon: const Icon(Icons.more_horiz_rounded, size: 18),
            iconColor: Apex.muted,
            padding: EdgeInsets.zero,
            style: IconButton.styleFrom(
              fixedSize: const Size(36, 36),
              minimumSize: const Size(36, 36),
            ),
            onSelected: (index) => menu[index].run(),
            itemBuilder: (context) => [
              for (final (index, action) in menu.indexed)
                PopupMenuItem(value: index, child: Text(action.label)),
            ],
          ),
      ],
    );
  }
}
