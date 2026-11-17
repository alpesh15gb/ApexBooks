import 'package:material_ui/material_ui.dart';

import '../../ui/apex_theme.dart';
import 'inventory_models.dart';

/// The web app's `info-box`: a tinted notice with optional action.
class InventoryNotice extends StatelessWidget {
  const InventoryNotice({required this.text, this.action, super.key});

  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: DecoratedBox(
      decoration: BoxDecoration(
        color: Apex.mintSoft,
        borderRadius: BorderRadius.circular(Apex.radiusControl),
        border: Border.all(color: Apex.mintLine),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              style: const TextStyle(
                fontSize: 13,
                height: 1.5,
                color: Apex.inkSoft,
              ),
            ),
            ?action,
          ],
        ),
      ),
    ),
  );
}

class InventoryEmpty extends StatelessWidget {
  const InventoryEmpty({required this.text, super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(32),
    child: Center(
      child: Text(text, textAlign: TextAlign.center, style: Apex.note),
    ),
  );
}

/// Search box for the stock register. Unlike the shared search field it
/// reports submit, which the register uses to open a scanned barcode.
class InventorySearchField extends StatelessWidget {
  const InventorySearchField({
    required this.controller,
    required this.hint,
    required this.onChanged,
    this.onSubmitted,
    this.width = 320,
    super.key,
  });

  final TextEditingController controller;
  final String hint;
  final ValueChanged<String> onChanged;
  final ValueChanged<String>? onSubmitted;
  final double? width;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: TextField(
      controller: controller,
      onChanged: onChanged,
      onSubmitted: onSubmitted,
      textInputAction: TextInputAction.search,
      style: const TextStyle(fontSize: 13),
      decoration: InputDecoration(
        hintText: hint,
        prefixIcon: const Icon(
          Icons.search_rounded,
          size: 18,
          color: Apex.muted,
        ),
        suffixIcon: ListenableBuilder(
          listenable: controller,
          builder: (context, _) => controller.text.isEmpty
              ? const SizedBox.shrink()
              : IconButton(
                  tooltip: 'Clear search',
                  icon: const Icon(Icons.close_rounded, size: 17),
                  onPressed: () {
                    controller.clear();
                    onChanged('');
                  },
                ),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 16,
        ),
      ),
    ),
  );
}

/// A dialog frame matching the web app's `.modal`: heading, one-line
/// description, close button, then the form and a right-aligned action row.
class InventoryModal extends StatelessWidget {
  const InventoryModal({
    required this.title,
    required this.child,
    required this.actions,
    this.subtitle,
    this.width = 520,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget child;
  final List<Widget> actions;
  final double width;

  @override
  Widget build(BuildContext context) => Dialog(
    backgroundColor: Colors.white,
    surfaceTintColor: Colors.transparent,
    insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(Apex.radiusCard),
    ),
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: width),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 22, 24, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: Apex.panelTitle),
                      if (subtitle != null) ...[
                        const SizedBox(height: 4),
                        Text(subtitle!, style: Apex.note),
                      ],
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Close',
                  onPressed: () => Navigator.maybePop(context),
                  icon: const Icon(Icons.close_rounded, size: 18),
                ),
              ],
            ),
            const SizedBox(height: 16),
            child,
            const SizedBox(height: 18),
            Wrap(
              alignment: WrapAlignment.end,
              spacing: 8,
              runSpacing: 8,
              children: actions,
            ),
          ],
        ),
      ),
    ),
  );
}

void showInventoryMessage(BuildContext context, String text) =>
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

String inventorySavedMessage(InventoryJson result, String kind) {
  if (kind == 'count') return 'Stock count recorded.';
  if (kind == 'opening') return 'Opening stock posted.';
  if (kind == 'adjustment') return 'Stock adjustment posted.';
  final number = inventoryText(result['number']);
  return result['posted'] == false
      ? 'Supplier bill $number was cancelled.'
      : 'Supplier bill $number posted.';
}

String inventoryOperationName(String kind) => switch (kind) {
  'receipt' => 'Supplier bill',
  'opening' => 'Opening stock',
  'adjustment' => 'Stock adjustment',
  _ => 'Stock count',
};

/// A table for use inside dialogs, where [ApexTable]'s LayoutBuilder cannot be measured.
/// Shows [card] rows instead of columns when the screen is narrower than [breakpoint].
class InventoryDialogTable extends StatelessWidget {
  const InventoryDialogTable({
    required this.headers,
    required this.flex,
    required this.cell,
    required this.rowCount,
    required this.card,
    this.breakpoint = 720,
    super.key,
  });

  final List<String> headers;
  final List<double> flex;
  final int rowCount;
  final Widget Function(int row, int column) cell;
  final Widget Function(int row) card;
  final double breakpoint;

  @override
  Widget build(BuildContext context) {
    final narrow = MediaQuery.sizeOf(context).width < breakpoint;
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.all(color: Apex.line),
        borderRadius: BorderRadius.circular(Apex.radiusControl),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!narrow)
            Container(
              color: Apex.tableHead,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                spacing: 12,
                children: [
                  for (final (i, title) in headers.indexed)
                    Expanded(
                      flex: (flex[i] * 100).round(),
                      child: Text(title.toUpperCase(), style: Apex.tableHeader),
                    ),
                ],
              ),
            ),
          for (var row = 0; row < rowCount; row++) ...[
            if (row > 0 || !narrow) const Divider(height: 1, color: Apex.lineSoft),
            Padding(
              padding: const EdgeInsets.all(12),
              child: narrow
                  ? card(row)
                  : Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      spacing: 12,
                      children: [
                        for (var column = 0; column < headers.length; column++)
                          Expanded(
                            flex: (flex[column] * 100).round(),
                            child: cell(row, column),
                          ),
                      ],
                    ),
            ),
          ],
        ],
      ),
    );
  }
}
