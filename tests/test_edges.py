import pytest

from moukey import edges

W, H = 1920, 1080


def test_crossing_each_side():
    assert edges.crossing(1919, 500, W, H, "right")
    assert not edges.crossing(1918, 500, W, H, "right")
    assert edges.crossing(0, 500, W, H, "left")
    assert not edges.crossing(1, 500, W, H, "left")
    assert edges.crossing(800, 0, W, H, "top")
    assert not edges.crossing(800, 1, W, H, "top")
    assert edges.crossing(800, 1079, W, H, "bottom")
    assert not edges.crossing(800, 1078, W, H, "bottom")


def test_leaving_needs_to_push_outward():
    assert edges.leaving(0, 500, -5, 0, W, H, "left")
    assert not edges.leaving(0, 500, 5, 0, W, H, "left")
    assert not edges.leaving(10, 500, -5, 0, W, H, "left")
    assert edges.leaving(1919, 500, 3, 0, W, H, "right")
    assert edges.leaving(800, 0, 0, -2, W, H, "top")
    assert not edges.leaving(800, 0, 4, 0, W, H, "top")
    assert edges.leaving(800, 1079, 0, 2, W, H, "bottom")


@pytest.mark.parametrize("edge", edges.SIDES)
def test_entry_point_is_inside_and_not_crossing(edge):
    x, y = edges.entry_point(edge, 0.5, W, H)
    assert 0 < x < W - 1 and 0 < y < H - 1
    assert not edges.crossing(x, y, W, H, edge)


def test_position_along_the_edge_survives_the_trip():
    for y in (0, 1, 540, 1079):
        at = edges.along(0, y, W, H, "left")
        assert edges.entry_point("left", at, W, H)[1] == y
    for x in (0, 960, 1919):
        at = edges.along(x, 0, W, H, "top")
        assert edges.entry_point("top", at, W, H)[0] == x


def test_different_resolutions_keep_proportion():
    # leaving a 1080p screen at the middle lands at the middle of a 768p one
    at = edges.along(0, 540, 1920, 1080, "right")
    assert edges.entry_point("left", at, 1366, 768)[1] == 384


def test_along_clamps():
    assert edges.along(0, -10, W, H, "left") == 0.0
    assert edges.along(0, 5000, W, H, "left") == 1.0


def test_opposite():
    assert edges.opposite("right") == "left"
    assert edges.opposite("top") == "bottom"


@pytest.mark.parametrize(
    "dx, dy, side",
    [(100, 10, "right"), (-100, 10, "left"), (5, -80, "top"), (-5, 80, "bottom")],
)
def test_side_from_drop_position(dx, dy, side):
    assert edges.side_from_offset(dx, dy) == side
