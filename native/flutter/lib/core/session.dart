import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'http_api.dart';
import 'workspace.dart';

typedef PendingFactory = PendingStore Function(
  Uri origin,
  String accountId,
  String companyId,
);

class SecurePendingStore implements PendingStore {
  SecurePendingStore(
    Uri origin,
    String accountId,
    String companyId, {
    this._storage = const FlutterSecureStorage(),
  }) : _scope = [origin.origin, accountId, companyId];

  final FlutterSecureStorage _storage;
  final List<String> _scope;

  String _key(String operation) {
    if (!RegExp(r'^[a-zA-Z0-9._:-]{1,100}$').hasMatch(operation)) {
      throw ArgumentError('Invalid pending operation name.');
    }
    final identity = utf8.encode(jsonEncode([..._scope, operation]));
    return 'apexbooks-flutter-v1-${sha256.convert(identity)}';
  }

  String _legacyKey(String operation) =>
      'apexbooks-flutter-v1:${base64Url.encode(utf8.encode(jsonEncode(_scope)))}:$operation';

  // The old name contained colons. Retain access to prior operations on
  // platforms that accepted it, while Windows uses a file-safe key.
  bool get _supportsLegacyKey =>
      kIsWeb || defaultTargetPlatform != TargetPlatform.windows;

  @override
  Future<Json?> load(String operation) async {
    final encoded =
        await _storage.read(key: _key(operation)) ??
        (_supportsLegacyKey
            ? await _storage.read(key: _legacyKey(operation))
            : null);
    if (encoded == null) return null;
    try {
      return jsonDecode(encoded) as Json;
    } catch (_) {
      throw const ApexApiException(
        message: 'A saved operation could not be read. Verify it before posting again.',
      );
    }
  }

  @override
  Future<void> save(String operation, Json data) =>
      _storage.write(key: _key(operation), value: jsonEncode(data));

  @override
  Future<void> clear(String operation) async {
    final key = _key(operation);
    if (_supportsLegacyKey) await _storage.delete(key: _legacyKey(operation));
    await _storage.delete(key: key);
  }
}

/// Keeps the sign-in token between page loads, like the web app's storage.
abstract class CredentialStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

class SecureCredentialStore implements CredentialStore {
  const SecureCredentialStore([this._storage = const FlutterSecureStorage()]);

  static const _key = 'apexbooks-flutter-session-v1';
  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

class ApexSession extends ChangeNotifier {
  ApexSession({
    required this.origin,
    http.Client? client,
    PendingFactory? pendingFactory,
    CredentialStore? credentials,
  }) : _client = client ?? http.Client(),
       _pendingFactory = pendingFactory ?? SecurePendingStore.new,
       _credentials =
           credentials ?? (kIsWeb ? const SecureCredentialStore() : null);

  final Uri origin;
  final http.Client _client;
  final PendingFactory _pendingFactory;
  final CredentialStore? _credentials;
  String? _token;
  String? _accountId;
  bool _disposed = false;
  int _authGeneration = 0;
  int _workspaceGeneration = 0;

  List<ApexCompany> companies = const [];
  Set<String> features = const {};
  WorkspaceContext? workspace;
  bool busy = false;
  String? message;
  int revision = 0;

  bool get signedIn => _token != null;

  HttpApexApi get accountApi {
    final token = _token;
    final generation = _authGeneration;
    if (token == null) {
      throw const ApexApiException(
        message: 'Please sign in again.',
        status: 401,
      );
    }
    return HttpApexApi(
      origin: origin,
      client: _client,
      token: token,
      isActive: () => _authActive(generation),
      onUnauthorized: () => _expire(generation),
    );
  }

  Future<void> refreshCompanies({String? select}) async {
    final generation = _authGeneration;
    final result = await accountApi.get('/api/companies');
    if (!_authActive(generation)) return;
    final assigned = (result as List)
        .cast<Json>()
        .map(ApexCompany.fromJson)
        .toList();
    companies = List.unmodifiable(assigned);
    final selected = select ?? workspace?.company.id;
    final matches = assigned.where((company) => company.id == selected);
    if (matches.isNotEmpty) {
      _choose(matches.single);
    } else if (assigned.length == 1) {
      _choose(assigned.single);
    } else {
      _workspaceGeneration++;
      workspace = null;
    }
    notifyListeners();
  }

  Future<void> register(String email, String password) async {
    final api = HttpApexApi(origin: origin, client: _client);
    await api.post(
      '/api/auth/register',
      body: {'email': email.trim(), 'password': password},
    );
  }

  Future<void> recover(String email, String code, String password) async {
    final api = HttpApexApi(origin: origin, client: _client);
    await api.post(
      '/api/auth/recover',
      body: {
        'email': email.trim(),
        'code': code.trim(),
        'new_password': password,
      },
    );
  }

  Future<void> signIn(String email, String password) async {
    if (busy || signedIn) return;
    busy = true;
    message = null;
    final generation = ++_authGeneration;
    notifyListeners();
    try {
      final anonymous = HttpApexApi(origin: origin, client: _client);
      final login = await anonymous.post(
        '/api/auth/login',
        body: {'email': email.trim(), 'password': password},
      );
      final token = login is Json ? login['token'] : null;
      if (token is! String || token.isEmpty) throw const FormatException();
      if (!await _activate(token, generation)) return;
      await _remember(token);
    } on ApexApiException catch (error) {
      if (_authActive(generation)) message = error.message;
    } on ArgumentError {
      if (_authActive(generation)) {
        message = 'The configured API address is invalid.';
      }
    } catch (_) {
      if (_authActive(generation)) {
        message = 'The API did not return a compatible sign-in response.';
      }
    } finally {
      if (_authActive(generation)) {
        busy = false;
        notifyListeners();
      }
    }
  }

  /// Opens the account from a token kept by an earlier page load, if any.
  Future<void> restore() async {
    final store = _credentials;
    if (store == null || busy || signedIn) return;
    final String? token;
    try {
      token = await store.read();
    } catch (_) {
      return;
    }
    if (token == null || token.isEmpty || busy || signedIn) return;
    busy = true;
    final generation = ++_authGeneration;
    notifyListeners();
    try {
      await _activate(token, generation);
    } on ApexApiException catch (error) {
      if (error.status == 401 || error.status == 403) await _forget();
    } catch (_) {
      await _forget();
    } finally {
      if (_authActive(generation)) {
        busy = false;
        notifyListeners();
      }
    }
  }

  Future<bool> _activate(String token, int generation) async {
    final accountId = _subject(token);
    final api = HttpApexApi(origin: origin, client: _client, token: token);
    final payloads = await Future.wait([
      api.get('/api/companies'),
      _loadFeatures(api),
    ]);
    if (!_authActive(generation)) return false;
    final assigned = (payloads[0] as List)
        .cast<Json>()
        .map(ApexCompany.fromJson)
        .toList(growable: false);
    companies = List.unmodifiable(assigned);
    features = payloads[1] as Set<String>;
    _token = token;
    _accountId = accountId;
    if (assigned.length == 1) _choose(assigned.single);
    return true;
  }

  Future<void> _remember(String token) async {
    try {
      await _credentials?.write(token);
    } catch (_) {
      // Staying signed in is a convenience; the session still works.
    }
  }

  Future<void> _forget() async {
    try {
      await _credentials?.clear();
    } catch (_) {}
  }

  Future<Set<String>> _loadFeatures(HttpApexApi api) async {
    try {
      final response = await api.get('/api/capabilities') as Json;
      return Set.unmodifiable(
        (response['supported_features'] as List).whereType<String>(),
      );
    } on ApexApiException catch (error) {
      if (error.status == 404) return const {};
      rethrow;
    }
  }

  void chooseCompany(String id) {
    if (!signedIn || busy) return;
    final matches = companies.where((company) => company.id == id);
    if (matches.isEmpty || workspace?.company.id == id) return;
    _choose(matches.single);
    notifyListeners();
  }

  void _choose(ApexCompany company) {
    final authGeneration = _authGeneration;
    final generation = ++_workspaceGeneration;
    bool active() =>
        _authActive(authGeneration) && _workspaceGeneration == generation;
    workspace = WorkspaceContext(
      api: HttpApexApi(
        origin: origin,
        client: _client,
        token: _token,
        companyId: company.id,
        isActive: active,
        onUnauthorized: () => _expire(authGeneration),
      ),
      company: company,
      pending: _pendingFactory(origin, _accountId!, company.id),
      features: features,
      refresh: () async {
        if (!active()) return;
        revision++;
        notifyListeners();
      },
    );
    revision++;
  }

  Future<void> signOut() async {
    final token = _token;
    _clear();
    notifyListeners();
    await _forget();
    if (token == null) return;
    try {
      await HttpApexApi(
        origin: origin,
        client: _client,
        token: token,
      ).post('/api/auth/logout', body: const {});
    } on ApexApiException {
      // The local credential has already been discarded.
    }
  }

  Future<void> verifyPassword(String password) async {
    final token = _token;
    final generation = _authGeneration;
    if (token == null || !features.contains('password_reveal')) {
      throw const ApexApiException(
        message: 'Password verification is unavailable.',
      );
    }
    final response = await HttpApexApi(
      origin: origin,
      client: _client,
      token: token,
      isActive: () => _authActive(generation),
    ).post('/api/auth/verify-password', body: {'password': password});
    if (response is! Json || response['verified'] != true) {
      throw const ApexApiException(message: 'Password could not be verified.');
    }
  }

  void _expire(int generation) {
    if (!_authActive(generation)) return;
    _clear();
    message = 'Your session ended. Sign in to continue.';
    notifyListeners();
    _forget();
  }

  void _clear() {
    _authGeneration++;
    _workspaceGeneration++;
    _token = null;
    _accountId = null;
    busy = false;
    message = null;
    companies = const [];
    features = const {};
    workspace = null;
  }

  bool _authActive(int generation) =>
      !_disposed && generation == _authGeneration;

  static String _subject(String token) {
    final parts = token.split('.');
    if (parts.length != 3) throw const FormatException();
    // Only used to namespace recovery storage after successful API login.
    final decoded = utf8.decode(
      base64Url.decode(base64Url.normalize(parts[1])),
    );
    final subject = (jsonDecode(decoded) as Json)['sub'];
    if (subject is! String || subject.isEmpty) throw const FormatException();
    return subject;
  }

  @override
  void dispose() {
    _disposed = true;
    _clear();
    _client.close();
    super.dispose();
  }
}
