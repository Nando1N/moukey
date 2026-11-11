import socket
import struct
import threading
from collections.abc import Container

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ponte import wire
from ponte.keys import raw_public


class HandshakeFailed(Exception):
    pass


class NotPaired(Exception):
    def __init__(self, peer_public: bytes):
        super().__init__("peer is not paired")
        self.peer_public = peer_public


def _nonce(counter: int) -> bytes:
    return struct.pack("<4xQ", counter)


class Channel:
    def __init__(self, sock: socket.socket, send_key: bytes, recv_key: bytes):
        self.sock = sock
        self._out = ChaCha20Poly1305(send_key)
        self._in = ChaCha20Poly1305(recv_key)
        self._out_count = 0
        self._in_count = 0
        # mouse, keyboard and clipboard will send from different threads
        self._lock = threading.Lock()

    def send(self, data: bytes) -> None:
        with self._lock:
            frame = self._out.encrypt(_nonce(self._out_count), data, None)
            self._out_count += 1
            wire.send_frame(self.sock, frame)

    def recv(self) -> bytes:
        frame = wire.recv_frame(self.sock)
        # tcp keeps order, so the counter must match exactly. a replayed or
        # reordered frame fails here
        try:
            data = self._in.decrypt(_nonce(self._in_count), frame, None)
        except InvalidTag:
            raise ConnectionError("message failed authentication") from None
        self._in_count += 1
        return data


def open_channel(
    sock: socket.socket,
    identity: X25519PrivateKey,
    initiator: bool,
    trusted: Container[bytes],
) -> tuple[Channel, bytes]:
    eph = X25519PrivateKey.generate()
    mine = raw_public(identity) + raw_public(eph)
    wire.send_frame(sock, mine)
    theirs = wire.recv_frame(sock)
    if len(theirs) != 64:
        raise HandshakeFailed("bad hello")
    their_static, their_eph = theirs[:32], theirs[32:]

    # both sides say if they know each other, so both bail out together
    wire.send_frame(sock, b"\x01" if their_static in trusted else b"\x00")
    if wire.recv_frame(sock) != b"\x01" or their_static not in trusted:
        raise NotPaired(their_static)

    # ephemeral dh gives forward secrecy, static dh proves who is on the other side
    shared = eph.exchange(X25519PublicKey.from_public_bytes(their_eph))
    shared += identity.exchange(X25519PublicKey.from_public_bytes(their_static))
    first, second = (mine, theirs) if initiator else (theirs, mine)
    okm = HKDF(
        algorithm=hashes.SHA256(), length=64, salt=first + second, info=b"ponte session v1"
    ).derive(shared)
    a_to_b, b_to_a = okm[:32], okm[32:]

    if initiator:
        ch = Channel(sock, a_to_b, b_to_a)
    else:
        ch = Channel(sock, b_to_a, a_to_b)

    # someone who only copied a public key can't get past this
    ch.send(b"ok")
    try:
        if ch.recv() != b"ok":
            raise HandshakeFailed("key confirmation failed")
    except ConnectionError as e:
        raise HandshakeFailed("key confirmation failed") from e
    return ch, their_static
