"""Final end-to-end verification of all implemented functionality."""
from app.main import app
from app.services.gst_engine import calculate_tax, classify_gstr1
from app.services.normalized_repository import normalized_repo
from app.services.trial_balance_service import verify_trial_balance, get_account_balances
from app.services.gstr_service import gstr3b_compute

errors = []

# 1. Verify app loads
try:
    routes = [r.path for r in app.routes]
    print(f"[OK] App loaded with {len(routes)} routes")
except Exception as e:
    errors.append(f"App load failed: {e}")
    print(f"[FAIL] App load: {e}")

# 2. GST engine correctness
try:
    r = calculate_tax('27', '27', 'B2B', [{'quantity': 2, 'unit_price': 100, 'gst_rate': 18}])
    assert r['total_cgst'] == 18.00, f"CGST: {r['total_cgst']}"
    assert r['total_sgst'] == 18.00, f"SGST: {r['total_sgst']}"
    assert r['grand_total'] == 236.00, f"Total: {r['grand_total']}"
    print("[OK] GST engine: intra-state B2B")
except Exception as e:
    errors.append(f"GST B2B: {e}")

try:
    r = calculate_tax('27', '99', 'Export with IGST', [{'quantity': 1, 'unit_price': 1000, 'gst_rate': 18}])
    assert r['total_cgst'] == 0 and r['total_sgst'] == 0 and r['total_igst'] == 0
    print("[OK] GST engine: zero-rated export")
except Exception as e:
    errors.append(f"GST export: {e}")

try:
    r = calculate_tax('27', '29', 'B2B', [{'quantity': 1, 'unit_price': 1000, 'gst_rate': 18, 'discount_percent': 10}])
    assert r['subtotal'] == 900.00
    assert r['total_igst'] == 162.00
    print("[OK] GST engine: interstate with discount")
except Exception as e:
    errors.append(f"GST interstate: {e}")

# 3. GSTR3B compute
try:
    result = gstr3b_compute([], [])
    assert 'sup_details' in result
    assert 'itc_elg' in result
    print("[OK] GSTR3B compute structure")
except Exception as e:
    errors.append(f"GSTR3B: {e}")

# 4. Verify accounts router imports cleanly
try:
    from app.api.v1.accounts.router import router as accounts_router
    paths = [r.path for r in accounts_router.routes]
    print(f"[OK] Accounts router: {len(paths)} endpoints")
except Exception as e:
    errors.append(f"Accounts router: {e}")

# 5. Verify models load
try:
    from app.models.e2e import AccountModel, JournalEntryModel
    print("[OK] AccountModel, JournalEntryModel loaded")
except Exception as e:
    errors.append(f"Models: {e}")

# 6. Check OpenAPI schema reachable
try:
    schema = app.openapi()
    print(f"[OK] OpenAPI schema: {len(schema['paths'])} paths, {len(schema.get('components', {}).get('schemas', {}))} schemas")
except Exception as e:
    errors.append(f"OpenAPI: {e}")

# 7. Verify no duplicate routes
try:
    route_set = {}
    for r in app.routes:
        path = r.path
        methods = tuple(sorted(r.methods)) if hasattr(r, 'methods') else ('GET',)
        key = (path, methods)
        assert key not in route_set, f"Duplicate route: {key}"
        route_set[key] = True
    print(f"[OK] No duplicate routes ({len(route_set)} unique)")
except Exception as e:
    errors.append(f"Duplicate check: {e}")

print(f"\n{'='*50}")
if errors:
    print(f"FAILURES: {len(errors)}")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL VERIFICATIONS PASSED")
print(f"{'='*50}")