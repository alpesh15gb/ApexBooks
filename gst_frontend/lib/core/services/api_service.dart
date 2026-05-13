import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';

class ApiService {
  final Dio _dio;

  ApiService({String? baseUrl})
      : _dio = Dio(BaseOptions(
          baseUrl: baseUrl ?? apiBaseUrl,
          connectTimeout: const Duration(milliseconds: 30000),
          receiveTimeout: const Duration(milliseconds: 30000,
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          }));

  // --- Auth ---
  Future<Response> login(Map<String, dynamic> credentials) async {
    return await _dio.post('/auth/login', data: credentials);
  }

  Future<Response> refreshToken(String refreshToken) async {
    return await _dio.post('/auth/refresh', data: {'refresh_token': refreshToken});
  }

  Future<Response> logout() async {
    return await _dio.post('/auth/logout', data: {});
  }

  Future<Response> validateTenant() async {
    return await _dio.post('/tenants/validate');
  }

  // --- Companies / Tenants ---
  Future<Response> registerCompany(Map<String, dynamic> data) async {
    return await _dio.post('/auth/register', data: data);
  }

  // --- Invoices ---
  Future<Response> getInvoices({
    required String kind, // 'sales' or 'purchase'
    String? status,
    int page = 1,
    int perPage = defaultPageSize,
  }) async {
    final params = {'kind': kind, 'page': page, 'per_page': perPage};
    if (status != null) params['status'] = status;
    return await _dio.get('/invoices', queryParameters: params);
  }

  Future<Response> createInvoice(Map<String, dynamic> data) async {
    return await _dio.post('/invoices/${data['kind']}', data: data);
  }

  Future<Response> getInvoice(String invoiceId, String kind) async {
    return await _dio.get('/invoices/$kind/$invoiceId');
  }

  Future<Response> updateInvoice(
      String invoiceId, String kind, Map<String, dynamic> data) async {
    return await _dio.put('/invoices/$kind/$invoiceId', data: data);
  }

  Future<Response> submitInvoice(String invoiceId, String kind) async {
    return await _dio.post('/invoices/$kind/$invoiceId/submit');
  }

  Future<Response> cancelInvoice(String invoiceId) async {
    return await _dio.post('/invoices/sales/$invoiceId/cancel');
  }

  Future<Response> voidInvoice(
      String invoiceId, Map<String, dynamic> payload) async {
    return await _dio.post('/invoices/sales/$invoiceId/void', data: payload);
  }

  Future<Response> amendInvoice(String invoiceId, Map<String, dynamic> data) async {
    return await _dio.post('/invoices/sales/$invoiceId/amend', data: data);
  }

  Future<Response> bulkSubmitInvoices(List<String> invoiceIds) async {
    return await _dio.post('/invoices/sales/bulk-submit',
        data: {'invoice_ids': invoiceIds});
  }

  Future<Response> getInvoicePdf(String invoiceId) async {
    return await _dio.get('/invoices/sales/$invoiceId/pdf');
  }

  Future<Response> checkPdfStatus(String jobId) async {
    return await _dio.get('/invoices/sales/$invoiceId/pdf/status/$jobId');
  }

  Future<Response> getEinvoiceJson(String invoiceId) async {
    return await _dio.get('/invoices/sales/$invoiceId/einvoice');
  }

  Future<Response> pushEinvoice(String invoiceId) async {
    return await _dio.post('/invoices/sales/$invoiceId/einvoice/push');
  }

  // --- Parties ---
  Future<Response> getParties({String? search, String? partyType}) async {
    final params = {};
    if (search != null) params['search'] = search;
    if (partyType != null) params['party_type'] = partyType;
    return await _dio.get('/parties', queryParameters: params);
  }

  Future<Response> createParty(Map<String, dynamic> data) async {
    return await _dio.post('/parties', data: data);
  }

  Future<Response> updateParty(String partyId, Map<String, dynamic> data) async {
    return await _dio.put('/parties/$partyId', data: data);
  }

  Future<Response> deleteParty(String partyId) async {
    return await _dio.delete('/parties/$partyId');
  }

  Future<Response> getPartyLedger(String partyId) async {
    return await _dio.get('/parties/$partyId/ledger');
  }

  Future<Response> getPartyOutstanding(String partyId) async {
    return await _dio.get('/parties/$partyId/outstanding');
  }

  Future<Response> exportParties() async {
    return await _dio.get('/parties/export');
  }

  Future<Response> importParties(List<int> fileBytes) async {
    final formData = FormData();
    formData.files.add(MapEntry('file',
        MultipartFile.fromBytes(fileBytes, filename: 'parties.csv')));
    return await _dio.post('/parties/import', data: formData);
  }

  // --- Items ---
  Future<Response> getItems({String? search}) async {
    final params = {};
    if (search != null) params['search'] = search;
    return await _dio.get('/items', queryParameters: params);
  }

  Future<Response> createItem(Map<String, dynamic> data) async {
    return await _dio.post('/items', data: data);
  }

  Future<Response> updateItem(String itemId, Map<String, dynamic> data) async {
    return await _dio.put('/items/$itemId', data: data);
  }

  Future<Response> deleteItem(String itemId) async {
    return await _dio.delete('/items/$itemId');
  }

  Future<Response> getTaxRates() async {
    return await _dio.get('/items/tax-rates');
  }

  Future<Response> getHSNSearch(String query) async {
    return await _dio.get('/items/hsn-search?q=$query');
  }

  // --- Payments ---
  Future<Response> getPayments() async {
    return await _dio.get('/payments');
  }

  Future<Response> createPayment(Map<String, dynamic> data) async {
    return await _dio.post('/payments', data: data);
  }

  Future<Response> updatePayment(
      String paymentId, Map<String, dynamic> data) async {
    return await _dio.put('/payments/$paymentId', data: data);
  }

  Future<Response> voidPayment(String paymentId) async {
    return await _dio.post('/payments/$paymentId/void');
  }

  Future<Response> reconcilePayment(
      String paymentId, String invoiceId, double amount) async {
    return await _dio
        .post('/payments/$paymentId/reconcile', data: {'invoice_id': invoiceId});
  }

  Future<Response> getUnreconciledPayments() async {
    return await _dio.get('/payments/unreconciled');
  }

  Future<Response> autoReconcilePayments() async {
    return await _dio.post('/payments/auto-reconcile');
  }

  // --- GST ---
  Future<Response> calculateTax(Map<String, dynamic> payload) async {
    return await _dio.post('/gst/tax-calculate', data: payload);
  }

  Future<Response> getGstr1Summary(int month, int year) async {
    return await _dio.get('/gst/gstr1/summary/$month/$year');
  }

  Future<Response> getGstr3b(int month, int year) async {
    return await _dio.get('/gst/gstr3b/compute/$month/$year');
  }

  Future<Response> fileGstr1(int month, int year) async {
    return await _dio.post('/gst/gstr1/file/$month/$year');
  }

  Future<Response> fileGstr3B(int month, int year) async {
    return await _dio.post('/gst/gstr3b/file/$month/$year');
  }

  Future<Response> getGstReconciliation(int month) async {
    return await _dio.get('/gst/reconcile/2a-vs-books/$month');
  }

  Future<Response> getItcAvailable(int month, int year) async {
    return await _dio.get('/gst/itc-available/$month/$year');
  }

  Future<Response> dispatchReconciliation(int month, int year) async {
    return await _dio
        .post('/gst/reconcile/dispatch', data: {'month': month, 'year': year});
  }

  Future<Response> sendNotification(Map<String, dynamic> data) async {
    return await _dio.post('/gst/notify/dispatch', data: data);
  }

  // --- Settings ---
  Future<Response> getSettingsCategories() async {
    return await _dio.get('/settings/categories');
  }

  Future<Response> getSettings({String? category}) async {
    if (category != null) {
      return await _dio.get('/settings/$category');
    }
    return await _dio.get('/settings');
  }

  Future<Response> updateSettings(
      String category, Map<String, dynamic> data) async {
    return await _dio.put('/settings/$category', data: data);
  }

  Future<Response> getGstStatus() async {
    return await _dio.get('/settings/gst/enabled');
  }

  Future<Response> getEinvoiceStatus() async {
    return await _dio.get('/settings/einvoice/enabled');
  }

  Future<Response> getEwaybillStatus() async {
    return await _dio.get('/settings/ewaybill/enabled');
  }

  Future<Response> getInvoiceNumbering(String kind) async {
    return await _dio.get('/settings/invoice-numbering?kind=$kind');
  }

  // --- Admin ---
  Future<Response> getAuditLogs({
    String? resource,
    String? action,
    String? actorId,
    int limit = 100,
    int offset = 0,
    String? startDate,
    String? endDate,
  }) async {
    final params = {
      'limit': limit.toString(),
      'offset': offset.toString(),
      if (resource != null) 'resource': resource,
      if (action != null) 'action': action,
      if (actorId != null) 'actor_id': actorId,
      if (startDate != null) 'start_date': startDate,
      if (endDate != null) 'end_date': endDate,
    };
    return await _dio.get('/admin/audit-logs', queryParameters: params);
  }

  Future<Response> getAuditSummary({int days = 7}) async {
    return await _dio.get('/admin/audit-logs/summary?days=$days');
  }

  Future<Response> getBackgroundJobs(
      {String? jobType, String? status, int limit = 50}) async {
    final params = {};
    if (jobType != null) params['job_type'] = jobType;
    if (status != null) params['status'] = status;
    params['limit'] = limit.toString();
    return await _dio.get('/admin/jobs', queryParameters: params);
  }

  Future<Response> getJobStatus(String jobId) async {
    return await _dio.get('/admin/jobs/$jobId');
  }

  Future<Response> cancelJob(String jobId) async {
    return await _dio.delete('/admin/jobs/$jobId');
  }

  Future<Response> getQueueStats() async {
    return await _dio.get('/admin/queue/stats');
  }

  Future<Response> getPendingWebhooks() async {
    return await _dio.get('/admin/webhooks/pending');
  }

  Future<Response> retryWebhook(int deliveryId) async {
    return await _dio.post('/admin/webhooks/$deliveryId/retry');
  }

  Future<Response> getFailedWebhooks() async {
    return await _dio.get('/admin/webhooks/failed');
  }

  Future<Response> getTenantActivity({int days = 7}) async {
    return await _dio.get('/admin/activity?days=$days');
  }

  Future<Response> getSystemInfo() async {
    return await _dio.get('/admin/system-info');
  }

  // Interceptors for auth token injection & refresh
  setAuthToken(String token) {
    _dio.options.headers['Authorization'] = 'Bearer $token';
  }

  clearAuthToken() {
    _dio.options.headers.remove('Authorization');
  }

  Future<Response> requestWithRetry(RequestOptions requestOptions) async {
    try {
      return await _dio.fetch(requestOptions);
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        // Token may need refresh — handled at auth layer
        rethrow;
      }
      rethrow;
    }
  }
}