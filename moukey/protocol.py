import json

# keys and buttons travel as plain names ("a", "enter", "shift"), never as OS codes,
# so a windows server can talk to a linux client without either knowing
FIELDS = {
    # screens: every monitor as [x, y, width, height], the main one first
    "hello": {"name": str, "version": str, "screens": list},
    # enter: the cursor shows up here, in the receiver's own desktop coordinates.
    # leave: it went back, in the coordinates of whoever gets it back
    "enter": {"x": int, "y": int},
    "leave": {"x": int, "y": int},
    # let go of every key and button, sent by the emergency shortcut
    "release": {},
    # where the sender's screens sit for the receiver: sender point + (dx, dy) = receiver point
    "layout": {"dx": int, "dy": int},
    "move": {"dx": int, "dy": int},
    "button": {"button": str, "down": bool},
    "scroll": {"dx": int, "dy": int},
    "key": {"key": str, "down": bool},
    "clipboard": {"text": str},
    # files go in pieces over the same encrypted channel. data is base64
    "file_offer": {"id": str, "name": str, "size": int},
    "file_chunk": {"id": str, "data": str},
    "file_end": {"id": str, "sha256": str},
    "file_cancel": {"id": str},
    "ping": {},
}

BUTTONS = {"left", "right", "middle"}


class BadMessage(ValueError):
    pass


def encode(kind: str, **fields) -> bytes:
    msg = {"t": kind, **fields}
    check(msg)
    return json.dumps(msg, separators=(",", ":")).encode()


def decode(data: bytes) -> dict:
    try:
        msg = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BadMessage("not valid json") from e
    check(msg)
    return msg


def _type_ok(value, expected) -> bool:
    # bool is a subclass of int in python, so True would pass as a mouse delta
    if isinstance(value, bool):
        return expected is bool
    if expected is float:
        return isinstance(value, int | float)
    if expected is list:
        return isinstance(value, list)
    return isinstance(value, expected)


def valid_screens(screens) -> bool:
    if not 1 <= len(screens) <= 16:
        return False
    for s in screens:
        if not (isinstance(s, list) and len(s) == 4):
            return False
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in s):
            return False
        if not (0 < s[2] <= 100_000 and 0 < s[3] <= 100_000):
            return False
    return True


def check(msg) -> None:
    if not isinstance(msg, dict):
        raise BadMessage("expected an object")

    kind = msg.get("t")
    if kind not in FIELDS:
        raise BadMessage(f"unknown message {kind!r}")

    expected = FIELDS[kind]
    if set(msg) - {"t"} != set(expected):
        raise BadMessage(f"wrong fields for {kind}")

    for name, typ in expected.items():
        if not _type_ok(msg[name], typ):
            raise BadMessage(f"{kind}.{name} should be {typ.__name__}")

    if kind == "hello" and not valid_screens(msg["screens"]):
        raise BadMessage("bad screens list")
    if kind == "file_offer" and msg["size"] < 0:
        raise BadMessage("negative file size")
    if kind == "button" and msg["button"] not in BUTTONS:
        raise BadMessage(f"unknown button {msg['button']!r}")
