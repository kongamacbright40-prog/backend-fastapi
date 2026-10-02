from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """The database stores naive UTC timestamps (``datetime.utcnow``)."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# Naive UTC datetimes serialized with an explicit "Z" so clients don't read
# them as local time.
UTCDateTime = Annotated[datetime, PlainSerializer(_serialize, return_type=str)]
