import 'dart:convert';

import 'package:apex_books/features/inventory/inventory_rules.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('movement quantity is signed and carries the item unit', () {
    expect(inventoryMovementQuantity('5.000', 'pcs'), '+5 pcs');
    expect(inventoryMovementQuantity('-2.500', 'kg'), '-2.5 kg');
    expect(inventoryMovementQuantity('3', null), '+3');
  });

  test('movement cost is signed and null is Unvalued', () {
    expect(inventoryMovementCost('1250.5'), '₹1,250.50');
    expect(inventoryMovementCost('-1250.50'), '-₹1,250.50');
    expect(inventoryMovementCost(null), 'Unvalued');
  });

  test('tax tile shows only once a quantity above zero is entered', () {
    expect(receivingShowsTaxTile(null), isFalse);
    expect(receivingShowsTaxTile(''), isFalse);
    expect(receivingShowsTaxTile('0'), isFalse);
    expect(receivingShowsTaxTile('0.5'), isTrue);
  });

  test('input tax credit shows only for regular tax mode', () {
    expect(receivingShowsInputCredit('regular'), isTrue);
    expect(receivingShowsInputCredit('composition'), isFalse);
    expect(receivingShowsInputCredit(''), isFalse);
  });

  test('tax basis states: order value omits the field', () {
    final overrides = <String, dynamic>{};
    applyReceivingTaxBasis(overrides, true);
    expect(jsonEncode(overrides), '{"price_includes_tax":true}');
    applyReceivingTaxBasis(overrides, false);
    expect(jsonEncode(overrides), '{"price_includes_tax":false}');
    applyReceivingTaxBasis(overrides, null);
    expect(overrides.containsKey('price_includes_tax'), isFalse);
  });
}
