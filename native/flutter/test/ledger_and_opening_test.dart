import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/ledger/journal_editor.dart';
import 'package:apex_books/features/settings/opening_party_panel.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class _Pending implements PendingStore {
  Json? value;

  @override
  Future<void> clear(String operation) async => value = null;

  @override
  Future<Json?> load(String operation) async => value;

  @override
  Future<void> save(String operation, Json data) async => value = data;
}

class _Api implements ApexApi {
  final calls = <({String path, Json body, String? key})>[];
  Json? journal;
  int lookups = 0;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    expect(path, '/api/companies/shop/journals');
    expect(query, {'reference': 'QA-001'});
    lookups++;
    return [journal];
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    calls.add((path: path, body: body, key: idempotencyKey));
    if (path.endsWith('/journals')) {
      journal = {...body, 'id': 'journal'};
    } else if (calls.length > 1) {
      return {'id': 'opening'};
    }
    throw const ApexApiException(message: 'Interrupted response');
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
}

WorkspaceContext _workspace(_Api api, _Pending pending) => WorkspaceContext(
  api: api,
  company: const ApexCompany(id: 'shop', name: 'Test Shop', role: 'owner'),
  pending: pending,
  features: const {},
  refresh: () async {},
);

Finder _field(String label) => find.byWidgetPredicate(
  (widget) => widget is TextField && widget.decoration?.labelText == label,
);

void main() {
  testWidgets(
    'journal validates equal paise and checks a committed reference after a lost response',
    (tester) async {
      final api = _Api();
      final workspace = _workspace(api, _Pending());
      bool? result;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  result = await showDialog<bool>(
                    context: context,
                    builder: (_) => JournalEditor(
                      workspace: workspace,
                      accounts: const [
                        {'id': 'cash', 'code': '1000', 'name': 'Cash'},
                        {'id': 'income', 'code': '4000', 'name': 'Income'},
                      ],
                    ),
                  );
                },
                child: const Text('Open editor'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open editor'));
      await tester.pumpAndSettle();
      await tester.enterText(_field('Reference'), 'QA-001');
      await tester.tap(find.text('Post journal'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Total debits and credits must match'),
        findsOneWidget,
      );
      expect(api.calls, isEmpty);

      Future<void> selectAccount(String label, String option) async {
        final dropdown = find.text(label);
        await tester.ensureVisible(dropdown);
        await tester.tap(dropdown);
        await tester.pumpAndSettle();
        await tester.tap(find.text(option).last);
        await tester.pumpAndSettle();
      }

      await selectAccount('Account 1', '1000 · Cash');
      await selectAccount('Account 2', '4000 · Income');
      await tester.enterText(_field('Amount (₹)').first, '0.19');
      await tester.enterText(_field('Amount (₹)').last, '0.19');
      await tester.tap(find.text('Post journal'));
      await tester.pumpAndSettle();
      expect(api.calls.single.body['lines'], [
        {'account_id': 'cash', 'debit': '0.19', 'credit': '0'},
        {'account_id': 'income', 'debit': '0', 'credit': '0.19'},
      ]);
      expect(api.lookups, 1);
      expect(result, true);
    },
  );

  testWidgets('opening party balance can replay the stored key and body', (
    tester,
  ) async {
    final pending = _Pending();
    final body = <String, dynamic>{
      'kind': 'opening',
      'date': '2026-04-01',
      'amount': '125.70',
      'data': {'balance_kind': 'receivable', 'party_id': 'party'},
    };
    pending.value = {
      'key': 'opening-test',
      'party': 'Corner Shop',
      'body': body,
    };
    final api = _Api();
    final workspace = _workspace(api, pending);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: OpeningPartyPanel(workspace: workspace)),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Corner Shop'), findsOneWidget);
    for (var attempt = 0; attempt < 2; attempt++) {
      await tester.tap(find.text('Retry original opening balance'));
      await tester.pumpAndSettle();
    }
    expect(api.calls.length, 2);
    expect(api.calls.first.path, '/api/companies/shop/opening-balances');
    expect(api.calls.last.key, 'opening-test');
    expect(api.calls.last.body, body);
    expect(pending.value, isNull);
    expect(find.text('Opening balance posted to the ledger.'), findsOneWidget);
  });
}
