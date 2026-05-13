import logging
from typing import BinaryIO
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_s3_client = None

def get_minio_client():
    global _s3_client
    if _s3_client is None:
        settings = get_settings()
        try:
            import boto3
            _s3_client = boto3.client(
                's3',
                endpoint_url=getattr(settings, 's3_endpoint', None) or 'http://minio:9000',
                aws_access_key_id=getattr(settings, 's3_access_key', 'minioadmin'),
                aws_secret_access_key=getattr(settings, 's3_secret_key', 'minioadmin'),
            )
        except Exception as e:
            logger.warning(f"MinIO client not available: {e}")
            return None
    return _s3_client

def upload_file(file_content: bytes, key: str, content_type: str, bucket: str) -> str:
    client = get_minio_client()
    if client is None:
        return f"local://{bucket}/{key}"
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=file_content,
            ContentType=content_type
        )
        settings = get_settings()
        base_url = getattr(settings, 's3_public_url', None) or settings.s3_endpoint or 'http://minio:9000'
        return f"{base_url}/{bucket}/{key}"
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return f"local://{bucket}/{key}"

def download_file(key: str, bucket: str) -> bytes | None:
    client = get_minio_client()
    if client is None:
        return None
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None

def delete_file(key: str, bucket: str) -> bool:
    client = get_minio_client()
    if client is None:
        return False
    try:
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        return False