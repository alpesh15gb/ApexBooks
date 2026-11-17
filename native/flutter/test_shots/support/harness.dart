// Renders real Flutter screens to PNG with the app's fonts, icons and recorded API data,
// so a screen can be compared with the web app without running the whole app.
//
//   flutter test test_shots/<name>_test.dart --update-goldens
//
// Images land in test_shots/out/. GET paths the recordings do not cover are listed in
// test_shots/out/missing.txt; add them to test_shots/paths.txt and run test_shots/capture.py.
import 'dart:convert';
import 'dart:io';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/ui/apex_theme.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

final _root = Directory.current.path.endsWith('test_shots')
    ? Directory.current.parent.path
    : Directory.current.path;
String _path(String relative) => '$_root/$relative';

bool _fontsLoaded = false;

Future<void> _loadFonts() async {
  if (_fontsLoaded) return;
  Future<void> family(String name, List<String> files) async {
    final loader = FontLoader(name);
    for (final file in files) {
      final bytes = File(_path(file)).readAsBytesSync();
      loader.addFont(Future.value(ByteData.view(Uint8List.fromList(bytes).buffer)));
    }
    await loader.load();
  }

  await family('DM Sans', [for (final w in [400, 500, 600, 700, 800]) 'assets/fonts/dm-sans-$w.ttf']);
  await family('DM Sans Display', [for (final w in [500, 600, 700, 800]) 'assets/fonts/dm-sans-display-$w.ttf']);
  final flutterRoot = Platform.environment['FLUTTER_ROOT'] ?? 'C:/src/flutter';
  final icons = File('$flutterRoot/bin/cache/artifacts/material_fonts/materialicons-regular.otf');
  final loader = FontLoader('MaterialIcons')
    ..addFont(Future.value(ByteData.view(Uint8List.fromList(icons.readAsBytesSync()).buffer)));
  await loader.load();
  _fontsLoaded = true;
}

/// Serves responses recorded from the local seeded API (test_shots/fixtures). Writes are accepted
/// and ignored, so forms can be opened and filled for a render.
class FixtureApi implements ApexApi, ApexWriteApi {
  FixtureApi() {
    final dir = Directory(_path('test_shots/fixtures'));
    final index = jsonDecode(File('${dir.path}/index.json').readAsStringSync()) as Map<String, dynamic>;
    for (final entry in index.entries) {
      _responses[entry.key] = jsonDecode(File('${dir.path}/${entry.value}').readAsStringSync());
    }
  }

  final _responses = <String, dynamic>{};
  static final _missing = <String>{};

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    final full = query == null || query.isEmpty ? path : '$path?${Uri(queryParameters: query).query}';
    if (_responses.containsKey(full)) return _responses[full];
    // Record lists are recorded once; filter them by kind the way the server would.
    final kind = query?['kind'] ?? '';
    if (path.endsWith('/records') && kind.isNotEmpty) {
      if (query?['offset'] case final offset? when offset != '0') return <dynamic>[];
      final all = _responses['$path?compact=true'] ?? _responses[path];
      if (all is List) return [for (final row in all) if (row is Map && row['kind'] == kind) row];
    }
    // Paged list requests: answer the first page with the whole recording, later pages empty.
    if (query?['offset'] case final offset? when offset != '0') return <dynamic>[];
    for (final candidate in [full, path]) {
      final match = _responses.keys.where((key) => key == candidate || key.split('?').first == path);
      if (match.isNotEmpty) return _responses[match.first];
    }
    _missing.add(full);
    Directory(_path('test_shots/out')).createSync(recursive: true);
    File(_path('test_shots/out/missing.txt')).writeAsStringSync(_missing.join('\n'));
    return path.endsWith('s') ? <dynamic>[] : <String, dynamic>{};
  }

  @override
  Future<dynamic> post(String path, {required Json body, String? idempotencyKey}) async => <String, dynamic>{};

  @override
  Future<dynamic> put(String path, {required Json body, String? idempotencyKey}) async => <String, dynamic>{};

  @override
  Future<dynamic> patch(String path, {required Json body, String? idempotencyKey}) async => <String, dynamic>{};

  @override
  Future<dynamic> delete(String path, {Map<String, String>? query}) async => <String, dynamic>{};

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async => Uint8List(0);

  @override
  dynamic noSuchMethod(Invocation invocation) => Future.value(<String, dynamic>{});
}

class _MemoryPending implements PendingStore {
  final _values = <String, Json>{};
  @override
  Future<void> clear(String operation) async => _values.remove(operation);
  @override
  Future<Json?> load(String operation) async => _values[operation];
  @override
  Future<void> save(String operation, Json data) async => _values[operation] = data;
}

/// The seeded company as an owner, with the recorded server features.
WorkspaceContext shotWorkspace({String role = 'owner'}) {
  final api = FixtureApi();
  final company = jsonDecode(File(_path('test_shots/fixtures/company.json')).readAsStringSync()) as Json;
  final capabilities = api._responses['/api/capabilities'];
  final features = capabilities is Map
      ? {for (final feature in (capabilities['supported_features'] as List? ?? const [])) '$feature'}
      : <String>{};
  return WorkspaceContext(
    api: api,
    company: ApexCompany.fromJson({...company, 'role': role}),
    pending: _MemoryPending(),
    features: features,
    refresh: () async {},
  );
}

/// Desktop and phone sizes used by the web comparison.
const desktop = Size(1208, 900);
const phone = Size(390, 844);

/// Pumps [screen] in the app theme at [size] and saves `test_shots/out/NAME.png`.
/// [before] can tap or type before the image is taken.
Future<void> shot(
  WidgetTester tester,
  String name,
  Widget screen, {
  Size size = desktop,
  Future<void> Function(WidgetTester tester)? before,
}) async {
  await tester.runAsync(_loadFonts);
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: apexTheme(),
      home: Scaffold(body: screen),
    ),
  );
  for (var i = 0; i < 6; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pump(const Duration(milliseconds: 100));
  }
  if (before != null) {
    await before(tester);
    for (var i = 0; i < 4; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
      await tester.pump(const Duration(milliseconds: 100));
    }
  }
  await expectLater(find.byType(MaterialApp), matchesGoldenFile('out/$name.png'));
}
