import socket
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from moukey import wire
from moukey.channel import HandshakeFailed, NotPaired, open_channel
from moukey.keys import raw_public


@pytest.fixture
def pair():
    a, b = socket.socketpair()
    a.settimeout(5)
    b.settimeout(5)
    yield a, b
    a.close()
    b.close()


def both(fa, fb):
    with ThreadPoolExecutor(1) as pool:
        other = pool.submit(fb)
        return fa(), other.result()


def test_paired_peers_talk(pair):
    a, b = pair
    ka, kb = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    (cha, peer_of_a), (chb, peer_of_b) = both(
        lambda: open_channel(a, ka, True, {raw_public(kb)}),
        lambda: open_channel(b, kb, False, {raw_public(ka)}),
    )
    assert peer_of_a == raw_public(kb)
    assert peer_of_b == raw_public(ka)

    cha.send(b"oi")
    chb.send(b"tudo bem")
    assert chb.recv() == b"oi"
    assert cha.recv() == b"tudo bem"


def test_unknown_peer_is_refused_on_both_sides(pair):
    a, b = pair
    ka, kb = X25519PrivateKey.generate(), X25519PrivateKey.generate()

    def side(sock, key, initiator, trusted):
        with pytest.raises(NotPaired):
            open_channel(sock, key, initiator, trusted)

    # b trusts a, but a never paired with b
    both(lambda: side(a, ka, True, set()), lambda: side(b, kb, False, {raw_public(ka)}))


def test_impostor_with_copied_public_key_fails(pair):
    a, b = pair
    real, server = X25519PrivateKey.generate(), X25519PrivateKey.generate()

    def impostor():
        # knows the real client's public key, not its private key
        wire.send_frame(a, raw_public(real) + raw_public(X25519PrivateKey.generate()))
        wire.recv_frame(a)
        wire.send_frame(a, b"\x01")
        wire.recv_frame(a)
        wire.send_frame(a, b"\x00" * 18)

    with ThreadPoolExecutor(1) as pool:
        pool.submit(impostor)
        with pytest.raises(HandshakeFailed):
            open_channel(b, server, False, {raw_public(real)})


def test_replayed_frame_is_rejected(pair):
    a, b = pair
    ka, kb = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    (cha, _), (chb, _) = both(
        lambda: open_channel(a, ka, True, {raw_public(kb)}),
        lambda: open_channel(b, kb, False, {raw_public(ka)}),
    )

    # grab a real encrypted frame off the wire and send it twice
    x, y = socket.socketpair()
    cha.sock = x
    cha.send(b"clique")
    frame = wire.recv_frame(y)
    x.close()
    y.close()

    wire.send_frame(a, frame)
    wire.send_frame(a, frame)
    assert chb.recv() == b"clique"
    with pytest.raises(ConnectionError):
        chb.recv()
