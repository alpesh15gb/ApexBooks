import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';

/// Section title used inside the settings panel (the web app's `.settings-panel h3`).
const settingsBlockTitle = TextStyle(
  fontSize: 18.7,
  fontWeight: FontWeight.w700,
  letterSpacing: -.47,
  color: Color(0xff365364),
);

/// One block of the settings panel: title, optional note, then its content.
/// [anchor] lets the jump links scroll to it.
class SettingsBlock extends StatelessWidget {
  const SettingsBlock({
    required this.title,
    required this.children,
    this.note,
    this.icon,
    this.anchor,
    this.trailing,
    super.key,
  });

  final String title;
  final String? note;
  final IconData? icon;
  final GlobalKey? anchor;
  final Widget? trailing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
    key: anchor,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Semantics(
              header: true,
              child: Row(
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 17, color: const Color(0xff365364)),
                    const SizedBox(width: 8),
                  ],
                  Flexible(child: Text(title, style: settingsBlockTitle)),
                ],
              ),
            ),
          ),
          ?trailing,
        ],
      ),
      if (note != null) ...[
        const SizedBox(height: 5),
        Text(note!, style: Apex.note),
      ],
      const SizedBox(height: 14),
      ...children,
    ],
  );
}

/// Label above a bold value, two columns on desktop and one on phones.
class SettingsDetails extends StatelessWidget {
  const SettingsDetails(this.entries, {super.key});

  final List<(String, String)> entries;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final columns = limits.maxWidth < 560 ? 1 : 2;
      final width = (limits.maxWidth - (columns - 1) * 20) / columns;
      return Wrap(
        spacing: 20,
        runSpacing: 18,
        children: [
          for (final (label, value) in entries)
            SizedBox(
              width: width,
              child: Semantics(
                container: true,
                label: '$label: $value',
                excludeSemantics: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label.toUpperCase(),
                      style: const TextStyle(
                        fontSize: 12,
                        letterSpacing: .48,
                        color: Apex.muted,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      value,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: Apex.ink,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      );
    },
  );
}

/// A bordered row used for members, locations, numbering and similar lists.
class SettingsRow extends StatelessWidget {
  const SettingsRow({
    required this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(vertical: 11),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Apex.lineSoft)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: Apex.ink,
                  ),
                ),
                if (subtitle != null && subtitle!.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(subtitle!, style: Apex.note.copyWith(height: 1.4)),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    ),
  );
}

/// Inline notice used for load failures and status messages.
class SettingsNotice extends StatelessWidget {
  const SettingsNotice(this.text, {this.error = false, this.action, super.key});

  final String text;
  final bool error;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: error ? const Color(0xfffcf1ef) : Apex.tint,
        borderRadius: BorderRadius.circular(Apex.radiusChip),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                fontSize: 12,
                color: error ? const Color(0xffa4413d) : Apex.inkSoft,
              ),
            ),
          ),
          ?action,
        ],
      ),
    ),
  );
}

/// White card holding settings blocks separated by rules, like `.settings-panel`.
class SettingsCard extends StatelessWidget {
  const SettingsCard({
    required this.padding,
    required this.children,
    super.key,
  });

  final double padding;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Material(
    color: Apex.card,
    clipBehavior: Clip.antiAlias,
    shape: RoundedRectangleBorder(
      side: const BorderSide(color: Apex.line),
      borderRadius: BorderRadius.circular(Apex.radiusPanel),
    ),
    child: Padding(
      padding: EdgeInsets.all(padding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var index = 0; index < children.length; index++) ...[
            if (index > 0)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Divider(height: 1, color: Apex.line),
              ),
            children[index],
          ],
        ],
      ),
    ),
  );
}

/// Pill-shaped jump link under a tab heading.
class SettingsJumpLink extends StatelessWidget {
  const SettingsJumpLink(this.label, {required this.onTap, super.key});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => OutlinedButton(
    onPressed: onTap,
    style: OutlinedButton.styleFrom(
      minimumSize: const Size(0, 34),
      padding: const EdgeInsets.symmetric(horizontal: 11),
      foregroundColor: Apex.link,
      side: const BorderSide(color: Color(0xffb9c0c9)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
      textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w400),
    ),
    child: Text(label),
  );
}
