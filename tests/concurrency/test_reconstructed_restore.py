"""Re-run reconstructed SQLite regression scenarios on the owned PostgreSQL fixture.

The PostgreSQL bootstrap refuses non-loopback or differently named databases.
A module shim supplies its initialized app/engine to existing scenario helpers;
it deliberately prevents importing test_api's separate SQLite bootstrap.
"""
import sys
import types
import unittest
import test_postgres  # validates the explicit disposable URL and migrates it
import main

if main.engine.dialect.name != 'postgresql':
    raise SystemExit('Reconstructed regression verification requires PostgreSQL')
fixture = types.ModuleType('test_api')
fixture.app, fixture.engine, fixture.Record = main.app, main.engine, main.Record
sys.modules['test_api'] = fixture

CASES = [
    'test_sales_return_capacity.SalesReturnCapacityTest',
    'test_cash_book_chronology.CashBookChronologyTest',
    'test_record_trail.RecordTrailTest',
    'test_gstin_entry.GstinEntryTest',
    'test_item_activity_scope.ItemActivityScopeTest',
    'test_day_book.DayBookTest',
    'test_rebuilt_import_images.RebuiltImportImagesTest',
    'test_pay_at_invoice.PayAtInvoiceTest',
    'test_rebuilt_pos_tender.RebuiltPosTenderTest',
    'test_restore_integrity.RestoreIntegrityTest',
    'test_recovered_stock_restore.RecoveredStockRestoreTest',
    'test_remaining_stock_restore.RemainingStockRestoreTest',
    'test_restore_core.RestoreCoreTest',
    'test_purchase_return_lines.PurchaseReturnLinesTest',
    'test_purchase_return_lines.RemainingSourceQuantityTest',
    'test_return_tax_residual.ReturnTaxResidualTest',
    'test_vyapar_expanded.ExpandedVyaparTests',
    'test_vyapar_tax_and_openings.VyaparTaxAndOpeningTests',
]
if __name__ == '__main__':
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in CASES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
