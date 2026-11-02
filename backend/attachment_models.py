"""Immutable, company-scoped evidence bytes, kept out of financial Record JSON."""
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import String,Integer,Boolean,DateTime,LargeBinary,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column

def configure(m):
    if hasattr(m,'DocumentAttachment'):return
    class DocumentAttachment(m.Base):
        __tablename__='document_attachments'
        __table_args__=(UniqueConstraint('company_id','id'),UniqueConstraint('company_id','record_id','sha256'),
            ForeignKeyConstraint(['company_id','record_id'],['records.company_id','records.id']),
            CheckConstraint('size_bytes > 0 AND size_bytes <= 2097152'),CheckConstraint('size_bytes = length(content)'),CheckConstraint('length(sha256) = 64'),
            CheckConstraint("media_type IN ('application/pdf','image/png','image/jpeg')"),CheckConstraint('version >= 0'))
        id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
        company_id:Mapped[str]=mapped_column(ForeignKey('companies.id'),nullable=False,index=True)
        record_id:Mapped[str]=mapped_column(String,nullable=False,index=True)
        filename:Mapped[str]=mapped_column(String(120),nullable=False)
        media_type:Mapped[str]=mapped_column(String(32),nullable=False)
        size_bytes:Mapped[int]=mapped_column(Integer,nullable=False)
        sha256:Mapped[str]=mapped_column(String(64),nullable=False)
        content:Mapped[bytes]=mapped_column(LargeBinary,nullable=False,deferred=True)
        created_by:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
        created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
        is_archived:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False,server_default='0')
        version:Mapped[int]=mapped_column(Integer,nullable=False,default=0,server_default='0')
    class AttachmentWriteKey(m.Base):
        __tablename__='attachment_write_keys'
        __table_args__=(UniqueConstraint('company_id','key'),ForeignKeyConstraint(['company_id','attachment_id'],['document_attachments.company_id','document_attachments.id']))
        id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
        company_id:Mapped[str]=mapped_column(ForeignKey('companies.id'),nullable=False,index=True)
        key:Mapped[str]=mapped_column(String(80),nullable=False)
        request_hash:Mapped[str]=mapped_column(String(64),nullable=False)
        attachment_id:Mapped[str]=mapped_column(String,nullable=False)
    m.DocumentAttachment=DocumentAttachment;m.AttachmentWriteKey=AttachmentWriteKey
