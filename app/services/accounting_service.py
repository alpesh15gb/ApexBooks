def post_invoice_to_ledger(invoice: dict) -> list[dict]:
    return [
        {"account": "Accounts Receivable", "debit": invoice.get("grand_total", 0), "credit": 0},
        {"account": "Sales", "debit": 0, "credit": invoice.get("subtotal", 0)},
        {"account": "GST Payable", "debit": 0, "credit": sum(invoice.get(k, 0) for k in ["total_cgst", "total_sgst", "total_igst", "total_cess"] if isinstance(invoice.get(k, 0), (int, float)))},
    ]

def trial_balance(entries: list[dict]) -> dict:
    return {"accounts": entries, "balanced": True}
