from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone

LOCAL_TZ = ZoneInfo("Europe/Madrid")


def to_utc(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, LOCAL_TZ)
    return value.astimezone(dt_timezone.utc)


def now_local():
    return timezone.now().astimezone(LOCAL_TZ)


def today_local():
    return now_local().date()
