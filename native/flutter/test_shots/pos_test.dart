import 'package:apex_books/features/pos/pos_screen.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/harness.dart';

Widget _pos() => PosScreen(workspace: shotWorkspace());

Future<void> _tapText(WidgetTester tester, String text, {bool last = false}) async {
  final all = find.textContaining(text, findRichText: true);
  final finder = last ? all.last : all.first;
  await tester.ensureVisible(finder);
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
}

Future<void> _fillCart(WidgetTester tester) async {
  final tiles = find.byWidgetPredicate(
    (widget) => widget.key is ValueKey && '${(widget.key as ValueKey).value}'.startsWith('product-'),
  );
  await tester.tap(tiles.at(0));
  await tester.pump(const Duration(milliseconds: 300));
  await tester.tap(tiles.at(1));
  await tester.pump(const Duration(milliseconds: 600));
}

Future<void> _split(WidgetTester tester) async {
  await _fillCart(tester);
  await _tapText(tester, 'Price and discount');
  await _tapText(tester, 'Customer and billing');
  await tester.tap(find.text('Cash').first);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Cash + bank / UPI / card').last);
  await tester.pumpAndSettle();
}

const tallDesktop = Size(1208, 1500);
const tallPhone = Size(390, 2300);

void main() {
  testWidgets('checkout empty', (tester) async {
    await shot(tester, 'pos-checkout-empty', _pos());
  });

  testWidgets('checkout split desktop', (tester) async {
    await shot(tester, 'pos-checkout-split', _pos(), size: tallDesktop, before: _split);
  });

  testWidgets('checkout split phone', (tester) async {
    await shot(tester, 'pos-checkout-split-phone', _pos(), size: tallPhone, before: _split);
  });

  testWidgets('held sales phone', (tester) async {
    await shot(tester, 'pos-held-phone', _pos(), size: tallPhone, before: (t) async {
      await _fillCart(t);
      await _tapText(t, 'Hold sale');
    });
  });

  testWidgets('receipts desktop', (tester) async {
    await shot(tester, 'pos-receipts', _pos(), size: tallDesktop, before: (t) async => _tapText(t, 'Receipts'));
  });

  testWidgets('receipts phone', (tester) async {
    await shot(tester, 'pos-receipts-phone', _pos(), size: tallPhone, before: (t) async => _tapText(t, 'Receipts'));
  });

  testWidgets('register desktop', (tester) async {
    await shot(tester, 'pos-register', _pos(), size: tallDesktop, before: (t) async {
      await _tapText(t, 'Register');
      await _tapText(t, 'Daily totals and CSV export');
    });
  });

  testWidgets('register phone', (tester) async {
    await shot(tester, 'pos-register-phone', _pos(), size: tallPhone, before: (t) async {
      await _tapText(t, 'Register');
      await _tapText(t, 'Daily totals and CSV export');
    });
  });

  testWidgets('return desktop', (tester) async {
    await shot(tester, 'pos-return', _pos(), size: tallDesktop, before: (t) async {
      await _tapText(t, 'Receipts');
      await _tapText(t, 'Start return');
    });
  });
}
