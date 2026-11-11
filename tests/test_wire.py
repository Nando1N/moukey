import socket
import struct

import pytest

from ponte import wire


@pytest.fixture
def pair():
    a, b = socket.socketpair()
    yield a, b
    a.close()
    b.close()


def test_roundtrip(pair):
    a, b = pair
    wire.send_frame(a, b"hello")
    wire.send_frame(a, b"")
    assert wire.recv_frame(b) == b"hello"
    assert wire.recv_frame(b) == b""


def test_refuses_to_send_huge_frame():
    with pytest.raises(wire.FrameTooBig):
        wire.pack(b"x" * (wire.MAX_FRAME + 1))


def test_rejects_huge_header(pair):
    a, b = pair
    a.sendall(struct.pack("!I", wire.MAX_FRAME + 1))
    with pytest.raises(wire.FrameTooBig):
        wire.recv_frame(b)


def test_peer_closed_mid_frame(pair):
    a, b = pair
    a.sendall(struct.pack("!I", 10) + b"abc")
    a.close()
    with pytest.raises(ConnectionError):
        wire.recv_frame(b)
