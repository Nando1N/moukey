from ponte import edges

W, H = 1920, 1080


def test_crossing_right():
    assert edges.crossing(1919, W, "right")
    assert not edges.crossing(1918, W, "right")
    assert not edges.crossing(0, W, "right")


def test_crossing_left():
    assert edges.crossing(0, W, "left")
    assert not edges.crossing(1, W, "left")


def test_leaving_needs_to_push_outward():
    assert edges.leaving(0, -5, W, "left")
    assert not edges.leaving(0, 5, W, "left")
    assert not edges.leaving(0, 0, W, "left")
    assert not edges.leaving(10, -5, W, "left")
    assert edges.leaving(1919, 3, W, "right")
    assert not edges.leaving(1919, -3, W, "right")


def test_ratio_and_back():
    for y in (0, 1, 540, 1079):
        assert edges.entry_point("left", edges.ratio(y, H), W, H)[1] == y


def test_ratio_clamps():
    assert edges.ratio(-10, H) == 0.0
    assert edges.ratio(5000, H) == 1.0


def test_different_resolutions_keep_proportion():
    # leaving a 1080p screen at the middle lands at the middle of a 768p one
    y = edges.ratio(540, 1080)
    assert edges.entry_point("left", y, 1366, 768)[1] == 384


def test_entry_point_is_inside_the_screen():
    assert edges.entry_point("left", 0.5, W, H)[0] == 2
    assert edges.entry_point("right", 0.5, W, H)[0] == W - 3
    assert not edges.crossing(edges.entry_point("right", 0.5, W, H)[0], W, "right")


def test_opposite():
    assert edges.opposite("right") == "left"
    assert edges.opposite("left") == "right"
