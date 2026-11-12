import json

# keys and buttons travel as plain names ("a", "enter", "shift"), never as OS codes,
# so a windows server can talk to a linux client without either knowing
FIELDS = {
    "hello": {"name": str, "version": str},
    # at: where along the edge, 0.0 to 1.0. edge: where the cursor shows up
    "enter": {"at": float, "edge": str},
    "leave": {"at": float},
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
    return isinstance(value, expected)


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

    if kind in ("enter", "leave") and not 0 <= msg["at"] <= 1:
        raise BadMessage("at out of range")
    if kind == "enter" and msg["edge"] not in ("left", "right", "top", "bottom"):
        raise BadMessage(f"unknown edge {msg['edge']!r}")
    if kind == "file_offer" and msg["size"] < 0:
        raise BadMessage("negative file size")
    if kind == "button" and msg["button"] not in BUTTONS:
        raise BadMessage(f"unknown button {msg['button']!r}")
