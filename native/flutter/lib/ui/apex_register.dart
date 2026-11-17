import 'package:material_ui/material_ui.dart';

import 'apex_theme.dart';
import 'apex_widgets.dart';

/// Shared register building blocks (Sales invoices, Parties, Items, …), measured
/// from the web app's register pages.

/// Title + subtitle on the left, primary actions on the right.
class ApexRegisterHeading extends StatelessWidget {
  const ApexRegisterHeading(this.title, {this.subtitle, this.actions = const [], super.key});

  final String title;
  final String? subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final heading = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Apex.registerTitle),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(subtitle!, style: const TextStyle(fontSize: 13, height: 1.7, color: Apex.muted)),
          ],
        ],
      );
      if (actions.isEmpty) return heading;
      if (limits.maxWidth < 640) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [heading, const SizedBox(height: 14), Wrap(spacing: 8, runSpacing: 8, children: actions)],
        );
      }
      // Title and actions share a row only while the subtitle fits on one line;
      // otherwise the actions move below, as the web header wraps.
      return Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 16,
        runSpacing: 14,
        children: [
          ConstrainedBox(constraints: BoxConstraints(maxWidth: limits.maxWidth), child: heading),
          Wrap(spacing: 8, runSpacing: 8, children: actions),
        ],
      );
    },
  );
}

/// One summary figure above a register: icon tile, small label, bold value.
class ApexStatCard extends StatelessWidget {
  const ApexStatCard({required this.label, required this.value, required this.icon, super.key});

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: '$label, $value',
    child: ExcludeSemantics(
      child: ApexPanel(
        radius: 10,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 20),
        child: Row(
          children: [
            ApexIconTile(icon, background: const Color(0xffe9f4ee), foreground: const Color(0xff23674d), size: 36),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: Apex.muted)),
                  const SizedBox(height: 6),
                  FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerLeft,
                    child: Text(
                      value,
                      style: const TextStyle(
                        fontFamily: Apex.display,
                        fontSize: 25,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -.6,
                        color: Color(0xff27313d),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// Row of stat cards that wraps to two columns on narrow screens.
class ApexStatGrid extends StatelessWidget {
  const ApexStatGrid(this.cards, {super.key});
  final List<Widget> cards;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      // Two per row on phones, like the web register (one only on very narrow screens).
      final columns = limits.maxWidth >= 900 ? cards.length : limits.maxWidth >= 300 ? 2 : 1;
      const gap = 16.0;
      final width = (limits.maxWidth - gap * (columns - 1)) / columns;
      return Wrap(spacing: gap, runSpacing: 12, children: [for (final card in cards) SizedBox(width: width, child: card)]);
    },
  );
}

/// Status tabs with counts (All 2 · Unpaid 2 · Settled 0 …).
class ApexFilterTabs<T> extends StatelessWidget {
  const ApexFilterTabs({required this.tabs, required this.selected, required this.onSelected, this.label = 'Status', super.key});

  final List<(T, String, int)> tabs;
  final T selected;
  final ValueChanged<T> onSelected;
  final String label;

  @override
  Widget build(BuildContext context) => Semantics(
    label: label,
    container: true,
    child: SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final (value, text, count) in tabs)
            Padding(
              padding: const EdgeInsets.only(right: 4),
              child: _FilterTab(text: text, count: count, selected: value == selected, onTap: () => onSelected(value)),
            ),
        ],
      ),
    ),
  );
}

class _FilterTab extends StatelessWidget {
  const _FilterTab({required this.text, required this.count, required this.selected, required this.onTap});

  final String text;
  final int count;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    selected: selected,
    label: '$text, $count',
    excludeSemantics: true,
    child: Material(
      color: selected ? const Color(0xffe3f2e9) : Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Apex.radiusChip),
        side: BorderSide(color: selected ? const Color(0xffb9d8c6) : Colors.transparent),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(Apex.radiusChip),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 13),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                text,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: selected ? const Color(0xff124e36) : Apex.muted,
                ),
              ),
              const SizedBox(width: 7),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: selected ? const Color(0xffdff0e5) : const Color(0xffedf0f3),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                  child: Text(
                    '$count',
                    style: TextStyle(
                      fontSize: 9,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                      color: selected ? Apex.greenDark : const Color(0xff465160),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

/// Search box used in register headers ("Search party or reference").
class ApexSearchField extends StatelessWidget {
  const ApexSearchField({required this.controller, required this.hint, this.onChanged, this.width = 300, super.key});

  final TextEditingController controller;
  final String hint;
  final ValueChanged<String>? onChanged;
  final double? width;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: TextField(
      controller: controller,
      onChanged: onChanged,
      textInputAction: TextInputAction.search,
      style: const TextStyle(fontSize: 13),
      decoration: InputDecoration(
        hintText: hint,
        prefixIcon: const Icon(Icons.search_rounded, size: 18, color: Apex.muted),
        suffixIcon: ListenableBuilder(
          listenable: controller,
          builder: (context, _) => controller.text.isEmpty
              ? const SizedBox.shrink()
              : IconButton(
                  tooltip: 'Clear search',
                  icon: const Icon(Icons.close_rounded, size: 17),
                  onPressed: () {
                    controller.clear();
                    onChanged?.call('');
                  },
                ),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
      ),
    ),
  );
}

/// The white register panel: a header (title, count, search), optional filter band, and its body.
class ApexRegisterPanel extends StatelessWidget {
  const ApexRegisterPanel({required this.title, required this.subtitle, required this.child, this.search, this.filters, super.key});

  final String title;
  final String subtitle;
  final Widget? search;
  final Widget? filters;
  final Widget child;

  @override
  Widget build(BuildContext context) => ApexPanel(
    radius: Apex.radiusPanel,
    child: LayoutBuilder(
      builder: (context, limits) {
        final narrow = limits.maxWidth < 640;
        final heading = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Apex.panelTitle),
            const SizedBox(height: 5),
            Text(subtitle, style: const TextStyle(fontSize: 13, color: Apex.muted)),
          ],
        );
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(narrow ? 18 : 26, 22, narrow ? 18 : 26, 22),
              child: search == null
                  ? heading
                  : narrow
                  ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [heading, const SizedBox(height: 14), search!])
                  : Row(children: [Expanded(child: heading), search!]),
            ),
            if (filters != null)
              DecoratedBox(
                decoration: const BoxDecoration(
                  color: Apex.filterBand,
                  border: Border(top: BorderSide(color: Apex.line), bottom: BorderSide(color: Apex.line)),
                ),
                child: Padding(padding: const EdgeInsets.fromLTRB(18, 12, 18, 12), child: filters),
              )
            else
              const Divider(color: Apex.line),
            child,
          ],
        );
      },
    ),
  );
}

/// Labelled dropdown in a register filter band (Period, Party, Sort by).
class ApexFilterSelect<T> extends StatelessWidget {
  const ApexFilterSelect({required this.label, required this.value, required this.items, required this.onChanged, this.width = 180, super.key});

  final String label;
  final T value;
  final List<(T, String)> items;
  final ValueChanged<T> onChanged;
  final double width;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Apex.muted)),
        const SizedBox(height: 6),
        Container(
          height: 40,
          padding: const EdgeInsets.only(left: 11, right: 6),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(Apex.radiusChip),
            border: Border.all(color: Apex.fieldBorder),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<T>(
              value: value,
              isExpanded: true,
              isDense: true,
              icon: const Icon(Icons.expand_more_rounded, size: 18),
              style: const TextStyle(fontFamily: Apex.body, fontSize: 12, fontWeight: FontWeight.w500, color: Color(0xff27313d)),
              items: [for (final (key, text) in items) DropdownMenuItem(value: key, child: Text(text, overflow: TextOverflow.ellipsis))],
              onChanged: (value) {
                if (value != null) onChanged(value);
              },
            ),
          ),
        ),
      ],
    ),
  );
}

/// Column definition for [ApexTable]. Give either a [flex] share or a fixed [width].
class ApexColumn {
  const ApexColumn(this.title, {this.flex = 1, this.width, this.alignEnd = false});
  final String title;
  final double flex;
  final double? width;
  final bool alignEnd;
}

/// Register table: grey uppercase header, hairline-separated rows, whole row tappable.
/// Below [cardBreakpoint] wide each row is shown as a stacked card from [card] instead.
class ApexTable extends StatelessWidget {
  const ApexTable({
    required this.columns,
    required this.rowCount,
    required this.cell,
    this.onRowTap,
    this.card,
    this.cardBreakpoint = 720,
    super.key,
  });

  final List<ApexColumn> columns;
  final int rowCount;
  final Widget Function(int row, int column) cell;
  final ValueChanged<int>? onRowTap;
  final Widget Function(int row)? card;
  final double cardBreakpoint;

  Widget _sized(ApexColumn column, Widget child) =>
      column.width != null ? SizedBox(width: column.width, child: child) : Expanded(flex: (column.flex * 100).round(), child: child);

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      if (card != null && limits.maxWidth < cardBreakpoint) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var row = 0; row < rowCount; row++) ...[
              if (row > 0) const Divider(color: Apex.lineSoft),
              InkWell(
                onTap: onRowTap == null ? null : () => onRowTap!(row),
                child: Padding(padding: const EdgeInsets.fromLTRB(18, 14, 18, 14), child: card!(row)),
              ),
            ],
          ],
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DecoratedBox(
            decoration: const BoxDecoration(color: Apex.tableHead, border: Border(bottom: BorderSide(color: Apex.lineStrong))),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 15),
              child: Row(
                children: [
                  for (final column in columns)
                    _sized(
                      column,
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        child: Text(
                          column.title.toUpperCase(),
                          textAlign: column.alignEnd ? TextAlign.right : TextAlign.left,
                          style: Apex.tableHeader,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
          for (var row = 0; row < rowCount; row++) ...[
            if (row > 0) const Divider(color: Color(0xffedf2f5)),
            InkWell(
              onTap: onRowTap == null ? null : () => onRowTap!(row),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 17),
                child: Row(
                  children: [
                    for (final (index, column) in columns.indexed)
                      _sized(
                        column,
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          child: Align(
                            alignment: column.alignEnd ? Alignment.centerRight : Alignment.centerLeft,
                            child: cell(row, index),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ],
      );
    },
  );
}

/// Empty or loading state inside a panel.
class ApexEmptyState extends StatelessWidget {
  const ApexEmptyState({required this.icon, required this.title, this.note, this.action, super.key});

  final IconData icon;
  final String title;
  final String? note;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 46, horizontal: 20),
    child: Column(
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(color: const Color(0xfff0f2f6), borderRadius: BorderRadius.circular(12)),
          child: Icon(icon, size: 21, color: const Color(0xff8693a9)),
        ),
        const SizedBox(height: 12),
        Text(title, textAlign: TextAlign.center, style: Apex.strong),
        if (note != null) ...[const SizedBox(height: 4), Text(note!, textAlign: TextAlign.center, style: Apex.small)],
        if (action != null) ...[const SizedBox(height: 14), action!],
      ],
    ),
  );
}

/// Small square icon button for row actions (download, more).
class ApexRowIconButton extends StatelessWidget {
  const ApexRowIconButton({required this.icon, required this.tooltip, required this.onPressed, super.key});

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: tooltip,
    onPressed: onPressed,
    icon: Icon(icon, size: 18),
    color: Apex.muted,
    style: IconButton.styleFrom(
      fixedSize: const Size(36, 36),
      minimumSize: const Size(36, 36),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
    ),
  );
}

/// Blue text link, like the web app's document numbers and party names.
class ApexLink extends StatelessWidget {
  const ApexLink(this.text, {required this.onTap, this.strong = false, super.key});

  final String text;
  final VoidCallback? onTap;
  final bool strong;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    borderRadius: BorderRadius.circular(4),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 1),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(fontSize: 13, fontWeight: strong ? FontWeight.w700 : FontWeight.w500, color: Apex.link),
      ),
    ),
  );
}

/// Standard page frame: scrolls, centres content up to the web app's width, uses its gutters.
class ApexPage extends StatelessWidget {
  const ApexPage({required this.children, this.maxWidth = 1540, super.key});

  final List<Widget> children;
  final double maxWidth;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final phone = limits.maxWidth < 700;
      final gutter = phone ? 16.0 : 28.0;
      return SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(gutter, phone ? 20 : 30, gutter, 40),
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
          ),
        ),
      );
    },
  );
}
