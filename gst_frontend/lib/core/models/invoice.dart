import 'package:equatable/equatable.dart';
import 'package:json_annotation/json_annotation.dart';

part 'invoice.g.dart';

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