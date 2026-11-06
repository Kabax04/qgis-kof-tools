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


# å, Å, ø and Ø in the DOS code pages CP865 (Nordic) and CP850 (same bytes
# for these letters). In cp1252 they are †, an unused byte, › and an unused
# byte, which Norwegian text does not have.
DOS_LETTERS = {0x86, 0x8F, 0x9B, 0x9D}
# Plus æ and Æ, which are ‘ and ’ in cp1252 and too common to go by alone.
DOS_NORWEGIAN = DOS_LETTERS | {0x91, 0x92}


def _looks_like_dos(data: bytes) -> bool:
    """Whether the high bytes are only Norwegian letters in CP865/CP850."""
    high = {b for b in data if b >= 0x80}
    return bool(high & DOS_LETTERS) and high <= DOS_NORWEGIAN


def read_text(path: Union[str, Path]) -> "tuple[str, str]":
    """Read the file and return (text, encoding).

    UTF-8 (with or without BOM) and UTF-16 (with BOM) are recognised, and
    files from old DOS programs in CP865. Anything else is read as cp1252.
    """
    data = Path(path).read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        pass
    if _looks_like_dos(data):
        return data.decode("cp865"), "cp865"
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
# Returned by _parse_point_tokens when the words fit more than one reading.
_AMBIGUOUS = object()

# A number after north and east larger than this is not read as a height.
MAX_HEIGHT = 10000.0


def parse_lines(lines: Iterable[str]) -> KofResult:
    result = KofResult()
    tracker = LineTracker(result.warnings)
    vectors = VectorReader(result.warnings)
    # Line numbers of points read by _parse_point_tokens, and of unknown records by type.
    irregular: List[int] = []
    unknown: dict = {}
    for line_no, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("-"):
            result.disabled += 1
            continue
        # Column 1 is blank, and the fixed columns count from there. Some
        # files leave it out or indent more; shift the line into place.
        if not line.startswith(" ") or line[1:2].isspace():
            line = " " + line.lstrip()
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
            point = _parse_point_fixed(line, line_no)
            if point is None:
                point = _parse_point_tokens(line, line_no)
                if point is _AMBIGUOUS:
                    result.warnings.append(tr(
                        "Line {line_no}: point {name} has irregular columns, and its code and coordinates "
                        "cannot be told apart, ignored: {text}",
                        line_no=line_no, name=line.split()[1], text=repr(stripped),
                    ))
                    continue
                if point is not None:
                    irregular.append(line_no)
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
            unknown.setdefault(record, []).append(line_no)
    # One warning per unknown record type, so a file with thousands of
    # observation records does not drown the other warnings.
    for record, line_nos in unknown.items():
        if len(line_nos) == 1:
            result.warnings.append(tr(
                "Line {line_no}: unknown record type {record}, ignored",
                line_no=line_nos[0], record=repr(record),
            ))
        else:
            result.warnings.append(tr(
                "{count} lines with unknown record type {record} ignored, first at line {line_no}",
                count=len(line_nos), record=repr(record), line_no=line_nos[0],
            ))
    if irregular:
        result.warnings.append(tr(
            "{count} point(s) do not follow the KOF columns and were read word by word. "
            "Check their code and coordinates. First at line {line_no}.",
            count=len(irregular), line_no=irregular[0],
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
    # The name and the code must end where their columns end.
    if line[COL_NAME.stop:COL_NAME.stop + 1].strip() or line[COL_CODE.stop:COL_CODE.stop + 1].strip():
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


def _is_number(text: str) -> bool:
    return _to_float(text) is not None


def _parse_point_tokens(line: str, line_no: int):
    """Fallback for files with irregular columns (tabs or shifted fields).

    Returns a KofPoint, None (unreadable) or _AMBIGUOUS.

    The first word is the point name. The last run of numbers holds an
    optional numeric code, N, E, an optional H and an optional calculation
    code; words before it are the code and words after it the remark. Every
    way of placing N and E in the run is tried, and kept if the rest fits:
    numbers before N must be whole (a code), at most H and a calculation
    code may follow E, H must be below MAX_HEIGHT and the calculation code a
    whole number of at most two digits. If several placements fit, the one
    where N and E both have decimals wins; if that does not settle it, the
    line is ambiguous rather than guessed.
    """
    tokens = line.split()[1:]
    if len(tokens) < 3:
        return None
    name, rest = tokens[0], tokens[1:]
    end = len(rest)
    while end > 0 and not _is_number(rest[end - 1]):
        end -= 1
    start = end
    while start > 0 and _is_number(rest[start - 1]):
        start -= 1
    numbers = rest[start:end]
    if len(numbers) < 2:
        return None

    readings = []
    for i in range(len(numbers) - 1):
        codes, after = numbers[:i], numbers[i + 2:]
        if not all(t.isdigit() for t in codes) or len(after) > 2:
            continue
        height = float(after[0]) if after else None
        if height is not None and abs(height) >= MAX_HEIGHT:
            continue
        bk = None
        if len(after) == 2:
            if not (after[1].isdigit() and len(after[1]) <= 2):
                continue
            bk = int(after[1])
        readings.append((i, codes, height, bk))
    if len(readings) > 1:
        with_decimals = [r for r in readings if "." in numbers[r[0]] and "." in numbers[r[0] + 1]]
        if len(with_decimals) != 1:
            return _AMBIGUOUS
        readings = with_decimals
    if not readings:
        return None
    (i, codes, height, bk), = readings
    return KofPoint(
        name=name,
        code=" ".join(rest[:start] + codes),
        north=float(numbers[i]),
        east=float(numbers[i + 1]),
        height=height,
        line_no=line_no,
        bk=bk,
        remark=" ".join(rest[end:]),
    )
