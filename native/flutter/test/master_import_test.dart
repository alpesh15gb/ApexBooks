import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/masters/master_csv.dart';
import 'package:apex_books/features/masters/master_import.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

const _base = '/api/companies/company/masters';

class _Pending implements PendingStore {
  Json? saved;
  @override
  Future<Json?> load(String operation) async => saved;
  @override
  Future<void> save(String operation, Json data) async => saved = data;
  @override
  Future<void> clear(String operation) async => saved = null;
}

class _ImportApi implements ApexApi {
  int commits = 0;
  int reads = 0;
  Json? receipt;
  Json? committedBody;
  Json? previewBody;
  String? failPreview;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    reads++;
    expect(path, '$_base/import-receipts/${receipt?['operation_key']}');
    return receipt;
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    expect(path, '$_base/import');
    if (body['dry_run'] == true) {
      previewBody = body;
      expect(idempotencyKey, isNull);
      return {
        'dry_run': true,
        'ready': failPreview == null ? 1 : 0,
        'duplicates': 0,
        'errors': failPreview == null
            ? []
            : [
                {'row': 2, 'message': failPreview},
              ],
      };
    }
    committedBody = body;
    commits++;
    receipt = {
      'created': 1,
      'duplicates': 0,
      'record_ids': ['saved'],
      'operation_key': idempotencyKey,
    };
    throw const ApexApiException(message: 'Response interrupted');
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async =>
      throw UnimplementedError();
}

Future<void> _show(WidgetTester tester, _ImportApi api, _Pending store) async {
  await tester.pumpWidget(
    MaterialApp(
      home: MasterImportPage(
        initialKind: 'party',
        workspace: WorkspaceContext(
          api: api,
          company: const ApexCompany(
            id: 'company',
            name: 'Shop',
            role: 'owner',
          ),
          features: const {'master_import_receipts'},
          pending: store,
          refresh: () async {},
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, String label) async {
  final target = find.text(label);
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  test(
    'Master CSV accepts exported item headings and preserves barcode text',
    () {
      final item = masterCsv(
        'Name,HSN / SAC,Barcode,Stock tracked,Item type,Sale rate,Tax treatment\r\n"Seal, small",0007,001089,Yes,Goods,245.50,Nil rated',
        'item',
      );
      expect(item.rows.single, {
        'name': 'Seal, small',
        'hsn': '0007',
        'barcode': '001089',
        'track_stock': true,
        'item_type': 'goods',
        'sale_rate': '245.50',
        'tax_treatment': 'nil_rated',
      });
      expect(
        () => masterCsv('Name,Phone,Phone\nSupplier,01,02', 'party'),
        throwsFormatException,
      );
      final contact = masterCsv(
        'Name,Phone,Address\n\n"सीमा",00104,"Street 1\nCity"',
        'party',
      );
      expect(contact.rows.single['address'], 'Street 1\nCity');
      expect(contact.lines, [3]);
    },
  );

  testWidgets(
    'Uses the original receipt to recover an interrupted CSV import after reopening',
    (tester) async {
      final api = _ImportApi();
      final store = _Pending();
      await _show(tester, api, store);
      await tester.enterText(
        find.byType(TextField),
        'Name,Type,Phone\nShop contact,customer,00135',
      );
      await _tap(tester, 'Preview import');
      expect(find.text('1 ready to import'), findsOneWidget);
      await _tap(tester, 'Import records');
      expect(find.text('Response interrupted'), findsOneWidget);
      expect(api.commits, 1);
      expect(store.saved?['key'], api.receipt?['operation_key']);
      expect(api.committedBody?['rows'], api.previewBody?['rows']);

      await tester.pumpWidget(const SizedBox());
      await _show(tester, api, store);
      await _tap(tester, 'Check receipt');
      expect(find.text('1 record imported'), findsOneWidget);
      expect(api.commits, 1);
      expect(api.reads, 1);
      expect(store.saved, isNull);
    },
  );

  testWidgets(
    'Reports physical CSV line numbers and blocks commit on server validation errors',
    (tester) async {
      final api = _ImportApi()..failPreview = 'Enter a valid GSTIN';
      await _show(tester, api, _Pending());
      await tester.enterText(
        find.byType(TextField),
        'Name,GSTIN\n\nContact,invalid',
      );
      await _tap(tester, 'Preview import');
      expect(find.text('CSV row 3: Enter a valid GSTIN'), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Import records'),
            )
            .onPressed,
        isNull,
      );
      expect(api.commits, 0);
    },
  );
}
