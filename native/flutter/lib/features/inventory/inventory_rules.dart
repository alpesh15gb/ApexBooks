import 'inventory_models.dart';

/// Signed quantity as the web history shows it: "+5 pcs" or "-2 pcs".
String inventoryMovementQuantity(Object? quantity, Object? unit) {
  final text = inventoryQuantity(quantity);
  final positive = (num.tryParse(text) ?? 0) > 0;
  final suffix = inventoryText(unit).trim();
  return '${positive ? '+$text' : text}${suffix.isEmpty ? '' : ' $suffix'}';
}

/// Signed cost change; a null cost is "Unvalued" exactly as on the web.
String inventoryMovementCost(Object? costValue) =>
    costValue == null ? 'Unvalued' : inventoryAmount(costValue);

/// The supplier tax and discount overrides only apply to lines being received.
bool receivingShowsTaxTile(String? quantity) =>
    (num.tryParse((quantity ?? '').trim()) ?? 0) > 0;

/// Input tax credit is only meaningful for regular-scheme companies.
bool receivingShowsInputCredit(String taxMode) => taxMode == 'regular';

/// Tri-state unit price tax basis: null keeps the order value and is omitted.
void applyReceivingTaxBasis(InventoryJson overrides, bool? includesTax) {
  if (includesTax == null) {
    overrides.remove('price_includes_tax');
  } else {
    overrides['price_includes_tax'] = includesTax;
  }
}
