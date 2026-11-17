import 'package:apex_books/features/banking/banking_screen.dart';
import 'package:apex_books/features/ledger/ledger_screen.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import 'support/harness.dart';

void main() {
  testWidgets('cash and bank', (tester) async {
    await shot(tester, 'banking-bank-desktop', BankingScreen(workspace: shotWorkspace()), size: const Size(1208, 2300));
  });

  testWidgets('cash and bank phone', (tester) async {
    await shot(tester, 'banking-bank-phone', BankingScreen(workspace: shotWorkspace()), size: const Size(390, 3600));
  });

  testWidgets('transfer dialog', (tester) async {
    await shot(
      tester,
      'banking-transfer',
      BankingScreen(workspace: shotWorkspace()),
      before: (tester) async {
        await tester.ensureVisible(find.text('Record cash/bank transfer'));
        await tester.tap(find.text('Record cash/bank transfer'));
        await tester.pump(const Duration(milliseconds: 300));
      },
    );
  });

  testWidgets('ledger', (tester) async {
    await shot(tester, 'banking-ledger-desktop', LedgerScreen(workspace: shotWorkspace()), size: const Size(1208, 3000));
  });

  testWidgets('ledger phone', (tester) async {
    await shot(tester, 'banking-ledger-phone', LedgerScreen(workspace: shotWorkspace()), size: const Size(390, 4200));
  });
}
