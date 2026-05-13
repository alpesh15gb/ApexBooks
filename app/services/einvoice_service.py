from datetime import datetime
from uuid import uuid4

def build_irp_json(invoice: dict, seller: dict | None = None, buyer: dict | None = None) -> dict:
    return {
        "Version": "1.1",
        "TranDtls": {"TaxSch": "GST", "SupTyp": invoice.get("supply_type", "B2B"), "RegRev": "Y" if invoice.get("reverse_charge") else "N"},
        "DocDtls": {"Typ": "INV", "No": invoice.get("invoice_number"), "Dt": str(invoice.get("invoice_date"))},
        "SellerDtls": seller or {}, "BuyerDtls": buyer or {},
        "ItemList": invoice.get("line_items", []),
        "ValDtls": {"AssVal": invoice.get("subtotal", 0), "CgstVal": invoice.get("total_cgst", 0), "SgstVal": invoice.get("total_sgst", 0), "IgstVal": invoice.get("total_igst", 0), "CesVal": invoice.get("total_cess", 0), "RndOffAmt": invoice.get("round_off", 0), "TotInvVal": invoice.get("grand_total", 0)},
    }

def push_to_irp(invoice: dict) -> dict:
    return {"irn": uuid4().hex + uuid4().hex, "ack_no": str(uuid4().int)[:15], "ack_date": datetime.utcnow().isoformat(), "qr_code_data": "mock-base64-qr", "signed_invoice": "mock.jwt.signed", "e_invoice_status": "Generated"}
