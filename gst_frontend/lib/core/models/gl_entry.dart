import 'package:equatable/equatable.dart';
import 'package:json_annotation/json_annotation.dart';

part 'gl_entry.g.dart';

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