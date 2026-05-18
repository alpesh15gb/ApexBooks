from fastapi import APIRouter, Depends
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.exceptions import ok
from app.api.v1.deps import current_tenant
from app.models.accounting import ItemModel, InvoiceModel, InvoiceLineModel

router = APIRouter(prefix='/inventory', tags=['Inventory'])


@router.post('/warehouses')
def create_warehouse(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Register a warehouse location."""
    name = payload.get('name')
    if not name:
        raise Exception('Warehouse name is required')
    from app.models.e2e import ResourceRecord
    from uuid import uuid4
    rec = ResourceRecord(
        tenant_id=tenant_id,
        resource='warehouse',
        resource_id=str(uuid4()),
        payload={'name': name, 'address': payload.get('address', ''),
                 'is_active': True},
        status='active',
        txn_date=date.today(),
    )
    db.add(rec)
    db.flush()
    return ok({'warehouse_id': rec.resource_id, 'name': name}, 'Warehouse created')


@router.get('/warehouses')
def list_warehouses(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """List all warehouses."""
    from app.models.e2e import ResourceRecord
    warehouses = db.query(ResourceRecord).filter_by(
        tenant_id=tenant_id, resource='warehouse', is_deleted=False
    ).all()
    return ok({
        'warehouses': [
            {
                'warehouse_id': w.resource_id,
                'name': w.payload.get('name', ''),
                'address': w.payload.get('address', ''),
                'is_active': w.payload.get('is_active', True),
            }
            for w in warehouses
        ]
    })


@router.get('/stock-entry')
def stock_entry(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get stock entry summary: items with current stock levels."""
    items = db.query(ItemModel).filter_by(tenant_id=tenant_id, is_deleted=False).all()
    result = []
    for item in items:
        if item.stock_keeping_unit:
            purchased = db.query(func.coalesce(func.sum(InvoiceLineModel.quantity), 0)).join(
                InvoiceModel).filter(
                InvoiceLineModel.item_id == item.item_id,
                InvoiceModel.tenant_id == tenant_id,
                InvoiceModel.invoice_kind == 'purchase',
                InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
            ).scalar()
            sold = db.query(func.coalesce(func.sum(InvoiceLineModel.quantity), 0)).join(
                InvoiceModel).filter(
                InvoiceLineModel.item_id == item.item_id,
                InvoiceModel.tenant_id == tenant_id,
                InvoiceModel.invoice_kind == 'sales',
                InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
            ).scalar()
            closing = float((purchased or 0) - (sold or 0))
            result.append({
                'item_id': item.item_id,
                'item_name': item.item_name,
                'item_code': item.item_code,
                'unit': item.unit_of_measure,
                'purchase_price': float(item.purchase_price),
                'selling_price': float(item.selling_price),
                'stock_in_hand': closing,
                'value': closing * float(item.purchase_price),
            })
    return ok(result)


@router.post('/stock-entry')
def add_stock_entry(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Manually add stock (for opening stock or adjustments)."""
    from app.models.e2e import ResourceRecord
    from uuid import uuid4
    item_id = payload.get('item_id')
    quantity = payload.get('quantity', 0)
    note = payload.get('note', 'Manual stock entry')

    if not item_id:
        raise Exception('item_id is required')

    item = db.query(ItemModel).filter_by(
        tenant_id=tenant_id, item_id=item_id, is_deleted=False
    ).first()
    if not item:
        raise Exception(f'Item {item_id} not found')

    rec = ResourceRecord(
        tenant_id=tenant_id,
        resource='stock_entry',
        resource_id=str(uuid4()),
        payload={'item_id': item_id, 'quantity': quantity, 'note': note,
                 'type': 'manual_addition'},
        status='recorded',
        txn_date=date.today(),
        amount=float(quantity) * float(item.purchase_price),
    )
    db.add(rec)
    db.flush()
    return ok({'stock_entry_id': rec.resource_id, 'item_id': item_id,
               'quantity': quantity}, 'Stock entry recorded')


@router.get('/stock-ledger')
def stock_ledger(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get stock movement ledger for all tracked items."""
    items = db.query(ItemModel).filter_by(tenant_id=tenant_id, is_deleted=False, stock_keeping_unit=True).all()
    result = []
    for item in items:
        invoices_sold = db.query(InvoiceLineModel).join(InvoiceModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).all()
        invoices_purchased = db.query(InvoiceLineModel).join(InvoiceModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'purchase',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).all()

        movements = []
        for inv in invoices_purchased:
            movements.append({
                'date': str(inv.invoice.invoice_date) if hasattr(inv, 'invoice') else '',
                'type': 'IN',
                'quantity': float(inv.quantity),
                'reference': inv.invoice.invoice_number if hasattr(inv, 'invoice') else '',
            })
        for inv in invoices_sold:
            movements.append({
                'date': str(inv.invoice.invoice_date) if hasattr(inv, 'invoice') else '',
                'type': 'OUT',
                'quantity': float(inv.quantity),
                'reference': inv.invoice.invoice_number if hasattr(inv, 'invoice') else '',
            })

        movements.sort(key=lambda x: x['date'])
        closing = sum(m['quantity'] for m in movements if m['type'] == 'IN') - \
                  sum(m['quantity'] for m in movements if m['type'] == 'OUT')

        result.append({
            'item_id': item.item_id,
            'item_name': item.item_name,
            'item_code': item.item_code,
            'movements': movements,
            'closing': closing,
        })

    return ok(result)


@router.get('/valuation')
def inventory_valuation(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get inventory valuation summary using FIFO method."""
    items = db.query(ItemModel).filter_by(tenant_id=tenant_id, is_deleted=False, stock_keeping_unit=True).all()
    total_value = 0
    valuation = []
    for item in items:
        purchased_qty = db.query(func.coalesce(func.sum(InvoiceLineModel.quantity), 0)).join(
            InvoiceModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'purchase',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).scalar() or 0

        sold_qty = db.query(func.coalesce(func.sum(InvoiceLineModel.quantity), 0)).join(
            InvoiceModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).scalar() or 0

        closing_qty = purchased_qty - sold_qty
        value = float(closing_qty) * float(item.purchase_price)
        total_value += value

        valuation.append({
            'item_id': item.item_id,
            'item_name': item.item_name,
            'item_code': item.item_code,
            'closing_qty': closing_qty,
            'purchase_price': float(item.purchase_price),
            'value': value,
            'method': 'FIFO',
        })

    return ok({'total_value': total_value, 'items': valuation})


@router.post('/physical-count')
def physical_count(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Record physical stock count and create variance report."""
    item_id = payload.get('item_id')
    counted_qty = payload.get('counted_qty')

    if not item_id or counted_qty is None:
        raise Exception('item_id and counted_qty are required')

    item = db.query(ItemModel).filter_by(
        tenant_id=tenant_id, item_id=item_id, is_deleted=False
    ).first()
    if not item:
        raise Exception(f'Item {item_id} not found')

    from app.models.e2e import ResourceRecord
    from uuid import uuid4
    rec = ResourceRecord(
        tenant_id=tenant_id,
        resource='physical_count',
        resource_id=str(uuid4()),
        payload={'item_id': item_id, 'counted_qty': counted_qty},
        status='recorded',
        txn_date=date.today(),
    )
    db.add(rec)
    db.flush()

    return ok({
        'item_id': item_id,
        'counted_qty': counted_qty,
        'physical_count_id': rec.resource_id,
        'status': 'Recorded',
    }, 'Physical count recorded')


@router.get('/reports/aging')
def stock_aging(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Get stock aging report for items with long inventory holding."""
    items = db.query(ItemModel).filter_by(tenant_id=tenant_id, is_deleted=False, stock_keeping_unit=True).all()
    from datetime import date
    today = date.today()
    result = []

    for item in items:
        oldest_purchase = db.query(InvoiceModel.invoice_date).join(InvoiceLineModel).filter(
            InvoiceLineModel.item_id == item.item_id,
            InvoiceModel.tenant_id == tenant_id,
            InvoiceModel.invoice_kind == 'purchase',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
        ).order_by(InvoiceModel.invoice_date.asc()).first()

        days_in_stock = (today - oldest_purchase.invoice_date).days if oldest_purchase else 0
        aging_bucket = '0-30' if days_in_stock <= 30 else '31-60' if days_in_stock <= 60 else '61-90' if days_in_stock <= 90 else '90+'

        result.append({
            'item_id': item.item_id,
            'item_name': item.item_name,
            'days_in_stock': days_in_stock,
            'aging_bucket': aging_bucket,
        })

    return ok(sorted(result, key=lambda x: -x['days_in_stock']))