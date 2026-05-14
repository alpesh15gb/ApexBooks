import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/services/api_service.dart';
import 'package:gst_frontend/core/services/auth_service.dart';
import 'package:gst_frontend/core/models/invoice.dart';
import 'package:gst_frontend/core/models/party.dart';
import 'package:gst_frontend/core/models/payment.dart';
import 'package:gst_frontend/core/models/gl_entry.dart';
import 'package:gst_frontend/core/models/user.dart';
import 'package:gst_frontend/core/models/system_info.dart';
import 'package:gst_frontend/core/models/audit_log.dart';
import 'package:gst_frontend/core/models/background_job.dart';
import 'package:gst_frontend/core/models/gstr.dart';
import 'package:gst_frontend/core/theme/app_theme.dart';

// -- API Provider --
final apiProvider = Provider<ApiService>((ref) {
  return ApiService();
});

// -- Auth Provider --
enum AuthStatus { loading, authenticated, unauthenticated }

class AuthState {
  final AuthStatus status;
  final User? user;
  final String? error;

  const AuthState({this.status = AuthStatus.loading, this.user, this.error});

  AuthState copyWith({AuthStatus? status, User? user, String? error}) {
    return AuthState(
      status: status ?? this.status,
      user: user ?? this.user,
      error: error,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiService _api;

  AuthNotifier(this._api) : super(const AuthState()) {
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    final token = await AuthService.getAccessToken();
    final tenantId = await AuthService.getTenantId();
    if (token != null && tenantId != null) {
      _api.setAuthToken(token);
      state = state.copyWith(status: AuthStatus.authenticated);
    } else {
      state = state.copyWith(status: AuthStatus.unauthenticated);
    }
  }

  Future<bool> login(String username, String password) async {
    try {
      final response = await _api.login({'username': username, 'password': password});
      final data = response.data as Map<String, dynamic>;
      final accessToken = data['access_token'] as String;
      final refreshToken = data['refresh_token'] as String;
      final tenantId = data['tenant_id'] as String;
      await AuthService.saveTokens(accessToken: accessToken, refreshToken: refreshToken);
      await AuthService.saveTenantId(tenantId);
      _api.setAuthToken(accessToken);
      final userData = data['user'] as Map<String, dynamic>? ?? {};
      final user = User.fromJson(userData);
      state = state.copyWith(status: AuthStatus.authenticated, user: user);
      return true;
    } catch (e) {
      state = state.copyWith(error: e.toString());
      return false;
    }
  }

  Future<void> logout() async {
    try {
      await _api.logout();
    } catch (_) {}
    await AuthService.clear();
    _api.clearAuthToken();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref.read(apiProvider));
});

// -- Theme Provider --
class ThemeNotifier extends StateNotifier<bool> {
  ThemeNotifier() : super(false);
  void toggle() => state = !state;
}

final themeProvider = StateNotifierProvider<ThemeNotifier, bool>((ref) {
  return ThemeNotifier();
});

// -- Invoice Provider (family by kind) --
final invoiceListProvider =
    StateNotifierProvider.autoDispose
        .family<InvoiceListNotifier, AsyncValue<List<Invoice>>, String>(
  (ref, kind) => InvoiceListNotifier(ref.read(apiProvider), kind: kind),
);

class InvoiceListNotifier extends StateNotifier<AsyncValue<List<Invoice>>> {
  final ApiService _api;
  final String _kind;

  InvoiceListNotifier(this._api, {required String kind})
      : _kind = kind,
        super(const AsyncValue.loading()) {
    fetchInvoices();
  }

  Future<void> fetchInvoices({String? status}) async {
    state = const AsyncValue.loading();
    try {
      final response = await _api.getInvoices(kind: _kind, status: status);
      final data = response.data as Map<String, dynamic>;
      final results = data['results'] as List<dynamic>;
      final invoices = results.map((e) => Invoice.fromJson(e)).toList();
      state = AsyncValue.data(invoices);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}

// -- Party Provider --
final partyListProvider =
    StateNotifierProvider<PartyListNotifier, AsyncValue<List<Party>>>((ref) {
  return PartyListNotifier(ref.read(apiProvider));
});

class PartyListNotifier extends StateNotifier<AsyncValue<List<Party>>> {
  final ApiService _api;

  PartyListNotifier(this._api) : super(const AsyncValue.loading()) {
    fetchParties();
  }

  Future<void> fetchParties() async {
    state = const AsyncValue.loading();
    try {
      final response = await _api.getParties();
      final data = response.data as Map<String, dynamic>;
      final results = data['results'] as List<dynamic>;
      final parties = results.map((e) => Party.fromJson(e)).toList();
      state = AsyncValue.data(parties);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}

// -- Payment Provider --
final paymentListProvider =
    StateNotifierProvider<PaymentListNotifier, AsyncValue<List<Payment>>>(
        (ref) => PaymentListNotifier(ref.read(apiProvider)));

class PaymentListNotifier extends StateNotifier<AsyncValue<List<Payment>>> {
  final ApiService _api;

  PaymentListNotifier(this._api) : super(const AsyncValue.loading()) {
    fetchPayments();
  }

  Future<void> fetchPayments() async {
    state = const AsyncValue.loading();
    try {
      final response = await _api.getPayments();
      final data = response.data as Map<String, dynamic>;
      final results = data['results'] as List<dynamic>? ?? [];
      final payments = results.map((e) => Payment.fromJson(e)).toList();
      state = AsyncValue.data(payments);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}

// -- GST Provider --
final gstr1Provider =
    StateNotifierProvider<Gstr1Notifier, AsyncValue<Gstr3bSummary>>((ref) {
  return Gstr1Notifier(ref.read(apiProvider));
});

class Gstr1Notifier extends StateNotifier<AsyncValue<Gstr3bSummary>> {
  final ApiService _api;

  Gstr1Notifier(this._api) : super(const AsyncValue.loading());

  Future<void> loadSummary(int month, int year) async {
    state = const AsyncValue.loading();
    try {
      final response = await _api.getGstr1Summary(month, year);
      final data = response.data['tables'] as Map<String, dynamic>;
      final b2b = Gstr1Bucket.fromJson(data['B2B'] ?? {});
      final summary = Gstr3bSummary(
        supDetails: Gstr3bSection(txval: b2b.taxable, iamt: b2b.tax),
        itcElg: const Gstr3bSection(),
      );
      state = AsyncValue.data(summary);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }
}

// -- System Info Provider --
final systemInfoProvider = FutureProvider<SystemInfo>((ref) async {
  final api = ref.read(apiProvider);
  final response = await api.getSystemInfo();
  return SystemInfo.fromJson(response.data as Map<String, dynamic>);
});

// -- Audit Logs Provider --
final auditLogsProvider = FutureProvider<List<AuditLogEntry>>((ref) async {
  final api = ref.read(apiProvider);
  final response = await api.getAuditLogs(limit: 50);
  final data = response.data as Map<String, dynamic>;
  final logs = data['logs'] as List<dynamic>;
  return logs.map((e) => AuditLogEntry.fromJson(e as Map<String, dynamic>)).toList();
});

// -- Background Jobs Provider --
final backgroundJobsProvider = FutureProvider<List<BackgroundJob>>((ref) async {
  final api = ref.read(apiProvider);
  final response = await api.getBackgroundJobs();
  final data = response.data as Map<String, dynamic>;
  final jobs = data['jobs'] as List<dynamic>;
  return jobs.map((e) => BackgroundJob.fromJson(e as Map<String, dynamic>)).toList();
});