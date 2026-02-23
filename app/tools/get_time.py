"""
Tool: get_time
Returns the current date/time for a given IANA timezone string.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


async def get_time(timezone: str = "UTC") -> dict[str, str]:
    """
    Return current date and time for the requested timezone.

    Args:
        timezone: IANA timezone name, e.g. "America/New_York".  Defaults to UTC.
    """
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning("Unknown timezone '%s', falling back to UTC", timezone)
        tz = ZoneInfo("UTC")
        timezone = "UTC"

    now = datetime.now(tz)
    return {
        "timezone": timezone,
        "datetime": now.isoformat(),
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "utc_offset": now.strftime("%z"),
    }
