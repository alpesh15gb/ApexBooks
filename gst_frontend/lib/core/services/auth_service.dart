import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  static const _storage = FlutterSecureStorage();

  static Future<void> init() async {
    // Ensure secure storage is initialized
  }

  static Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: 'gst_access_token', value: accessToken);
    await _storage.write(key: 'gst_refresh_token', value: refreshToken);
  }

  static Future<String?> getAccessToken() async {
    return await _storage.read(key: 'gst_access_token');
  }

  static Future<String?> getRefreshToken() async {
    return await _storage.read(key: 'gst_refresh_token');
  }

  static Future<void> saveTenantId(String tenantId) async {
    await _storage.write(key: 'gst_tenant_id', value: tenantId);
  }

  static Future<String?> getTenantId() async {
    return await _storage.read(key: 'gst_tenant_id');
  }

  static Future<void> clear() async {
    await _storage.delete(key: 'gst_access_token');
    await _storage.delete(key: 'gst_refresh_token');
    await _storage.delete(key: 'gst_tenant_id');
  }

  static bool hasToken() {
    // Synchronous check — used for routing guard
    // In production, use async version
    return true; // Placeholder
  }
}