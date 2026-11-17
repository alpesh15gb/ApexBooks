import 'dart:convert';

import 'package:apex_books/core/session.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/settings/settings_screen.dart';
import 'dart:ui' show Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'support/harness.dart';

class _Pending implements PendingStore {
  @override
  Future<void> clear(String operation) async {}
  @override
  Future<Json?> load(String operation) async => null;
  @override
  Future<void> save(String operation, Json data) async {}
}

Future<ApexSession> _session() async {
  final subject = base64Url.encode(utf8.encode('{"sub":"shot-user"}'));
  final session = ApexSession(
    origin: Uri.parse('https://apex.invalid'),
    pendingFactory: (_, _, _) => _Pending(),
    client: MockClient((request) async {
      final path = request.url.path;
      final Object body = switch (path) {
        '/api/auth/login' => {'token': 'qa.$subject.signature'},
        '/api/auth/recovery-codes/status' => {'remaining': 8},
        '/api/companies' => <Object>[],
        '/api/capabilities' => {'supported_features': <String>[]},
        _ => <String, dynamic>{},
      };
      return http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});
    }),
  );
  await session.signIn('shot@example.invalid', 'Synthetic shot test');
  return session;
}

const _tabs = {
  'company': 'Company',
  'documents': 'Documents & branding',
  'accounting': 'Accounting',
  'data': 'Data & migration',
  'access': 'People & access',
  'security': 'Account security',
  'inventory': 'Stock & modules',
  'commerce': 'Ecommerce',
};

void main() {
  for (final entry in _tabs.entries) {
    for (final size in [(desktop, 'desktop'), (phone, 'phone')]) {
      testWidgets('${entry.key} ${size.$2}', (tester) async {
        final session = await _session();
        addTearDown(session.dispose);
        await shot(
          tester,
          'settings-${entry.key}-${size.$2}',
          SettingsScreen(workspace: shotWorkspace(), session: session),
          size: size.$2 == 'desktop' ? const Size(1208, 2600) : const Size(390, 3200),
          before: (tester) async {
            final target = find.text(entry.value).first;
            await tester.ensureVisible(target);
            await tester.tap(target, warnIfMissed: false);
            await tester.pump(const Duration(milliseconds: 200));
            await tester.runAsync(
              () => Future<void>.delayed(const Duration(milliseconds: 100)),
            );
            await tester.pump(const Duration(milliseconds: 200));
          },
        );
      });
    }
  }
}
