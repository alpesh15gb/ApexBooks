import 'dart:convert';

import 'package:apex_books/app.dart';
import 'package:apex_books/core/session.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:material_ui/material_ui.dart';

class _Pending implements PendingStore {
  @override
  Future<void> clear(String operation) async {}

  @override
  Future<Json?> load(String operation) async => null;

  @override
  Future<void> save(String operation, Json data) async {}
}

Future<ApexSession> _session({String role = 'owner'}) async {
  final subject = base64Url.encode(utf8.encode('{"sub":"qa-user"}'));
  final session = ApexSession(
    origin: Uri.parse('https://apex.invalid'),
    pendingFactory: (_, _, _) => _Pending(),
    client: MockClient((request) async {
      final path = request.url.path;
      final Object body = switch (path) {
        '/api/auth/login' => {'token': 'qa.$subject.signature'},
        '/api/capabilities' => {'supported_features': <String>[]},
        '/api/companies' => [
          {
            'id': 'shop',
            'name': 'Layout Store',
            'role': role,
            'tax_mode': 'regular',
          },
        ],
        _ when path.endsWith('/records') => <Object>[],
        _ => <String, dynamic>{},
      };
      return http.Response(jsonEncode(body), 200);
    }),
  );
  await session.signIn('layout@example.invalid', 'Synthetic layout test');
  return session;
}

void main() {
  testWidgets(
    'desktop toolbar finds workspaces and mobile retains the active destination',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await tester.binding.setSurfaceSize(const Size(1280, 850));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final session = await _session();
      addTearDown(session.dispose);
      await tester.pumpWidget(ApexApp(session: session));
      await tester.pumpAndSettle();
      // Same sections as the web app's sidebar.
      for (final section in ['TRANSACTIONS', 'ACCOUNTING', 'BUSINESS TOOLS']) {
        expect(find.text(section), findsOneWidget);
      }
      expect(find.text('Sales'), findsOneWidget);
      expect(find.text('Purchases'), findsOneWidget);
      await tester.tap(find.text('Sales'));
      await tester.pumpAndSettle();
      expect(find.text('Sales invoices'), findsOneWidget);
      expect(find.text('Credit notes'), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
      expect(find.text('Owner · GST registered'), findsOneWidget);

      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.keyK);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pumpAndSettle();
      expect(find.byType(Dialog), findsOneWidget);
      await tester.enterText(find.byType(TextField), 'GST');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(find.text('Find a report, e.g. sales, GST or stock'), findsOneWidget);

      await tester.binding.setSurfaceSize(const Size(390, 844));
      await tester.pumpAndSettle();
      final nav = tester.widget<NavigationBar>(find.byType(NavigationBar));
      expect(nav.selectedIndex, 4);
      expect(find.text('Find a report, e.g. sales, GST or stock'), findsOneWidget);
      expect(find.text('TRANSACTIONS'), findsNothing);
      semantics.dispose();
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('desktop shortcut opens the existing entry chooser', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1280, 850));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final session = await _session();
    addTearDown(session.dispose);
    await tester.pumpWidget(ApexApp(session: session));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(Dialog), findsOneWidget);
    expect(find.text('Sales invoice'), findsOneWidget);
    await tester.tap(find.text('Sales invoice'));
    await tester.pumpAndSettle();
    expect(find.text('New sales invoice'), findsOneWidget);
  });
}
