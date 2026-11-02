"""Bounded evidence and portable-backup budgets; no secrets or company data."""
import os
MIB=1024*1024
MAX_FILE_BYTES=2*MIB
MAX_FILES_PER_RECORD=5
MAX_FILES_PER_COMPANY=500
MAX_IMAGE_PIXELS=4_000_000

def _company_quota():
    value=os.getenv('APEX_ATTACHMENT_COMPANY_QUOTA_MIB','64')
    try:
        number=int(value)
        if str(number)!=value.strip() or not 1<=number<=256:raise ValueError()
    except (ValueError,TypeError):raise RuntimeError('APEX_ATTACHMENT_COMPANY_QUOTA_MIB must be an integer from 1 to 256') from None
    return number*MIB

COMPANY_QUOTA_BYTES=_company_quota()
BACKUP_CHUNK_BYTES=524288
BACKUP_ARCHIVE_MAX_BYTES=max(128*MIB,COMPANY_QUOTA_BYTES+54*MIB)
BACKUP_COMPANY_JSON_MAX_BYTES=50_000_000
BACKUP_STAGE_TTL_SECONDS=86400

def public_limits():
    return {'attachment_max_file_bytes':MAX_FILE_BYTES,'attachment_company_quota_bytes':COMPANY_QUOTA_BYTES,
            'attachment_max_files_per_record':MAX_FILES_PER_RECORD,'attachment_max_files_per_company':MAX_FILES_PER_COMPANY,
            'backup_chunk_bytes':BACKUP_CHUNK_BYTES,'backup_archive_max_bytes':BACKUP_ARCHIVE_MAX_BYTES,
            'backup_company_json_max_bytes':BACKUP_COMPANY_JSON_MAX_BYTES,'backup_stage_ttl_seconds':BACKUP_STAGE_TTL_SECONDS}
