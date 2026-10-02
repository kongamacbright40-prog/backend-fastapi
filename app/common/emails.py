from typing import Annotated

from pydantic import BeforeValidator, EmailStr


def _normalize(value):
    return value.strip().lower() if isinstance(value, str) else value


# Input email: surrounding spaces removed and lower-cased, so "Amina@Uni.edu "
# (e.g. typed on a phone keyboard that capitalizes) matches "amina@uni.edu".
Email = Annotated[EmailStr, BeforeValidator(_normalize)]
