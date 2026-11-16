import 'dart:convert';
import 'dart:typed_data';

import 'package:apex_books/core/apex_files.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/settings/vyapar_panel.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  test('saved import carries the exact source digest and scope without backup bytes', () {
    final source = _file([1, 2, 3]);
    final request = VyaparRequest.fromFile(VyaparScope.archive, source);
    expect(request.payload(source, commit: false), {
      'backup_base64': base64Encode(source.bytes),
      'digest': '',
    });
    final pending = VyaparRequest.fromJson(request.toJson());
    expect(pending.scope, VyaparScope.archive);
    expect(pending.payload(source, commit: true)['digest'], request.digest);
    expect(pending.toJson().containsKey('backup_base64'), isFalse);
    expect(
      () => pending.payload(_file([1, 2, 4]), commit: true),
      throwsFormatException,
    );
  });

  testWidgets(
    'review gates full migration and persists recovery before sending exact digest',
    (tester) async {
      final file = _file([1, 2, 3]);
      final request = VyaparRequest.fromFile(VyaparScope.posting, file);
      final pending = _Pending();
      var committed = 0;
      final api = _Api((path, body) async {
        expect(path, startsWith('/api/companies/shop/imports/vyapar-posting/'));
        expect(body['backup_base64'], base64Encode(file.bytes));
        if (path.endsWith('/preview')) {
          expect(body['digest'], '');
          return {
            'digest': request.digest,
            'ready': true,
            'errors': [],
            'company_name': 'Source shop',
          };
        }
        committed++;
        expect(body['digest'], request.digest);
        expect(pending.value, request.toJson());
        return {
          'digest': request.digest,
          'imported': true,
          'reconciliation': [
            {'check': 'Stock', 'expected': 2, 'actual': 2, 'passed': true},
          ],
        };
      });
      await tester.pumpWidget(
        _host(
          VyaparPanel(
            workspace: _workspace(api, pending),
            pickFile: (extensions, max) async => file,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Choose .vyb backup'));
      await tester.pumpAndSettle();
      final post = find.widgetWithText(
        FilledButton,
        'Post and reconcile migration',
      );
      expect(tester.widget<FilledButton>(post).onPressed, isNull);
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pumpAndSettle();
      await tester.tap(post);
      await tester.pumpAndSettle();
      expect(committed, 1);
      expect(pending.value, isNull);
      expect(find.text('Migration posted and reconciled.'), findsOneWidget);
    },
  );

  testWidgets(
    'recovery requires the original file and cannot switch import scope',
    (tester) async {
      final original = _file([8, 1, 9]);
      final pending = _Pending()
        ..value = VyaparRequest.fromFile(
          VyaparScope.archive,
          original,
        ).toJson();
      var current = _file([3, 7, 1]);
      var commits = 0;
      final api = _Api((path, body) async {
        commits++;
        expect(path, '/api/companies/shop/imports/vyapar/commit');
        return {'digest': body['digest'], 'already_imported': true};
      });
      await tester.pumpWidget(
        _host(
          VyaparPanel(
            workspace: _workspace(api, pending),
            pickFile: (extensions, max) async => current,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(DropdownButtonFormField<VyaparScope>), findsNothing);
      final retry = find.text('Choose original backup and retry');
      await tester.tap(retry);
      await tester.pumpAndSettle();
      expect(commits, 0);
      expect(
        find.text('Choose the exact backup used for the original import.'),
        findsOneWidget,
      );
      current = original;
      await tester.tap(retry);
      await tester.pumpAndSettle();
      expect(commits, 1);
      expect(pending.value, isNull);
      expect(
        find.text('This exact backup is already imported.'),
        findsOneWidget,
      );
    },
  );
}

ApexPickedFile _file(List<int> bytes) =>
    (name: 'synthetic.vyb', bytes: Uint8List.fromList(bytes));
Widget _host(Widget child) => MaterialApp(
  home: Scaffold(body: SingleChildScrollView(child: child)),
);
WorkspaceContext _workspace(ApexApi api, _Pending pending) => WorkspaceContext(
  api: api,
  company: const ApexCompany(id: 'shop', name: 'Destination', role: 'owner'),
  pending: pending,
  features: const {},
  refresh: () async {},
);

class _Pending implements PendingStore {
  Json? value;
  @override
  Future<void> clear(String key) async => value = null;
  @override
  Future<Json?> load(String key) async => value;
  @override
  Future<void> save(String key, Json data) async => value = data;
}

class _Api implements ApexApi {
  _Api(this.onPost);
  final Future<dynamic> Function(String, Json) onPost;
  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => onPost(path, body);
  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
}
