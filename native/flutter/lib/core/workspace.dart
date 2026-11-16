import 'dart:typed_data';

typedef Json = Map<String, dynamic>;

abstract interface class ApexApi {
  Future<dynamic> get(String path, {Map<String, String>? query});
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  });
  Future<Uint8List> download(String path, {Map<String, String>? query});
}

abstract interface class ApexWriteApi {
  Future<dynamic> put(
    String path, {
    required Json body,
    String? idempotencyKey,
  });
  Future<dynamic> patch(
    String path, {
    required Json body,
    String? idempotencyKey,
  });
  Future<dynamic> delete(String path, {Map<String, String>? query});
}

extension ApexApiWrites on ApexApi {
  ApexWriteApi get _writer {
    final api = this;
    if (api is ApexWriteApi) return api as ApexWriteApi;
    throw const ApexApiException(
      message: 'This connection does not support the selected action.',
    );
  }

  Future<dynamic> put(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async => _writer.put(path, body: body, idempotencyKey: idempotencyKey);
  Future<dynamic> patch(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async => _writer.patch(path, body: body, idempotencyKey: idempotencyKey);
  Future<dynamic> delete(String path, {Map<String, String>? query}) async =>
      _writer.delete(path, query: query);
}

class ApexApiException implements Exception {
  const ApexApiException({required this.message, this.status, this.code});

  final int? status;
  final String? code;
  final String message;

  bool get uncertain =>
      status == null || status == 408 || status == 429 || status! >= 500;

  @override
  String toString() => message;
}

class ApexCompany {
  const ApexCompany({
    required this.id,
    required this.name,
    required this.role,
    this.stateCode = '',
    this.taxMode = '',
    this.gstin = '',
    this.address = '',
    this.bookLabel = '',
  });

  factory ApexCompany.fromJson(Json json) => ApexCompany(
    id: json['id'] as String,
    name: json['name'] as String,
    role: json['role'] as String? ?? '',
    stateCode: json['state_code'] as String? ?? '',
    taxMode: json['tax_mode'] as String? ?? '',
    gstin: json['gstin'] as String? ?? '',
    address: json['address'] as String? ?? '',
    bookLabel: json['book_label'] as String? ?? '',
  );

  final String id;
  final String name;
  final String role;
  final String stateCode;
  final String taxMode;
  final String gstin;
  final String address;
  final String bookLabel;

  bool get canWrite => role == 'owner' || role == 'editor';

  String get _label =>
      bookLabel.trim().isEmpty ? name : '$name · ${bookLabel.trim()}';

  String displayName([Iterable<ApexCompany> companies = const []]) {
    final matches = companies.where(
      (company) =>
          company._label.trim().toLowerCase() == _label.trim().toLowerCase(),
    );
    if (matches.length < 2) return _label;
    final shortId = id.length > 8 ? id.substring(id.length - 8) : id;
    final suffix =
        matches.where((company) => company.id.endsWith(shortId)).length > 1
        ? id
        : shortId;
    return '$_label · Book $suffix';
  }
}

abstract interface class PendingStore {
  Future<Json?> load(String operation);
  Future<void> save(String operation, Json data);
  Future<void> clear(String operation);
}

class WorkspaceContext {
  const WorkspaceContext({
    required this.api,
    required this.company,
    required this.pending,
    required this.features,
    required this.refresh,
  });

  final ApexApi api;
  final ApexCompany company;
  final PendingStore pending;
  final Set<String> features;
  final Future<void> Function() refresh;

  String get path => '/api/companies/${company.id}';
}

DateTime businessToday([DateTime? clock]) => (clock ?? DateTime.now())
    .toUtc()
    .add(const Duration(hours: 5, minutes: 30));

String businessDate([DateTime? clock]) =>
    businessToday(clock).toIso8601String().substring(0, 10);
