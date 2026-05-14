import 'package:json_annotation/json_annotation.dart';

part 'system_info.g.dart';

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
    return SystemInfo(
      totalTenants: json['total_tenants'] as int? ?? 0,
      totalInvoices: json['total_invoices'] as int? ?? 0,
      totalGlEntries: json['total_gl_entries'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => _$SystemInfoToJson(this);
}