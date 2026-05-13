import 'package:equatable/equatable.dart';
import 'package:json_annotation/json_annotation.dart';

part 'user.g.dart';

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