"""Writer for KOF files.

Plain Python without QGIS dependencies, so it can be tested with pytest.
Records are written in the fixed columns that kof_parser reads, following
the KOF specification version 2.00 (Norkart, 2005):

    -05 PPPPPPPPPP KKKKKKKK NNNNNNNN.NNN EEEEEEE.EEE HHHH.HHH Bk MMMMMMM

Lines and polygons are written as 09 blocks with program code 91
(straight line), ended by 99 or, for polygons, 96.

Coordinates are written north before east, and the 01 block says so.
Values that do not fit are shortened or left out, and reported in
`warnings` instead of breaking the columns.
"""

from __future__ import annotations

import math
from datetime import date as Date
from pathlib import Path
from typing import List, Optional, Union

from .crs_detect import sosi_code_from_epsg
from .i18n import tr
from .kof_parser import COL_CODE, COL_EAST, COL_HEIGHT, COL_NAME, COL_NORTH, COL_01_JOB

DEFAULT_ENCODING = "cp1252"
# Instruments and Windows software expect CRLF.
NEWLINE = "\r\n"

# North before east, see KofHeader.east_first.
UNITS_NORTH_FIRST = "$11100000000"
HEADER_LABELS = " 00 Oppdrag      Dato     Ver   K.sys K.nr        Enhet    Observatør"

NAME_WIDTH = COL_NAME.stop - COL_NAME.start
CODE_WIDTH = COL_CODE.stop - COL_CODE.start
NORTH_WIDTH = COL_NORTH.stop - COL_NORTH.start
EAST_WIDTH = COL_EAST.stop - COL_EAST.start
HEIGHT_WIDTH = COL_HEIGHT.stop - COL_HEIGHT.start
JOB_WIDTH = COL_01_JOB.stop - COL_01_JOB.start

# Number of examples named in each warning.
EXAMPLES = 3


def _clean(text) -> str:
    """Text for a single record: no line breaks or tabs, which break the columns."""
    if text is None:
        return ""
    return " ".join(str(text).replace("\t", " ").splitlines()).strip()


def _number(value) -> Optional[float]:
    """The value as a float, or None if it is missing (None, NaN or not a number)."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def _fit(value: float, width: int, decimals: int) -> Optional[str]:
    text = f"{value:.{decimals}f}"
    return text if len(text) <= width else None


class KofWriter:
    """Collects KOF records. Write `text()` or `save()` when done.

        writer = KofWriter()
        writer.header(job="Oppmåling", epsg=25832)
        writer.point("100", "2000", 6615798.981, 599667.952, 98.848)
        writer.save("ut.kof")
    """

    def __init__(self):
        self.records: List[str] = []
        self.points = 0
        self.lines = 0
        self.polygons = 0
        # Index in records and point count where the open 09 block started.
        self._block: Optional[tuple] = None
        # Names of the points behind each kind of warning.
        self._long_names: List[str] = []
        self._long_codes: List[str] = []
        self._missing: List[str] = []
        self._too_large: List[str] = []
        self._height_too_large: List[str] = []
        self._bad_bk: List[str] = []
        self._short_lines: List[str] = []

    def comment(self, text: str) -> None:
        """One 00 record per line of text."""
        for line in str(text).splitlines() or [""]:
            self.records.append(f" 00 {line.strip()}".rstrip())

    def header(
        self,
        job: str = "",
        epsg: Optional[int] = None,
        date: Optional[Date] = None,
        observer: str = "",
        height_system: Optional[str] = None,
    ) -> None:
        """The 01 block (version 2) with column labels, plus 00 comments for the CRS.

        The EPSG code is written as a comment as well, so the CRS is known
        even when it has no SOSI code.
        """
        if epsg is not None:
            self.comment(f"EPSG: {epsg}")
        if height_system:
            self.comment(f"Høydesystem: {height_system}")
        sosi = sosi_code_from_epsg(epsg) if epsg is not None else None
        day = (date or Date.today()).strftime("%d%m%Y")
        self.records.append(HEADER_LABELS)
        self.records.append(
            f" 01 {_clean(job)[:JOB_WIDTH]:<{JOB_WIDTH}} {day:>8} {'2':>3} "
            f"{sosi if sosi is not None else '':>7} {'':>4} {UNITS_NORTH_FIRST:<12} {_clean(observer)}".rstrip()
        )

    def start_line(self, pi: int = 91) -> None:
        """Start a line, by default straight (09 91); 93 gives a circular arc.

        Add its points with point(), then call end_line().
        """
        if self._block is not None:
            self.end_line()
        self._block = (len(self.records), self.points)
        self.records.append(f" 09 {pi}")

    def end_line(self, closed: bool = False) -> bool:
        """End the line with 09 99, or 09 96 to close it to a polygon.

        A line needs 2 points and a polygon 3. With fewer, the whole block is
        removed, as the import would ignore it. Returns False in that case.
        """
        start, points_before = self._block
        self._block = None
        if self.points - points_before < (3 if closed else 2):
            first = self.records[start + 1][COL_NAME].strip() if len(self.records) > start + 1 else ""
            self._short_lines.append(first)
            del self.records[start:]
            self.points = points_before
            return False
        self.records.append(" 09 96" if closed else " 09 99")
        if closed:
            self.polygons += 1
        else:
            self.lines += 1
        return True

    def point(
        self,
        name,
        code,
        north,
        east,
        height=None,
        bk=None,
        remark="",
    ) -> bool:
        """Add a 05 record. Returns False if the point was skipped."""
        name = _clean(name)
        if len(name) > NAME_WIDTH:
            self._long_names.append(name)
            name = name[:NAME_WIDTH]
        code = _clean(code)
        if len(code) > CODE_WIDTH:
            self._long_codes.append(code)
            code = code[:CODE_WIDTH]

        north, east = _number(north), _number(east)
        if north is None or east is None:
            self._missing.append(name)
            return False
        north_text = _fit(north, NORTH_WIDTH, 3)
        east_text = _fit(east, EAST_WIDTH, 3)
        if north_text is None or east_text is None:
            self._too_large.append(name)
            return False

        height_text = ""
        height = _number(height)
        if height is not None:
            # Large heights lose decimals before they are left out.
            for decimals in (3, 2, 1, 0):
                height_text = _fit(height, HEIGHT_WIDTH, decimals)
                if height_text is not None:
                    break
            else:
                self._height_too_large.append(name)
                height_text = ""

        # Calculation code: two digits in column 58-59, with a space on each side.
        bk_text = ""
        if bk is not None and bk != "":
            value = _number(bk)
            if value is not None and value.is_integer() and 0 <= value <= 99:
                bk_text = f"{int(value):>2}"
            else:
                self._bad_bk.append(name)

        self.records.append((
            f" 05 {name:<{NAME_WIDTH}} {code:<{CODE_WIDTH}} {north_text:>{NORTH_WIDTH}} "
            f"{east_text:>{EAST_WIDTH}} {height_text:>{HEIGHT_WIDTH}} {bk_text:>2} {_clean(remark)}"
        ).rstrip())
        self.points += 1
        return True

    @property
    def warnings(self) -> List[str]:
        warnings = []
        for names, message in (
            (self._long_names, tr(
                "{count} point name(s) longer than 10 characters were shortened, e.g. {examples}"
            )),
            (self._long_codes, tr(
                "{count} code(s) longer than 8 characters were shortened, e.g. {examples}"
            )),
            (self._missing, tr(
                "{count} point(s) without north or east coordinate were skipped, e.g. {examples}"
            )),
            (self._too_large, tr(
                "{count} point(s) with north or east too large for the KOF columns were skipped, "
                "e.g. {examples}. Check the coordinate reference system."
            )),
            (self._height_too_large, tr(
                "{count} height(s) too large for the KOF column were left empty, e.g. for point {examples}"
            )),
            (self._bad_bk, tr(
                "{count} calculation code(s) that are not a whole number from 0 to 99 were left out, "
                "e.g. for point {examples}"
            )),
            (self._short_lines, tr(
                "{count} line(s) or polygon(s) with too few points were skipped, e.g. starting at point {examples}"
            )),
        ):
            if names:
                examples = ", ".join(repr(n) for n in names[:EXAMPLES])
                warnings.append(message.format(count=len(names), examples=examples))
        return warnings

    def text(self) -> str:
        return NEWLINE.join(self.records) + NEWLINE

    def save(self, path: Union[str, Path], encoding: str = DEFAULT_ENCODING) -> List[str]:
        """Write the file. Returns the warnings, including characters the encoding cannot store."""
        warnings = self.warnings
        unstorable = []
        for line_no, record in enumerate(self.records, start=1):
            try:
                record.encode(encoding)
            except UnicodeEncodeError:
                unstorable.append(line_no)
        if unstorable:
            warnings.append(tr(
                "{count} line(s) have characters that {encoding} cannot store, written as '?'. "
                "First at line {line_no}.",
                count=len(unstorable), encoding=encoding, line_no=unstorable[0],
            ))
        # newline="" keeps the CRLF from text() as it is on every platform.
        with open(path, "w", encoding=encoding, errors="replace", newline="") as f:
            f.write(self.text())
        return warnings
