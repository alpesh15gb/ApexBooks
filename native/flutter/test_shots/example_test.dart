import 'package:apex_books/features/home/home_screen.dart';
import 'package:apex_books/features/masters/master_editor.dart';
import 'package:apex_books/features/masters/masters_screen.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/harness.dart';

void main() {
  testWidgets('dashboard', (tester) async {
    await shot(
      tester,
      'example-dashboard',
      HomeScreen(
        workspace: shotWorkspace(),
        revision: 0,
        openCheckout: () {},
        openBank: (_) {},
        openReport: (_, _) {},
        openRegister: (_, _) {},
        openPage: (_) {},
        newEntry: (_) {},
        verifyPassword: (_) async {},
      ),
    );
  });

  testWidgets('parties phone', (tester) async {
    await shot(
      tester,
      'example-parties-phone',
      MastersScreen(workspace: shotWorkspace(), group: MasterGroup.customer),
      size: phone,
    );
  });
}
