import base64
import binascii
import httpx
import json
import os
import re
from accounting import company_for, current_user, db, require_write
from fastapi import APIRouter, Depends, HTTPException
from models import User
from ocr_transport import validate_ocr_base_url
from schemas import OcrInput
from sqlalchemy.orm import Session


router = APIRouter()


def ocr_configuration():
    try: base_url = validate_ocr_base_url(os.getenv('OCR_BASE_URL', 'https://api.openai.com/v1'))
    except ValueError as exc: raise HTTPException(503, str(exc)) from None
    external_provider = base_url != 'https://api.openai.com/v1'
    key = (os.getenv('OMNIROUTE_API_KEY') or os.getenv('OMNIROUTE', '')) if external_provider else os.getenv('OPENAI_API_KEY', '')
    if not key: raise HTTPException(503, 'OCR is not configured on this server')
    return base_url, key, os.getenv('OCR_MODEL', os.getenv('OPENAI_OCR_MODEL', 'gpt-4o-mini'))


@router.get('/api/ocr/status')
def ocr_status(user: User = Depends(current_user)):
    try: ocr_configuration()
    except HTTPException as exc: return {'ready': False, 'message': exc.detail}
    return {'ready': True, 'message': 'OCR draft extraction is configured'}


@router.post('/api/companies/{company_id}/ocr/purchase-draft')
def ocr_purchase_draft(company_id: str, body: OcrInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    require_write(company, user, session)
    base_url, key, model = ocr_configuration()
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', body.image_data_url)
    if not match: raise HTTPException(422, 'Upload a PNG, JPEG or WebP image')
    try: raw = base64.b64decode(match.group(2), validate=True)
    except binascii.Error: raise HTTPException(422, 'Invalid image encoding')
    if len(raw) > 5_000_000: raise HTTPException(413, 'Image exceeds 5 MB')
    image_type = match.group(1)
    signature_ok = (image_type == 'png' and raw.startswith(b'\x89PNG\r\n\x1a\n')
                    or image_type == 'jpeg' and raw.startswith(b'\xff\xd8\xff')
                    or image_type == 'webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')
    if not signature_ok: raise HTTPException(422, 'Image content does not match its file type')
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['supplier_name','supplier_gstin','supplier_address','place_of_supply','invoice_number','invoice_date','total','items'], 'properties': {
        'supplier_name': {'type': 'string'},'supplier_gstin':{'type':'string'},'supplier_address':{'type':'string'},'place_of_supply':{'type':'string'}, 'invoice_number': {'type': 'string'}, 'invoice_date': {'type': 'string'}, 'total': {'type': 'string'},
        'items': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['description', 'quantity', 'rate', 'gst_rate', 'hsn'], 'properties': {key: {'type': 'string'} for key in ('description', 'quantity', 'rate', 'gst_rate', 'hsn')}}}
    }}
    payload = {'model': model, 'store': False,
        'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Extract this purchase invoice into JSON. Use YYYY-MM-DD for date, a two-digit Indian state code for place_of_supply, the printed GSTIN for supplier_gstin, and decimal strings for money and quantities. Rates must exclude GST; when only a tax-inclusive price is printed, derive the pre-tax rate from the explicit printed GST rate. For gst_rate, return the printed percentage as a number string, for example "18" for "18 percent" or "18%". Leave uncertain fields blank. Do not infer input-credit eligibility, tax treatment or missing data.'}, {'type': 'input_image', 'image_url': body.image_data_url, 'detail': 'high'}]}],
        'text': {'format': {'type': 'json_schema', 'name': 'purchase_invoice_draft', 'strict': True, 'schema': schema}}}
    try:
        response = httpx.post(base_url + '/responses', json=payload, headers={'Authorization': 'Bearer ' + key}, timeout=45)
        response.raise_for_status()
        result = response.json()
        text_blocks = [part.get('text', '') for item in result.get('output', []) if item.get('type') == 'message' for part in item.get('content', []) if part.get('type') == 'output_text']
        if not text_blocks: raise ValueError('No extraction returned')
        draft = json.loads(''.join(text_blocks))
        if not isinstance(draft, dict) or not isinstance(draft.get('items'), list): raise ValueError('Invalid extraction')
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(502, 'OCR could not extract a draft; enter the bill manually')
    return {'status': 'review_required', 'draft': draft}
