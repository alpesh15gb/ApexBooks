from typing import Any
from fastapi import APIRouter, Depends
from app.api.v1.deps import current_tenant
from app.core.exceptions import ok, APIError
from app.services.repository import repo

def page(rows: list[dict], page: int = 1, per_page: int = 25):
    total=len(rows); start=(page-1)*per_page; end=start+per_page
    return rows[start:end], {"page":page,"per_page":per_page,"total":total,"total_pages":(total+per_page-1)//per_page if per_page else 1}

router=APIRouter(tags=['Item Masters'])
@router.get('/hsn-codes')
def hsn_codes(search: str | None = None): return ok([{'code':'1001','description':'Wheat'},{'code':'998314','description':'IT design and development services'}])
@router.get('/sac-codes')
def sac_codes(search: str | None = None): return ok([{'code':'998314','description':'Information technology services'}])
@router.get('/tax-rates')
def tax_rates(): return ok([0,0.1,0.25,1,1.5,3,5,7.5,12,18,28])
