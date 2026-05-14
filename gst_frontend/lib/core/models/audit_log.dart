import 'package:json_annotation/json_annotation.dart';
import 'package:equatable/equatable.dart';

part 'audit_log.g.dart';

@JsonSerializable()
class AuditLogEntry extends Equatable {
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
      tenantId: json['tenant_id'] as String? ?? '',
      actorId: json['actor_id'] as String? ?? '',
      action: json['action'] as String? ?? '',
      resource: json['resource'] as String? ?? '',
      resourceId: json['resource_id'] as String?,
      details: json['details'] is Map
          ? Map<String, dynamic>.from(json['details'])
          : {},
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
    );
  }

  @override
  List<Object?> get props => [id, action, resource];
}