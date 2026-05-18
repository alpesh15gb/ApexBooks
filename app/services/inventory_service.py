from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.models.accounting import InvoiceModel, InvoiceLineModel


class InventoryValuationEngine:
    """FIFO-based inventory valuation engine.

    Tracks cost layers on purchase and consumes oldest layers on sale.
    """

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def _get_purchase_layers(self, item_id: str) -> list[dict]:
        """Get all purchase layers for an item ordered by date (oldest first).

        Each layer represents a purchase invoice line with available quantity.
        """
        from app.models.accounting import InvoiceModel, InvoiceLineModel

        rows = self.db.query(
            InvoiceLineModel, InvoiceModel.invoice_date, InvoiceModel.invoice_id
        ).join(
            InvoiceModel,
            InvoiceLineModel.invoice_pk == InvoiceModel.id
        ).filter(
            InvoiceLineModel.item_id == item_id,
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.invoice_kind == 'purchase',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
            InvoiceLineModel.quantity > 0,
        ).order_by(InvoiceModel.invoice_date.asc(), InvoiceLineModel.id.asc()).all()

        layers = []
        for line, inv_date, inv_id in rows:
            unit_cost = Decimal(str(line.unit_price or 0))
            qty = Decimal(str(line.quantity or 0))
            if qty > 0:
                layers.append({
                    'invoice_line_id': line.id,
                    'invoice_id': inv_id,
                    'invoice_date': inv_date,
                    'quantity': qty,
                    'unit_cost': unit_cost,
                    'consumed_qty': Decimal('0'),
                })
        return layers

    def _get_total_sold_qty(self, item_id: str) -> Decimal:
        """Get total quantity sold for an item."""
        from app.models.accounting import InvoiceModel, InvoiceLineModel

        result = self.db.query(
            func.coalesce(func.sum(InvoiceLineModel.quantity), 0)
        ).join(
            InvoiceModel,
            InvoiceLineModel.invoice_pk == InvoiceModel.id
        ).filter(
            InvoiceLineModel.item_id == item_id,
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        ).scalar()
        return Decimal(str(result or 0))

    def compute_cogs(self, item_id: str, sale_quantity: Decimal) -> dict:
        """Compute COGS for a sale using FIFO layers.

        Returns:
            dict with cogs_value, layers_consumed (list), remaining_layers (list)
        """
        layers = self._get_purchase_layers(item_id)
        remaining_qty = sale_quantity
        cogs_value = Decimal('0')
        layers_consumed = []
        remaining_layers = []

        for layer in layers:
            available = layer['quantity']
            consume = min(available, remaining_qty)
            if consume > 0:
                cost = consume * layer['unit_cost']
                cogs_value += cost
                remaining_qty -= consume
                layers_consumed.append({
                    'invoice_id': layer['invoice_id'],
                    'invoice_date': str(layer['invoice_date']),
                    'unit_cost': float(layer['unit_cost']),
                    'qty_consumed': float(consume),
                    'cost': float(cost),
                })
                layer['consumed_qty'] = consume
                leftover = available - consume
                if leftover > 0:
                    remaining_layers.append({
                        'invoice_line_id': layer['invoice_line_id'],
                        'quantity': float(leftover),
                        'unit_cost': float(layer['unit_cost']),
                        'invoice_date': str(layer['invoice_date']),
                    })
            else:
                remaining_layers.append({
                    'invoice_line_id': layer['invoice_line_id'],
                    'quantity': float(available),
                    'unit_cost': float(layer['unit_cost']),
                    'invoice_date': str(layer['invoice_date']),
                })

        return {
            'item_id': item_id,
            'sold_qty': float(sale_quantity),
            'cogs_value': float(cogs_value),
            'layers_consumed': layers_consumed,
            'remaining_layers': remaining_layers,
            'underflow': float(remaining_qty) > 0,
        }

    def compute_closing_stock(self, item_id: str) -> dict:
        """Compute closing stock quantity and value using FIFO."""
        from app.models.e2e import ItemModel

        item = self.db.query(ItemModel).filter_by(
            tenant_id=self.tenant_id, item_id=item_id, is_deleted=False
        ).first()
        if not item:
            return {'item_id': item_id, 'closing_qty': 0, 'closing_value': 0, 'layers': []}

        layers = self._get_purchase_layers(item_id)
        total_sold = self._get_total_sold_qty(item_id)

        remaining_qty = total_sold
        total_value = Decimal('0')
        active_layers = []

        for layer in layers:
            available = layer['quantity']
            consume = min(available, remaining_qty)
            if consume > 0:
                remaining_qty -= consume
            leftover = available - consume
            if leftover > 0:
                value = leftover * layer['unit_cost']
                total_value += value
                active_layers.append({
                    'invoice_id': layer['invoice_id'],
                    'invoice_date': str(layer['invoice_date']),
                    'qty': float(leftover),
                    'unit_cost': float(layer['unit_cost']),
                    'value': float(value),
                })

        return {
            'item_id': item_id,
            'item_name': item.item_name,
            'item_code': item.item_code,
            'closing_qty': float(sum(l['qty'] for l in active_layers)),
            'closing_value': float(total_value),
            'layers': active_layers,
        }

    def compute_all_valuations(self) -> list[dict]:
        """Compute closing stock for all active stock-keeping items."""
        from app.models.e2e import ItemModel

        items = self.db.query(ItemModel).filter_by(
            tenant_id=self.tenant_id, is_deleted=False, stock_keeping_unit=True
        ).all()

        results = []
        total_value = Decimal('0')
        for item in items:
            val = self.compute_closing_stock(item.item_id)
            results.append(val)
            total_value += Decimal(str(val['closing_value']))
        return results


class ReorderService:
    """Service for monitoring reorder levels and generating purchase suggestions."""

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def check_reorder_levels(self) -> list[dict]:
        """Check which items have fallen below reorder level."""
        from app.models.e2e import ItemModel, ResourceRecord
        from decimal import Decimal

        items = self.db.query(ItemModel).filter_by(
            tenant_id=self.tenant_id, is_deleted=False, stock_keeping_unit=True
        ).all()

        alerts = []
        for item in items:
            min_stock = Decimal(str(item.custom_fields.get('min_stock', 0))) if item.custom_fields else Decimal('0')
            max_stock = Decimal(str(item.custom_fields.get('max_stock', 0))) if item.custom_fields else Decimal('0')

            if min_stock > 0:
                closing = InventoryValuationEngine(self.db, self.tenant_id).compute_closing_stock(item.item_id)
                closing_qty = Decimal(str(closing['closing_qty']))

                if closing_qty <= min_stock:
                    alerts.append({
                        'item_id': item.item_id,
                        'item_name': item.item_name,
                        'item_code': item.item_code,
                        'closing_qty': float(closing_qty),
                        'min_stock': float(min_stock),
                        'max_stock': float(max_stock),
                        'suggested_order_qty': float(max(Decimal('0'), max_stock - closing_qty)),
                        'alert_type': 'low_stock' if closing_qty <= min_stock else 'out_of_stock' if closing_qty == 0 else 'info',
                    })
        return alerts


def auto_post_cogs(db: Session, tenant_id: str, invoice_id: str, item_id: str, quantity: Decimal) -> dict:
    """Auto-compute and post COGS entry when a sales invoice is submitted.

    This should be called during sales invoice submit to create the COGS GL entry.
    """
    engine = InventoryValuationEngine(db, tenant_id)
    result = engine.compute_cogs(item_id, quantity)

    if result['cogs_value'] > 0:
        from app.models.accounting import GLEntryModel
        from app.models.e2e import InvoiceModel

        inv = db.query(InvoiceModel).filter_by(
            tenant_id=tenant_id, invoice_id=invoice_id
        ).first()

        if inv:
            db.add(GLEntryModel(
                tenant_id=tenant_id,
                posting_date=inv.invoice_date,
                account='Cost of Goods Sold',
                party_id=inv.party_id,
                voucher_type='cogs',
                voucher_id=invoice_id,
                debit=Decimal(str(result['cogs_value'])),
                credit=Decimal('0'),
                remarks=f'COGS for {item_id}: qty={float(quantity)}, cost={result["cogs_value"]}',
            ))
            db.add(GLEntryModel(
                tenant_id=tenant_id,
                posting_date=inv.invoice_date,
                account='Inventory',
                party_id=inv.party_id,
                voucher_type='cogs',
                voucher_id=invoice_id,
                debit=Decimal('0'),
                credit=Decimal(str(result['cogs_value'])),
                remarks=f'Inventory reduction for {item_id}',
            ))
            db.flush()
    return result
