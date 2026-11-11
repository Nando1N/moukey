def opposite(side: str) -> str:
    return "left" if side == "right" else "right"


def crossing(x: int, width: int, side: str) -> bool:
    return x >= width - 1 if side == "right" else x <= 0


def leaving(x: int, dx: int, width: int, edge: str) -> bool:
    # the os clamps the cursor at the border, so "still pushing" means the
    # delta keeps pointing outward while we're already sitting on the edge
    if edge == "left":
        return x <= 0 and dx < 0
    return x >= width - 1 and dx > 0


def ratio(y: int, height: int) -> float:
    return min(max(y / max(height - 1, 1), 0.0), 1.0)


def entry_point(edge: str, y: float, width: int, height: int) -> tuple[int, int]:
    # land a few pixels inside, right on the border it would bounce straight back
    x = 2 if edge == "left" else width - 3
    return x, round(y * (height - 1))
