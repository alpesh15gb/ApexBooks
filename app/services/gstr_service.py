from decimal import Decimal
from app.services.gst_engine import classify_gstr1

def gstr1_payload(gstin: str, month: int, year: int, invoices: list[dict]) -> dict:
    tables = {"b2b": [], "b2cl": [], "b2cs": [], "exp": [], "cdnr": [], "cdnur": [], "hsn": [], "doc_issue": []}
    for inv in invoices:
        cls = classify_gstr1(inv).lower()
        key = "doc_issue" if cls == "docs" else cls
        if key in tables: tables[key].append(inv)
    return {"gstin": gstin, "fp": f"{month:02d}{year}", **tables}

def gstr3b_compute(sales: list[dict], purchases: list[dict]) -> dict:
    outward = sum(Decimal(str(i.get("grand_total", 0))) for i in sales)
    tax = {k: sum(Decimal(str(i.get(k, 0))) for i in sales) for k in ["total_igst", "total_cgst", "total_sgst", "total_cess"]}
    itc = {k: sum(Decimal(str(i.get(k, 0))) for i in purchases) for k in ["total_igst", "total_cgst", "total_sgst", "total_cess"]}
    return {"sup_details": {"osup_det": {"txval": outward, **tax}}, "itc_elg": {"itc_avl": itc}, "inward_sup": {}, "intr_ltfee": {}}
