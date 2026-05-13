import 'package:equatable/equatable.dart';
import 'package:json_annotation/json_annotation.dart';

part 'party.g.dart';

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