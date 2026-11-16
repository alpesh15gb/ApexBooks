import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';

/// Blue info box, red error banner or green confirmation, as on the web page.
enum BankTone { info, error, ok }

class BankNote extends StatelessWidget {
  const BankNote({required this.child, this.tone = BankTone.info, this.live = false, super.key});

  final Widget child;
  final BankTone tone;
  final bool live;

  @override
  Widget build(BuildContext context) {
    final (background, border, color) = switch (tone) {
      BankTone.info => (const Color(0xffeef6fb), const Color(0xffcfe3f0), Apex.inkSoft),
      BankTone.error => (const Color(0xfffcecea), const Color(0xfff1c6c3), Apex.red),
      BankTone.ok => (Apex.mintSoft, Apex.mintLine, Apex.greenDark),
    };
    return Semantics(
      liveRegion: live,
      container: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: border),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: DefaultTextStyle.merge(style: TextStyle(fontSize: 12, height: 1.6, color: color), child: child),
        ),
      ),
    );
  }
}

/// Summary card: small caps label, large figure, optional caption and icon.
class BankMetric extends StatelessWidget {
  const BankMetric({required this.label, required this.value, this.caption, this.icon, super.key});

  final String label;
  final String value;
  final String? caption;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: '$label, $value',
    child: ExcludeSemantics(
      child: ApexPanel(
        radius: 10,
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(label.toUpperCase(), maxLines: 2, overflow: TextOverflow.ellipsis, style: Apex.tableHeader),
                ),
                if (icon != null) Icon(icon, size: 18, color: Apex.muted),
              ],
            ),
            const SizedBox(height: 12),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                value,
                style: const TextStyle(
                  fontFamily: Apex.display,
                  fontSize: 26,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -.6,
                  color: Color(0xff27313d),
                ),
              ),
            ),
            if (caption != null) ...[const SizedBox(height: 6), Text(caption!, style: Apex.small)],
          ],
        ),
      ),
    ),
  );
}

/// Metric cards in a row on wide screens, two columns on phones.
class BankMetricGrid extends StatelessWidget {
  const BankMetricGrid(this.cards, {super.key});
  final List<Widget> cards;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final columns = limits.maxWidth >= 720
          ? cards.length
          : limits.maxWidth >= 360 && cards.length > 2
          ? 2
          : 1;
      const gap = 16.0;
      final width = (limits.maxWidth - gap * (columns - 1)) / columns;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [for (final card in cards) SizedBox(width: width, child: card)],
      );
    },
  );
}

/// Text field with its label above it, used in filter bands.
class BankFilterField extends StatelessWidget {
  const BankFilterField({
    required this.label,
    required this.controller,
    this.width = 170,
    this.hint,
    this.maxLength,
    this.keyboard,
    super.key,
  });

  final String label;
  final TextEditingController controller;
  final double width;
  final String? hint;
  final int? maxLength;
  final TextInputType? keyboard;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Apex.muted)),
        const SizedBox(height: 6),
        SizedBox(
          height: 40,
          child: Semantics(
            label: label,
            child: TextField(
              controller: controller,
              maxLength: maxLength,
              keyboardType: keyboard,
              style: const TextStyle(fontSize: 13),
              decoration: InputDecoration(
                hintText: hint,
                counterText: '',
                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

/// The two views of the page.
class BankTabs extends StatelessWidget {
  const BankTabs({required this.reconcile, required this.onChanged, super.key});
  final bool reconcile;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      for (final (value, text) in const [(false, 'Cash book'), (true, 'Reconciliation')])
        Padding(
          padding: const EdgeInsets.only(right: 6),
          child: Semantics(
            button: true,
            selected: reconcile == value,
            child: Material(
              color: reconcile == value ? const Color(0xffe3f2e9) : Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(Apex.radiusChip),
                side: BorderSide(color: reconcile == value ? const Color(0xffb9d8c6) : Colors.transparent),
              ),
              child: InkWell(
                onTap: () => onChanged(value),
                borderRadius: BorderRadius.circular(Apex.radiusChip),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 12),
                  child: Text(
                    text,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: reconcile == value ? FontWeight.w700 : FontWeight.w500,
                      color: reconcile == value ? const Color(0xff124e36) : Apex.muted,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
    ],
  );
}

/// White panel with the web panel heading (title, note, optional trailing actions).
class BankPanel extends StatelessWidget {
  const BankPanel({required this.title, required this.children, this.note, this.trailing, this.flush = false, super.key});

  final String title;
  final String? note;
  final Widget? trailing;
  final List<Widget> children;

  /// Children run edge to edge (tables) instead of inside the panel padding.
  final bool flush;

  @override
  Widget build(BuildContext context) => ApexPanel(
    radius: Apex.radiusPanel,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(22, 22, 22, flush ? 16 : 14),
          child: ApexPanelHeading(title, note: note, trailing: trailing),
        ),
        if (flush)
          ...children
        else
          Padding(
            padding: const EdgeInsets.fromLTRB(22, 0, 22, 22),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
          ),
      ],
    ),
  );
}
