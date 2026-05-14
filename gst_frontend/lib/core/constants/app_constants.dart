// App-wide constants

// API Configuration — Override via --dart-define=API_BASE_URL=... during build
// Examples:
//   flutter build web --dart-define=API_BASE_URL=https://api.apexbooks.in/api/v1
//   flutter build linux --dart-define=API_BASE_URL=https://api.apexbooks.in/api/v1
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://api.apexbooks.in/api/v1',
);
const String apiHealthEndpoint = '/health';
const String apiTimeout = '30000';

// Auth
const String tokenKey = 'gst_access_token';
const String refreshTokenKey = 'gst_refresh_token';
const String tenantIdKey = 'gst_tenant_id';

// Storage
const String hiveBoxSettings = 'app_settings';
const String hiveBoxInvoices = 'invoices_cache';
const String hiveBoxParties = 'parties_cache';
const String hiveBoxAuth = 'auth_cache';

// Pagination
const int defaultPageSize = 25;
const int maxPageSize = 100;

// GST Constants
const List<Map<String, dynamic>> gstRates = [
  {'rate': 0.0, 'label': '0%', 'cgst': 0.0, 'sgst': 0.0, 'igst': 0.0},
  {'rate': 5.0, 'label': '5%', 'cgst': 2.5, 'sgst': 2.5, 'igst': 5.0},
  {'rate': 12.0, 'label': '12%', 'cgst': 6.0, 'sgst': 6.0, 'igst': 12.0},
  {'rate': 18.0, 'label': '18%', 'cgst': 9.0, 'sgst': 9.0, 'igst': 18.0},
  {'rate': 28.0, 'label': '28%', 'cgst': 14.0, 'sgst': 14.0, 'igst': 28.0},
];

const List<String> supplyTypes = ['B2B', 'B2CL', 'B2CS', 'EXP', 'SEZ'];
const List<String> invoiceTypes = ['Regular', 'Credit Note', 'Debit Note'];
const List<String> paymentModes = ['Cash', 'Bank Transfer', 'UPI', 'Cheque', 'Card'];

// Date formats
const String dateFormat = 'dd-MM-yyyy';
const String dateTimeFormat = 'dd-MM-yyyy HH:mm';
const String apiDateFormat = 'yyyy-MM-dd';

// Currency
const String currencySymbol = '\u20B9'; // ₹
const int currencyDecimalPlaces = 2;