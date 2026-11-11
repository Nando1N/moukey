import pytest

from ponte.protocol import BadMessage, decode, encode


def test_roundtrip():
    data = encode("move", dx=5, dy=-3)
    assert decode(data) == {"t": "move", "dx": 5, "dy": -3}


def test_ping_has_no_fields():
    assert decode(encode("ping")) == {"t": "ping"}


def test_clipboard_keeps_unicode():
    msg = decode(encode("clipboard", text="ação ✓"))
    assert msg["text"] == "ação ✓"


def test_enter_accepts_int_y():
    assert decode(b'{"t":"enter","y":1}')["y"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"\xff\xfe",
        b"[1, 2]",
        b'{"t":"nope"}',
        b'{"t":"move","dx":1}',
        b'{"t":"move","dx":1,"dy":2,"extra":3}',
        b'{"t":"move","dx":"1","dy":2}',
        b'{"t":"move","dx":true,"dy":2}',
        b'{"t":"key","key":"a","down":1}',
        b'{"t":"enter","y":1.5}',
        b'{"t":"button","button":"side","down":true}',
    ],
)
def test_rejects_bad_messages(raw):
    with pytest.raises(BadMessage):
        decode(raw)


def test_encode_validates_too():
    with pytest.raises(BadMessage):
        encode("move", dx=1)
