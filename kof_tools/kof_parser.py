"""Parser for KOF files.

Plain Python without QGIS dependencies, so it can be tested with pytest.
The column layout follows the KOF specification version 2.00 (Norkart, 2005).

KOF stores coordinates as N (north) before E (east). The parser keeps those
names; the swap to x = E, y = N happens when the layers are built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Union

from .i18n import tr
from .kof_lines import KofLine, LineTracker
from .kof_vectors import VECTOR_RECORDS, KofVector, VectorReader

ENCODINGS = ("utf-8-sig", "cp1252")

# Fixed columns of 05 records (0-based slices).
COL_NAME = slice(4, 14)
COL_CODE = slice(15, 23)
COL_NORTH = slice(24, 36)
COL_EAST = slice(37, 48)
COL_HEIGHT = slice(49, 57)
COL_BK = slice(57, 61)
COL_REMARK = slice(61, None)

# Fixed columns of 01 records, version 2 (recognised by "$" in the units field).
COL_01_JOB = slice(4, 16)
COL_01_DATE = slice(17, 25)
COL_01_VERSION = slice(26, 29)
COL_01_CRS = slice(30, 37)
COL_01_MUNICIPALITY = slice(38, 42)
COL_01_UNITS = slice(43, 55)
COL_01_OBSERVER = slice(56, None)


@dataclass
class KofPoint:
    name: str
    code: str
    north: float
    east: float
    height: Optional[float]
    line_no: int
    # Calculation code (30-38) and remark, including a comment after "!".
    bk: Optional[int] = None
    remark: str = ""


@dataclass
class KofHeader:
    """01 block in version 2 format."""

    job: str
    date: str
    version: Optional[int]
    crs_code: Optional[int]
    municipality: Optional[int]
    units: str
    observer: str

    @property
    def east_first(self) -> bool:
        # 2nd character of the units field: direction of the 1st axis, 1 = north, 2 = east.
        return self.units[1:2] == "2"


@dataclass
class KofResult:
    points: List[KofPoint] = field(default_factory=list)
    # Lines and polygons from 09 blocks. Their points are also in `points`.
    lines: List[KofLine] = field(default_factory=list)
    # GNSS baselines from 42/43 records, with 44 and 46 attached.
    vectors: List[KofVector] = field(default_factory=list)
    # "Key: value" from 00 comments, e.g. {"Projeksjon": "NORWAY-EUREF89 UTM 32"}
    metadata: dict = field(default_factory=dict)
    comments: List[str] = field(default_factory=list)
    # Raw text of all 01 records, and the last one that parsed as version 2.
    headers: List[str] = field(default_factory=list)
    header: Optional[KofHeader] = None
    # Number of lines disabled with "-" in column 1.
    disabled: int = 0
    warnings: List[str] = field(default_factory=list)
    encoding: Optional[str] = None
    source: Optional[str] = None

    def swap_axes(self) -> None:
        for point in self.points:
            point.north, point.east = point.east, point.north


def read_text(path: Union[str, Path]) -> "tuple[str, str]":
    """Read the file and return (text, encoding)."""
    data = Path(path).read_bytes()
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # cp1252 has a few undefined bytes; keep the rest of the file.
    return data.decode("cp1252", errors="replace"), "cp1252"


def parse_file(path: Union[str, Path]) -> KofResult:
    text, encoding = read_text(path)
    result = parse_lines(text.splitlines())
    result.encoding = encoding
    result.source = str(path)
    return result


# Returned by _parse_point_fixed for a well-formed line without north or east.
_MISSING = object()


def parse_lines(lines: Iterable[str]) -> KofResult:
    result = KofResult()
    tracker = LineTracker(result.warnings)
    vectors = VectorReader(result.warnings)
    for line_no, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("-"):
            result.disabled += 1
            continue
        record = stripped[:2]
        if record == "00":
            # Free text; "!" is not a comment marker here.
            _parse_comment(stripped[2:].strip(), result)
            continue

        line, _, comment = line.partition("!")
        line = line.rstrip()
        if record == "01":
            result.headers.append(line.strip()[2:].strip())
            header = _parse_header(line)
            if header is not None:
                result.header = header
        elif record == "05":
            point = _parse_point(line, line_no)
            if point is _MISSING:
                result.warnings.append(tr(
                    "Line {line_no}: point {name} is missing north or east coordinate, ignored",
                    line_no=line_no, name=line[COL_NAME].strip(),
                ))
                continue
            if point is None:
                result.warnings.append(tr(
                    "Line {line_no}: could not read point: {text}",
                    line_no=line_no, text=repr(stripped),
                ))
                continue
            if result.header is not None and result.header.east_first:
                point.north, point.east = point.east, point.north
            point.remark = " ".join(t for t in (point.remark, comment.strip()) if t)
            result.points.append(point)
            tracker.point(point)
        elif record == "09":
            pi = _program_code(stripped)
            if pi is None:
                # Some instruments use 09 for free text, e.g. "09 Laget av versjon 5.5.1".
                result.comments.append(stripped[2:].strip())
            else:
                tracker.program(pi, line_no)
        elif record == "08":
            if stripped[2:].split()[:1] == ["141"]:
                result.warnings.append(tr(
                    "Line {line_no}: radius (08 141) is not supported, drawn as a straight line",
                    line_no=line_no,
                ))
            # Other property codes do not affect the geometry.
        elif record in VECTOR_RECORDS:
            vectors.record(record, line.strip(), line_no)
        else:
            result.warnings.append(tr(
                "Line {line_no}: unknown record type {record}, ignored",
                line_no=line_no, record=repr(record),
            ))
    result.lines = tracker.finish()
    result.vectors = vectors.vectors
    return result


def _program_code(stripped: str) -> Optional[int]:
    """The program code (Pi) of a 09 block, e.g. 91 in "09 91" or "09_91"."""
    tokens = stripped[2:].lstrip("_").split()
    if tokens and tokens[0].isdigit() and len(tokens[0]) <= 2:
        return int(tokens[0])
    return None


def _parse_comment(text: str, result: KofResult) -> None:
    result.comments.append(text)
    key, sep, value = text.partition(":")
    if sep and key.strip():
        result.metadata[key.strip()] = value.strip()


def _to_int(text: str) -> Optional[int]:
    text = text.strip()
    return int(text) if text.isdigit() else None


def _parse_header(line: str) -> Optional[KofHeader]:
    units = line[COL_01_UNITS].strip()
    if not units.startswith("$"):
        # Version 1 has a different, free layout that we do not interpret.
        return None
    return KofHeader(
        job=line[COL_01_JOB].strip(),
        date=line[COL_01_DATE].strip(),
        version=_to_int(line[COL_01_VERSION]),
        crs_code=_to_int(line[COL_01_CRS]),
        municipality=_to_int(line[COL_01_MUNICIPALITY]),
        units=units,
        observer=line[COL_01_OBSERVER].strip(),
    )


def _parse_point(line: str, line_no: int):
    """Return a KofPoint, _MISSING or None (unreadable)."""
    point = _parse_point_fixed(line, line_no)
    if point is None:
        point = _parse_point_tokens(line, line_no)
    return point


def _to_float(text: str) -> Optional[float]:
    try:
        return float(text)
    except ValueError:
        return None


def _fixed_number(line: str, columns: slice) -> "tuple[Optional[float], bool]":
    """Read a numeric field. Returns (value, aligned).

    The field is aligned if it is empty, or holds a number that does not run
    into the neighbouring columns.
    """
    text = line[columns].strip()
    if not text:
        return None, True
    before = line[columns.start - 1:columns.start]
    after = line[columns.stop:columns.stop + 1]
    value = _to_float(text)
    aligned = value is not None and before in (" ", "") and after in (" ", "")
    return value, aligned


def _parse_point_fixed(line: str, line_no: int):
    """Read a 05 record using the standard column layout.

    Returns None if the line does not follow the layout, so the caller can
    fall back to reading tokens, and _MISSING if it follows the layout but
    lacks north or east.
    """
    if "\t" in line:
        return None
    north, north_ok = _fixed_number(line, COL_NORTH)
    east, east_ok = _fixed_number(line, COL_EAST)
    height, height_ok = _fixed_number(line, COL_HEIGHT)
    if not (north_ok and east_ok and height_ok):
        return None
    if north is None or east is None:
        return _MISSING
    # After H come the calculation code (I2) and a remark. Anything other than
    # an integer where Bk belongs is treated as part of the remark.
    bk_text = line[COL_BK].strip()
    bk = _to_int(bk_text)
    if bk_text and bk is None:
        remark = line[COL_BK.start:].strip()
    else:
        remark = line[COL_REMARK].strip()
    return KofPoint(
        name=line[COL_NAME].strip(),
        code=line[COL_CODE].strip(),
        north=north,
        east=east,
        height=height,
        line_no=line_no,
        bk=bk,
        remark=remark,
    )


def _parse_point_tokens(line: str, line_no: int) -> Optional[KofPoint]:
    """Fallback for files with irregular columns: read coordinates from the right.

    The first word is the point name. Of the words after the name, the last
    2-3 numbers are read as N, E and optionally H; anything before them is
    the code. Calculation code and remark are not supported here.
    """
    tokens = line.split()[1:]
    if len(tokens) < 3:
        return None
    name, rest = tokens[0], tokens[1:]
    numbers = []
    while rest and len(numbers) < 3 and _to_float(rest[-1]) is not None:
        numbers.insert(0, float(rest.pop()))
    if len(numbers) < 2:
        return None
    if len(numbers) == 2:
        north, east, height = numbers[0], numbers[1], None
    else:
        north, east, height = numbers
    return KofPoint(
        name=name,
        code=" ".join(rest),
        north=north,
        east=east,
        height=height,
        line_no=line_no,
    )
