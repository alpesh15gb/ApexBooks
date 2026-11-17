import 'dart:ui' show FontFeature, PathMetric;

import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';

/// Colours measured from the web `pos-counter.css`.
abstract final class PosColors {
  static const ink = Color(0xff202b29);
  static const muted = Color(0xff576664);
  static const rule = Color(0xffd9e2df);
  static const green = Color(0xff087546);
  static const wash = Color(0xffedf6f1);
  static const tabTrack = Color(0xffe9efec);
  static const tabActiveBorder = Color(0xffd0dbd5);
  static const tabActiveText = Color(0xff075b37);
  static const scanBorder = Color(0xffaabbb3);
  static const scanFill = Color(0xfff9fbfa);
  static const scanText = Color(0xff455b52);
  static const media = Color(0xffedf3f0);
  static const emptyBorder = Color(0xffc7d7cf);
  static const emptyFill = Color(0xfff8fbf9);
  static const emptyText = Color(0xff345b49);
  static const totalBorder = Color(0xffcee0d6);
  static const totalText = Color(0xff234e3a);
  static const warn = Color(0xff92501b);
  static const successBorder = Color(0xffb7d8c2);
  static const successFill = Color(0xffeef7f0);
  static const successText = Color(0xff17623b);
}

/// Card used for every POS section (Products, Current sale, Receipt history…).
class PosPanel extends StatelessWidget {
  const PosPanel({required this.children, this.spacing = 9, super.key});

  final List<Widget> children;
  final double spacing;

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 700;
    return ApexPanel(
      borderColor: PosColors.rule,
      padding: EdgeInsets.all(wide ? 22 : 14),
      child: Material(
        type: MaterialType.transparency,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var index = 0; index < children.length; index++) ...[
              if (index > 0) SizedBox(height: spacing),
              children[index],
            ],
          ],
        ),
      ),
    );
  }
}

/// "Products ........ 4 items" row at the top of a panel.
class PosPanelHeading extends StatelessWidget {
  const PosPanelHeading(this.title, {this.detail, super.key});

  final String title;
  final String? detail;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 5),
    child: Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontFamily: Apex.display,
              fontSize: 19,
              fontWeight: FontWeight.w600,
              letterSpacing: -.48,
              color: Apex.ink,
            ),
          ),
        ),
        if (detail != null) ...[
          const SizedBox(width: 12),
          Text(
            detail!,
            style: const TextStyle(fontSize: 12, color: PosColors.muted),
          ),
        ],
      ],
    ),
  );
}

/// Title and the "Today's sales" badge.
class PosHeader extends StatelessWidget {
  const PosHeader({
    required this.salesTotal,
    required this.receiptCount,
    super.key,
  });

  final String salesTotal;
  final String receiptCount;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 700;
    final title = Text(
      'Point of sale',
      style: Apex.pageTitle.copyWith(
        fontSize: compact ? 28 : 38,
        letterSpacing: compact ? -1.1 : -1.7,
      ),
    );
    final amount = TextStyle(
      fontSize: compact ? 16 : 19,
      fontWeight: FontWeight.w700,
      color: Apex.ink,
    );
    final badge = ApexPanel(
      radius: 10,
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 10 : 12,
        vertical: compact ? 8 : 10,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (compact) ...[
            const Text(
              'Today’s sales',
              style: TextStyle(fontSize: 12, color: PosColors.muted),
            ),
            Text(salesTotal, style: amount),
          ] else
            Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                const Text(
                  'Today’s sales',
                  style: TextStyle(fontSize: 12, color: PosColors.muted),
                ),
                const SizedBox(width: 10),
                Text(salesTotal, style: amount),
              ],
            ),
          const SizedBox(height: 1),
          Text(
            receiptCount,
            style: const TextStyle(fontSize: 12, color: PosColors.muted),
          ),
        ],
      ),
    );
    return Row(
      crossAxisAlignment: compact
          ? CrossAxisAlignment.start
          : CrossAxisAlignment.center,
      children: [
        Expanded(child: title),
        const SizedBox(width: 12),
        badge,
      ],
    );
  }
}

class PosTabItem<T> {
  const PosTabItem(this.value, this.label, this.icon);

  final T value;
  final String label;
  final IconData icon;
}

/// Segmented Checkout / Receipts / Register control with icons.
class PosViewTabs<T> extends StatelessWidget {
  const PosViewTabs({
    required this.tabs,
    required this.selected,
    required this.onSelected,
    super.key,
  });

  final List<PosTabItem<T>> tabs;
  final T selected;
  final ValueChanged<T> onSelected;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 520;
    Widget tab(PosTabItem<T> item) {
      final active = item.value == selected;
      final content = Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            item.icon,
            size: compact ? 16 : 18,
            color: active ? PosColors.tabActiveText : PosColors.muted,
          ),
          SizedBox(width: compact ? 5 : 8),
          Flexible(
            child: Text(
              item.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: compact ? 13 : 14,
                fontWeight: FontWeight.w700,
                color: active ? PosColors.tabActiveText : PosColors.muted,
              ),
            ),
          ),
        ],
      );
      final button = Semantics(
        button: true,
        selected: active,
        child: Material(
          color: active ? Colors.white : Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(6),
            side: BorderSide(
              color: active ? PosColors.tabActiveBorder : Colors.transparent,
            ),
          ),
          elevation: 0,
          child: InkWell(
            borderRadius: BorderRadius.circular(6),
            onTap: () => onSelected(item.value),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 42),
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: compact ? 2 : 14),
                child: Center(widthFactor: compact ? null : 1, child: content),
              ),
            ),
          ),
        ),
      );
      return compact ? Expanded(child: button) : button;
    }

    final row = Row(
      mainAxisSize: compact ? MainAxisSize.max : MainAxisSize.min,
      children: [
        for (var index = 0; index < tabs.length; index++) ...[
          if (index > 0) const SizedBox(width: 5),
          tab(tabs[index]),
        ],
      ],
    );
    return Align(
      alignment: Alignment.centerLeft,
      widthFactor: compact ? null : 1,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: PosColors.tabTrack,
          border: Border.all(color: PosColors.rule),
          borderRadius: BorderRadius.circular(9),
        ),
        child: Padding(padding: const EdgeInsets.all(4), child: row),
      ),
    );
  }
}

/// Dashed rounded box ("Your cart is empty").
class PosDashedBox extends StatelessWidget {
  const PosDashedBox({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) => CustomPaint(
    painter: _DashedBorder(),
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 18),
      decoration: BoxDecoration(
        color: PosColors.emptyFill,
        borderRadius: BorderRadius.circular(9),
      ),
      child: child,
    ),
  );
}

class _DashedBorder extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = PosColors.emptyBorder
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    final path = Path()
      ..addRRect(
        RRect.fromRectAndRadius(
          (Offset.zero & size).deflate(.5),
          const Radius.circular(9),
        ),
      );
    for (final PathMetric metric in path.computeMetrics()) {
      var distance = 0.0;
      while (distance < metric.length) {
        canvas.drawPath(metric.extractPath(distance, distance + 4), paint);
        distance += 7;
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Bordered row used for receipt history entries and similar lists.
class PosListRow extends StatelessWidget {
  const PosListRow({required this.child, this.onTap, super.key});

  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    child: DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Apex.lineSoft)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: child,
      ),
    ),
  );
}

/// Rounded, bordered text field style used for POS search fields.
InputDecoration posFieldDecoration({
  String? label,
  String? hint,
  Widget? prefix,
  Widget? suffix,
}) {
  OutlineInputBorder border(Color color, [double width = 1]) =>
      OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: BorderSide(color: color, width: width),
      );
  return InputDecoration(
    labelText: label,
    hintText: hint,
    prefixIcon: prefix,
    suffixIcon: suffix,
    filled: true,
    fillColor: PosColors.scanFill,
    enabledBorder: border(PosColors.scanBorder),
    focusedBorder: border(PosColors.green, 1.5),
    border: border(PosColors.scanBorder),
  );
}

/// Bordered box of label/value pairs ("Expected cash", "Cash sales"…), the
/// web `pos-reconciliation-results` block.
class PosResultsBox extends StatelessWidget {
  const PosResultsBox(this.items, {super.key});

  final List<(String, String)> items;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      border: Border.all(color: Apex.line),
      borderRadius: BorderRadius.circular(7),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Wrap(
        spacing: 28,
        runSpacing: 12,
        children: [
          for (final (label, value) in items)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: const TextStyle(fontSize: 12.8, color: PosColors.muted),
                ),
                const SizedBox(height: 3),
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: Apex.ink,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
              ],
            ),
        ],
      ),
    ),
  );
}

/// Collapsible block styled like the web `<details>` summaries.
class PosDisclosure extends StatelessWidget {
  const PosDisclosure({
    required this.title,
    required this.children,
    this.detail,
    this.initiallyExpanded = false,
    this.boxed = false,
    this.onExpansionChanged,
    super.key,
  });

  final String title;
  final String? detail;
  final bool initiallyExpanded;
  final bool boxed;
  final ValueChanged<bool>? onExpansionChanged;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final tile = Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        initiallyExpanded: initiallyExpanded,
        backgroundColor: Colors.transparent,
        collapsedBackgroundColor: Colors.transparent,
        shape: const Border(),
        collapsedShape: const Border(),
        onExpansionChanged: onExpansionChanged,
        tilePadding: EdgeInsets.symmetric(horizontal: boxed ? 18 : 0),
        childrenPadding: EdgeInsets.fromLTRB(
          boxed ? 18 : 0,
          0,
          boxed ? 18 : 0,
          boxed ? 16 : 8,
        ),
        expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
        expandedAlignment: Alignment.centerLeft,
        minTileHeight: 44,
        title: Text.rich(
          TextSpan(
            text: title,
            style: TextStyle(
              fontSize: boxed ? 15 : 13,
              fontWeight: FontWeight.w700,
              color: boxed ? Apex.ink : const Color(0xff36594b),
            ),
            children: [
              if (detail != null)
                TextSpan(
                  text: '  $detail',
                  style: const TextStyle(
                    fontWeight: FontWeight.w500,
                    color: PosColors.muted,
                  ),
                ),
            ],
          ),
        ),
        children: children,
      ),
    );
    if (!boxed) return tile;
    return ApexPanel(
      borderColor: PosColors.rule,
      child: Material(type: MaterialType.transparency, child: tile),
    );
  }
}

/// Field group with a bold legend, the web `<fieldset>` inside a form.
class PosFieldset extends StatelessWidget {
  const PosFieldset({required this.legend, required this.children, super.key});

  final String? legend;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (legend != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Text(
            legend!,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: Apex.ink,
            ),
          ),
        ),
      for (var index = 0; index < children.length; index++) ...[
        if (index > 0) const SizedBox(height: 12),
        children[index],
      ],
    ],
  );
}

/// Two fields side by side on wide layouts, stacked on phones.
class PosFieldRow extends StatelessWidget {
  const PosFieldRow(this.children, {super.key});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      if (limits.maxWidth < 420 || children.length == 1) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var index = 0; index < children.length; index++) ...[
              if (index > 0) const SizedBox(height: 12),
              children[index],
            ],
          ],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var index = 0; index < children.length; index++) ...[
            if (index > 0) const SizedBox(width: 12),
            Expanded(child: children[index]),
          ],
        ],
      );
    },
  );
}

/// The "info-box" paragraph: pale green box for status text.
class PosInfoBox extends StatelessWidget {
  const PosInfoBox(this.message, {this.error = false, this.child, super.key});

  final String message;
  final bool error;
  final Widget? child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    decoration: BoxDecoration(
      color: error ? const Color(0xfffdf1ee) : PosColors.wash,
      border: Border.all(
        color: error ? const Color(0xffe9bdb3) : PosColors.totalBorder,
      ),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          liveRegion: true,
          child: Text(
            message,
            style: TextStyle(
              fontSize: 13,
              color: error ? const Color(0xff9b2d1a) : PosColors.totalText,
            ),
          ),
        ),
        ?child,
      ],
    ),
  );
}
