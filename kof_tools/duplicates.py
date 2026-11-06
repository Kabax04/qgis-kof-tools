"""Grouping of repeated measurements of the same point."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Callable, List, Optional, Sequence

from .kof_parser import KofPoint


@dataclass
class PointGroup:
    members: List[KofPoint]
    north: float
    east: float
    height: Optional[float]
    std_north: float
    std_east: float
    std_height: Optional[float]
    # Largest horizontal distance from a member to the mean point.
    max_deviation: float

    @property
    def names(self) -> List[str]:
        return [p.name for p in self.members]


# Defaults for the import. The height tolerance keeps points on top of each
# other apart, such as the lid and bottom of a manhole or the top and foot of
# a kerb, while repeated measurements of one point agree within centimetres.
DEFAULT_TOLERANCE = 0.05
DEFAULT_HEIGHT_TOLERANCE = 0.10

# How often the loops ask whether the user has cancelled.
_CANCEL_CHECK = 1000


def _cells(points: Sequence[KofPoint], size: float) -> dict:
    """Point indexes by grid cell. Points within `size` are in the same or a neighbouring cell."""
    cells: dict = {}
    for i, p in enumerate(points):
        cells.setdefault((math.floor(p.east / size), math.floor(p.north / size)), []).append(i)
    return cells


def _pairs_within(points: Sequence[KofPoint], limit: float, is_canceled: Optional[Callable[[], bool]]):
    """Yield (i, j, distance) for every pair of points at most `limit` apart horizontally, i < j.

    Uses a grid with cells of `limit`, so each point is only compared with
    points in its own and the eight neighbouring cells.
    """
    cells = _cells(points, limit if limit > 0 else 1.0)
    for count, ((cx, cy), members) in enumerate(cells.items()):
        if is_canceled is not None and count % _CANCEL_CHECK == 0 and is_canceled():
            return
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                others = cells.get((cx + dx, cy + dy))
                if not others:
                    continue
                for i in members:
                    pi = points[i]
                    for j in others:
                        if j <= i:
                            continue
                        pj = points[j]
                        distance = math.hypot(pi.north - pj.north, pi.east - pj.east)
                        if distance <= limit:
                            yield i, j, distance


def group_points(
    points: Sequence[KofPoint],
    tolerance: float = DEFAULT_TOLERANCE,
    height_tolerance: Optional[float] = None,
    is_canceled: Optional[Callable[[], bool]] = None,
) -> List[PointGroup]:
    """All groups, including points measured only once, ordered by line in the file.

    Two points end up in the same group if they are within `tolerance`
    metres of each other horizontally, or are connected through a chain of
    such neighbours (single linkage). With `height_tolerance` the height
    difference must also be within that limit. `is_canceled` is called now
    and then; when it returns True the grouping stops early.
    """
    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, _ in _pairs_within(points, tolerance, is_canceled):
        if height_tolerance is not None and not _heights_close(points[a], points[b], height_tolerance):
            continue
        parent[find(a)] = find(b)

    clusters: dict = {}
    for i in range(len(points)):
        clusters.setdefault(find(i), []).append(points[i])
    groups = [_summarize(members) for members in clusters.values()]
    groups.sort(key=lambda g: g.members[0].line_no)
    return groups


def find_groups(
    points: Sequence[KofPoint],
    tolerance: float = DEFAULT_TOLERANCE,
    height_tolerance: Optional[float] = None,
    include_singles: bool = False,
) -> List[PointGroup]:
    """Groups of repeated measurements, see group_points. Single points only with `include_singles`."""
    groups = group_points(points, tolerance, height_tolerance)
    return groups if include_singles else [g for g in groups if len(g.members) > 1]


@dataclass
class NearMiss:
    a: KofPoint
    b: KofPoint
    distance: float


def find_near_misses(
    points: Sequence[KofPoint],
    tolerance: float = DEFAULT_TOLERANCE,
    height_tolerance: Optional[float] = None,
    factor: float = 2.0,
    groups: Optional[List[PointGroup]] = None,
    is_canceled: Optional[Callable[[], bool]] = None,
) -> List[NearMiss]:
    """Find point pairs just outside the tolerance.

    Pairs with a distance in (tolerance, factor * tolerance] are often
    repeated measurements with poorer precision and should be checked by
    hand. Pairs that still ended up in the same group through a chain of
    neighbours are left out. Pass the result of group_points as `groups`
    to avoid grouping again.
    """
    if groups is None:
        groups = group_points(points, tolerance, height_tolerance, is_canceled)
    group_of = {}
    for index, group in enumerate(groups):
        for member in group.members:
            group_of[id(member)] = index

    misses = []
    for i, j, distance in _pairs_within(points, tolerance * factor, is_canceled):
        a, b = points[i], points[j]
        if distance <= tolerance or group_of.get(id(a)) == group_of.get(id(b)):
            continue
        first, second = sorted((a, b), key=lambda p: p.line_no)
        misses.append(NearMiss(first, second, distance))
    misses.sort(key=lambda m: (m.a.line_no, m.b.line_no))
    return misses


def _heights_close(a: KofPoint, b: KofPoint, tolerance: float) -> bool:
    if a.height is None or b.height is None:
        return True
    return abs(a.height - b.height) <= tolerance


def _std(values: List[float]) -> float:
    return stdev(values) if len(values) > 1 else 0.0


def _summarize(members: List[KofPoint]) -> PointGroup:
    members = sorted(members, key=lambda p: p.line_no)
    north = mean(p.north for p in members)
    east = mean(p.east for p in members)
    heights = [p.height for p in members if p.height is not None]
    return PointGroup(
        members=members,
        north=north,
        east=east,
        height=mean(heights) if heights else None,
        std_north=_std([p.north for p in members]),
        std_east=_std([p.east for p in members]),
        std_height=_std(heights) if heights else None,
        max_deviation=max(math.hypot(p.north - north, p.east - east) for p in members),
    )
