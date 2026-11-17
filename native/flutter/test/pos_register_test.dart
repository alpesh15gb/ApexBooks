import 'dart:convert';
import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/pos/pos_day_summary.dart';
import 'package:apex_books/features/pos/pos_register_controller.dart';
import 'package:apex_books/features/pos/pos_screen.dart';
import 'package:apex_books/features/pos/pos_workspace_api.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  test('daily totals split tenders, link refunds and export a safe CSV', () {
    Map<String, dynamic> row(
      String id,
      String kind,
      String amount, {
      Map<String, dynamic> data = const {},
      bool cancelled = false,
    }) => {
      'id': id,
      'kind': kind,
      'number': '=$id',
      'date': '2026-11-16',
      'amount': amount,
      'posted': true,
      'cancelled': cancelled,
      'data': data,
    };
    final records = [
      row('s1', 'pos', '100.00', data: {'payment_account': 'cash'}),
      row(
        's2',
        'pos',
        '80.00',
        data: {
          'payment_account': 'split',
          'cash_amount': '30.00',
          'bank_amount': '50.00',
        },
      ),
      row('s3', 'pos', '10.00', cancelled: true),
      row('c1', 'credit_note', '20.00', data: {'applied_to': 's1'}),
      row(
        'r1',
        'customer_refund',
        '20.00',
        data: {'credit_note_id': 'c1', 'payment_account': 'cash'},
      ),
    ];
    final day = summarizePosDay(records, '2026-11-16');
    expect(day.saleCount, 2);
    expect(day.refundCount, 1);
    expect(day.cancelledCount, 1);
    expect(day.cashSales, BigInt.from(13000));
    expect(day.bankSales, BigInt.from(5000));
    expect(day.cashRefunds, BigInt.from(2000));
    final result = reconcilePosCash(day, {
      'openingFloat': '50',
      'cashCounted': '160',
    });
    expect(result.expected, BigInt.from(16000));
    expect(result.variance, BigInt.zero);
    final csv = posCloseCsv(
      companyName: '=Shop',
      date: '2026-11-16',
      day: day,
      reconciliation: result,
    );
    expect(csv, contains("\"'=Shop\""));
    expect(csv, contains('Cash over / short,0.00'));
    expect(reconcilePosCash(day, {'openingFloat': 'x'}).expected, isNull);
  });

  testWidgets(
    '390px register opens, records cash and requires a variance reason',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 860);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetPhysicalSize);
      final store = _RegisterStore();
      final api = _RegisterApi(store);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: PosScreen(workspace: _workspace(api, store))),
        ),
      );
      await tester.pumpAndSettle();

      final register = find.text('Register');
      expect(tester.getRect(register).right, lessThan(390));
      await _tap(tester, 'Register');
      await _write(tester, 'Opening float (₹)', '100');
      await _tap(tester, 'Open register');
      expect(find.text('Expected cash'), findsWidgets);
      expect(find.text('Register opening recorded.'), findsOneWidget);

      await _write(tester, 'Amount (₹)', '15');
      final postMovement = find.widgetWithText(
        OutlinedButton,
        'Record cash movement',
      );
      expect(tester.widget<OutlinedButton>(postMovement).onPressed, isNull);
      await _write(tester, 'Reason', 'Extra change');
      await _tap(tester, 'Record cash movement');
      expect(find.text('₹115.00'), findsWidgets);

      await _write(tester, 'Counted cash (₹)', '110');
      expect(find.text('Cash short by ₹5.00.'), findsOneWidget);
      final postClose = find.widgetWithText(FilledButton, 'Close register');
      expect(tester.widget<FilledButton>(postClose).onPressed, isNull);
      await _write(tester, 'Reason for any difference *', 'Five rupees short');
      await _tap(tester, 'Close register');
      expect(find.text('Closed'), findsOneWidget);
      expect(find.text('Register closing count recorded.'), findsOneWidget);
      expect(
        tester.getRect(find.text('Register closing count recorded.')).bottom,
        lessThan(860),
      );
      final recent = find.textContaining('Counted ₹110.00');
      await tester.ensureVisible(recent);
      await tester.tap(recent);
      await tester.pumpAndSettle();
      expect(find.text('Five rupees short'), findsOneWidget);
      expect(api.closePayload?['snapshot'], api.afterMovementSnapshot);
      expect(api.closePayload?['counted_cash'], '110.00');
      expect(store.values, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );

  test(
    'lost movement response replays the same route, body and key after restart',
    () async {
      final store = _RegisterStore();
      final api = _RegisterApi(store)..loseMovementResponse = true;
      final workspace = _workspace(api, store);
      final first = _controller(workspace);
      await first.recover();
      await first.refresh();
      await first.open('100');
      await first.move('drawer', 'out', '5.50', 'Takeaway cash');
      expect(first.blocksNewSale, true);
      final pending = first.pending!;
      expect(store.values['pos_register']?['key'], pending.key);
      first.dispose();

      final second = _controller(workspace);
      addTearDown(second.dispose);
      await second.recover();
      await second.retry();
      expect(api.movementRequests, hasLength(2));
      expect(api.movementRequests.toSet(), hasLength(1));
      expect(second.active?.expected, BigInt.from(9450));
      expect(second.pending, isNull);
      expect(second.blocksNewSale, false);
      expect(store.values, isEmpty);
    },
  );

  test(
    'server rejects a stale close and requires a new count on refreshed totals',
    () async {
      final store = _RegisterStore();
      final api = _RegisterApi(store);
      final controller = _controller(_workspace(api, store));
      addTearDown(controller.dispose);
      await controller.recover();
      await controller.refresh();
      await controller.open('100');
      final old = controller.active!.snapshot;
      api.otherDrawerActivity();
      await controller.close('drawer', '100', '', old);
      expect(controller.message, startsWith('Register activity changed.'));
      expect(controller.active?.expected, BigInt.from(10100));
      expect(controller.pending, isNull);
      expect(controller.validateClose('100', '', old), isNotNull);
      expect(api.closed, isFalse);
      await controller.close('drawer', '101', '', controller.active!.snapshot);
      expect(api.closed, isTrue);
      expect(api.closePayload?['reason'], '');
    },
  );

  test(
    'viewer can read register status but cannot send new operations',
    () async {
      final store = _RegisterStore();
      final api = _RegisterApi(store);
      final viewer = _controller(_workspace(api, store, role: 'viewer'));
      addTearDown(viewer.dispose);
      await viewer.recover();
      await viewer.refresh();
      expect(viewer.overview, isNotNull);
      expect(viewer.writable, isFalse);
      await viewer.open('50');
      expect(api.opened, isFalse);
      expect(store.values, isEmpty);
    },
  );
}

Future<void> _tap(WidgetTester tester, String label) async {
  final finder = find.text(label).last;
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _write(WidgetTester tester, String label, String text) async {
  final finder = find.widgetWithText(TextField, label);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.enterText(finder, text);
  await tester.pumpAndSettle();
}

WorkspaceContext _workspace(
  _RegisterApi api,
  _RegisterStore store, {
  String role = 'owner',
}) => WorkspaceContext(
  api: api,
  company: ApexCompany(id: 'front', name: 'Register test', role: role),
  pending: store,
  features: const {'pos_register_sessions'},
  refresh: () async {},
);

PosRegisterController _controller(WorkspaceContext workspace) =>
    PosRegisterController(
      gateway: WorkspacePosGateway(workspace),
      canWrite: workspace.company.canWrite,
      onChanged: () {},
    );

class _RegisterStore implements PendingStore {
  final Map<String, Json> values = {};

  @override
  Future<Json?> load(String operation) async => values[operation];

  @override
  Future<void> clear(String operation) async => values.remove(operation);

  @override
  Future<void> save(String operation, Json data) async =>
      values[operation] = data;
}

class _RegisterApi implements ApexApi {
  _RegisterApi(this.store);
  final _RegisterStore store;
  bool opened = false;
  bool closed = false;
  bool loseMovementResponse = false;
  int expected = 0;
  int opening = 0;
  int cashIn = 0;
  int cashOut = 0;
  final movements = <Json>[];
  final movementRequests = <String>[];
  final posted = <String, Json>{};
  Json? closePayload;
  final initialSnapshot = List.filled(64, 'a').join();
  final afterMovementSnapshot = List.filled(64, 'b').join();
  bool activity = false;

  String _money(int minor) => (minor / 100).toStringAsFixed(2);
  int _minor(dynamic amount) => (double.parse(amount as String) * 100).round();

  String get snapshot => activity ? afterMovementSnapshot : initialSnapshot;

  void otherDrawerActivity() {
    activity = true;
    expected += 100;
  }

  Json _register() {
    final totals = {
      'cash_sales': '0.00',
      'bank_sales': '0.00',
      'cash_refunds': '0.00',
      'cash_in': _money(cashIn),
      'cash_out': _money(cashOut),
      'expected_cash': _money(expected),
    };
    return {
      'id': 'drawer',
      'kind': 'pos_register_session',
      'date': '2026-11-16',
      'data': {
        'opening_float': _money(opening),
        if (closed) ...{
          'closed_at': '2026-11-16T10:00:00Z',
          'closed_totals': totals,
          'counted_cash': closePayload?['counted_cash'],
          'variance': _money(_minor(closePayload?['counted_cash']) - expected),
          'close_reason': closePayload?['reason'],
        },
      },
      'movements': movements,
      if (!closed) ...{'totals': totals, 'snapshot': snapshot},
    };
  }

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    if (path.endsWith('/pos-register')) {
      return {
        'active': opened && !closed ? _register() : null,
        'closed': [if (closed) _register()],
      };
    }
    if (path.endsWith('/records') || path.endsWith('/bank-accounts')) {
      return <dynamic>[];
    }
    throw StateError('Unexpected GET $path');
  }

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async {
    expect(store.values['pos_register']?['key'], idempotencyKey);
    final key = idempotencyKey!;
    if (path.endsWith('/pos-register/open')) {
      opening = expected = _minor(body['opening_float']);
      opened = true;
      return _register();
    }
    if (path.endsWith('/pos-register/drawer/movements')) {
      movementRequests.add(jsonEncode([path, key, body]));
      if (posted.containsKey(key)) return posted[key];
      final amount = _minor(body['amount']);
      final direction = body['direction'];
      if (direction == 'in') {
        cashIn += amount;
        expected += amount;
      } else {
        cashOut += amount;
        expected -= amount;
      }
      activity = true;
      final movement = <String, dynamic>{
        'id': 'movement',
        'kind': 'pos_register_movement',
        'amount': body['amount'],
        'data': {
          'pos_register_session_id': 'drawer',
          'direction': direction,
          'reason': body['reason'],
        },
      };
      movements.add(movement);
      posted[key] = movement;
      if (loseMovementResponse) {
        throw const ApexApiException(message: 'Interrupted response.');
      }
      return movement;
    }
    if (path.endsWith('/pos-register/drawer/close')) {
      if (body['snapshot'] != snapshot) {
        throw const ApexApiException(
          message: 'Register activity changed. Refresh and review the current drawer total.',
          status: 409,
        );
      }
      closePayload = body;
      closed = true;
      return _register();
    }
    throw StateError('Unexpected POST $path');
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) =>
      throw UnimplementedError();
}
