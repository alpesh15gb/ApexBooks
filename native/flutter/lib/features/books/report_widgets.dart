import 'package:material_ui/material_ui.dart';

import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';

/// Building blocks shared by every report view, measured from the web report pages.

const _infoBackground = Color(0xffeff5fb);
const _infoBorder = Color(0xffd0e0f1);

/// Safe list-of-records reader: a missing or malformed list is an empty one.
List<BooksJson> reportRows(Object? value) =>
    value is List ? booksRows(value) : const [];

/// Underscored server words ("sales_invoice") as plain lowercase text.
String reportWords(Object? value) => booksText(value).replaceAll('_', ' ');

/// Blue note under a report ("Receivables and payables are outstanding as of…").
class ReportInfoBox extends StatelessWidget {
  const ReportInfoBox(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => text.trim().isEmpty
      ? const SizedBox.shrink()
      : Padding(
          padding: const EdgeInsets.only(top: 16),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: _infoBackground,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: _infoBorder),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: SizedBox(
                width: double.infinity,
                child: Text(
                  text.trim(),
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.5,
                    color: Apex.inkSoft,
                  ),
                ),
              ),
            ),
          ),
        );
}

/// One summary figure: grey uppercase label above a large value.
class ReportMetric {
  const ReportMetric(this.label, this.value, {this.color, this.note});
  final String label;
  final String value;
  final Color? color;
  final String? note;
}

/// Row of summary cards (4 across on desktop, 2, then 1 on phones).
class ReportMetricGrid extends StatelessWidget {
  const ReportMetricGrid(this.metrics, {super.key});
  final List<ReportMetric> metrics;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final width = limits.maxWidth;
      var columns = width >= 900
          ? metrics.length
          : width >= 560
          ? 2
          : 1;
      columns = columns.clamp(1, metrics.isEmpty ? 1 : metrics.length);
      const gap = 16.0;
      Widget card(ReportMetric metric) => Semantics(
        container: true,
        label: '${metric.label}, ${metric.value}',
        child: ExcludeSemantics(
          child: ApexPanel(
            radius: 10,
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 22),
            child: SizedBox(
              width: double.infinity,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    metric.label.toUpperCase(),
                    style: Apex.tableHeader.copyWith(fontSize: 11),
                  ),
                  const SizedBox(height: 14),
                  FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerLeft,
                    child: Text(
                      metric.value,
                      style: TextStyle(
                        fontFamily: Apex.display,
                        fontSize: 30,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -1,
                        color: metric.color ?? Apex.ink,
                      ),
                    ),
                  ),
                  if (metric.note != null) ...[
                    const SizedBox(height: 10),
                    Text(metric.note!, style: Apex.small),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
      return Padding(
        padding: const EdgeInsets.only(top: 16),
        child: Column(
          children: [
            for (var start = 0; start < metrics.length; start += columns) ...[
              if (start > 0) const SizedBox(height: gap),
              IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (var i = 0; i < columns; i++) ...[
                      if (i > 0) const SizedBox(width: gap),
                      Expanded(
                        child: start + i < metrics.length
                            ? card(metrics[start + i])
                            : const SizedBox.shrink(),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ],
        ),
      );
    },
  );
}

/// Panels laid side by side on desktop, stacked on phones.
class ReportPanelRow extends StatelessWidget {
  const ReportPanelRow(this.children, {super.key});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 16),
    child: LayoutBuilder(
      builder: (context, limits) {
        if (limits.maxWidth < 760 || children.length < 2) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final (index, child) in children.indexed) ...[
                if (index > 0) const SizedBox(height: 16),
                child,
              ],
            ],
          );
        }
        return IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final (index, child) in children.indexed) ...[
                if (index > 0) const SizedBox(width: 16),
                Expanded(child: child),
              ],
            ],
          ),
        );
      },
    ),
  );
}

/// White panel with a title (and optional note) above its body.
class ReportPanel extends StatelessWidget {
  const ReportPanel({
    required this.title,
    required this.child,
    this.subtitle,
    this.padded = false,
    this.topGap = true,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget child;

  /// Pad the body like a settings panel instead of letting a table run edge to edge.
  final bool padded;
  final bool topGap;

  @override
  Widget build(BuildContext context) {
    final phone = MediaQuery.sizeOf(context).width < 700;
    final side = phone ? 18.0 : 26.0;
    final panel = ApexPanel(
      radius: Apex.radiusPanel,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(side, 22, side, padded ? 10 : 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Apex.panelTitle.copyWith(
                    fontFamily: Apex.display,
                    fontSize: 20,
                  ),
                ),
                if (subtitle != null && subtitle!.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(
                    subtitle!,
                    style: const TextStyle(fontSize: 13, color: Apex.muted),
                  ),
                ],
              ],
            ),
          ),
          if (padded)
            Padding(
              padding: EdgeInsets.fromLTRB(side, 0, side, 22),
              child: child,
            )
          else
            child,
        ],
      ),
    );
    return topGap
        ? Padding(padding: const EdgeInsets.only(top: 16), child: panel)
        : panel;
  }
}

/// Label on the left, bold amount on the right, hairline between lines.
class ReportLine extends StatelessWidget {
  const ReportLine(this.label, this.value, {super.key});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: const BoxDecoration(
      border: Border(bottom: BorderSide(color: Apex.lineSoft)),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(fontSize: 12.5, color: Apex.muted),
            ),
          ),
          const SizedBox(width: 12),
          Text(
            value,
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: Apex.ink,
            ),
          ),
        ],
      ),
    ),
  );
}

/// Panel of label/amount lines ("Cash activity", "Balance sheet at …").
class ReportLinesPanel extends StatelessWidget {
  const ReportLinesPanel({
    required this.title,
    required this.lines,
    this.intro,
    this.topGap = false,
    super.key,
  });

  final String title;
  final List<(String, String)> lines;
  final String? intro;
  final bool topGap;

  @override
  Widget build(BuildContext context) => ReportPanel(
    title: title,
    padded: true,
    topGap: topGap,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (intro != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              intro!,
              style: const TextStyle(
                fontSize: 14,
                height: 1.6,
                color: Apex.muted,
              ),
            ),
          ),
        for (final (label, value) in lines) ReportLine(label, value),
      ],
    ),
  );
}

/// A table cell: text with an optional small second line, tone and weight.
class ReportCell {
  const ReportCell(
    this.text, {
    this.sub,
    this.color,
    this.bold = false,
    this.link = false,
    this.onTap,
  });
  final String text;
  final String? sub;
  final Color? color;
  final bool bold;
  final bool link;

  /// Overrides the row tap for this link cell.
  final VoidCallback? onTap;
}

class ReportTableRow {
  const ReportTableRow(this.cells, {this.onTap, this.muted = false});
  final List<Object> cells;
  final VoidCallback? onTap;
  final bool muted;
}

ReportCell _cell(Object value) =>
    value is ReportCell ? value : ReportCell(value.toString());

/// Report table in a panel: grey uppercase header, right-aligned amounts, 30-row pages,
/// stacked cards on phones, horizontal scroll when a desktop table has many columns.
class ReportTable extends StatefulWidget {
  const ReportTable({
    required this.title,
    required this.columns,
    required this.rows,
    required this.empty,
    this.subtitle,
    this.pageSize = 30,
    this.minColumnWidth = 112,
    this.below,
    super.key,
  });

  final String title;
  final String? subtitle;
  final List<ApexColumn> columns;
  final List<ReportTableRow> rows;
  final String empty;
  final int pageSize;
  final double minColumnWidth;

  /// Shown under the rows inside the panel (for example an opened stock history).
  final Widget? below;

  @override
  State<ReportTable> createState() => _ReportTableState();
}

class _ReportTableState extends State<ReportTable> {
  int _page = 0;

  Widget _body(List<ReportTableRow> rows) => LayoutBuilder(
    builder: (context, limits) {
      final columns = widget.columns;
      Widget cell(int row, int column) {
        final value = _cell(rows[row].cells[column]);
        final muted = rows[row].muted;
        final style = TextStyle(
          fontSize: 13,
          fontWeight: value.bold ? FontWeight.w700 : FontWeight.w400,
          color: value.color ?? (muted ? Apex.muted : Apex.inkSoft),
        );
        final alignEnd = columns[column].alignEnd;
        return Column(
          crossAxisAlignment: alignEnd
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            if (value.link)
              ApexLink(
                value.text,
                onTap: value.onTap ?? rows[row].onTap,
                strong: value.bold,
              )
            else
              Text(
                value.text,
                textAlign: alignEnd ? TextAlign.right : TextAlign.left,
                style: style,
              ),
            if (value.sub != null && value.sub!.isNotEmpty)
              Text(
                value.sub!,
                textAlign: alignEnd ? TextAlign.right : TextAlign.left,
                style: const TextStyle(
                  fontSize: 12,
                  height: 1.5,
                  color: Apex.muted,
                ),
              ),
          ],
        );
      }

      Widget card(int row) {
        final cells = [for (final value in rows[row].cells) _cell(value)];
        final first = cells.first;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              first.text,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: Apex.ink,
              ),
            ),
            if (first.sub != null && first.sub!.isNotEmpty)
              Text(first.sub!, style: Apex.note),
            const SizedBox(height: 8),
            for (var i = 1; i < cells.length; i++)
              if (cells[i].text.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          columns[i].title,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Apex.muted,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Flexible(
                        child: cells[i].link && cells[i].onTap != null
                            ? Align(
                                alignment: Alignment.centerRight,
                                child: ApexLink(
                                  cells[i].text,
                                  onTap: cells[i].onTap,
                                ),
                              )
                            : Text(
                                cells[i].sub == null || cells[i].sub!.isEmpty
                                    ? cells[i].text
                                    : '${cells[i].text}\n${cells[i].sub}',
                                textAlign: TextAlign.right,
                                style: TextStyle(
                                  fontSize: 12.5,
                                  fontWeight: cells[i].bold
                                      ? FontWeight.w700
                                      : FontWeight.w500,
                                  color: cells[i].color ?? Apex.inkSoft,
                                ),
                              ),
                      ),
                    ],
                  ),
                ),
          ],
        );
      }

      ApexTable table({double breakpoint = 720}) => ApexTable(
        columns: columns,
        rowCount: rows.length,
        cell: cell,
        card: card,
        cardBreakpoint: breakpoint,
        onRowTap: rows.any((row) => row.onTap != null)
            ? (index) => rows[index].onTap?.call()
            : null,
      );

      final minWidth = columns.fold<double>(
        0,
        (sum, column) => sum + (column.width ?? widget.minColumnWidth),
      );
      if (limits.maxWidth < 720 || minWidth <= limits.maxWidth) {
        return table();
      }
      return Scrollbar(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: SizedBox(width: minWidth, child: table(breakpoint: 0)),
        ),
      );
    },
  );

  @override
  Widget build(BuildContext context) {
    final rows = widget.rows;
    if (rows.isEmpty) {
      return ReportPanel(
        title: widget.title,
        subtitle: widget.subtitle,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Divider(color: Apex.line, height: 1),
            _body(const []),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 36),
              child: Center(
                child: Text(
                  widget.empty,
                  style: Apex.strong.copyWith(fontSize: 14),
                ),
              ),
            ),
          ],
        ),
      );
    }
    final size = widget.pageSize;
    final page = _page.clamp(0, (rows.length - 1) ~/ size);
    final offset = page * size;
    final current = rows.skip(offset).take(size).toList(growable: false);
    return ReportPanel(
      title: widget.title,
      subtitle: widget.subtitle,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _body(current),
          ?widget.below,
          if (rows.length > size)
            DecoratedBox(
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: Apex.line)),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 8,
                ),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    TextButton(
                      onPressed: page > 0
                          ? () => setState(() => _page = page - 1)
                          : null,
                      child: const Text('Previous'),
                    ),
                    Text(
                      '${offset + 1}–${offset + current.length} of ${rows.length}',
                      style: const TextStyle(fontSize: 12.5, color: Apex.muted),
                    ),
                    TextButton(
                      onPressed: offset + current.length < rows.length
                          ? () => setState(() => _page = page + 1)
                          : null,
                      child: const Text('Next'),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

ApexColumn reportText(String title, {double flex = 1}) =>
    ApexColumn(title, flex: flex);
ApexColumn reportAmount(String title, {double flex = 1}) =>
    ApexColumn(title, flex: flex, alignEnd: true);
