import pytest

from kof_tools.duplicates import find_groups, find_near_misses
from kof_tools.kof_parser import KofPoint


def test_topcon_5_cm(topcon):
    groups = find_groups(topcon.points, tolerance=0.05)
    assert [g.names for g in groups] == [
        ["104", "105", "106"],
        ["109", "110", "111"],
        ["112", "113", "114"],
        ["115", "117", "120"],
        ["116", "118", "119"],
    ]


def test_topcon_10_cm_tar_med_102_og_108(topcon):
    names = [g.names for g in find_groups(topcon.points, tolerance=0.10)]
    assert ["102", "108"] in names
    assert len(names) == 6


def test_100_og_104_slaas_aldri_sammen(topcon):
    for g in find_groups(topcon.points, tolerance=1.0, height_tolerance=0.5):
        assert not {"100", "104"} <= set(g.names)


def test_middel_og_spredning(topcon):
    group = find_groups(topcon.points)[0]  # 104, 105, 106
    assert group.north == pytest.approx((6615799.708 + 6615799.707 + 6615799.695) / 3)
    assert group.east == pytest.approx((599668.467 + 599668.474 + 599668.469) / 3)
    assert group.height == pytest.approx((96.967 + 96.974 + 96.955) / 3)
    assert 0 < group.std_north < 0.01
    assert 0 < group.max_deviation < 0.02


def test_med_enkeltpunkter(topcon):
    groups = find_groups(topcon.points, include_singles=True)
    assert sum(len(g.members) for g in groups) == 21
    assert len(groups) == 21 - 5 * 2


def test_nesten_treff_102_og_108(topcon):
    misses = find_near_misses(topcon.points, tolerance=0.05)
    assert [(m.a.name, m.b.name) for m in misses] == [("102", "108")]
    assert misses[0].distance == pytest.approx(0.0607, abs=0.001)


def test_ingen_nesten_treff_naar_de_er_gruppert(topcon):
    assert find_near_misses(topcon.points, tolerance=0.10) == []


def test_kjede_i_samme_gruppe_er_ikke_nesten_treff():
    points = [KofPoint(f"P{i}", "", 0.0, 0.04 * i, None, i) for i in range(3)]
    assert len(find_groups(points, tolerance=0.05)) == 1
    assert find_near_misses(points, tolerance=0.05) == []


def _brute_force_groups(points, tolerance, height_tolerance):
    """Reference: compare every pair."""
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            a, b = points[i], points[j]
            if ((a.north - b.north) ** 2 + (a.east - b.east) ** 2) ** 0.5 > tolerance:
                continue
            if height_tolerance is not None and abs(a.height - b.height) > height_tolerance:
                continue
            parent[find(i)] = find(j)
    clusters = {}
    for i, p in enumerate(points):
        clusters.setdefault(find(i), []).append(p.name)
    return sorted(sorted(c) for c in clusters.values())


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("height_tolerance", [None, 0.1])
def test_rutenett_gir_samme_grupper_som_alle_par(seed, height_tolerance):
    import random

    rng = random.Random(seed)
    points = [
        KofPoint(str(i), "", 6600000 + rng.random() * 2, 600000 + rng.random() * 2, rng.random() * 0.3, i)
        for i in range(300)
    ]
    groups = find_groups(points, 0.05, height_tolerance, include_singles=True)
    assert sorted(sorted(g.names) for g in groups) == _brute_force_groups(points, 0.05, height_tolerance)


def test_lang_nord_sor_trase_er_rask():
    import time

    # Points along a straight north-south line, as on a long road or pipe.
    points = [KofPoint(str(i), "", 6600000 + i * 0.5, 600000.0, 10.0, i) for i in range(50000)]
    start = time.perf_counter()
    assert find_groups(points, 0.2) == []
    assert find_near_misses(points, 0.2) == []
    assert time.perf_counter() - start < 10


def test_kan_avbrytes():
    from kof_tools.duplicates import group_points

    points = [KofPoint(str(i), "", 6600000 + i * 0.01, 600000.0, 10.0, i) for i in range(10000)]
    groups = group_points(points, 0.05, is_canceled=lambda: True)
    # Cancelled before any pair was compared: every point on its own.
    assert len(groups) == len(points)


def test_kumlokk_og_kumbunn_holdes_adskilt_med_hoydetoleranse():
    from kof_tools.duplicates import DEFAULT_HEIGHT_TOLERANCE

    points = [
        KofPoint("lokk", "KUM", 6600000.0, 600000.0, 100.0, 1),
        KofPoint("bunn", "KUM", 6600000.01, 600000.0, 97.5, 2),
        KofPoint("lokk2", "KUM", 6600000.0, 600000.01, 100.02, 3),
    ]
    assert [g.names for g in find_groups(points, 0.05, DEFAULT_HEIGHT_TOLERANCE)] == [["lokk", "lokk2"]]
    assert [g.names for g in find_groups(points, 0.05)] == [["lokk", "bunn", "lokk2"]]
