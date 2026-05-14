import sqlite3
import json

db_path = r'//Vault/ApexBooks/gst-api-engine/scripts/vyapar_extract/ApexIntegrations__t_2026_04_15_12_30_13_viho.vyp'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

CURR = 'INR'

# Summary stats (fixed query)
print("=" * 80)
print("IMPORT SUMMARY:")
print("=" * 80)

cursor.execute("SELECT COUNT(*) FROM kb_transactions")
print(f"  Total transactions: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM kb_lineitems")
print(f"  Total line items: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM kb_names WHERE name_type = 1")
print(f"  Customers (type=1): {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM kb_names WHERE name_type = 2")
print(f"  Vendors/Parties (type=2): {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM kb_items")
print(f"  Items: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM kb_tax_code")
print(f"  Tax codes: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM kb_paymentTypes")
print(f"  Payment types: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM other_accounts")
print(f"  Other accounts: {cursor.fetchone()[0]}")

# Sales total
cursor.execute("""
    SELECT SUM(t.txn_balance_amount), SUM(li.lineitem_tax_amount)
    FROM kb_transactions t
    JOIN kb_lineitems li ON t.txn_id = li.lineitem_txn_id
    WHERE t.txn_type IN (1, 27)
""")
totals = cursor.fetchone()
print(f"  Sum of all invoice amounts: {CURR} {totals[0]}")
print(f"  Sum of all line item tax: {CURR} {totals[1]}")

# Sales vs Purchase breakdown
cursor.execute("""
    SELECT txn_type, COUNT(*), SUM(txn_balance_amount)
    FROM kb_transactions
    WHERE txn_type IN (1, 27)
    GROUP BY txn_type
""")
for row in cursor.fetchall():
    label = {1: 'SALES', 27: 'PURCHASES'}.get(row[0], f'Type {row[0]}')
    print(f"  {label}: {row[1]} txns, {CURR} {row[2]}")

# Payment summary
cursor.execute("""
    SELECT txn_type, COUNT(*), SUM(t.txn_cash_amount)
    FROM kb_transactions
    WHERE txn_type IN (1, 28)
    GROUP BY txn_type
""")
for row in cursor.fetchall():
    label = {1: 'SALES with payments', 28: 'PAYMENT entries'}.get(row[0], f'Type {row[0]}')
    print(f"  {label}: {row[1]} txns, {CURR} {row[2]} total cash")

# Tax rate distribution
print("\n" + "=" * 80)
print("TAX RATE DISTRIBUTION:")
print("=" * 80)
cursor.execute("""
    SELECT tc.tax_code_name, tc.tax_rate, tc.tax_code_type,
           COUNT(li.lineitem_id) as usage_count,
           SUM(li.lineitem_tax_amount) as total_tax
    FROM kb_lineitems li
    JOIN kb_tax_code tc ON li.lineitem_tax_id = tc.tax_code_id
    GROUP BY tc.tax_code_id
    ORDER BY tc.tax_rate DESC
""")
print(f"  {'Tax Name':20s} {'Rate':>6s} {'Type':>4s} {'Usage':>6s} {'Total Tax':>14s}")
print(f"  {'-'*20} {'-'*6} {'-'*4} {'-'*6} {'-'*14}")
for row in cursor.fetchall():
    ctype = {0: 'IGST', 1: 'SGST', 2: 'CGST'}.get(row[2], '???')
    print(f"  {row[0]:20s} {row[1]:>6.1f}% {ctype:>4s} {row[3]:>6d} {CURR} {row[4]:>12.2f}")

# Party distribution
print("\n" + "=" * 80)
print("PARTY TRANSACTION COUNT:")
print("=" * 80)
cursor.execute("""
    SELECT n.name_id, n.full_name, n.name_gstin_number,
           COUNT(DISTINCT t.txn_id) as txn_count,
           SUM(t.txn_balance_amount) as total,
           t.txn_type
    FROM kb_transactions t
    JOIN kb_names n ON t.txn_name_id = n.name_id
    GROUP BY n.name_id, t.txn_type
    ORDER BY txn_count DESC
""")
for row in cursor.fetchall():
    ttype = 'SALE' if row[5] == 1 else 'PURCHASE' if row[5] == 27 else 'PAYMENT'
    print(f"  [{ttype}] {row[1][:30]:30s} GSTIN:{str(row[2] or 'N/A'):15s} Txns:{row[3]:>3d} Total:{CURR} {row[4]}")

# Payment mapping
print("\n" + "=" * 80)
print("PAYMENT MAPPINGS:")
print("=" * 80)
cursor.execute("""
    SELECT pm.id, pm.payment_id, pm.txn_id, pm.amount,
           t.txn_ref_number_char, t.txn_date
    FROM txn_payment_mapping pm
    LEFT JOIN kb_transactions t ON pm.txn_id = t.txn_id
    ORDER BY pm.id
""")
for row in cursor.fetchall():
    print(f"  Payment#{row[1]} -> Txn#{row[2]} ({CURR} {row[3]}) Invoice#{row[4]} Date:{row[5]}")

conn.close()
print("\n" + "=" * 80)
print("ANALYSIS COMPLETE - Ready for import endpoint design")
print("=" * 80)