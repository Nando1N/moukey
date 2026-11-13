import pytest

from moukey.protocol import BadMessage, decode, encode


def test_roundtrip():
    data = encode("move", dx=5, dy=-3)
    assert decode(data) == {"t": "move", "dx": 5, "dy": -3}


def test_ping_has_no_fields():
    assert decode(encode("ping")) == {"t": "ping"}


def test_clipboard_keeps_unicode():
    msg = decode(encode("clipboard", text="ação ✓"))
    assert msg["text"] == "ação ✓"


def test_enter_takes_negative_coordinates():
    # a monitor left of the main one has negative x
    assert decode(encode("enter", x=-1500, y=300))["x"] == -1500


def test_hello_with_screens():
    msg = decode(encode("hello", name="PC", version="0.1", screens=[[0, 0, 3440, 1440]]))
    assert msg["screens"] == [[0, 0, 3440, 1440]]


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
        b'{"t":"enter","x":1.5,"y":2}',
        b'{"t":"enter","x":1}',
        b'{"t":"hello","name":"a","version":"1","screens":[]}',
        b'{"t":"hello","name":"a","version":"1","screens":[[0,0,0,10]]}',
        b'{"t":"hello","name":"a","version":"1","screens":[[0,0,10]]}',
        b'{"t":"hello","name":"a","version":"1","screens":"nope"}',
        b'{"t":"layout","dx":true,"dy":0}',
        b'{"t":"button","button":"side","down":true}',
    ],
)
def test_rejects_bad_messages(raw):
    with pytest.raises(BadMessage):
        decode(raw)


def test_encode_validates_too():
    with pytest.raises(BadMessage):
        encode("move", dx=1)
