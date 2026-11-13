from moukey import edges

# a real desk: ultrawide as the main screen and a 1080p one to its left
PC = [(0, 0, 3440, 1440), (-1920, 0, 1920, 1080)]
NOTE = [(0, 0, 1920, 1080)]


def test_inside_and_bbox():
    assert edges.inside(PC, -5, 10) == (-1920, 0, 1920, 1080)
    assert edges.inside(PC, 3440, 10) is None
    assert edges.bbox(PC) == (-1920, 0, 5360, 1440)


def test_place_on_each_side():
    assert edges.place(PC, NOTE, "right") == (3440, 180)
    assert edges.place(PC, NOTE, "left") == (-3840, 180)
    assert edges.place(PC, NOTE, "bottom") == (-200, 1440)
    assert edges.place(PC, NOTE, "top") == (-200, -1080)


def test_crossing_lands_on_the_right_spot_over_there():
    offset = edges.place(PC, NOTE, "right")
    # right edge of the ultrawide, at a height where the notebook is next to it
    assert edges.cross(PC, NOTE, offset, 3439, 700) == (2, 520)


def test_no_crossing_where_the_screens_dont_touch():
    offset = edges.place(PC, NOTE, "right")
    # the notebook is shorter, there's nothing next to the top of the ultrawide
    assert edges.cross(PC, NOTE, offset, 3439, 100) is None
    # far left edge of the second monitor leads nowhere
    assert edges.cross(PC, NOTE, offset, -1920, 500) is None


def test_edges_between_our_own_screens_stay_local():
    assert edges.beyond(PC, 0, 500) == []
    offset = edges.place(PC, NOTE, "left")
    # the notebook sits left of everything, the cursor reaches it from the second monitor
    assert edges.cross(PC, NOTE, offset, 0, 500) is None
    assert edges.cross(PC, NOTE, offset, -1920, 500) == (1917, 320)


def test_coming_back_needs_to_push_against_the_edge():
    offset = edges.place(PC, NOTE, "right")
    pc_seen_from_note = edges.shift(PC, -offset[0], -offset[1])
    assert edges.pushing_out(NOTE, 0, 520, -4, 0) == (-1, 520)
    assert edges.inside(pc_seen_from_note, -1, 520) == (-3440, -180, 3440, 1440)
    assert edges.pushing_out(NOTE, 0, 520, 4, 0) is None
    assert edges.pushing_out(NOTE, 500, 520, -4, 0) is None


def test_land_keeps_the_cursor_inside():
    assert edges.land((0, 0, 1920, 1080), -50, 5000) == (2, 1077)


def test_snap_glues_to_the_closest_side():
    # dropped somewhere to the right and too low, it snaps right and keeps an edge in common
    x, y = edges.snap(PC, NOTE, (6000, 1400))
    assert x == 3440
    assert y == 1440 - edges.MIN_OVERLAP
    # dropped above the middle of the desk, it goes on top
    x, y = edges.snap(PC, NOTE, (300, -1500))
    assert y == -1080


def test_different_resolutions():
    offset = edges.place(PC, [(0, 0, 1366, 768)], "right")
    assert edges.cross(PC, [(0, 0, 1366, 768)], offset, 3439, 720) == (2, 384)
