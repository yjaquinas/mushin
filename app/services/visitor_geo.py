"""GeoIP lookup helpers for visitor analytics."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import geoip2.database


@lru_cache(maxsize=1)
def _geo_reader() -> geoip2.database.Reader | None:
    path = os.getenv("GEOIP_DATABASE_PATH", "")
    if not path:
        return None
    db_path = Path(path)
    if not db_path.exists():
        return None
    return geoip2.database.Reader(str(db_path))


def lookup_location(ip_address: str) -> dict[str, str | None]:
    reader = _geo_reader()
    if reader is None or not ip_address:
        return empty_location()
    try:
        response = reader.city(ip_address)
    except Exception:
        return empty_location()
    subdivision = response.subdivisions.most_specific
    return {
        "country_code": response.country.iso_code,
        "country_name": response.country.name,
        "region": subdivision.name,
        "city": response.city.name,
    }


def empty_location() -> dict[str, str | None]:
    return {"country_code": None, "country_name": None, "region": None, "city": None}
