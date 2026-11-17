import 'package:apex_books/features/masters/masters_screen.dart';
import 'package:apex_books/features/masters/master_editor.dart';
import 'package:apex_books/features/masters/party_statement.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import 'support/harness.dart';

Future<List<Json>> _rows(WorkspaceContext workspace, String kind) async {
  final all = await workspace.api.get('${workspace.path}/records', query: {'kind': kind, 'compact': 'true'});
  return [for (final row in all as List) Map<String, dynamic>.from(row as Map)];
}

void main() {
  for (final entry in {'desktop': desktop, 'phone': phone}.entries) {
    final size = entry.value;
    final tag = entry.key;
    testWidgets('parties $tag', (tester) async {
      await shot(tester, 'masters-parties-$tag',
          MastersScreen(workspace: shotWorkspace(), group: MasterGroup.customer), size: size);
    });
    testWidgets('items $tag', (tester) async {
      await shot(tester, 'masters-items-$tag',
          MastersScreen(workspace: shotWorkspace(), group: MasterGroup.item), size: size);
    });
    testWidgets('statement $tag', (tester) async {
      final workspace = shotWorkspace();
      final party = (await tester.runAsync(() => _rows(workspace, 'party')))!.first;
      await shot(tester, 'masters-statement-$tag', PartyStatementPage(workspace: workspace, party: party),
          size: size);
    });
    testWidgets('item edit $tag', (tester) async {
      final workspace = shotWorkspace();
      final item = (await tester.runAsync(() => _rows(workspace, 'item')))!.first;
      await shot(
        tester,
        'masters-itemedit-$tag',
        Builder(
          builder: (context) => Center(
            child: TextButton(
              onPressed: () => showDialog<void>(
                context: context,
                builder: (_) => MasterEditorPage(
                  group: MasterGroup.item,
                  workspace: workspace,
                  record: item,
                  onSave: (_, _) async {},
                  canWrite: true,
                  canArchive: true,
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
        size: size,
        before: (tester) async {
          await tester.tap(find.text('open'));
          await tester.pump(const Duration(milliseconds: 300));
        },
      );
    });
  }
}
