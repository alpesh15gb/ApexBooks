import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'workspace.dart';

const configuredApiOrigin = String.fromEnvironment('APEX_API_ORIGIN');

Uri apiOrigin() {
  if (configuredApiOrigin.isNotEmpty) return Uri.parse(configuredApiOrigin);
  if (kIsWeb) return Uri.parse(Uri.base.origin);
  if (kDebugMode) {
    return Uri.parse(
      defaultTargetPlatform == TargetPlatform.android
          ? 'http://10.0.2.2:8012'
          : 'http://127.0.0.1:8012',
    );
  }
  throw StateError('Configure APEX_API_ORIGIN when building for this device.');
}

class HttpApexApi implements ApexApi, ApexWriteApi {
  HttpApexApi({
    required this.origin,
    required this._client,
    this._token,
    this.companyId,
    this._isActive,
    this._onUnauthorized,
    this.timeout = const Duration(seconds: 25),
  }) {
    if (!origin.hasAuthority ||
        origin.host.isEmpty ||
        origin.userInfo.isNotEmpty ||
        origin.hasQuery ||
        origin.hasFragment ||
        (origin.path.isNotEmpty && origin.path != '/') ||
        (origin.scheme != 'https' &&
            !(origin.scheme == 'http' &&
                const {
                  'localhost',
                  '127.0.0.1',
                  '::1',
                  '10.0.2.2',
                }.contains(origin.host)))) {
      throw ArgumentError(
        'Use an HTTPS API origin or a local development API.',
      );
    }
  }

  final Uri origin;
  final http.Client _client;
  final String? _token;
  final bool Function()? _isActive;
  final void Function()? _onUnauthorized;
  final String? companyId;
  final Duration timeout;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      _json('GET', path, query: query);

  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => _json('POST', path, body: body, idempotencyKey: idempotencyKey);

  @override
  Future<dynamic> put(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => _json('PUT', path, body: body, idempotencyKey: idempotencyKey);

  @override
  Future<dynamic> patch(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) => _json('PATCH', path, body: body, idempotencyKey: idempotencyKey);

  @override
  Future<dynamic> delete(String path, {Map<String, String>? query}) =>
      _json('DELETE', path, query: query);

  Future<dynamic> uploadBytes(
    String path,
    Uint8List bytes, {
    String method = 'PUT',
    Map<String, String>? query,
    String contentType = 'application/octet-stream',
    String? idempotencyKey,
  }) async {
    final response = await _request(
      method,
      path,
      query: query,
      raw: bytes,
      contentType: contentType,
      idempotencyKey: idempotencyKey,
    );
    if (response.statusCode == 204) return null;
    try {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw const ApexApiException(
        message: 'The upload could not be confirmed. Retry the same operation.',
      );
    }
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async {
    final response = await _request('GET', path, query: query, accept: '*/*');
    final contentType = response.headers['content-type'] ?? '';
    if (contentType.startsWith('text/html') || response.bodyBytes.isEmpty) {
      throw const ApexApiException(message: 'The file is not available.');
    }
    return response.bodyBytes;
  }

  Future<dynamic> _json(
    String method,
    String path, {
    Map<String, String>? query,
    Json? body,
    String? idempotencyKey,
  }) async {
    final response = await _request(
      method,
      path,
      query: query,
      body: body,
      idempotencyKey: idempotencyKey,
    );
    if (response.statusCode == 204) return null;
    try {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      throw ApexApiException(
        message: method == 'GET'
            ? 'The API returned an unreadable response.'
            : 'The API could not confirm the save. Retry the same operation.',
      );
    }
  }

  Future<http.Response> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Json? body,
    Uint8List? raw,
    String? contentType,
    String? idempotencyKey,
    String accept = 'application/json',
  }) async {
    final destination = _destination(method, path, query);
    final timeLimit = method == 'POST' && path.endsWith('/ocr/purchase-draft')
        ? const Duration(seconds: 55)
        : timeout;
    _requireActive();
    final abort = Completer<void>();
    final request = http.AbortableRequest(
      method,
      destination,
      abortTrigger: abort.future,
    )..followRedirects = false;
    request.headers['Accept'] = accept;
    if (_token != null) request.headers['Authorization'] = 'Bearer $_token';
    if (body != null) {
      request.headers['Content-Type'] = 'application/json; charset=utf-8';
      request.bodyBytes = utf8.encode(jsonEncode(body));
    } else if (raw != null) {
      request.headers['Content-Type'] = contentType!;
      request.bodyBytes = raw;
    }
    if (idempotencyKey != null) {
      request.headers['Idempotency-Key'] = idempotencyKey;
    }

    late final http.Response response;
    try {
      response = await _client
          .send(request)
          .then(http.Response.fromStream)
          .timeout(
            timeLimit,
            onTimeout: () {
              abort.complete();
              throw TimeoutException('API request timed out');
            },
          );
    } on TimeoutException {
      throw ApexApiException(
        status: 408,
        message: method == 'GET'
            ? 'The request timed out. Please retry.'
            : 'The API could not confirm the save. Retry the same operation.',
      );
    } on http.ClientException {
      throw ApexApiException(
        message: method == 'GET'
            ? 'Couldn’t connect to Apex Books. Please retry.'
            : 'Connection lost before confirmation. Retry the same operation.',
      );
    }
    _requireActive(method);
    final status = response.statusCode;
    if (status >= 200 && status < 300) return response;

    String? detail;
    try {
      final payload = jsonDecode(utf8.decode(response.bodyBytes));
      if (payload is Map && payload['detail'] is String) {
        detail = payload['detail'] as String;
      }
    } on FormatException {
      // Upstream errors can be HTML. Do not display internal server output.
    }
    if (status == 401 && detail != 'Current password is incorrect') {
      _onUnauthorized?.call();
    }
    throw ApexApiException(
      status: status,
      code: response.headers['x-apex-error'],
      message: status >= 500
          ? (method == 'GET'
                ? 'Apex Books is temporarily unavailable. Please retry.'
                : 'The API could not confirm the save. Retry the same operation.')
          : detail ??
                switch (status) {
                  401 => 'Please sign in again.',
                  403 => 'You don’t have access to this company or action.',
                  429 => 'Too many requests. Wait a moment and try again.',
                  _ => 'The API rejected this request (HTTP $status).',
                },
    );
  }

  Uri _destination(String method, String path, Map<String, String>? query) {
    // API callers supply literal paths and query parameters independently.
    if (!path.startsWith('/api/') || path.contains(RegExp(r'[?#\\]'))) {
      throw ArgumentError('Invalid API path.');
    }
    final parts = path
        .substring(1)
        .split('/')
        .map(Uri.decodeComponent)
        .toList();
    if (parts.any(
      (part) =>
          part.isEmpty ||
          part == '.' ||
          part == '..' ||
          part.contains(RegExp(r'[/\\%\x00-\x1F\x7F]')),
    )) {
      throw ArgumentError('Invalid API path.');
    }
    final id = companyId;
    if (id != null &&
        (method != 'GET' || path != '/api/ocr/status') &&
        (parts.length < 3 || parts[1] != 'companies' || parts[2] != id)) {
      throw const ApexApiException(
        message: 'This request belongs to a different company.',
        status: 403,
      );
    }
    return origin.replace(pathSegments: parts, queryParameters: query);
  }

  void _requireActive([String? method]) {
    if (_isActive?.call() == false) {
      throw ApexApiException(
        message: 'The active account or company changed.',
        // A rejected send is definitive; a switched workspace after POST
        // leaves the original operation available for recovery.
        status: method != null && method != 'GET' ? null : 403,
      );
    }
  }
}
