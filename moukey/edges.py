SIDES = ("left", "right", "top", "bottom")

_OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


def opposite(side: str) -> str:
    return _OPPOSITE[side]


def crossing(x: int, y: int, width: int, height: int, side: str) -> bool:
    if side == "right":
        return x >= width - 1
    if side == "left":
        return x <= 0
    if side == "bottom":
        return y >= height - 1
    return y <= 0


def leaving(x: int, y: int, dx: int, dy: int, width: int, height: int, edge: str) -> bool:
    # the os clamps the cursor at the border, so "still pushing" means the
    # delta keeps pointing outward while we're already sitting on the edge
    if edge == "left":
        return x <= 0 and dx < 0
    if edge == "right":
        return x >= width - 1 and dx > 0
    if edge == "top":
        return y <= 0 and dy < 0
    return y >= height - 1 and dy > 0


def _ratio(v: int, size: int) -> float:
    return min(max(v / max(size - 1, 1), 0.0), 1.0)


def along(x: int, y: int, width: int, height: int, edge: str) -> float:
    # side edges run top to bottom, top and bottom edges run left to right
    if edge in ("left", "right"):
        return _ratio(y, height)
    return _ratio(x, width)


def entry_point(edge: str, at: float, width: int, height: int) -> tuple[int, int]:
    # land a few pixels inside, right on the border it would bounce straight back
    if edge == "left":
        return 2, round(at * (height - 1))
    if edge == "right":
        return width - 3, round(at * (height - 1))
    if edge == "top":
        return round(at * (width - 1)), 2
    return round(at * (width - 1)), height - 3


def side_from_offset(dx: float, dy: float) -> str:
    # where the user dropped the other screen in the layout picker
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "bottom" if dy >= 0 else "top"
