import 'package:json_annotation/json_annotation.dart';
import 'package:equatable/equatable.dart';

part 'background_job.g.dart';

@JsonSerializable()
class BackgroundJob extends Equatable {
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

  factory BackgroundJob.fromJson(Map<String, dynamic> json) {
    return BackgroundJob(
      id: json['id'] as String? ?? '',
      jobType: json['job_type'] as String? ?? '',
      status: json['status'] as String? ?? 'unknown',
      payload: json['payload'] is Map
          ? Map<String, dynamic>.from(json['payload'])
          : {},
      result: json['result'] is Map
          ? Map<String, dynamic>.from(json['result'])
          : null,
      error: json['error'] as String?,
      attempts: json['attempts'] as int? ?? 0,
      maxAttempts: json['max_attempts'] as int? ?? 3,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      startedAt: json['started_at'] != null
          ? DateTime.tryParse(json['started_at'] as String)
          : null,
      completedAt: json['completed_at'] != null
          ? DateTime.tryParse(json['completed_at'] as String)
          : null,
    );
  }

  bool get isPending => status == 'pending';
  bool get isProcessing => status == 'processing';
  bool get isCompleted => status == 'completed';
  bool get isFailed => status == 'failed';
  bool get isCancelled => status == 'cancelled';
  bool get isTerminal => isCompleted || isFailed || isCancelled;

  @override
  List<Object?> get props => [id, jobType, status];
}