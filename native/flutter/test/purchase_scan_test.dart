import 'dart:convert';
import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/books_entry_draft.dart';
import 'package:apex_books/features/books/purchase_scan.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class _ScanApi implements ApexApi {
  Json? extractedPhoto;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    expect(path, '/api/ocr/status');
    return {'ready': true};
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    expect(path, '/api/companies/shop/ocr/purchase-draft');
    extractedPhoto = body;
    return {
      'status': 'review_required',
      'draft': {'supplier_name': 'Corner Supplies', 'items': []},
    };
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
}

class _NoPending implements PendingStore {
  @override
  Future<Json?> load(String operation) => throw UnimplementedError();
  @override
  Future<void> save(String operation, Json data) => throw UnimplementedError();
  @override
  Future<void> clear(String operation) => throw UnimplementedError();
}

void main() {
  testWidgets(
    'Android camera preview keeps photo local until extraction is chosen',
    (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      const png =
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC';
      final api = _ScanApi();
      final workspace = WorkspaceContext(
        api: api,
        company: const ApexCompany(id: 'shop', name: 'Shop', role: 'owner'),
        pending: _NoPending(),
        features: const {},
        refresh: () async {},
      );
      Json? result;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  result = await scanPurchaseBill(
                    context,
                    workspace,
                    capture: () async =>
                        (name: 'Camera photo', bytes: base64Decode(png)),
                  );
                },
                child: const Text('Open bill scanner'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Open bill scanner'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Take photo'));
      await tester.pumpAndSettle();
      expect(find.text('Camera photo'), findsOneWidget);
      expect(api.extractedPhoto, isNull);
      await tester.tap(find.text('Extract draft'));
      await tester.pumpAndSettle();
      expect(api.extractedPhoto, {
        'image_data_url': 'data:image/png;base64,$png',
      });
      expect(result?['supplier_name'], 'Corner Supplies');
    },
  );

  test('purchase scan clears the previous supplier and preserves printed prices when linking an item', () {
    final draft = BooksEntryDraft(
      const BooksEntryIntent('purchase_bill'),
      const ApexCompany(
        id: 'shop',
        name: 'Test Shop',
        role: 'owner',
        stateCode: '27',
      ),
    );
    draft.set('name', 'Old supplier');
    draft.set('party_id', 'old-supplier');
    draft.set('due_date', '2026-05-01');
    draft.applyPurchaseScan({
      'supplier_name': 'Paper Supplier',
      'supplier_gstin': '29abcde1234f1z5',
      'invoice_date': '2026-04-10',
      'invoice_number': 'PDF-42',
      'items': [
        {
          'description': 'Paper',
          'quantity': '3',
          'rate': '43.10',
          'gst_rate': '12',
          'hsn': '4802',
        },
      ],
    });
    final line = draft.lines.single;
    line.chooseItem(
      BooksRecord({
        'id': 'paper',
        'kind': 'item',
        'name': 'Catalogue Paper',
        'data': {
          'purchase_rate': '99',
          'unit': 'ream',
          'gst_rate': '18',
          'hsn': '1234',
        },
      }),
      purchase: true,
      regular: true,
    );
    expect(draft.get('name'), 'Paper Supplier');
    expect(draft.get('party_id'), isEmpty);
    expect(draft.get('due_date'), isEmpty);
    expect(draft.get('supplier_state'), '29');
    expect(draft.get('date'), '2026-04-10');
    expect(line.get('item_id'), 'paper');
    expect(line.get('unit'), 'ream');
    expect(line.get('quantity'), '3');
    expect(line.get('rate'), '43.10');
    expect(line.get('gst_rate'), '12');
    expect(line.get('hsn'), '4802');
    expect(line.get('itc_treatment'), 'pending_review');
  });
}
