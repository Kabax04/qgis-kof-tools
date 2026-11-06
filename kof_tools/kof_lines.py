"""Build lines and polygons from the program codes in 09 blocks.

Plain Python without QGIS dependencies. The codes follow the KOF
specification 2.00 (Norkart, 2005), section 4.2.2 Linjemåling:

    91  start straight line     92  start spline     93  start circular arc
    94  start point swarm (no geometry)
    72-79  start 2-9 simultaneous lines, saw method  (A, B, C, A, B, C, ...)
    82-89  start 2-9 simultaneous lines, wave method (A, B, C, C, B, A, A, ...)
    96  end, close to polygon       99  end line/swarm

A new start ends the previous line. Points with calculation code 37 are
single points and do not belong to the line. Other program codes (39-64)
do not affect lines and are ignored here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

from .i18n import tr

if TYPE_CHECKING:  # kof_parser imports this module
    from .kof_parser import KofPoint

SINGLE_KINDS = {91: "line", 92: "spline", 93: "arc"}
SWARM = 94
CLOSE = 96
END = 99
SINGLE_POINT_BK = 37

# Arcs are drawn with this many straight pieces between each pair of
# measured points. Being fixed, it lets the export find the measured points
# again among the vertices: every ARC_SEGMENTS-th vertex is one.
ARC_SEGMENTS = 16


@dataclass
class KofLine:
    # "line", "spline" or "arc"
    kind: str
    pi: int
    # Line in the file holding the 09 block that started this line.
    line_no: int
    points: List[KofPoint] = field(default_factory=list)
    closed: bool = False


def is_line_start(pi: int) -> bool:
    return pi in SINGLE_KINDS or pi == SWARM or 72 <= pi <= 79 or 82 <= pi <= 89


class LineTracker:
    def __init__(self, warnings: List[str]):
        self.lines: List[KofLine] = []
        self.warnings = warnings
        self._active: List[KofLine] = []
        self._pi: Optional[int] = None
        self._count = 0

    def program(self, pi: int, line_no: int) -> None:
        if is_line_start(pi):
            if self._pi is not None:
                self._finish(closed=False)
            self._start(pi, line_no)
        elif pi == CLOSE:
            if not self._active:
                self.warnings.append(tr(
                    "Line {line_no}: 09 96 (close polygon) without an active line", line_no=line_no
                ))
            self._finish(closed=True)
        elif pi == END:
            self._finish(closed=False)

    def point(self, point: KofPoint) -> None:
        if not self._active or point.bk == SINGLE_POINT_BK:
            return
        self._active[self._line_index(self._count)].points.append(point)
        self._count += 1

    def finish(self) -> List[KofLine]:
        """Call at end of file. Returns all finished lines."""
        if self._pi is not None and self._pi != SWARM:
            self.warnings.append(tr(
                "Line {line_no}: the line was not ended with 09 99 or 96",
                line_no=self._active[0].line_no,
            ))
        self._finish(closed=False)
        return self.lines

    def _start(self, pi: int, line_no: int) -> None:
        self._pi = pi
        self._count = 0
        if pi == SWARM:
            self._active = []
            return
        if pi == 92:
            self.warnings.append(tr(
                "Line {line_no}: spline (09 92) is drawn as straight lines", line_no=line_no
            ))
        kind = SINGLE_KINDS.get(pi, "line")
        self._active = [KofLine(kind, pi, line_no) for _ in range(self._line_count(pi))]

    @staticmethod
    def _line_count(pi: int) -> int:
        if 72 <= pi <= 79:
            return pi - 70
        if 82 <= pi <= 89:
            return pi - 80
        return 1

    def _line_index(self, k: int) -> int:
        n = len(self._active)
        if 82 <= self._pi <= 89:
            # Wave method: back and forth, A B C C B A A B C ...
            pos = k % (2 * n)
            return pos if pos < n else 2 * n - 1 - pos
        return k % n

    def _finish(self, closed: bool) -> None:
        for line in self._active:
            minimum = 3 if closed else 2
            if len(line.points) >= minimum:
                line.closed = closed
                self.lines.append(line)
            elif closed and len(line.points) == 2:
                self.warnings.append(tr(
                    "Line {line_no}: polygon with only 2 points, drawn as a line",
                    line_no=line.line_no,
                ))
                self.lines.append(line)
            else:
                self.warnings.append(tr(
                    "Line {line_no}: line with {count} point(s) ignored",
                    line_no=line.line_no, count=len(line.points),
                ))
        self._active = []
        self._pi = None
        self._count = 0


def arc_vertices(points: "List[KofPoint]") -> List[Tuple[float, float, Optional[float]]]:
    """(east, north, height) along a circular arc (09 93) through the points.

    As in the specification the points go start, mid, end, mid, end, ...;
    each three consecutive points from the start give one circle. With an
    even number of points the last piece follows the circle through the last
    three. Each piece between two measured points becomes ARC_SEGMENTS
    straight pieces, so the measured points are every ARC_SEGMENTS-th
    vertex. Heights are interpolated along each piece. Three points on a
    straight line give a straight piece.
    """
    n = len(points)
    vertices = [(points[0].east, points[0].north, points[0].height)]
    for j in range(n - 1):
        first = min(2 * (j // 2), n - 3)
        a, b, c = points[first:first + 3]
        vertices.extend(_arc_piece(points[j], points[j + 1], a, b, c)[1:])
    return vertices


def _arc_piece(p, q, a, b, c):
    """Vertices from p to q along the circle through a, b and c."""
    ax, ay, bx, by, cx, cy = a.east, a.north, b.east, b.north, c.east, c.north
    cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    d = 2 * cross
    span = max(math.hypot(bx - ax, by - ay), math.hypot(cx - bx, cy - by), math.hypot(cx - ax, cy - ay))
    straight = span == 0 or abs(cross) <= 1e-12 * span * span
    if not straight:
        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
        radius = math.hypot(p.east - ux, p.north - uy)
        start = math.atan2(p.north - uy, p.east - ux)
        end = math.atan2(q.north - uy, q.east - ux)
        # Counter-clockwise when a, b, c turn left.
        sweep = (end - start) % (2 * math.pi) if cross > 0 else -((start - end) % (2 * math.pi))
    vertices = []
    for k in range(ARC_SEGMENTS + 1):
        t = k / ARC_SEGMENTS
        if k == 0:
            x, y = p.east, p.north
        elif k == ARC_SEGMENTS:
            x, y = q.east, q.north
        elif straight:
            x, y = p.east + t * (q.east - p.east), p.north + t * (q.north - p.north)
        else:
            angle = start + t * sweep
            x, y = ux + radius * math.cos(angle), uy + radius * math.sin(angle)
        if p.height is None or q.height is None:
            z = None if k not in (0, ARC_SEGMENTS) else (p.height if k == 0 else q.height)
        else:
            z = p.height + t * (q.height - p.height)
        vertices.append((x, y, z))
    return vertices


def measured_arc_step(vertex_count: int, point_count: int) -> Optional[int]:
    """The step between measured points in an arc made by arc_vertices, or None.

    Lets the export write an imported arc with its measured points only.
    """
    if point_count >= 3 and vertex_count - 1 == ARC_SEGMENTS * (point_count - 1):
        return ARC_SEGMENTS
    return None
