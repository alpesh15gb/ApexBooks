import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:gst_frontend/core/theme/app_theme.dart';
import 'package:gst_frontend/core/services/api_service.dart';
import 'package:gst_frontend/core/services/auth_service.dart';
import 'package:gst_frontend/providers/app_providers.dart';
import 'package:gst_frontend/screens/auth/login_screen.dart';
import 'package:gst_frontend/screens/auth/register_screen.dart';
import 'package:gst_frontend/screens/dashboard/dashboard_screen.dart';
import 'package:gst_frontend/screens/invoices/invoice_list_screen.dart';
import 'package:gst_frontend/screens/invoices/invoice_detail_screen.dart';
import 'package:gst_frontend/screens/parties/party_list_screen.dart';
import 'package:gst_frontend/screens/payments/payment_list_screen.dart';
import 'package:gst_frontend/screens/settings/settings_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  await AuthService.init();

  runApp(const ProviderScope(child: GstApp()));
}

class GstApp extends ConsumerWidget {
  const GstApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final isDark = ref.watch(themeProvider);

    Widget homeWidget;
    if (authState.status == AuthStatus.loading) {
      homeWidget = const Scaffold(body: Center(child: CircularProgressIndicator()));
    } else if (authState.status == AuthStatus.authenticated) {
      homeWidget = const DashboardScreen();
    } else {
      homeWidget = const LoginScreen();
    }

    return MaterialApp(
      title: 'GST API Engine',
      debugShowCheckedModeBanner: false,
      theme: isDark ? AppTheme.darkTheme : AppTheme.lightTheme,
      home: homeWidget,
      routes: {
         '/login': (ctx) => const LoginScreen(),
         '/dashboard': (ctx) => const DashboardScreen(),
         '/invoices': (ctx) => const InvoiceListScreen(),
         '/invoices/detail': (ctx) => const InvoiceDetailScreen(invoiceId: '', kind: 'sales'),
         '/parties': (ctx) => const PartyListScreen(),
         '/payments': (ctx) => PaymentListScreen(),
         // '/gst': (ctx) => const GstDashboardScreen(),
         '/settings': (ctx) => SettingsScreen(),
         '/settings/business': (ctx) => SettingsScreen(),
         '/settings/gst': (ctx) => SettingsScreen(),
         '/settings/einvoice': (ctx) => SettingsScreen(),
         '/settings/ewaybill': (ctx) => SettingsScreen(),
         '/settings/numbering': (ctx) => SettingsScreen(),
         '/settings/notifications': (ctx) => SettingsScreen(),
         '/settings/integrations': (ctx) => SettingsScreen(),
         // '/admin': (ctx) => const AdminDashboardScreen(),
      },
    );
  }
}