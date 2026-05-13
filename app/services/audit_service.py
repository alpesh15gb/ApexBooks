from datetime import datetime
from typing import Any
from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.orm import Session

class AuditLog:
    def __init__(self, db: Session):
        self.db = db

    def log(self, tenant_id: str, actor_id: str, action: str, resource: str, resource_id: str | None = None, details: dict | None = None, ip_address: str | None = None, user_agent: str | None = None):
        from sqlalchemy import text
        import json
        self.db.execute(
            text("""
                INSERT INTO audit_logs (tenant_id, actor_id, action, resource, resource_id, details, ip_address, user_agent, created_at)
                VALUES (:tenant_id, :actor_id, :action, :resource, :resource_id, :details, :ip_address, :user_agent, :created_at)
            """),
            {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "action": action,
                "resource": resource,
                "resource_id": resource_id,
                "details": json.dumps(details) if details else '{}',
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": datetime.utcnow()
            }
        )
        self.db.flush()

    def get_logs(self, tenant_id: str, resource: str | None = None, resource_id: str | None = None, actor_id: str | None = None, limit: int = 100, offset: int = 0):
        from sqlalchemy import text
        query = "SELECT * FROM audit_logs WHERE tenant_id = :tenant_id"
        params = {"tenant_id": tenant_id}
        if resource:
            query += " AND resource = :resource"
            params["resource"] = resource
        if resource_id:
            query += " AND resource_id = :resource_id"
            params["resource_id"] = resource_id
        if actor_id:
            query += " AND actor_id = :actor_id"
            params["actor_id"] = actor_id
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        result = self.db.execute(text(query), params).fetchall()
        return [dict(row._mapping) for row in result]