import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'commerce_commands.dart';

/// Presentation pieces for the Ecommerce screen, measured from the web app's
/// commerce.css (card titles 15px, notes 13px, alerts, metric tiles, tabs).

const _alertInk = Color(0xff1c3c72);
const _alertBackground = Color(0xffe8edf5);
const _alertBorder = Color(0xffced7e7);
const _errorInk = Color(0xffa13f35);
const _errorBackground = Color(0xfffff0ed);
const _errorBorder = Color(0xfff3d8d2);

/// Status pill: active, review, paused, and so on.
class CommerceStatus extends StatelessWidget {
  const CommerceStatus(this.status, {super.key});

  final Object? status;

  @override
  Widget build(BuildContext context) => ApexStatusBadge(
    commerceLabel(status),
    tone: switch (status) {
      'active' || 'done' || 'balanced' => ApexBadgeTone.converted,
      'review' || 'retry' => ApexBadgeTone.draft,
      _ => ApexBadgeTone.neutral,
    },
  );
}

/// Info or error notice above the workspace, like the web commerce-alert.
class CommerceAlert extends StatelessWidget {
  const CommerceAlert(this.text, {this.action, this.error = false, super.key});

  final String text;
  final Widget? action;
  final bool error;

  @override
  Widget build(BuildContext context) {
    final ink = error ? _errorInk : _alertInk;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: error ? _errorBackground : _alertBackground,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: error ? _errorBorder : _alertBorder),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (error) ...[
                  Icon(Icons.error_outline, size: 18, color: ink),
                  const SizedBox(width: 9),
                ],
                Expanded(
                  child: Text(
                    text,
                    style: TextStyle(fontSize: 13, height: 1.5, color: ink),
                  ),
                ),
              ],
            ),
            if (action != null) ...[
              const SizedBox(height: 6),
              Align(alignment: Alignment.centerLeft, child: action),
            ],
          ],
        ),
      ),
    );
  }
}

/// White commerce card: title, note, action buttons, then its content.
class CommerceSection extends StatelessWidget {
  const CommerceSection({
    required this.title,
    this.note,
    this.actions = const [],
    this.children = const [],
    super.key,
  });

  final String title;
  final String? note;
  final List<Widget> actions;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => ApexPanel(
    child: LayoutBuilder(
      builder: (context, limits) {
        final pad = limits.maxWidth < 640 ? 16.0 : 22.0;
        return Padding(
          padding: EdgeInsets.all(pad),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title, style: _sectionTitle),
              if (note != null) ...[
                const SizedBox(height: 7),
                Text(note!, style: _sectionNote),
              ],
              if (actions.isNotEmpty) ...[
                const SizedBox(height: 14),
                Wrap(spacing: 8, runSpacing: 8, children: actions),
              ],
              if (children.isNotEmpty) ...[
                const SizedBox(height: 16),
                for (final (index, child) in children.indexed) ...[
                  if (index > 0) const SizedBox(height: 12),
                  child,
                ],
              ],
            ],
          ),
        );
      },
    ),
  );
}

const _sectionTitle = TextStyle(
  fontSize: 15,
  fontWeight: FontWeight.w700,
  color: Apex.ink,
);
const _sectionNote = TextStyle(fontSize: 13, height: 1.6, color: Apex.muted);

/// Two cards side by side on desktop, stacked on phones.
class CommerceGrid extends StatelessWidget {
  const CommerceGrid(this.cards, {super.key});

  final List<Widget> cards;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      if (limits.maxWidth < 800) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final (index, card) in cards.indexed) ...[
              if (index > 0) const SizedBox(height: 18),
              card,
            ],
          ],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (index, card) in cards.indexed) ...[
            if (index > 0) const SizedBox(width: 18),
            Expanded(child: card),
          ],
        ],
      );
    },
  );
}

/// Four figures in a row on desktop, two per row on phones.
class CommerceMetrics extends StatelessWidget {
  const CommerceMetrics(this.metrics, {super.key});

  final List<(IconData, String, int)> metrics;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      const gap = 14.0;
      final columns = limits.maxWidth >= 800 ? metrics.length : 2;
      final width = (limits.maxWidth - gap * (columns - 1)) / columns;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final (icon, label, value) in metrics)
            SizedBox(
              width: width,
              child: _CommerceMetric(icon: icon, label: label, value: value),
            ),
        ],
      );
    },
  );
}

class _CommerceMetric extends StatelessWidget {
  const _CommerceMetric({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final int value;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: '$label, $value',
    child: ExcludeSemantics(
      child: ApexPanel(
        radius: 12,
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(fontSize: 12, color: Apex.muted),
                  ),
                ),
                Icon(icon, size: 20, color: Apex.green),
              ],
            ),
            const SizedBox(height: 10),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                '$value',
                style: const TextStyle(
                  fontFamily: Apex.display,
                  fontSize: 26,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -1,
                  color: Apex.ink,
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// Underlined section tabs (Overview, Catalogue, Orders …).
class CommerceTabBar<T> extends StatelessWidget {
  const CommerceTabBar({
    required this.tabs,
    required this.selected,
    required this.onSelected,
    super.key,
  });

  final List<(T, String)> tabs;
  final T selected;
  final ValueChanged<T> onSelected;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: const BoxDecoration(
      border: Border(bottom: BorderSide(color: Apex.line)),
    ),
    child: SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final (value, text) in tabs)
            Semantics(
              button: true,
              selected: value == selected,
              child: InkWell(
                onTap: () => onSelected(value),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    border: Border(
                      bottom: BorderSide(
                        width: 3,
                        color: value == selected
                            ? Apex.green
                            : Colors.transparent,
                      ),
                    ),
                  ),
                  child: Text(
                    text,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: value == selected
                          ? FontWeight.w700
                          : FontWeight.w500,
                      color: value == selected ? Apex.green : Apex.muted,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    ),
  );
}

/// Bold title with a small grey line under it, for table and list cells.
class CommerceCellTitle extends StatelessWidget {
  const CommerceCellTitle(this.title, {this.subtitle, super.key});

  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        title,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w700,
          color: Apex.ink,
        ),
      ),
      if (subtitle != null && subtitle!.isNotEmpty) ...[
        const SizedBox(height: 3),
        Text(
          subtitle!,
          style: const TextStyle(fontSize: 11, color: Color(0xff7c8697)),
        ),
      ],
    ],
  );
}

/// Plain table cell text.
class CommerceCell extends StatelessWidget {
  const CommerceCell(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) =>
      Text(text, style: const TextStyle(fontSize: 13, color: Apex.inkSoft));
}

/// One stacked row in a phone card list: title, detail, optional badge and action.
class CommerceListRow extends StatelessWidget {
  const CommerceListRow({
    required this.title,
    this.subtitle,
    this.detail,
    this.trailing,
    this.badge,
    this.action,
    super.key,
  });

  final String title;
  final String? subtitle;
  final String? detail;
  final Widget? trailing;
  final Widget? badge;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: CommerceCellTitle(title, subtitle: subtitle)),
          if (trailing != null) ...[const SizedBox(width: 10), trailing!],
        ],
      ),
      if (badge != null || (detail != null && detail!.isNotEmpty)) ...[
        const SizedBox(height: 8),
        Wrap(
          spacing: 10,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            ?badge,
            if (detail != null && detail!.isNotEmpty)
              Text(
                detail!,
                style: const TextStyle(fontSize: 12, color: Apex.muted),
              ),
          ],
        ),
      ],
      if (action != null) ...[
        const SizedBox(height: 8),
        Align(alignment: Alignment.centerLeft, child: action),
      ],
    ],
  );
}

/// Small heading inside a card, above a sub-list (e.g. "Mappings").
class CommerceSubheading extends StatelessWidget {
  const CommerceSubheading(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(
      fontSize: 13,
      fontWeight: FontWeight.w700,
      color: Apex.ink,
    ),
  );
}
