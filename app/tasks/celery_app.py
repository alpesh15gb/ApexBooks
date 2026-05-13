from celery import Celery
from app.core.config import get_settings
celery_app = Celery('gst_api_engine', broker=get_settings().redis_url, backend=get_settings().redis_url)
