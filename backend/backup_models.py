"""Durable bounded transport staging; never stores live accounting replacements."""
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import String,Integer,BigInteger,DateTime,ForeignKey,UniqueConstraint,CheckConstraint,LargeBinary,JSON
from sqlalchemy.orm import Mapped,mapped_column

def configure(m):
    if hasattr(m,'BackupJob'):return
    class BackupJob(m.Base):
        __tablename__='backup_jobs'
        __table_args__=(UniqueConstraint('user_id','request_key'),CheckConstraint('byte_count >= 0 AND reserved_bytes >= 0'),)
        id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
        user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False,index=True)
        company_id:Mapped[str|None]=mapped_column(ForeignKey('companies.id'),nullable=True,index=True)
        direction:Mapped[str]=mapped_column(String(8),nullable=False)
        state:Mapped[str]=mapped_column(String(16),nullable=False)
        company_name:Mapped[str]=mapped_column(String(120),nullable=False,default='')
        request_key:Mapped[str]=mapped_column(String(80),nullable=False)
        request_hash:Mapped[str]=mapped_column(String(64),nullable=False)
        byte_count:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
        sha256:Mapped[str]=mapped_column(String(64),nullable=False,default='')
        reserved_bytes:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
        created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
        expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,index=True)
        report:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
        restored_company_id:Mapped[str|None]=mapped_column(ForeignKey('companies.id'),nullable=True)
    class BackupChunk(m.Base):
        __tablename__='backup_chunks'
        __table_args__=(CheckConstraint('chunk_index >= 0 AND size_bytes > 0 AND size_bytes <= 524288 AND size_bytes = length(content) AND length(sha256) = 64'),)
        job_id:Mapped[str]=mapped_column(ForeignKey('backup_jobs.id',ondelete='CASCADE'),primary_key=True)
        chunk_index:Mapped[int]=mapped_column(Integer,primary_key=True)
        size_bytes:Mapped[int]=mapped_column(Integer,nullable=False)
        sha256:Mapped[str]=mapped_column(String(64),nullable=False)
        content:Mapped[bytes]=mapped_column(LargeBinary,nullable=False)
    class BackupStorageBudget(m.Base):
        __tablename__='backup_storage_budget'
        __table_args__=(CheckConstraint('reserved_bytes >= 0'),)
        id:Mapped[str]=mapped_column(String(32),primary_key=True)
        reserved_bytes:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
    m.BackupJob=BackupJob;m.BackupChunk=BackupChunk;m.BackupStorageBudget=BackupStorageBudget
