import '../../core/workspace.dart';
import 'inventory_models.dart';

class ShelfLocation {
  const ShelfLocation({
    required this.id,
    required this.name,
    required this.active,
  });
  final String id;
  final String name;
  final bool active;

  String get label => active ? name : '$name (archived)';
}

class InventorySetup {
  const InventorySetup({
    this.shelves = const [],
    this.automobileEnabled = false,
    this.modelsByMake = const {},
    this.shelfLimit = 5,
  });

  factory InventorySetup.fromJson(InventoryJson data) {
    final limit = data['location_limit_per_item'];
    final shelves = {
      for (final row in inventoryRows(data['locations']))
        if (row['id'] is String && row['name'] is String)
          row['id'] as String: ShelfLocation(
            id: row['id'] as String,
            name: row['name'] as String,
            active: row['active'] != false,
          ),
    };
    return InventorySetup(
      shelves: shelves.values.toList(),
      automobileEnabled: data['automobile_enabled'] == true,
      modelsByMake: {
        for (final make in inventoryRows(data['vehicle_options']))
          if (make['make'] is String)
            make['make'] as String: [
              for (final model in inventoryRows(make['models']))
                if (model['name'] is String) model['name'] as String,
            ],
      },
      shelfLimit: limit is int ? limit.clamp(1, 5) : 5,
    );
  }

  static Future<InventorySetup> load(WorkspaceContext workspace) async {
    if (!workspace.features.contains('inventory_setup')) {
      return const InventorySetup();
    }
    return InventorySetup.fromJson(
      inventoryObject(
        await workspace.api.get('${workspace.path}/inventory-setup'),
      ),
    );
  }

  final List<ShelfLocation> shelves;
  final bool automobileEnabled;
  final Map<String, List<String>> modelsByMake;
  final int shelfLimit;

  Map<String, String> get shelfLabels => {
    for (final shelf in shelves) shelf.id: shelf.label,
  };
}

class VehicleFitment {
  const VehicleFitment({
    required this.make,
    this.model = '',
    this.from,
    this.to,
  });

  factory VehicleFitment.fromJson(InventoryJson row) => VehicleFitment(
    make: inventoryText(row['make']),
    model: inventoryText(row['model']),
    from: int.tryParse(inventoryText(row['year_from'])),
    to: int.tryParse(inventoryText(row['year_to'])),
  );

  final String make;
  final String model;
  final int? from;
  final int? to;

  String get label {
    final vehicle = model.isEmpty ? make : '$make $model';
    if (from == null && to == null) return vehicle;
    if (from == null) return '$vehicle (through $to)';
    if (to == null) return '$vehicle ($from onwards)';
    return from == to ? '$vehicle ($from)' : '$vehicle ($from–$to)';
  }

  InventoryJson toJson() => {
    'make': make,
    'model': model,
    'year_from': from,
    'year_to': to,
  };
}
