import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';

/// Text shown to the user for a failed settings request.
String settingsFailure(Object failure) => switch (failure) {
  ApexApiException() => failure.message,
  FormatException() => failure.message,
  _ => 'The operation could not be completed.',
};

const _labelStyle = TextStyle(
  fontFamily: Apex.body,
  fontSize: 13,
  fontWeight: FontWeight.w500,
  color: Apex.label,
);

/// A web-style form field: the label above, then the control.
class SettingsLabeled extends StatelessWidget {
  const SettingsLabeled({
    required this.label,
    required this.child,
    this.note,
    super.key,
  });

  final String label;
  final Widget child;
  final String? note;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(label, style: _labelStyle),
      const SizedBox(height: 7),
      child,
      if (note != null) ...[
        const SizedBox(height: 5),
        Text(note!, style: Apex.small),
      ],
    ],
  );
}

/// Single- or multi-line text input with the label above it.
class SettingsTextField extends StatelessWidget {
  const SettingsTextField({
    required this.label,
    required this.controller,
    this.maxLength,
    this.maxLines = 1,
    this.enabled = true,
    this.obscure = false,
    this.keyboardType,
    this.hint,
    this.note,
    this.onChanged,
    this.onSubmitted,
    super.key,
  });

  final String label;
  final TextEditingController controller;
  final int? maxLength;
  final int maxLines;
  final bool enabled;
  final bool obscure;
  final TextInputType? keyboardType;
  final String? hint;
  final String? note;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) => SettingsLabeled(
    label: label,
    note: note,
    child: Semantics(
      label: label,
      textField: true,
      child: TextField(
        controller: controller,
        enabled: enabled,
        maxLength: maxLength,
        maxLines: obscure ? 1 : maxLines,
        minLines: maxLines > 1 ? maxLines : null,
        obscureText: obscure,
        enableSuggestions: !obscure,
        autocorrect: !obscure,
        keyboardType: maxLines > 1 ? TextInputType.multiline : keyboardType,
        maxLengthEnforcement: MaxLengthEnforcement.enforced,
        onChanged: onChanged,
        onSubmitted: onSubmitted,
        style: const TextStyle(fontSize: 13),
        decoration: InputDecoration(hintText: hint, counterText: ''),
      ),
    ),
  );
}

/// Drop-down with the label above it.
class SettingsSelect extends StatelessWidget {
  const SettingsSelect({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
    super.key,
  });

  final String label;
  final String value;
  final List<(String, String)> options;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) => SettingsLabeled(
    label: label,
    child: Semantics(
      label: label,
      child: DropdownButtonFormField<String>(
        key: ValueKey('$label:$value'),
        isExpanded: true,
        initialValue: options.any((entry) => entry.$1 == value) ? value : null,
        style: const TextStyle(
          fontFamily: Apex.body,
          fontSize: 13,
          color: Apex.ink,
        ),
        items: [
          for (final (key, text) in options)
            DropdownMenuItem(value: key, child: Text(text)),
        ],
        onChanged: onChanged == null
            ? null
            : (next) {
                if (next != null) onChanged!(next);
              },
      ),
    ),
  );
}

/// One cell of [SettingsGrid]; [full] spans both columns.
class SettingsCell {
  const SettingsCell(this.child, {this.full = false});
  final Widget child;
  final bool full;
}

/// The web `.form-grid`: two columns on wide layouts, one on phones.
class SettingsGrid extends StatelessWidget {
  const SettingsGrid(this.cells, {this.gap = 16, super.key});

  final List<SettingsCell> cells;
  final double gap;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, limits) {
      final two = limits.maxWidth >= 560;
      final half = (limits.maxWidth - gap) / 2;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final cell in cells)
            SizedBox(
              width: two && !cell.full ? half : limits.maxWidth,
              child: cell.child,
            ),
        ],
      );
    },
  );
}

/// Status line below a form: red for a failure, plain for a confirmation.
class SettingsMessage extends StatelessWidget {
  const SettingsMessage(this.text, {this.error = false, super.key});

  final String text;
  final bool error;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: Apex.body,
          fontSize: 13,
          height: 1.5,
          color: error ? const Color(0xffb3261e) : Apex.inkSoft,
        ),
      ),
    ),
  );
}

/// The web `.info-box`: a tinted notice that can hold a title and actions.
class SettingsInfoBox extends StatelessWidget {
  const SettingsInfoBox({required this.children, super.key});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 12, bottom: 4),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xfffff7eb),
        border: Border.all(color: const Color(0xfff2dec3)),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      ),
    ),
  );
}

/// A nested white panel with a rule, like the web `section.panel.settings-panel`.
class SettingsPanelBox extends StatelessWidget {
  const SettingsPanelBox({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(22),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: Apex.line),
      borderRadius: BorderRadius.circular(7),
    ),
    child: child,
  );
}

/// A small text-style action, like the web `button.link`.
class SettingsLinkButton extends StatelessWidget {
  const SettingsLinkButton(this.label, {required this.onPressed, super.key});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => TextButton(
    onPressed: onPressed,
    style: TextButton.styleFrom(
      foregroundColor: Apex.link,
      padding: const EdgeInsets.symmetric(horizontal: 6),
      minimumSize: const Size(0, 32),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      textStyle: const TextStyle(fontFamily: Apex.body, fontSize: 12),
    ),
    child: Text(label),
  );
}

/// Primary and secondary buttons that never grow past their label.
class SettingsButton extends StatelessWidget {
  const SettingsButton(
    this.label, {
    required this.onPressed,
    this.primary = false,
    this.icon,
    super.key,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool primary;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final text = Text(label);
    final glyph = icon == null ? null : Icon(icon, size: 16);
    return Align(
      alignment: Alignment.centerLeft,
      widthFactor: 1,
      heightFactor: 1,
      child: primary
          ? (glyph == null
                ? FilledButton(onPressed: onPressed, child: text)
                : FilledButton.icon(
                    onPressed: onPressed,
                    icon: glyph,
                    label: text,
                  ))
          : (glyph == null
                ? OutlinedButton(onPressed: onPressed, child: text)
                : OutlinedButton.icon(
                    onPressed: onPressed,
                    icon: glyph,
                    label: text,
                  )),
    );
  }
}
