import 'dart:async';
import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/books_register.dart';
import 'package:apex_books/features/books/books_reports.dart';
import 'package:apex_books/ui/apex_register.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  testWidgets(
    'register refreshes on reveal and revision, keeping filters at 320dp',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 700);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var reads = 0;
      final api = _FakeApi((path, {query}) async {
        reads++;
        return [
          {
            ..._invoice('item-one', 'INV/0030', 'Corner Shop'),
            'amount': '123456789012345.67',
          },
          _invoice('item-two', 'INV/0021', 'Different customer'),
        ];
      });
      final workspace = _workspace(api);
      Future<void> render(bool active, int revision) async {
        await tester.pumpWidget(
          _host(
            BooksRegister(
              workspace: workspace,
              active: active,
              revision: revision,
            ),
          ),
        );
        await tester.pumpAndSettle();
      }

      await render(false, 0);
      expect(reads, 0);
      await render(true, 0);
      expect(reads, 1);
      await tester.enterText(find.byType(TextField), 'corner');
      await tester.pumpAndSettle();
      expect(find.text('INV/0030'), findsOneWidget);
      expect(find.text('INV/0021'), findsNothing);
      await render(false, 1);
      expect(reads, 1);
      await render(true, 1);
      expect(reads, 2);
      await render(true, 2);
      expect(reads, 3);
      expect(find.text('corner'), findsOneWidget);
      expect(find.text('INV/0021'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'register searches older records and loads exact source detail and trail',
    (tester) async {
      final paths = <String>[];
      final api = _FakeApi((path, {query}) async {
        paths.add(path);
        expect(path, startsWith('/api/companies/test-shop/'));
        if (path.endsWith('/records')) {
          if (query?['offset'] == '0') {
            return List.generate(
              100,
              (index) =>
                  _invoice('recent-$index', 'INV/$index', 'New customer'),
            );
          }
          expect(query?['offset'], '100');
          return [_invoice('invoice-id', 'INV/0023', 'Corner Shop')];
        }
        if (path.endsWith('/records/invoice-id')) {
          return {
            ..._invoice('invoice-id', 'INV/0023', 'Corner Shop'),
            'data': {
              'lines': [
                {'name': 'Counter cable', 'quantity': '2', 'rate': '120.00'},
              ],
            },
            'document_trail': [
              {
                'id': 'receipt-id',
                'kind': 'payment_in',
                'number': 'PIN/0027',
                'relations': ['Payment / allocation'],
              },
            ],
          };
        }
        return {
          'id': 'receipt-id',
          'kind': 'payment_in',
          'number': 'PIN/0027',
          'posted': true,
          'amount': '240.00',
        };
      });

      await tester.pumpWidget(_host(BooksRegister(workspace: _workspace(api))));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'corner inv/0023');
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pumpAndSettle();
      await tester.tap(find.text('INV/0023'));
      await tester.pumpAndSettle();
      expect(find.text('Counter cable'), findsOneWidget);
      final payment = find.text('PIN/0027');
      await tester.scrollUntilVisible(
        payment,
        150,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.ensureVisible(payment);
      await tester.pumpAndSettle();
      await tester.tap(payment);
      await tester.pumpAndSettle();
      expect(find.text('Payment in'), findsOneWidget);
      expect(paths, [
        '/api/companies/test-shop/records',
        '/api/companies/test-shop/records',
        '/api/companies/test-shop/records/invoice-id',
        '/api/companies/test-shop/records/receipt-id',
      ]);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('company switch discards a previous company response', (
    tester,
  ) async {
    final oldRequest = Completer<Object?>();
    final api = _FakeApi((path, {query}) {
      if (path.contains('/company-a/')) return oldRequest.future;
      return Future.value([_invoice('b', 'B-002', 'New company')]);
    });
    await tester.pumpWidget(
      _host(BooksRegister(workspace: _workspace(api, companyId: 'company-a'))),
    );
    await tester.pump();
    await tester.pumpWidget(
      _host(BooksRegister(workspace: _workspace(api, companyId: 'company-b'))),
    );
    await tester.pumpAndSettle();
    expect(find.text('B-002'), findsOneWidget);
    oldRequest.complete([_invoice('a', 'A-002', 'Old company')]);
    await tester.pumpAndSettle();
    expect(find.text('A-002'), findsNothing);
    expect(find.text('B-002'), findsOneWidget);
  });

  for (final width in [1440.0, 390.0]) {
    testWidgets('sales invoice register matches the web layout at ${width.toInt()}dp', (
      tester,
    ) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = Size(width, 1600);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final api = _FakeApi((path, {query}) async {
        expect(query?['kind'], 'sales_invoice');
        return [
          {
            ..._invoice('a', 'INV/0002', 'Gupta & Sons'),
            'date': '2026-11-10',
            'amount': '1950.00',
            'outstanding': '1950.00',
          },
          {
            ..._invoice('b', 'INV/0001', 'Sharma Electronics'),
            'date': '2026-11-05',
            'amount': '1500.00',
            'outstanding': '500.00',
          },
        ];
      });
      final workspace = WorkspaceContext(
        api: api,
        company: ApexCompany(id: 'test-shop', name: 'Shop', role: 'owner'),
        pending: _MemoryPending(),
        features: const {},
        refresh: () async {},
      );
      await tester.pumpWidget(
        _host(
          BooksRegister(
            workspace: workspace,
            kind: 'sales_invoice',
            title: 'Sales invoices',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Create invoices, follow collections and review balances.'), findsOneWidget);
      expect(find.text('Add sales invoice'), findsOneWidget);
      expect(find.text('Posted value'), findsOneWidget);
      expect(find.text('₹3,450.00'), findsOneWidget);
      expect(find.text('₹2,450.00'), findsOneWidget);
      expect(find.text('2 records in this view'), findsOneWidget);
      expect(find.text('Part settled'), findsOneWidget);
      expect(find.text('Collect payment'), findsNWidgets(2));
      expect(find.text('Search party or reference'), findsOneWidget);
      await tester.tap(
        find.descendant(
          of: find.byType(ApexFilterTabs<String>),
          matching: find.text('Unpaid'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('2 records in this view'), findsOneWidget);
      await tester.tap(
        find.descendant(
          of: find.byType(ApexFilterTabs<String>),
          matching: find.text('Settled'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('No matching records'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('reports render server totals and offer dated refresh', (
    tester,
  ) async {
    final calls = <Map<String, String>>[];
    final api = _FakeApi((path, {query}) async {
      expect(path, '/api/companies/test-shop/reports/register');
      calls.add(query!);
      return {
        'total': '105.25',
        'rows': [
          {
            'number': 'CN/0142',
            'kind': 'credit_note',
            'party': 'Rekha Retail',
            'date': '2026-04-01',
            'amount': '-2.75',
            'taxable': '-2.75',
            'cgst': '0',
            'sgst': '0',
            'igst': '0',
          },
        ],
      };
    });
    final workspace = _workspace(api);
    await tester.pumpWidget(_host(BooksReports(workspace: workspace)));
    await tester.pumpAndSettle();
    expect(find.text('Profit & loss and balance sheet'), findsNothing);
    // The library is as long as the web one, so bring the report into view first.
    await tester.ensureVisible(find.text('Sales register'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sales register'));
    await tester.pumpAndSettle();
    expect(find.text('₹105.25'), findsOneWidget);
    // Taxable value and total both show the return, as in the web register table.
    expect(find.text('−₹2.75'), findsWidgets);
    expect(calls.single['group'], 'sales');
    expect(calls.single['to_date'], businessDate());
    await tester.tap(find.byTooltip('Refresh report'));
    await tester.pumpAndSettle();
    expect(calls, hasLength(2));
    expect(calls[1], calls[0]);
    await tester.pumpWidget(
      _host(BooksReports(workspace: workspace, active: false, revision: 1)),
    );
    await tester.pumpAndSettle();
    expect(calls, hasLength(2));
    await tester.pumpWidget(
      _host(BooksReports(workspace: workspace, revision: 1)),
    );
    await tester.pumpAndSettle();
    expect(calls, hasLength(3));
    expect(calls[2], calls[0]);
    expect(find.text('₹105.25'), findsOneWidget);
  });
}

Widget _host(Widget pane) => MaterialApp(home: Scaffold(body: pane));

BooksJson _invoice(String id, String number, String party) => {
  'id': id,
  'kind': 'sales_invoice',
  'number': number,
  'name': party,
  'date': '2026-04-01',
  'posted': true,
  'amount': '240.00',
};

WorkspaceContext _workspace(_FakeApi api, {String companyId = 'test-shop'}) =>
    WorkspaceContext(
      api: api,
      company: ApexCompany(id: companyId, name: 'Test company', role: 'viewer'),
      pending: _UnusedPending(),
      features: const {},
      refresh: () async {},
    );

class _FakeApi implements ApexApi {
  const _FakeApi(this.read);
  final BooksGet read;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      read(path, query: query);

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => throw UnimplementedError();

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
}

class _UnusedPending implements PendingStore {
  @override
  Future<Json?> load(String operation) => throw UnimplementedError();

  @override
  Future<void> save(String operation, Json data) => throw UnimplementedError();

  @override
  Future<void> clear(String operation) => throw UnimplementedError();
}

class _MemoryPending implements PendingStore {
  final _saved = <String, Json>{};

  @override
  Future<Json?> load(String operation) async => _saved[operation];

  @override
  Future<void> save(String operation, Json data) async =>
      _saved[operation] = data;

  @override
  Future<void> clear(String operation) async => _saved.remove(operation);
}
