from collections import defaultdict
from copy import deepcopy
from uuid import uuid4
from datetime import datetime

class TenantRepository:
    """Simple repository abstraction. Swap this with SQLAlchemy repositories without changing routers."""
    def __init__(self):
        self._data = defaultdict(dict)
    def key(self, tenant_id: str, resource: str) -> str:
        return f"{tenant_id}:{resource}"
    def create(self, tenant_id: str, resource: str, payload: dict, id_field: str = "id") -> dict:
        row = deepcopy(payload)
        row.setdefault(id_field, str(uuid4()))
        row.setdefault("created_at", datetime.utcnow().isoformat())
        row.setdefault("updated_at", datetime.utcnow().isoformat())
        row.setdefault("is_deleted", False)
        self._data[self.key(tenant_id, resource)][str(row[id_field])] = row
        return deepcopy(row)
    def list(self, tenant_id: str, resource: str, include_deleted: bool = False) -> list[dict]:
        rows = list(self._data[self.key(tenant_id, resource)].values())
        return deepcopy(rows if include_deleted else [r for r in rows if not r.get("is_deleted")])
    def get(self, tenant_id: str, resource: str, row_id: str) -> dict | None:
        row = self._data[self.key(tenant_id, resource)].get(str(row_id))
        return deepcopy(row) if row and not row.get("is_deleted") else None
    def update(self, tenant_id: str, resource: str, row_id: str, payload: dict) -> dict:
        existing = self._data[self.key(tenant_id, resource)].get(str(row_id), {})
        row = {**existing, **deepcopy(payload), "updated_at": datetime.utcnow().isoformat()}
        self._data[self.key(tenant_id, resource)][str(row_id)] = row
        return deepcopy(row)
    def soft_delete(self, tenant_id: str, resource: str, row_id: str) -> None:
        if str(row_id) in self._data[self.key(tenant_id, resource)]:
            self._data[self.key(tenant_id, resource)][str(row_id)]["is_deleted"] = True

repo = TenantRepository()

def tenant_id(header_value: str | None) -> str:
    return header_value or "public"
