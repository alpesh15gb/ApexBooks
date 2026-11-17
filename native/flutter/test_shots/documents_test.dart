import 'package:apex_books/features/books/books_register.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import 'support/harness.dart';



Future<void> _fill(WidgetTester tester) async {
  Future<void> type(String key, String value) async {
    final field = find.byKey(ValueKey(key));
    await tester.scrollUntilVisible(field, 150, scrollable: find.byType(Scrollable).first);
    await tester.enterText(field, value);
    await tester.pump();
  }

  final customer = find.byWidgetPredicate(
    (w) =>
        w is TextField &&
        (w.decoration?.labelText?.contains('/ description') ?? false),
  );
  await tester.enterText(customer.first, 'Corner Shop');
  await type('line-0-description', 'Counter installation');
  await type('line-0-quantity', '2');
  await type('line-0-rate', '120');
  await tester.pump();
}

void main() {
  for (final (kind, title) in [
    ('sales_invoice', 'Sales invoices'),
    ('purchase_bill', 'Purchase bills'),
    ('estimate', 'Estimates'),
    ('credit_note', 'Credit notes'),
    ('payment_in', 'Payment in'),
    ('expense', 'Expenses'),
  ]) {
    for (final (size, label) in [(desktop, 'desktop'), (phone, 'phone')]) {
      testWidgets('$kind $label', (tester) async {
        await shot(
          tester,
          'documents-$kind-new-$label',
          BooksRegister(
            workspace: shotWorkspace(),
            kind: kind,
            title: title,
            entryRequest: 1,
          ),
          size: size,
          before: kind == 'sales_invoice' || kind == 'purchase_bill'
              ? _fill
              : null,
        );
      });
    }
  }
}
