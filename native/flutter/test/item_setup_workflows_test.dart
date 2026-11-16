import 'dart:typed_data';

import 'package:apex_books/core/workspace.dart';
import 'package:apex_books/features/inventory/inventory_models.dart';
import 'package:apex_books/features/masters/master_editor.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

class _SetupApi implements ApexApi {
  const _SetupApi(this.automobileEnabled);
  final bool automobileEnabled;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    expect(path, '/api/companies/shop/inventory-setup');
    return {
      'automobile_enabled': automobileEnabled,
      'location_limit_per_item': 5,
      'locations': [
        {'id': 'shelf-old', 'name': 'Back wall', 'active': false},
        {'id': 'shelf-closed', 'name': 'Closed bin', 'active': false},
        {'id': 'shelf-open', 'name': 'Front rack', 'active': true},
      ],
      'vehicle_options': [
        {
          'make': 'Tata',
          'models': [
            {'name': 'Nexon'},
          ],
        },
      ],
    };
  }

  @override
  Future<Uint8List> download(String path, {Map<String, String>? query}) async =>
      throw UnimplementedError();
  @override
  Future<dynamic> post(
    String path, {
    required Json body,
    String? idempotencyKey,
  }) async => throw UnimplementedError();
}

class _Pending implements PendingStore {
  @override
  Future<Json?> load(String operation) async => null;
  @override
  Future<void> save(String operation, Json data) async {}
  @override
  Future<void> clear(String operation) async {}
}

const _part = {
  'id': 'item-1',
  'name': 'Cable harness',
  'data': {
    'track_stock': true,
    'item_type': 'goods',
    'sale_rate': '100.00',
    'location_ids': ['shelf-old'],
    'oem_number': 'OO-1',
    'part_brand': 'Original company',
    'vehicle_fitment': [
      {
        'make': 'Archive make',
        'model': 'Archive model',
        'year_from': 2017,
        'year_to': 2019,
      },
    ],
  },
};

Future<void> _show(
  WidgetTester tester, {
  required bool automobileEnabled,
  required Future<void> Function(String?, Json) save,
}) async {
  tester.view.physicalSize = const Size(900, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      home: MasterEditorPage(
        workspace: WorkspaceContext(
          api: _SetupApi(automobileEnabled),
          company: const ApexCompany(
            id: 'shop',
            name: 'Workshop',
            role: 'owner',
          ),
          pending: _Pending(),
          features: const {'inventory_setup'},
          refresh: () async {},
        ),
        group: MasterGroup.item,
        record: _part,
        canWrite: true,
        canArchive: true,
        onSave: save,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, String label) async {
  final target = find.text(label);
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  test(
    'Vehicle lookup is available only when the company enables Automobile',
    () {
      expect(
        itemMatches(_part, 'archive model', const {}, automobileEnabled: true),
        isTrue,
      );
      expect(itemMatches(_part, 'archive model', const {}), isFalse);
      expect(
        itemMatches(_part, 'oo-1', const {}, automobileEnabled: true),
        isTrue,
      );
      expect(
        itemMatches(
          _part,
          'Archive model 2018',
          const {},
          automobileEnabled: true,
        ),
        isTrue,
      );
      expect(
        itemMatches(
          _part,
          'Archive model 2020',
          const {},
          automobileEnabled: true,
        ),
        isFalse,
      );
      final several = {
        ..._part,
        'data': {
          'vehicle_fitment': [
            {'make': 'Tata', 'model': 'Nexon'},
            {'make': 'Maruti', 'model': 'Swift'},
          ],
        },
      };
      expect(
        itemMatches(several, 'Tata Swift', const {}, automobileEnabled: true),
        isFalse,
      );
    },
  );

  testWidgets(
    'Ordinary edits preserve disabled vehicle data and assigned archived shelves',
    (tester) async {
      Json? updated;
      await _show(
        tester,
        automobileEnabled: false,
        save: (id, body) async {
          expect(id, 'item-1');
          updated = body;
        },
      );
      expect(find.text('Back wall (archived)'), findsOneWidget);
      expect(
        find.text('Saved vehicle details are kept while Automobile is off.'),
        findsOneWidget,
      );
      expect(find.text('OEM part number'), findsNothing);
      await tester.enterText(
        find.widgetWithText(TextField, 'Sale rate (₹)'),
        '105.50',
      );
      await _tap(tester, 'Save item');
      expect(updated?['sale_rate'], '105.50');
      expect(updated?['track_stock'], true);
      expect(updated?.containsKey('location_ids'), isFalse);
      expect(updated?.containsKey('vehicle_fitment'), isFalse);
      expect(updated?.containsKey('oem_number'), isFalse);
      expect(updated?.containsKey('part_brand'), isFalse);
    },
  );

  testWidgets(
    'Assigns an active shelf and adds a catalogue fitment with valid model years',
    (tester) async {
      Json? updated;
      await _show(
        tester,
        automobileEnabled: true,
        save: (id, body) async => updated = body,
      );
      expect(find.text('Where it is kept'), findsOneWidget);
      expect(find.text('Vehicle details'), findsOneWidget);
      expect(find.text('Closed bin (archived)'), findsNothing);
      expect(
        tester
            .widget<FilterChip>(
              find.widgetWithText(FilterChip, 'Back wall (archived)'),
            )
            .selected,
        isTrue,
      );
      await _tap(tester, 'Front rack');
      expect(
        tester
            .widget<FilterChip>(find.widgetWithText(FilterChip, 'Front rack'))
            .selected,
        isTrue,
      );

      await _tap(tester, 'Add vehicle');
      await tester.enterText(
        find.widgetWithText(TextField, 'Make').last,
        'Tat',
      );
      await tester.pumpAndSettle();
      await _tap(tester, 'Tata');
      await tester.enterText(
        find.widgetWithText(TextField, 'Model').last,
        'Nex',
      );
      await tester.pumpAndSettle();
      await _tap(tester, 'Nexon');
      await tester.enterText(find.widgetWithText(TextField, 'From').last, '2020');
      await tester.enterText(find.widgetWithText(TextField, 'To').last, '2019');
      await _tap(tester, 'Save item');
      expect(
        find.text('The first model year must come before the last.'),
        findsOneWidget,
      );
      expect(updated, isNull);
      await tester.enterText(find.widgetWithText(TextField, 'To').last, '2025');
      await _tap(tester, 'Save item');
      expect(updated?['location_ids'], ['shelf-old', 'shelf-open']);
      expect(updated?['vehicle_fitment'], [
        {
          'make': 'Archive make',
          'model': 'Archive model',
          'year_from': 2017,
          'year_to': 2019,
        },
        {'make': 'Tata', 'model': 'Nexon', 'year_from': 2020, 'year_to': 2025},
      ]);
      expect(updated?.containsKey('oem_number'), isFalse);
      expect(updated?['track_stock'], true);
    },
  );
}
