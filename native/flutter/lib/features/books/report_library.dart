import 'package:material_ui/material_ui.dart';

import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'report_catalog.dart';

/// The Reports landing page: business questions, search, categories and report groups.
class ReportLibrary extends StatefulWidget {
  const ReportLibrary({
    required this.available,
    required this.onSelect,
    super.key,
  });

  final bool Function(BooksReport report) available;
  final ValueChanged<BooksReport> onSelect;

  @override
  State<ReportLibrary> createState() => _ReportLibraryState();
}

class _ReportLibraryState extends State<ReportLibrary> {
  final _search = TextEditingController();
  String _category = 'all';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final phone = limits.maxWidth < 700;
      final searching = _search.text.trim().isNotEmpty;
      final showShortcuts =
          !searching &&
          _category == 'all' &&
          [
            BooksReport.statements,
            BooksReport.ageing,
            BooksReport.stock,
          ].any(widget.available);
      final matches = [
        for (final group in reportGroups)
          if (_category == 'all' || _category == group.title)
            (
              group,
              [
                for (final report in group.reports)
                  if (widget.available(report) &&
                      reportMatches(group, report, _search.text))
                    report,
              ],
            ),
      ].where((entry) => entry.$2.isNotEmpty).toList();
      final total = matches.fold<int>(0, (sum, entry) => sum + entry.$2.length);
      return ApexPage(
        maxWidth: 1540,
        children: [
          ApexRegisterHeading(
            'Reports',
            subtitle: 'Find a report by name or category.',
            actions: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: const Color(0xffeef2f4),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: Text(
                    '$reportLibraryCount reports · PDF & XLSX',
                    style: TextStyle(fontSize: 11.5, color: Apex.muted),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          if (showShortcuts && !phone) ...[
            _shortcuts(),
            const SizedBox(height: 24),
          ],
          Align(
            alignment: Alignment.centerLeft,
            child: ApexSearchField(
              controller: _search,
              hint: 'Find a report, e.g. sales, GST or stock',
              width: phone ? null : 600,
              onChanged: (_) => setState(() {}),
            ),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final (key, label) in [
                ('all', 'All reports'),
                for (final group in reportGroups) (group.title, group.title),
              ])
                _CategoryChip(
                  label: label,
                  selected: _category == key,
                  onTap: () => setState(() => _category = key),
                ),
            ],
          ),
          if (searching || _category != 'all')
            Padding(
              padding: const EdgeInsets.only(top: 14),
              child: Semantics(
                liveRegion: true,
                child: Text(
                  '$total matching ${total == 1 ? 'report' : 'reports'}',
                  style: const TextStyle(fontSize: 13, color: Apex.muted),
                ),
              ),
            ),
          const SizedBox(height: 20),
          if (showShortcuts && phone) ...[
            _shortcuts(compact: true),
            const SizedBox(height: 20),
          ],
          if (matches.isEmpty)
            ApexPanel(
              child: ApexEmptyState(
                icon: Icons.search_off_rounded,
                title: 'No matching reports',
                note: 'Try sales, party, GST or inventory.',
                action: TextButton(
                  onPressed: () => setState(() {
                    _search.clear();
                    _category = 'all';
                  }),
                  child: const Text('Show all reports'),
                ),
              ),
            )
          else
            _grid(matches, phone || limits.maxWidth < 900),
        ],
      );
    },
  );

  Widget _shortcuts({bool compact = false}) {
    final cards = [
      (
        BooksReport.statements,
        'How is my business doing?',
        'Profit & loss and balance sheet',
        Icons.trending_up_rounded,
      ),
      (
        BooksReport.ageing,
        'Who owes money?',
        'Unpaid customer invoices and supplier bills',
        Icons.account_balance_wallet_outlined,
      ),
      (
        BooksReport.stock,
        'What is in stock?',
        'Quantities on hand and inventory value',
        Icons.inventory_2_outlined,
      ),
    ].where((card) => widget.available(card.$1)).toList();
    Widget card((BooksReport, String, String, IconData) data) => Semantics(
      button: true,
      label: '${data.$2}, ${data.$3}',
      excludeSemantics: true,
      child: InkWell(
        onTap: () => widget.onSelect(data.$1),
        borderRadius: BorderRadius.circular(10),
        child: ApexPanel(
          radius: 10,
          padding: const EdgeInsets.fromLTRB(22, 22, 22, 16),
          child: SizedBox(
            width: double.infinity,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(data.$4, size: 22, color: Apex.green),
                const SizedBox(height: 14),
                Text(
                  data.$2,
                  style: Apex.strong.copyWith(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  data.$3,
                  style: const TextStyle(fontSize: 13.5, color: Apex.muted),
                ),
                const SizedBox(height: 14),
                const Align(
                  alignment: Alignment.centerRight,
                  child: Icon(
                    Icons.north_east_rounded,
                    size: 17,
                    color: Apex.inkSoft,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (compact) {
      return ApexPanel(
        padding: EdgeInsets.zero,
        child: Material(
          type: MaterialType.transparency,
          child: Column(
            children: [
              for (final (i, data) in cards.indexed) ...[
                if (i > 0) const Divider(height: 1, color: Apex.line),
                ListTile(
                  leading: Icon(data.$4, size: 20, color: Apex.green),
                  title: Text(data.$2, style: Apex.strong),
                  subtitle: Text(data.$3),
                  trailing: const Icon(Icons.chevron_right_rounded, size: 20),
                  onTap: () => widget.onSelect(data.$1),
                ),
              ],
            ],
          ),
        ),
      );
    }
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, data) in cards.indexed) ...[
            if (i > 0) const SizedBox(width: 13),
            Expanded(child: card(data)),
          ],
        ],
      ),
    );
  }

  Widget _grid(List<(ReportGroup, List<BooksReport>)> matches, bool narrow) {
    if (narrow) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, entry) in matches.indexed) ...[
            if (i > 0) const SizedBox(height: 20),
            _category_(entry.$1, entry.$2),
          ],
        ],
      );
    }
    return Column(
      children: [
        for (var i = 0; i < matches.length; i += 2) ...[
          if (i > 0) const SizedBox(height: 20),
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: _category_(matches[i].$1, matches[i].$2)),
                const SizedBox(width: 20),
                Expanded(
                  child: i + 1 < matches.length
                      ? _category_(matches[i + 1].$1, matches[i + 1].$2)
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _category_(ReportGroup group, List<BooksReport> reports) => ApexPanel(
    radius: 10,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        DecoratedBox(
          decoration: const BoxDecoration(
            color: Apex.filterBand,
            border: Border(bottom: BorderSide(color: Apex.line)),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 22, 24, 22),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.bar_chart_rounded,
                  size: 21,
                  color: Apex.green,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        group.title,
                        style: Apex.panelTitle.copyWith(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(group.description, style: Apex.note),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        for (final (i, report) in reports.indexed) ...[
          if (i > 0) const Divider(height: 1, color: Apex.lineSoft),
          Semantics(
            button: true,
            label: '${report.title}, ${reportDescription(report)}',
            excludeSemantics: true,
            child: InkWell(
              onTap: () => widget.onSelect(report),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 22, 16),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            report.title,
                            style: const TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w700,
                              color: Apex.ink,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            reportDescription(report),
                            style: const TextStyle(
                              fontSize: 12.5,
                              color: Apex.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    const Icon(
                      Icons.north_east_rounded,
                      size: 16,
                      color: Apex.inkSoft,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ],
    ),
  );
}

class _CategoryChip extends StatelessWidget {
  const _CategoryChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    selected: selected,
    label: label,
    excludeSemantics: true,
    child: Material(
      color: selected ? const Color(0xffe3f2e9) : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Apex.radiusChip),
        side: BorderSide(color: selected ? const Color(0xffb9d8c6) : Apex.line),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(Apex.radiusChip),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
              color: selected ? Apex.greenDark : Apex.inkSoft,
            ),
          ),
        ),
      ),
    ),
  );
}
