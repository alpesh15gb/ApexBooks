import 'package:equatable/equatable.dart';
import 'package:json_annotation/json_annotation.dart';

part 'invoice.g.dart';
part 'party.g.dart';
part 'payment.g.dart';
part 'gl_entry.g.dart';
part 'user.g.dart';

/// User / Principal
@JsonSerializable()
class User extends Equatable {
  final String userId;
  final String email;
  final String fullName;
  final List<String> roles;
  final List<String> permissions;

  const User({
    required this.userId,
    required this.email,
    required this.fullName,
    this.roles = const [],
    this.permissions = const [],
  });

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
  Map<String, dynamic> toJson() => _$UserToJson(this);

  @override
  List<Object?> get props => [userId, email, fullName, roles, permissions];
}

/// Auth Token Response
@JsonSerializable()
class AuthTokens {
  final String accessToken;
  final String refreshToken;
  final String tokenType;

  const AuthTokens({
    required this.accessToken,
    required this.refreshToken,
    this.tokenType = 'bearer',
  });

  factory AuthTokens.fromJson(Map<String, dynamic> json) =>
      _$AuthTokensFromJson(json);
  Map<String, dynamic> toJson() => _$AuthTokensToJson(this);
}

/// Login Request
@JsonSerializable()
class LoginRequest {
  final String username;
  final String password;

  const LoginRequest({required this.username, required this.password});

  Map<String, dynamic> toJson() => _$LoginRequestToJson(this);
}

/// Invoice
@JsonSerializable()
class Invoice extends Equatable {
  final String invoiceId;
  final String invoiceNumber;
  final String invoiceKind; // 'sales' | 'purchase'
  final String invoiceType;
  final String status;
  final DateTime invoiceDate;
  final DateTime? dueDate;
  final String partyId;
  final String? partyGstin;
  final String placeOfSupply;
  final String supplyType;
  final String paymentStatus;
  final double subtotal;
  final double totalDiscount;
  final double totalCgst;
  final double totalSgst;
  final double totalIgst;
  final double totalCess;
  final double roundOff;
  final double grandTotal;
  final double amountPaid;
  final double outstandingAmount;
  final List<InvoiceLine> lines;

  const Invoice({
    required this.invoiceId,
    required this.invoiceNumber,
    required this.invoiceKind,
    required this.invoiceType,
    required this.status,
    required this.invoiceDate,
    this.dueDate,
    required this.partyId,
    this.partyGstin,
    required this.placeOfSupply,
    required this.supplyType,
    required this.paymentStatus,
    required this.subtotal,
    required this.totalDiscount,
    required this.totalCgst,
    required this.totalSgst,
    required this.totalIgst,
    required this.totalCess,
    required this.roundOff,
    required this.grandTotal,
    required this.amountPaid,
    required this.outstandingAmount,
    this.lines = const [],
  });

  factory Invoice.fromJson(Map<String, dynamic> json) =>
      _$InvoiceFromJson(json);
  Map<String, dynamic> toJson() => _$InvoiceToJson(this);

  bool get isDraft => status == 'Draft';
  bool get isSubmitted => status == 'Submitted';
  bool get isPaid => status == 'Paid';
  bool get isPartPaid => status == 'Part Paid';
  bool get isCancelled => status == 'Cancelled';
  bool get isVoided => status == 'Voided';
  bool get isPendingPayment => isSubmitted || isPartPaid;

  bool get isSales => invoiceKind == 'sales';
  bool get isPurchase => invoiceKind == 'purchase';

  @override
  List<Object?> get props => [invoiceId, invoiceNumber, status, grandTotal];
}

/// Invoice Line
@JsonSerializable()
class InvoiceLine extends Equatable {
  final int lineNo;
  final String? itemId;
  final String itemCode;
  final String itemName;
  final String? hsnCode;
  final String? sacCode;
  final double quantity;
  final String unit;
  final double unitPrice;
  final double discountAmount;
  final double taxableValue;
  final double gstRate;
  final double cgstAmount;
  final double sgstAmount;
  final double igstAmount;
  final double cessAmount;
  final double totalAmount;

  const InvoiceLine({
    required this.lineNo,
    this.itemId,
    required this.itemCode,
    required this.itemName,
    this.hsnCode,
    this.sacCode,
    required this.quantity,
    required this.unit,
    required this.unitPrice,
    required this.discountAmount,
    required this.taxableValue,
    required this.gstRate,
    required this.cgstAmount,
    required this.sgstAmount,
    required this.igstAmount,
    required this.cessAmount,
    required this.totalAmount,
  });

  factory InvoiceLine.fromJson(Map<String, dynamic> json) =>
      _$InvoiceLineFromJson(json);
  Map<String, dynamic> toJson() => _$InvoiceLineToJson(this);

  @override
  List<Object?> get props => [lineNo, itemName, totalAmount];
}

/// Party
@JsonSerializable()
class Party extends Equatable {
  final String partyId;
  final String partyName;
  final String partyType;
  final String? gstin;
  final String? pan;
  final String? stateCode;
  final String? partyCategory;
  final double creditLimit;
  final int creditDays;
  final double openingBalance;
  final bool tdsApplicable;
  final List<Map<String, dynamic>> addresses;
  final List<Map<String, dynamic>> contacts;
  final List<Map<String, dynamic>> bankAccounts;

  const Party({
    required this.partyId,
    required this.partyName,
    required this.partyType,
    this.gstin,
    this.pan,
    this.stateCode,
    this.partyCategory,
    this.creditLimit = 0,
    this.creditDays = 0,
    this.openingBalance = 0,
    this.tdsApplicable = false,
    this.addresses = const [],
    this.contacts = const [],
    this.bankAccounts = const [],
  });

  factory Party.fromJson(Map<String, dynamic> json) => _$PartyFromJson(json);
  Map<String, dynamic> toJson() => _$PartyToJson(this);

  bool get isCustomer => partyType == 'Customer';
  bool get isSupplier => partyType == 'Supplier';

  String get displayName =>
      gstin != null && gstin!.isNotEmpty ? '$partyName ($gstin)' : partyName;

  @override
  List<Object?> get props => [partyId, partyName, partyType];
}

/// Payment
@JsonSerializable()
class Payment extends Equatable {
  final String paymentId;
  final String paymentType; // 'Receive' | 'Make'
  final String paymentMode;
  final DateTime paymentDate;
  final String partyId;
  final double amount;
  final double tdsAmount;
  final double netAmount;
  final String referenceNo;
  final String narration;
  final String status;
  final List<Map<String, dynamic>> allocations;

  const Payment({
    required this.paymentId,
    required this.paymentType,
    required this.paymentMode,
    required this.paymentDate,
    required this.partyId,
    required this.amount,
    required this.tdsAmount,
    required this.netAmount,
    required this.referenceNo,
    required this.narration,
    required this.status,
    this.allocations = const [],
  });

  factory Payment.fromJson(Map<String, dynamic> json) =>
      _$PaymentFromJson(json);
  Map<String, dynamic> toJson() => _$PaymentToJson(this);

  bool get isReceived => paymentType == 'Receive';
  bool get isMade => paymentType == 'Make';
  bool get isReconciled => status == 'Reconciled';
  bool get isVoided => status == 'Voided';

  @override
  List<Object?> get props => [paymentId, paymentType, amount];
}

/// GL Entry
@JsonSerializable()
class GLEntry extends Equatable {
  final String id;
  final DateTime postingDate;
  final String account;
  final String? partyId;
  final String voucherType;
  final String voucherId;
  final double debit;
  final double credit;
  final String remarks;

  const GLEntry({
    required this.id,
    required this.postingDate,
    required this.account,
    this.partyId,
    required this.voucherType,
    required this.voucherId,
    required this.debit,
    required this.credit,
    this.remarks = '',
  });

  factory GLEntry.fromJson(Map<String, dynamic> json) =>
      _$GLEntryFromJson(json);

  double get net => debit - credit;
  bool get isDebit => debit > 0;

  @override
  List<Object?> get props => [id, account, debit, credit];
}

/// GSTR-1 Summary Bucket
@JsonSerializable()
class Gstr1Bucket {
  final int count;
  final double taxable;
  final double tax;
  final double total;

  const Gstr1Bucket({
    this.count = 0,
    this.taxable = 0,
    this.tax = 0,
    this.total = 0,
  });

  factory Gstr1Bucket.fromJson(Map<String, dynamic> json) {
    final val = json is Map ? json : {};
    return Gstr1Bucket(
      count: val['count'] ?? 0,
      taxable: (val['taxable'] is num ? val['taxable'] : 0).toDouble(),
      tax: (val['tax'] is num ? val['tax'] : 0).toDouble(),
      total: (val['total'] is num ? val['total'] : 0).toDouble(),
    );
  }
}

/// GSTR-3B Summary
@JsonSerializable()
class Gstr3bSummary {
  final Gstr3bSection supDetails;
  final Gstr3bSection itcElg;

  const Gstr3bSummary({
    required this.supDetails,
    required this.itcElg,
  });

  factory Gstr3bSummary.fromJson(Map<String, dynamic> json) {
    final data = json is Map ? json : {};
    return Gstr3bSummary(
      supDetails: Gstr3bSection.fromJson(data['sup_details'] ?? {}),
      itcElg: Gstr3bSection.fromJson(data['itc_elg'] ?? {}),
    );
  }
}

@JsonSerializable()
class Gstr3bSection {
  final double txval;
  final double iamt;
  final double camt;
  final double samt;
  final double csamt;

  const Gstr3bSection({
    this.txval = 0,
    this.iamt = 0,
    this.camt = 0,
    this.samt = 0,
    this.csamt = 0,
  });

  factory Gstr3bSection.fromJson(Map<String, dynamic> json) {
    final data = json is Map ? json : {};
    double val(String key) =>
        data[key] is num ? (data[key] as num).toDouble() : 0;
    return Gstr3bSection(
      txval: val('txval'),
      iamt: val('iamt'),
      camt: val('camt'),
      samt: val('samt'),
      csamt: val('csamt'),
    );
  }

  double get totalTax => iamt + camt + samt + csamt;
}

/// Audit Log Entry
@JsonSerializable()
class AuditLogEntry {
  final int? id;
  final String tenantId;
  final String actorId;
  final String action;
  final String resource;
  final String? resourceId;
  final Map<String, dynamic> details;
  final DateTime? createdAt;

  const AuditLogEntry({
    this.id,
    required this.tenantId,
    required this.actorId,
    required this.action,
    required this.resource,
    this.resourceId,
    this.details = const {},
    this.createdAt,
  });

  factory AuditLogEntry.fromJson(Map<String, dynamic> json) {
    return AuditLogEntry(
      id: json['id'] as int?,
      tenantId: json['tenant_id'] ?? '',
      actorId: json['actor_id'] ?? '',
      action: json['action'] ?? '',
      resource: json['resource'] ?? '',
      resourceId: json['resource_id'] as String?,
      details: json['details'] is Map
          ? Map<String, dynamic>.from(json['details'])
          : {},
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'])
          : null,
    );
  }
}

/// Background Job
@JsonSerializable()
class BackgroundJob {
  final String id;
  final String jobType;
  final String status;
  final Map<String, dynamic> payload;
  final Map<String, dynamic>? result;
  final String? error;
  final int attempts;
  final int maxAttempts;
  final DateTime? createdAt;
  final DateTime? startedAt;
  final DateTime? completedAt;

  const BackgroundJob({
    required this.id,
    required this.jobType,
    required this.status,
    this.payload = const {},
    this.result,
    this.error,
    this.attempts = 0,
    this.maxAttempts = 3,
    this.createdAt,
    this.startedAt,
    this.completedAt,
  });

  factory BackgroundJob.fromJson(Map<String, dynamic> json) =>
      _$BackgroundJobFromJson(json);

  bool get isPending => status == 'pending';
  bool get isProcessing => status == 'processing';
  bool get isCompleted => status == 'completed';
  bool get isFailed => status == 'failed';
  bool get isCancelled => status == 'cancelled';
  bool get isTerminal => isCompleted || isFailed || isCancelled;
  double get progress => maxAttempts > 0 ? attempts / maxAttempts : 0;
}

/// System Info
@JsonSerializable()
class SystemInfo {
  final int totalTenants;
  final int totalInvoices;
  final int totalGlEntries;

  const SystemInfo({
    this.totalTenants = 0,
    this.totalInvoices = 0,
    this.totalGlEntries = 0,
  });

  factory SystemInfo.fromJson(Map<String, dynamic> json) {
    final data = json is Map ? json : {};
    return SystemInfo(
      totalTenants: data['total_tenants'] ?? 0,
      totalInvoices: data['total_invoices'] ?? 0,
      totalGlEntries: data['total_gl_entries'] ?? 0,
    );
  }
}