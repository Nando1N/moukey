# screen geometry. a rect is (x, y, width, height) in a computer's own desktop
# coordinates, the same numbers windows uses (a monitor left of the main one has x < 0).
# the other computer's monitors are kept in their own coordinates plus an offset that
# says where they sit next to ours: their point + offset = our point.

Rect = tuple[int, int, int, int]
Point = tuple[int, int]

# keep the cursor a couple of pixels inside, right on the border it would bounce back
INSET = 2
# when snapping the other computer next to ours, keep at least this much edge in common
MIN_OVERLAP = 120

SIDES = ("left", "right", "top", "bottom")


def inside(rects: list[Rect], x: int, y: int) -> Rect | None:
    for r in rects:
        rx, ry, rw, rh = r
        if rx <= x < rx + rw and ry <= y < ry + rh:
            return r
    return None


def shift(rects: list[Rect], dx: int, dy: int) -> list[Rect]:
    return [(x + dx, y + dy, w, h) for x, y, w, h in rects]


def bbox(rects: list[Rect]) -> Rect:
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return left, top, right - left, bottom - top


def land(rect: Rect, x: int, y: int) -> Point:
    rx, ry, rw, rh = rect
    x = min(max(x, rx + INSET), rx + rw - 1 - INSET)
    y = min(max(y, ry + INSET), ry + rh - 1 - INSET)
    return x, y


def beyond(rects: list[Rect], x: int, y: int) -> list[Point]:
    """points just past each edge the cursor is touching, unless one of our own screens is there"""
    r = inside(rects, x, y)
    if r is None:
        return []
    rx, ry, rw, rh = r
    points = []
    if x >= rx + rw - 1:
        points.append((rx + rw, y))
    if x <= rx:
        points.append((rx - 1, y))
    if y >= ry + rh - 1:
        points.append((x, ry + rh))
    if y <= ry:
        points.append((x, ry - 1))
    return [p for p in points if inside(rects, *p) is None]


def pushing_out(rects: list[Rect], x: int, y: int, dx: int, dy: int) -> Point | None:
    """like beyond(), but only for the edge the movement is pushing against"""
    r = inside(rects, x, y)
    if r is None:
        return None
    rx, ry, rw, rh = r
    candidates = []
    if dx > 0 and x >= rx + rw - 1:
        candidates.append((rx + rw, y))
    if dx < 0 and x <= rx:
        candidates.append((rx - 1, y))
    if dy > 0 and y >= ry + rh - 1:
        candidates.append((x, ry + rh))
    if dy < 0 and y <= ry:
        candidates.append((x, ry - 1))
    return next((p for p in candidates if inside(rects, *p) is None), None)


def cross(mine: list[Rect], theirs: list[Rect], offset: Point, x: int, y: int) -> Point | None:
    """if (x, y) sits on an edge that touches one of their screens, where to land over there"""
    ox, oy = offset
    placed = shift(theirs, ox, oy)
    for bx, by in beyond(mine, x, y):
        target = inside(placed, bx, by)
        if target is not None:
            lx, ly = land(target, bx, by)
            return lx - ox, ly - oy
    return None


def place(mine: list[Rect], theirs: list[Rect], side: str) -> Point:
    """offset that puts their screens next to ours on one side, centered"""
    mx, my, mw, mh = bbox(mine)
    tx, ty, tw, th = bbox(theirs)
    if side == "right":
        return mx + mw - tx, my + (mh - th) // 2 - ty
    if side == "left":
        return mx - tw - tx, my + (mh - th) // 2 - ty
    if side == "bottom":
        return mx + (mw - tw) // 2 - tx, my + mh - ty
    return mx + (mw - tw) // 2 - tx, my - th - ty


def side_from_offset(dx: float, dy: float) -> str:
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "bottom" if dy >= 0 else "top"


def snap(mine: list[Rect], theirs: list[Rect], offset: Point) -> Point:
    """takes wherever the user dropped their screens and glues them to our closest side"""
    mx, my, mw, mh = bbox(mine)
    tx, ty, tw, th = bbox(theirs)
    ox, oy = offset
    cx, cy = tx + ox + tw / 2, ty + oy + th / 2
    side = side_from_offset((cx - (mx + mw / 2)) / mw, (cy - (my + mh / 2)) / mh)
    if side in ("left", "right"):
        x = mx + mw - tx if side == "right" else mx - tw - tx
        overlap = min(MIN_OVERLAP, mh, th)
        y = min(max(ty + oy, my - th + overlap), my + mh - overlap) - ty
        return x, y
    y = my + mh - ty if side == "bottom" else my - th - ty
    overlap = min(MIN_OVERLAP, mw, tw)
    x = min(max(tx + ox, mx - tw + overlap), mx + mw - overlap) - tx
    return x, y
