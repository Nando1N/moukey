import os
import socket
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from moukey import pairing, wire
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


def test_both_sides_see_the_same_code(pair):
    a, b = pair
    ka, kb = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    (peer_a, code_a), (peer_b, code_b) = both(
        lambda: pairing.pair(a, ka, True),
        lambda: pairing.pair(b, kb, False),
    )
    assert code_a == code_b
    assert len(code_a) == 6 and code_a.isdigit()
    assert peer_a == raw_public(kb)
    assert peer_b == raw_public(ka)


def test_code_changes_every_time(pair):
    a, b = pair
    ka, kb = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    codes = set()
    for _ in range(5):
        (_, code), _ = both(lambda: pairing.pair(a, ka, True), lambda: pairing.pair(b, kb, False))
        codes.add(code)
    # same keys, fresh nonces. 5 equal codes in a row would be a 1 in 10^24 fluke
    assert len(codes) > 1


def test_responder_cant_change_its_nonce(pair):
    a, b = pair

    def cheater():
        wire.recv_frame(b)
        wire.send_frame(b, raw_public(X25519PrivateKey.generate()))
        wire.send_frame(b, os.urandom(32))  # commit to something
        wire.recv_frame(b)
        wire.send_frame(b, os.urandom(16))  # then reveal something else

    with ThreadPoolExecutor(1) as pool:
        pool.submit(cheater)
        with pytest.raises(pairing.PairingFailed):
            pairing.pair(a, X25519PrivateKey.generate(), True)


@pytest.mark.parametrize("ans_a, ans_b, expected", [(True, True, True), (True, False, False)])
def test_confirm_needs_both_yes(pair, ans_a, ans_b, expected):
    a, b = pair
    res_a, res_b = both(lambda: pairing.confirm(a, ans_a), lambda: pairing.confirm(b, ans_b))
    assert res_a is expected
    assert res_b is expected
