import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';

/// One cell of a [MasterFormGrid]; [full] spans both columns.
class MasterFormCell {
  const MasterFormCell(this.child, {this.full = false});
  final Widget child;
  final bool full;
}

/// The web modal's form grid: two columns on desktop, one on phones.
class MasterFormGrid extends StatelessWidget {
  const MasterFormGrid(this.cells, {super.key});
  final List<MasterFormCell> cells;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      const gap = 16.0;
      final single = limits.maxWidth < 520;
      final half = (limits.maxWidth - gap) / 2;
      return Wrap(
        spacing: gap,
        runSpacing: 16,
        children: [
          for (final cell in cells)
            SizedBox(width: cell.full || single ? limits.maxWidth : half, child: cell.child),
        ],
      );
    },
  );
}

/// A bordered group with a legend, like the web form's fieldsets.
class MasterFormSection extends StatelessWidget {
  const MasterFormSection({required this.title, required this.child, this.icon, super.key});
  final String title;
  final IconData? icon;
  final Widget child;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: Apex.tint,
      borderRadius: BorderRadius.circular(10),
      border: Border.all(color: Apex.line),
    ),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              if (icon != null) ...[Icon(icon, size: 15, color: Apex.greenText), const SizedBox(width: 6)],
              Text(title, style: Apex.strong),
            ],
          ),
          const SizedBox(height: 12),
          child,
        ],
      ),
    ),
  );
}

/// Small grey helper text under a field or section.
class MasterHint extends StatelessWidget {
  const MasterHint(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 6),
    child: Text(text, style: const TextStyle(fontSize: 12, height: 1.5, color: Apex.muted)),
  );
}
