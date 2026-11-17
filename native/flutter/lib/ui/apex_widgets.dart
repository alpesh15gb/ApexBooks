import 'package:intl/intl.dart';
import 'package:material_ui/material_ui.dart';

import 'apex_theme.dart';

final _rupees = NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 2);
final _compact = NumberFormat.compact(locale: 'en_IN');

/// ₹ amount the way the web app shows it (en-IN grouping, two decimals).
String apexMoney(num? value) => value == null || !value.isFinite ? '—' : _rupees.format(value);

/// Axis labels: 4K, 1.5L and so on.
String apexCompact(num value) => _compact.format(value);

num? apexNumber(Object? value) => value == null ? null : num.tryParse('$value');

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'];

/// "16 Nov 2026" from an ISO date, matching the web app's en-IN dates.
String apexDate(String iso) {
  final date = DateTime.tryParse(iso);
  if (date == null) return iso;
  return '${date.day} ${_months[date.month - 1]} ${date.year}';
}

String apexMonth(int month) => _months[month - 1];

/// White panel with the web app's card border and radius.
class ApexPanel extends StatelessWidget {
  const ApexPanel({
    required this.child,
    this.padding = EdgeInsets.zero,
    this.color = Apex.card,
    this.borderColor = Apex.line,
    this.radius = Apex.radiusCard,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;
  final Color borderColor;
  final double radius;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: color,
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(color: borderColor),
      boxShadow: const [BoxShadow(color: Color(0x06204132), blurRadius: 12, offset: Offset(0, 3))],
    ),
    child: ClipRRect(
      borderRadius: BorderRadius.circular(radius - 1),
      child: Padding(padding: padding, child: child),
    ),
  );
}

/// Title and optional note at the top of a panel.
class ApexPanelHeading extends StatelessWidget {
  const ApexPanelHeading(this.title, {this.note, this.trailing, this.titleColor, this.noteColor, super.key});

  final String title;
  final String? note;
  final Widget? trailing;
  final Color? titleColor;
  final Color? noteColor;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Apex.sectionTitle.copyWith(color: titleColor)),
            if (note != null) ...[
              const SizedBox(height: 5),
              Text(note!, style: Apex.note.copyWith(color: noteColor)),
            ],
          ],
        ),
      ),
      ?trailing,
    ],
  );
}

enum ApexBadgeTone { posted, draft, cancelled, converted, neutral }

/// Small status pill: Posted, Draft, Cancelled…
class ApexStatusBadge extends StatelessWidget {
  const ApexStatusBadge(this.label, {this.tone = ApexBadgeTone.neutral, super.key});

  final String label;
  final ApexBadgeTone tone;

  @override
  Widget build(BuildContext context) {
    final (background, foreground) = switch (tone) {
      ApexBadgeTone.posted => (const Color(0xffeaf4ee), const Color(0xff24745a)),
      ApexBadgeTone.draft => (const Color(0xfffbf2e2), const Color(0xff98631c)),
      ApexBadgeTone.cancelled => (const Color(0xfffcecea), const Color(0xffa4413d)),
      ApexBadgeTone.converted => (const Color(0xffe7f3fb), const Color(0xff0077b7)),
      ApexBadgeTone.neutral => (const Color(0xfff2f3f6), const Color(0xff5c6779)),
    };
    return DecoratedBox(
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(7)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        child: Text(
          label,
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: .12, color: foreground),
        ),
      ),
    );
  }
}

/// Rounded square holding an icon, as used beside list rows and in task tiles.
class ApexIconTile extends StatelessWidget {
  const ApexIconTile(
    this.icon, {
    this.background = Apex.mintIcon,
    this.foreground = Apex.greenText,
    this.size = 34,
    this.iconSize = 18,
    this.radius = 8,
    this.circle = false,
    super.key,
  });

  final IconData icon;
  final Color background;
  final Color foreground;
  final double size;
  final double iconSize;
  final double radius;
  final bool circle;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      color: background,
      shape: circle ? BoxShape.circle : BoxShape.rectangle,
      borderRadius: circle ? null : BorderRadius.circular(radius),
    ),
    child: Icon(icon, size: iconSize, color: foreground),
  );
}

/// Page title block used at the top of workspace pages.
class ApexPageHeading extends StatelessWidget {
  const ApexPageHeading(this.title, {this.subtitle, this.actions = const [], this.compact = false, super.key});

  final String title;
  final String? subtitle;
  final List<Widget> actions;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final heading = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: compact ? Apex.pageTitle.copyWith(fontSize: 28, letterSpacing: -1.1) : Apex.pageTitle,
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 5),
          Text(subtitle!, style: Apex.lead),
        ],
      ],
    );
    if (actions.isEmpty) return heading;
    if (compact) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [heading, const SizedBox(height: 14), Wrap(spacing: 8, runSpacing: 8, children: actions)],
      );
    }
    return LayoutBuilder(
      builder: (context, limits) => Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.end,
        spacing: 20,
        runSpacing: 14,
        children: [
          ConstrainedBox(constraints: BoxConstraints(maxWidth: limits.maxWidth), child: heading),
          Wrap(spacing: 8, runSpacing: 8, children: actions),
        ],
      ),
    );
  }
}
