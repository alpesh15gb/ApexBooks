import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gst_frontend/core/theme/app_theme.dart';
import 'package:gst_frontend/core/services/api_service.dart';
import 'package:gst_frontend/core/services/auth_service.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/screens/auth/login_screen.dart';
import 'package:gst_frontend/screens/dashboard/dashboard_screen.dart';
import 'package:gst_frontend/core/constants/app_constants.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await SecureStorageService.init();

  runApp(const ProviderScope(child: GstApp()));
}

class GstApp extends ConsumerWidget {
  const GstApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final isDark = ref.watch(themeProvider);

    return MaterialApp(
      title: 'GST API Engine',
      debugShowCheckedModeBanner: false,
      theme: isDark ? AppTheme.darkTheme : AppTheme.lightTheme,
      home: authState.when(
        loading: () => const Scaffold(body: Center(child: CircularProgressIndicator())),
        authenticated: () => const DashboardScreen(),
        unauthenticated: () => const LoginScreen(),
      ),
      routes: {
        '/login': (ctx) => const LoginScreen(),
        '/dashboard': (ctx) => const DashboardScreen(),
        '/invoices': (ctx) => const InvoiceListScreen(),
        '/parties': (ctx) => const PartyListScreen(),
        '/payments': (ctx) => const PaymentListScreen(),
        '/gst': (ctx) => const GstDashboardScreen(),
        '/settings': (ctx) => const SettingsScreen(),
        '/admin': (ctx) => const AdminDashboardScreen(),
      },
    );
  }
}