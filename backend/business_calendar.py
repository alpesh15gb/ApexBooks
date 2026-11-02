"""India business-day defaults. Audit/session instants remain UTC elsewhere."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    INDIA_TIMEZONE = ZoneInfo('Asia/Kolkata')
except ZoneInfoNotFoundError:
    # Windows minimal Python installs may not ship an IANA database. Current
    # Indian business dates use UTC+05:30, with no DST; explicit old dates are
    # never interpreted or converted by this default-only helper.
    INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name='Asia/Kolkata')


def business_today(now: datetime | None = None) -> date:
    instant = datetime.now(timezone.utc) if now is None else now
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('Business calendar requires an aware instant')
    return instant.astimezone(INDIA_TIMEZONE).date()


def financial_year_start(value: date | None = None) -> int:
    day = business_today() if value is None else value
    return day.year if day.month >= 4 else day.year - 1
