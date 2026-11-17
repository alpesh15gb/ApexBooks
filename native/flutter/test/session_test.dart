import 'dart:async';
import 'dart:convert';

import 'package:apex_books/core/http_api.dart';
import 'package:apex_books/core/session.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

final origin = Uri.parse('https://api.example.invalid');

http.Response jsonResponse(Object data, [int status = 200]) => http.Response(
  jsonEncode(data),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'pending operations use Windows-safe storage and stay company scoped',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      debugDefaultTargetPlatformOverride = TargetPlatform.windows;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      const storage = FlutterSecureStorage();
      final own = SecurePendingStore(origin, 'account-a', 'company-a');
      final other = SecurePendingStore(origin, 'account-a', 'company-b');
      await own.save('checkout:post', {'sale': 'one'});
      expect(await own.load('checkout:post'), {'sale': 'one'});
      expect(await other.load('checkout:post'), isNull);
      final stored = await storage.readAll();
      expect(
        stored.keys.single,
        matches(r'^apexbooks-flutter-v1-[a-f0-9]{64}$'),
      );
      await own.clear('checkout:post');
      expect(await storage.readAll(), isEmpty);
    },
  );

  test('existing non-Windows pending operations remain recoverable', () async {
    final scope = base64Url.encode(
      utf8.encode(jsonEncode([origin.origin, 'account-a', 'company-a'])),
    );
    FlutterSecureStorage.setMockInitialValues({
      'apexbooks-flutter-v1:$scope:checkout:post': '{"sale":"legacy"}',
    });
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final own = SecurePendingStore(origin, 'account-a', 'company-a');
    expect(await own.load('checkout:post'), {'sale': 'legacy'});
    await own.clear('checkout:post');
    expect(await own.load('checkout:post'), isNull);
  });

  test(
    'decodes quoted amounts and forwards review and idempotency headers',
    () async {
      final api = HttpApexApi(
        origin: origin,
        client: MockClient((request) async {
          expect(request.url.origin, origin.origin);
          expect(request.followRedirects, isFalse);
          expect(request.headers['authorization'], 'Bearer synthetic');
          expect(request.headers['idempotency-key'], 'sale-abc');
          expect(jsonDecode(request.body), {'expected_total': '1234.50'});
          return http.Response(
            '{"detail":"Review the changed total."}',
            409,
            headers: {'x-apex-error': 'POS_REQUOTE_REQUIRED'},
          );
        }),
        token: 'synthetic',
        companyId: 'company-a',
      );
      await expectLater(
        api.post(
          '/api/companies/company-a/records',
          body: {'expected_total': '1234.50'},
          idempotencyKey: 'sale-abc',
        ),
        throwsA(
          isA<ApexApiException>()
              .having((e) => e.status, 'HTTP status', 409)
              .having((e) => e.code, 'API code', 'POS_REQUOTE_REQUIRED')
              .having((e) => e.uncertain, 'uncertain', false),
        ),
      );
    },
  );

  test('rejects outgoing requests outside the active company', () async {
    var sent = 0;
    final api = HttpApexApi(
      origin: origin,
      client: MockClient((_) async {
        sent++;
        return jsonResponse({});
      }),
      companyId: 'company-a',
    );
    await expectLater(
      api.get('/api/companies/company-b/records'),
      throwsA(isA<ApexApiException>().having((e) => e.status, 'status', 403)),
    );
    for (final path in [
      'https://different.example/api/records',
      '/api/companies/company-a/../company-b/records',
      '/api/companies/company-a/%2E%2E',
    ]) {
      await expectLater(api.get(path), throwsArgumentError);
    }
    expect(sent, 0);
  });

  test(
    'switch discards late replies and does not expose another company',
    () async {
      final execute = Completer<http.Response>();
      final issued = Completer<void>();
      final account = base64Url.encode(utf8.encode('{"sub":"account-a"}'));
      final namespaces = <List<String>>[];
      final session = ApexSession(
        origin: origin,
        pendingFactory: (uri, accountId, companyId) {
          namespaces.add([uri.origin, accountId, companyId]);
          return _Pending();
        },
        client: MockClient((request) async {
          switch (request.url.path) {
            case '/api/auth/login':
              return jsonResponse({'token': 'header.$account.signature'});
            case '/api/companies':
              return jsonResponse([
                {'id': 'a', 'name': 'First company', 'role': 'owner'},
                {'id': 'b', 'name': 'Second company', 'role': 'viewer'},
              ]);
            case '/api/capabilities':
              return jsonResponse({
                'supported_features': ['stock_counts'],
              });
            case '/api/companies/a/records':
              issued.complete();
              return execute.future;
            case '/api/auth/logout':
              return jsonResponse({'message': 'Signed out'});
            default:
              fail('Unexpected request ${request.url.path}');
          }
        }),
      );
      addTearDown(session.dispose);
      await session.signIn('staff@example.invalid', 'synthetic password');
      expect(session.signedIn, isTrue);
      expect(session.workspace, isNull);
      session.chooseCompany('a');
      final first = session.workspace!;
      expect(first.company.canWrite, isTrue);
      final posting = expectLater(
        first.api.post('${first.path}/records', body: {'amount': '100'}),
        throwsA(
          isA<ApexApiException>().having((e) => e.uncertain, 'uncertain', true),
        ),
      );
      await issued.future;
      session.chooseCompany('b');
      execute.complete(jsonResponse({'id': 'sale-a'}));
      await posting;
      expect(session.workspace!.company.id, 'b');
      expect(session.workspace!.company.canWrite, isFalse);
      expect(session.workspace!.features, {'stock_counts'});
      expect(namespaces, [
        [origin.origin, 'account-a', 'a'],
        [origin.origin, 'account-a', 'b'],
      ]);
      await session.signOut();
      expect(session.workspace, isNull);
      expect(session.signedIn, isFalse);
    },
  );

  test('sign-in keeps core books available on an API without optional capabilities', () async {
    final account = base64Url.encode(utf8.encode('{"sub":"account-a"}'));
    final session = ApexSession(
      origin: origin,
      pendingFactory: (_, _, _) => _Pending(),
      client: MockClient(
        (request) async => switch (request.url.path) {
          '/api/auth/login' => jsonResponse({'token': 'qa.$account.signature'}),
          '/api/companies' => jsonResponse([
            {'id': 'shop', 'name': 'Corner Store', 'role': 'owner'},
          ]),
          '/api/capabilities' => jsonResponse({'detail': 'Not Found'}, 404),
          _ => throw StateError('Unexpected request ${request.url.path}'),
        },
      ),
    );
    addTearDown(session.dispose);
    await session.signIn('staff@example.invalid', 'synthetic password');
    expect(session.workspace?.company.id, 'shop');
    expect(session.workspace?.features, isEmpty);
  });

  test('a kept sign-in reopens the account and a rejected one is forgotten', () async {
    final account = base64Url.encode(utf8.encode('{"sub":"account-a"}'));
    final kept = _Credentials();
    var accept = true;
    ApexSession build() => ApexSession(
      origin: origin,
      credentials: kept,
      pendingFactory: (_, _, _) => _Pending(),
      client: MockClient(
        (request) async => switch (request.url.path) {
          '/api/auth/login' => jsonResponse({'token': 'qa.$account.signature'}),
          '/api/auth/logout' => jsonResponse({}),
          '/api/companies' => accept
              ? jsonResponse([
                  {'id': 'shop', 'name': 'Corner Store', 'role': 'owner'},
                ])
              : jsonResponse({'detail': 'Not authenticated'}, 401),
          '/api/capabilities' => jsonResponse({'supported_features': []}),
          _ => throw StateError('Unexpected request ${request.url.path}'),
        },
      ),
    );
    final first = build();
    await first.signIn('staff@example.invalid', 'synthetic password');
    expect(kept.token, 'qa.$account.signature');
    first.dispose();

    final reloaded = build();
    addTearDown(reloaded.dispose);
    await reloaded.restore();
    expect(reloaded.signedIn, isTrue);
    expect(reloaded.workspace?.company.id, 'shop');
    await reloaded.signOut();
    expect(kept.token, isNull);

    kept.token = 'qa.$account.signature';
    accept = false;
    final expired = build();
    addTearDown(expired.dispose);
    await expired.restore();
    expect(expired.signedIn, isFalse);
    expect(expired.busy, isFalse);
    expect(kept.token, isNull);
  });

  test('India business day turns over at 18:30 UTC', () {
    expect(businessDate(DateTime.utc(2026, 11, 16, 18, 29)), '2026-11-16');
    expect(businessDate(DateTime.utc(2026, 11, 16, 18, 30)), '2026-11-17');
  });
}

class _Pending implements PendingStore {
  @override
  Future<void> clear(String operation) async {}
  @override
  Future<Json?> load(String operation) async => null;
  @override
  Future<void> save(String operation, Json data) async {}
}

class _Credentials implements CredentialStore {
  String? token;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
  @override
  Future<void> clear() async => token = null;
}
