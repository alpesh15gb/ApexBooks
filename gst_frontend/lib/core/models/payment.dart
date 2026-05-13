import 'package:equatable/equatable.dart';
import 'package:json_annotation/json_annotation.dart';

part 'payment.g.dart';

@JsonSerializable()
class Payment extends Equatable {
  final String paymentId;
  final String paymentType;
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