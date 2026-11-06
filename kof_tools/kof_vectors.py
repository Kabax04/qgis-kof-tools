"""GNSS baselines (vectors) in KOF files.

Post-processing software such as Topcon MAGNET Tools exports baselines as:

    42 <from>  X Y Z ...      start station, geocentric (ECEF) coordinates
    43 <to>    dX dY dZ ...   vector from the last 42 station to <to>
    44 sX sY sZ 1 rXY rXZ 1 rYZ 1   standard deviations and correlations
    46 ddmmyyyy hh:mm:ss ...  observation date and time

One 42 record can be followed by several 43 records; 44 and 46 belong to the
43 record before them.

Plain Python without QGIS dependencies, so it can be tested with pytest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .i18n import tr

VECTOR_RECORDS = ("42", "43", "44", "46")

# GRS80, the ellipsoid of EUREF89/ETRS89.
GRS80_A = 6378137.0
GRS80_F = 1 / 298.257222101


@dataclass
class KofVector:
    from_name: str
    # Start station, geocentric coordinates (metres).
    x: float
    y: float
    z: float
    to_name: str
    dx: float
    dy: float
    dz: float
    line_no: int
    # From the 44 record.
    sx: Optional[float] = None
    sy: Optional[float] = None
    sz: Optional[float] = None
    rxy: Optional[float] = None
    rxz: Optional[float] = None
    ryz: Optional[float] = None
    # From the 46 record: date as YYYY-MM-DD, time as hh:mm:ss, the rest unparsed.
    date: str = ""
    time: str = ""
    info: str = ""

    @property
    def length(self) -> float:
        return math.sqrt(self.dx ** 2 + self.dy ** 2 + self.dz ** 2)

    @property
    def end(self) -> Tuple[float, float, float]:
        return self.x + self.dx, self.y + self.dy, self.z + self.dz


@dataclass
class VectorReader:
    """Collects vectors from 42-46 records, line by line."""

    warnings: List[str]
    vectors: List[KofVector] = field(default_factory=list)
    _station: Optional[Tuple[str, float, float, float]] = None
    _last: Optional[KofVector] = None

    def record(self, record: str, stripped: str, line_no: int) -> None:
        tokens = stripped.split()[1:]
        if record == "42":
            self._last = None
            values = _numbers(tokens[1:4]) if len(tokens) >= 4 else None
            if values is None:
                self._station = None
                self._unreadable(line_no, stripped)
                return
            self._station = (tokens[0], *values)
        elif record == "43":
            self._last = None
            values = _numbers(tokens[1:4]) if len(tokens) >= 4 else None
            if values is None:
                self._unreadable(line_no, stripped)
                return
            if self._station is None:
                self.warnings.append(tr(
                    "Line {line_no}: vector (43) without a start station (42), ignored",
                    line_no=line_no,
                ))
                return
            name, x, y, z = self._station
            dx, dy, dz = values
            self._last = KofVector(name, x, y, z, tokens[0], dx, dy, dz, line_no)
            self.vectors.append(self._last)
        elif record == "44":
            vector = self._vector_for(record, line_no)
            values = _numbers(tokens[:9]) if len(tokens) >= 9 else None
            if vector is None:
                return
            if values is None:
                self._unreadable(line_no, stripped)
                return
            # Upper triangle of the correlation matrix, row by row.
            vector.sx, vector.sy, vector.sz = values[0:3]
            vector.rxy, vector.rxz, vector.ryz = values[4], values[5], values[7]
        elif record == "46":
            vector = self._vector_for(record, line_no)
            if vector is None:
                return
            if tokens:
                vector.date = _date(tokens[0])
            if len(tokens) > 1:
                vector.time = tokens[1]
            vector.info = " ".join(tokens[2:])

    def _vector_for(self, record: str, line_no: int) -> Optional[KofVector]:
        if self._last is None:
            self.warnings.append(tr(
                "Line {line_no}: {record} record without a vector (43) before it, ignored",
                line_no=line_no, record=record,
            ))
        return self._last

    def _unreadable(self, line_no: int, stripped: str) -> None:
        self.warnings.append(tr(
            "Line {line_no}: could not read GNSS vector record: {text}",
            line_no=line_no, text=repr(stripped),
        ))


def _numbers(tokens: List[str]) -> Optional[List[float]]:
    try:
        return [float(t) for t in tokens]
    except ValueError:
        return None


def _date(text: str) -> str:
    """ddmmyyyy -> YYYY-MM-DD. Other text is kept as it is."""
    if len(text) == 8 and text.isdigit():
        return f"{text[4:]}-{text[2:4]}-{text[:2]}"
    return text


def ecef_to_geodetic(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Geocentric X, Y, Z on GRS80 -> (latitude, longitude, ellipsoidal height).

    Degrees and metres. Iterates until the latitude changes less than 1e-12 rad,
    which is well below a millimetre.
    """
    e2 = GRS80_F * (2 - GRS80_F)
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    height = 0.0
    for _ in range(10):
        n = GRS80_A / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        height = p / math.cos(lat) - n
        new_lat = math.atan2(z, p * (1 - e2 * n / (n + height)))
        if abs(new_lat - lat) < 1e-12:
            lat = new_lat
            break
        lat = new_lat
    # This form of the height is accurate at all latitudes, also near the poles.
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    height = p * cos_lat + z * sin_lat - GRS80_A * math.sqrt(1 - e2 * sin_lat ** 2)
    return math.degrees(lat), math.degrees(lon), height


def utm_epsg(latitude: float, longitude: float) -> int:
    """EPSG code of the UTM zone for a position: ETRS89 (258zz) in zones 28-38, else WGS84."""
    zone = min(int((longitude + 180) // 6) + 1, 60)
    if latitude >= 0 and 28 <= zone <= 38:
        return 25800 + zone
    return (32600 if latitude >= 0 else 32700) + zone
