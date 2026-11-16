import 'dart:convert';
import 'dart:typed_data';

import 'package:apex_books/core/pdf_output.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_attachments.dart';
import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/books_document_output.dart';
import 'package:apex_books/features/books/books_entry_posting.dart';
import 'package:apex_books/features/books/books_recurring.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  testWidgets('PDF save and print load the same exact server document', (
    tester,
  ) async {
    final pdf = Uint8List.fromList(ascii.encode('%PDF-1.4\n'));
    final deliveries = <String>[];
    final api = _Io(
      loadBytes: (path) async {
        expect(path, '/api/companies/shop/documents/doc-1.pdf');
        deliveries.add(path);
        return pdf;
      },
    );
    final printer = _Printer();
    final savedNames = <String>[];
    await tester.pumpWidget(
      _host(
        BooksDocumentOutput(
          workspace: _workspace(api),
          record: _bill,
          printer: printer,
          saveFile: (name, bytes, type) async {
            expect(bytes, pdf);
            expect(type, 'application/pdf');
            savedNames.add(name);
            return true;
          },
        ),
      ),
    );
    await tester.tap(find.text('Save PDF'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Print document'));
    await tester.pumpAndSettle();
    expect(savedNames.single, 'apex-BILL-0001.pdf');
    expect(printer.document?.bytes, pdf);
    expect(deliveries, hasLength(2));
    expect(
      canOutputBooksDocument(BooksRecord({..._bill.json, 'cancelled': true})),
      isFalse,
    );
  });

  test('attachment retry metadata verifies exact document and digest without retaining file bytes', () {
    final digest = sha256.convert([1, 2, 3]).toString();
    final command = BooksAttachmentCommand.create({
      'type': 'upload',
      'filename': 'Receipt.pdf',
      'sha256': digest,
      'media_type': 'application/pdf',
    });
    final restored = BooksAttachmentCommand.fromJson(command.toJson());
    expect(restored.key, command.key);
    expect(restored.values.containsKey('bytes'), isFalse);
    expect(
      restored.confirms({
        'id': 'a',
        'record_id': 'doc-1',
        'sha256': digest,
        'media_type': 'application/pdf',
      }, 'doc-1'),
      isTrue,
    );
    expect(
      restored.confirms({
        'id': 'a',
        'record_id': 'other',
        'sha256': digest,
        'media_type': 'application/pdf',
      }, 'doc-1'),
      isFalse,
    );
    expect(booksAttachmentType('bill.JPEG'), 'image/jpeg');
    expect(booksAttachmentType('bill.exe'), isNull);
  });

  testWidgets(
    'viewer can save verified retained evidence without upload permissions',
    (tester) async {
      final content = Uint8List.fromList(ascii.encode('%PDF-1.6\n'));
      final receipt = <String, dynamic>{
        'id': 'evidence',
        'record_id': 'doc-1',
        'filename': 'Supplier.pdf',
        'media_type': 'application/pdf',
        'sha256': sha256.convert(content).toString(),
        'version': 0,
        'is_archived': false,
      };
      final api = _Io(
        read: (path) async {
          expect(path, '/api/companies/shop/records/doc-1/attachments');
          return {
            'attachments': [receipt],
            'storage': {'max_file_bytes': 2100000},
          };
        },
        loadBytes: (path) async {
          expect(path, '/api/companies/shop/attachments/evidence/download');
          return content;
        },
      );
      var exported = false;
      await tester.pumpWidget(
        _host(
          BooksAttachments(
            workspace: _workspace(api, role: 'viewer'),
            record: _bill,
            saveFile: (name, bytes, type) async {
              expect(name, 'Supplier.pdf');
              expect(bytes, content);
              exported = true;
              return true;
            },
          ),
        ),
      );
      await tester.tap(find.text('Receipts & attachments'));
      await tester.pumpAndSettle();
      expect(find.text('Attach receipt'), findsNothing);
      await tester.tap(find.byTooltip('Receipt actions'));
      await tester.pumpAndSettle();
      expect(find.text('Archive receipt'), findsNothing);
      await tester.tap(find.text('Save receipt'));
      await tester.pumpAndSettle();
      expect(exported, isTrue);
    },
  );

  testWidgets(
    'due occurrence requires explicit action and opens the exact nonposting draft',
    (tester) async {
      final today = businessDate();
      final pending = _Pending();
      var posts = 0;
      final api = _Io(
        read: (path) async {
          expect(path, '/api/companies/shop/recurring-templates');
          return {
            'templates': [
              {
                'id': 'schedule-id',
                'name': 'Weekly supplies',
                'is_active': true,
                'next_due': today,
                'draft_kind': 'purchase_order',
                'party_name': 'Corner shop',
                'frequency': 'weekly',
                'generated_count': 0,
              },
            ],
          };
        },
        write: (path, body, key) async {
          expect(
            path,
            '/api/companies/shop/recurring-templates/schedule-id/occurrences',
          );
          expect(body, {'occurrence_date': today});
          expect(pending.value?['key'], key);
          posts++;
          return {
            'template_id': 'schedule-id',
            'occurrence_date': today,
            'record': {
              'id': 'generated',
              'kind': 'purchase_order',
              'name': 'Corner shop',
              'posted': false,
              'data': {
                'recurring_template_id': 'schedule-id',
                'recurring_occurrence_date': today,
              },
            },
          };
        },
      );
      final posting = BooksPosting(_workspace(api, pending: pending));
      addTearDown(posting.dispose);
      await posting.recover();
      BooksRecord? generated;
      await tester.pumpWidget(
        _host(
          BooksRecurring(
            posting: posting,
            onGenerated: (record) => generated = record,
            onBack: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(posts, 0);
      await tester.ensureVisible(find.text('Create due draft'));
      await tester.tap(find.text('Create due draft'));
      await tester.pumpAndSettle();
      expect(posts, 0);
      await tester.tap(find.text('Create draft'));
      await tester.pumpAndSettle();
      expect(posts, 1);
      expect(generated?.id, 'generated');
      expect(pending.value, isNull);
    },
  );
}

final _bill = BooksRecord({
  'id': 'doc-1',
  'kind': 'purchase_bill',
  'number': 'BILL/0001',
});
Widget _host(Widget content) => MaterialApp(home: Scaffold(body: content));

WorkspaceContext _workspace(
  _Io api, {
  _Pending? pending,
  String role = 'owner',
}) => WorkspaceContext(
  api: api,
  company: ApexCompany(id: 'shop', name: 'Corner shop', role: role),
  pending: pending ?? _Pending(),
  features: const {'document_attachments', 'recurring_drafts'},
  refresh: () async {},
);

class _Printer implements PdfOutput {
  ApexPdf? document;
  @override
  Future<bool> print(ApexPdf document) async {
    this.document = document;
    return true;
  }
}

class _Pending implements PendingStore {
  Json? value;
  @override
  Future<void> clear(String key) async => value = null;
  @override
  Future<Json?> load(String key) async => value;
  @override
  Future<void> save(String key, Json data) async => value = data;
}

class _Io implements ApexApi {
  _Io({this.read, this.write, this.loadBytes});
  final Future<Object?> Function(String path)? read;
  final Future<Object?> Function(String path, Json body, String? key)? write;
  final Future<Uint8List> Function(String path)? loadBytes;
  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) => read!(path);
  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => write!(path, body, idempotencyKey);
  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      loadBytes!(path);
}
