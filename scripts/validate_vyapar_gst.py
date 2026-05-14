"""
Vyapar Import Validation Test
Run against the actual .vyb backup file to validate GST totals.
"""
import sys
import os
import tempfile
import zipfile
import sqlite3
from decimal import Decimal

sys.path.insert(0, '//Vault/ApexBooks/gst-api-engine')
os.chdir('//Vault\ApexBooks\gst-api-engine')

from app.services.gst_engine import calculate_tax
from app.services.vyapar_importer import extract_vyapar_db


def find_vyb_file():
    """Find the .vyb backup file."""
    for root, dirs, files in os.walk('//Vault\ApexBooks\gst-api-engine'):
        for f in files:
            if f.endswith('.vyb'):
                return os.path.join(root, f)
    return None


def get_schema(cursor):
    """Print all tables and their columns."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("\n=== Vyapar Database Schema ===")
    for table in tables:
        tname = table[0]
        cursor.execute(f"PRAGMA table_info({tname})")
        cols = cursor.fetchall()
        col_names = [c[1] for c in cols]
        print(f"  {tname}: {', '.join(col_names)}")


def validate_gst_calculation(db_path):
    """Validate that GST calculations match between Vyapar and our engine."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Show schema first
    get_schema(cursor)

    # Find transaction columns
    cursor.execute("PRAGMA table_info(kb_transactions)")
    txn_cols = [c[1] for c in cursor.fetchall()]
    print(f"\nkb_transactions columns: {txn_cols}")

    # Find the right column names
    balance_col = None
    for col in txn_cols:
        if 'balance' in col.lower() or 'total' in col.lower():
            balance_col = col
            break

    if not balance_col:
        print("Could not find balance/total column in kb_transactions")
        return 0

    print(f"Using balance column: {balance_col}")

    cursor.execute(f"""
        SELECT t.txn_id, t.txn_type, t.{balance_col} as txn_total
        FROM kb_transactions t
        WHERE t.txn_type IN (1, 27) AND t.{balance_col} != 0
        LIMIT 15
    """)
    transactions = cursor.fetchall()

    print(f"\n{'='*70}")
    print("GST CALCULATION VALIDATION")
    print(f"{'='*70}")

    mismatches = 0
    total_checked = 0
    for txn in transactions:
        txn_id = txn['txn_id']
        txn_total = float(txn['txn_total'] or 0)
        total_checked += 1

        # Get line items
        cursor.execute("""
            SELECT li.quantity, li.priceperunit, li.lineitem_tax_amount,
                   li.lineitem_tax_id, i.item_name
            FROM kb_lineitems li
            LEFT JOIN kb_items i ON li.item_id = i.item_id
            WHERE li.lineitem_txn_id = ?
        """, (txn_id,))
        lines = cursor.fetchall()

        if not lines:
            print(f"\nTxn #{txn_id}: SKIPPED (no line items)")
            continue

        # Build line items for our engine
        line_items = []
        for line in lines:
            rate = 0
            if line['lineitem_tax_id']:
                cursor.execute("SELECT tax_rate FROM kb_tax_code WHERE tax_code_id = ?",
                              (line['lineitem_tax_id'],))
                row = cursor.fetchone()
                if row:
                    rate = float(row['tax_rate'] or 0)

            line_items.append({
                'description': line['item_name'] or 'Item',
                'quantity': float(line['quantity'] or 0),
                'unit_price': float(line['priceperunit'] or 0),
                'gst_rate': rate,
            })

        # Calculate using our engine
        our_calc = calculate_tax('27', '27', 'B2B', line_items)

        our_total = float(our_calc['grand_total'])
        diff = abs(txn_total - our_total)
        # Use 1.0 tolerance for larger transactions due to rounding
        tolerance = max(0.02, abs(txn_total) * 0.001)
        status = "PASS" if diff < tolerance else "FAIL"

        if status == "FAIL":
            mismatches += 1

        print(f"\nTxn #{txn_id} (type={txn['txn_type']}, lines={len(line_items)}):")
        print(f"  Vyapar Total: INR {txn_total:.2f}")
        print(f"  Our Engine:   INR {our_total:.2f}")
        print(f"  Difference:   INR {diff:.2f} (tolerance: {tolerance:.2f}) [{status}]")

    conn.close()
    print(f"\nChecked {total_checked} transactions")
    return mismatches


def main():
    vyb_path = find_vyb_file()
    if not vyb_path:
        print("No .vyb file found in the project directory")
        return

    print(f"Found Vyapar backup: {vyb_path}")
    print(f"File size: {os.path.getsize(vyb_path)} bytes")

    # Extract to get the SQLite DB
    db_path = extract_vyapar_db(vyb_path)
    print(f"Extracted SQLite DB: {db_path}")

    # Run GST validation
    mismatches = validate_gst_calculation(db_path)

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY: {mismatches} GST calculation mismatches found")
    if mismatches == 0:
        print("All GST calculations match within tolerance!")
    else:
        print("Review mismatches above. May be due to:")
        print("  - Different rounding methods between Vyapar and our engine")
        print("  - Tax-inclusive vs tax-exclusive price interpretation")
        print("  - Additional fees/discounts in Vyapar not captured")
    print(f"{'='*70}")

    # Cleanup
    import shutil
    extract_dir = os.path.dirname(db_path)
    shutil.rmtree(extract_dir, ignore_errors=True)


if __name__ == '__main__':
    main()