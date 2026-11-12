import hashlib
import os
import socket

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from moukey import wire
from moukey.keys import raw_public

# same idea as bluetooth numeric comparison. the responder commits to its nonce
# before seeing ours, so a man in the middle can't grind keys until the 6 digits
# match on both screens. he gets one guess in a million per try.


class PairingFailed(Exception):
    pass


def _hash(*parts: bytes) -> bytes:
    return hashlib.sha256(b"".join(parts)).digest()


def _recv(sock: socket.socket, size: int) -> bytes:
    data = wire.recv_frame(sock)
    if len(data) != size:
        raise PairingFailed("unexpected message during pairing")
    return data


def code_for(pub_a: bytes, pub_b: bytes, nonce_a: bytes, nonce_b: bytes) -> str:
    digest = _hash(b"moukey pairing", pub_a, pub_b, nonce_a, nonce_b)
    return f"{int.from_bytes(digest[:8], 'big') % 1_000_000:06d}"


def pair(sock: socket.socket, identity: X25519PrivateKey, initiator: bool) -> tuple[bytes, str]:
    mine = raw_public(identity)
    nonce = os.urandom(16)

    if initiator:
        wire.send_frame(sock, mine)
        theirs = _recv(sock, 32)
        commit = _recv(sock, 32)
        wire.send_frame(sock, nonce)
        their_nonce = _recv(sock, 16)
        if _hash(theirs, mine, their_nonce) != commit:
            raise PairingFailed("the other side changed its answer")
        return theirs, code_for(mine, theirs, nonce, their_nonce)

    theirs = _recv(sock, 32)
    wire.send_frame(sock, mine)
    wire.send_frame(sock, _hash(mine, theirs, nonce))
    their_nonce = _recv(sock, 16)
    wire.send_frame(sock, nonce)
    return theirs, code_for(theirs, mine, their_nonce, nonce)


def confirm(sock: socket.socket, accepted: bool) -> bool:
    wire.send_frame(sock, b"yes" if accepted else b"no")
    return accepted and wire.recv_frame(sock) == b"yes"
