"""Report-specific preparation limits shared by API views and exports."""
STATEMENT_LIMITATIONS = ('Depreciation, net realisable value write-downs and accruals are not calculated; '
                        'review with your accountant before using these statements for filing or lending.')
AGEING_BASIS = ('Age buckets use the document date. Where entered, the due date and days overdue are shown separately. '
               'Payments and linked notes dated through the selected day reduce open amounts. '
               'Manual ledger adjustments are not allocated to individual documents.')
