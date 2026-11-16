import 'package:apex_books/features/books/books_data.dart';
import 'package:apex_books/features/books/register_query.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'compact pages keep the server cursor when master rows are excluded',
    () async {
      final api = BooksData('company/one', (path, {query}) async {
        expect(path, '/api/companies/company%2Fone/records');
        expect(query, {
          'compact': 'true',
          'offset': '48',
          'limit': '2',
          'kind': 'sales_invoice',
        });
        return [
          {'id': 'item-id', 'kind': 'item'},
          {
            'id': 'invoice-id',
            'kind': 'sales_invoice',
            'number': 'INV/26-27/0012',
            'posted': true,
          },
        ];
      });
      final page = await api.records(
        kind: 'sales_invoice',
        offset: 48,
        limit: 2,
      );
      expect(page.records.single.label, 'INV/26-27/0012');
      expect(page.records.single.status, 'Posted');
      expect(page.nextOffset, 50);
      expect(page.hasMore, isTrue);
    },
  );

  test(
    'exact detail verifies returned identity and preserves posting facts',
    () async {
      final api = BooksData('shop', (path, {query}) async {
        expect(path, '/api/companies/shop/records/invoice%2Fone');
        expect(query, isNull);
        return {'id': 'not-requested', 'kind': 'sales_invoice'};
      });
      await expectLater(api.record('invoice/one'), throwsFormatException);

      final order = BooksRecord({
        'id': 'po',
        'kind': 'purchase_order',
        'number': 'PO/0021',
        'name': 'Market Supply',
        'data': {'purchase_order_receiving_started': true},
      });
      expect(order.status, 'Receiving started');
      expect(order.matches('supply po/0021'), isTrue);
      expect(order.matches('market invoice'), isFalse);
      expect(
        BooksRecord({...order.json, 'cancelled': true}).status,
        'Cancelled',
      );
    },
  );

  test(
    'sales and ageing query distinct authoritative report endpoints',
    () async {
      var calls = 0;
      final api = BooksData('shop', (path, {query}) async {
        calls++;
        if (path.endsWith('/ageing')) {
          expect(query, {'as_of': '2026-05-01'});
        } else {
          expect(path, '/api/companies/shop/reports/register');
          expect(query, {
            'group': 'sales',
            'from_date': '2026-04-01',
            'to_date': '2026-05-01',
          });
        }
        return {'total': '1.00'};
      });
      final first = DateTime(2026, 4);
      final last = DateTime(2026, 5);
      await api.report(BooksReport.sales, from: first, to: last);
      await api.report(BooksReport.ageing, from: first, to: last);
      await expectLater(
        api.report(BooksReport.sales, from: last, to: first),
        throwsArgumentError,
      );
      expect(calls, 2);
    },
  );

  test(
    'money formatting preserves decimal precision and missing valuation',
    () {
      expect(booksMoney('123456789012345.67'), '₹12,34,56,78,90,12,345.67');
      expect(booksMoney('-1234567.895'), '−₹12,34,567.90');
      expect(booksMoney('0'), '₹0.00');
      expect(booksMoney(null), '—');
    },
  );

  group('register query', () {
    BooksRecord invoice(
      String id,
      String party,
      String amount,
      String outstanding, {
      String date = '2026-11-10',
      bool posted = true,
      bool cancelled = false,
    }) => BooksRecord({
      'id': id,
      'kind': 'sales_invoice',
      'number': 'INV/$id',
      'name': party,
      'date': date,
      'posted': posted,
      'cancelled': cancelled,
      'amount': amount,
      'outstanding': outstanding,
    });

    final rows = [
      invoice('1', 'Sharma', '1500.00', '500.00', date: '2026-11-05'),
      invoice('2', 'Gupta', '1950.00', '1950.00'),
      invoice('3', 'Gupta', '300.00', '0.00', date: '2026-10-01'),
      invoice('4', 'Void', '99.00', '99.00', cancelled: true),
    ];

    test('stat cards, tabs and settlement follow the web register', () {
      final stats = registerStats('sales_invoice', rows);
      expect(stats.map((s) => s.label), [
        'Posted value',
        'Outstanding',
        'Unpaid documents',
        'Settled documents',
      ]);
      expect(stats[0].value, '₹3,750.00');
      expect(stats[1].value, '₹2,450.00');
      expect(stats[2].value, '2');
      expect(stats[3].value, '1');
      final tabs = registerTabs('sales_invoice', rows, '2026-11-16');
      expect(tabs.map((t) => (t.$2, t.$3)), [
        ('All', 4),
        ('Unpaid', 2),
        ('Settled', 1),
        ('Overdue', 0),
        ('Cancelled', 1),
      ]);
      expect(registerSettlement(rows[0]), 'Part settled');
      expect(registerSettlement(rows[1]), 'Unpaid');
      expect(registerSettlement(rows[2]), 'Settled');
      expect(registerStats('', rows), isEmpty);
    });

    test('period, party, tab, search and sort narrow the rows', () {
      const none = BooksRegisterQuery();
      expect(
        registerVisible('sales_invoice', rows, none, '2026-11-16')
            .map((r) => r.id),
        ['4', '2', '1', '3'],
      );
      final month = registerPeriodDates('month', DateTime.utc(2026, 11, 16));
      expect((month.from, month.to), ('2026-11-01', '2026-11-30'));
      final last = registerPeriodDates('last_month', DateTime.utc(2026, 1, 9));
      expect((last.from, last.to), ('2025-12-01', '2025-12-31'));
      final scoped = registerScope(
        rows,
        BooksRegisterQuery(from: month.from, to: month.to, party: 'Gupta'),
      );
      expect(scoped.map((r) => r.id), ['2']);
      expect(
        registerVisible(
          'sales_invoice',
          rows,
          const BooksRegisterQuery(tab: 'unpaid', sort: 'amount'),
          '2026-11-16',
        ).map((r) => r.id),
        ['2', '1'],
      );
      expect(
        registerVisible(
          'sales_invoice',
          rows,
          const BooksRegisterQuery(search: 'sharma', sort: 'oldest'),
          '2026-11-16',
        ).map((r) => r.id),
        ['1'],
      );
    });
  });
}
