import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/books_register.dart';
import 'package:apex_books/features/books/books_reports.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/harness.dart';

Widget reports({BooksReport? report}) =>
    BooksReports(workspace: shotWorkspace(), report: report, reportRequest: 1);

void main() {
  testWidgets('library', (tester) async {
    await shot(tester, 'reports-library', BooksReports(workspace: shotWorkspace()));
  });
  testWidgets('library phone', (tester) async {
    await shot(tester, 'reports-library-phone', BooksReports(workspace: shotWorkspace()), size: phone);
  });

  testWidgets('stock movements', (tester) async {
    await shot(
      tester,
      'reports-stock-movements',
      reports(report: BooksReport.stock),
      size: const Size(1440, 1000),
      before: (tester) async {
        await tester.tap(find.text('View movements').first);
        await tester.pump();
      },
    );
  });
  testWidgets('day book with entries', (tester) async {
    await shot(
      tester,
      'reports-day-book-entries',
      reports(report: BooksReport.dayBook),
      size: const Size(1440, 1000),
      before: (tester) async {
        for (var i = 0; i < 7; i++) {
          await tester.tap(find.bySemanticsLabel('Previous day'));
          await tester.pump();
        }
      },
    );
  });
  testWidgets('day book with entries phone', (tester) async {
    await shot(
      tester,
      'reports-day-book-entries-phone',
      reports(report: BooksReport.dayBook),
      size: phone,
      before: (tester) async {
        for (var i = 0; i < 7; i++) {
          await tester.tap(find.byIcon(Icons.chevron_left_rounded));
          await tester.pump();
        }
      },
    );
  });

  for (final report in BooksReport.values) {
    final slug = report.title.toLowerCase().replaceAll(RegExp('[^a-z0-9]+'), '-');
    testWidgets('report $slug', (tester) async {
      await shot(tester, 'reports-$slug', reports(report: report), size: const Size(1440, 1000));
    });
    testWidgets('report $slug phone', (tester) async {
      await shot(tester, 'reports-$slug-phone', reports(report: report), size: phone);
    });
  }

  for (final (kind, title) in [
    ('sales_invoice', 'Sales invoices'),
    ('purchase_bill', 'Purchase bills'),
    ('payment_in', 'Payments in'),
    ('expense', 'Expenses'),
    ('estimate', 'Estimates'),
    ('purchase_order', 'Purchase orders'),
  ]) {
    testWidgets('register $kind', (tester) async {
      await shot(
        tester,
        'reports-reg-$kind',
        BooksRegister(workspace: shotWorkspace(), kind: kind, title: title),
        size: const Size(1440, 1000),
      );
    });
    testWidgets('register $kind phone', (tester) async {
      await shot(tester, 'reports-reg-$kind-phone', BooksRegister(workspace: shotWorkspace(), kind: kind, title: title), size: phone);
    });
  }
}
