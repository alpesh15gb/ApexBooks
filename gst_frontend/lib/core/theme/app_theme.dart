import 'dart:io';
import 'package:flutter/material.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';

class AppTheme {
  // Color palette inspired by Indian GST portal (saffron + green)
  static const Color _primarySaffron = Color(0xFFFF6B35);
  static const Color _primaryGreen = Color(0xFF10B981);
  static const Color _bgLight = Color(0xFFF8FAFC);
  static const Color _bgDark = Color(0xFF0F172A);
  static const Color _surfaceLight = Colors.white;
  static const Color _surfaceDark = Color(0xFF1E293B);

  static ThemeData lightTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    colorSchemeSeed: _primarySaffron,
    scaffoldBackgroundColor: _bgLight,
    appBarTheme: const AppBarTheme(
      backgroundColor: _primarySaffron,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
    ),
    cardTheme: CardTheme(
      color: _surfaceLight,
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: _primarySaffron,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xFFF1F5F9),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
    ),
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      selectedItemColor: _primarySaffron,
      unselectedItemColor: Colors.grey,
      backgroundColor: Colors.white,
    ),
  );

  static ThemeData darkTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorSchemeSeed: _primaryGreen,
    scaffoldBackgroundColor: _bgDark,
    appBarTheme: const AppBarTheme(
      backgroundColor: _surfaceDark,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
    ),
    cardTheme: CardTheme(
      color: _surfaceDark,
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xFF334155),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
    ),
  );
}