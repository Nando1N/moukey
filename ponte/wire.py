import socket
import struct

# clipboard text is the biggest thing we send, 1 MiB is plenty
MAX_FRAME = 1024 * 1024

_header = struct.Struct("!I")


class FrameTooBig(Exception):
    pass


def pack(payload: bytes) -> bytes:
    if len(payload) > MAX_FRAME:
        raise FrameTooBig(len(payload))
    return _header.pack(len(payload)) + payload


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed the connection")
        buf += chunk
    return bytes(buf)


def send_frame(sock: socket.socket, payload: bytes) -> None:
    sock.sendall(pack(payload))


def recv_frame(sock: socket.socket) -> bytes:
    (size,) = _header.unpack(recv_exact(sock, _header.size))
    # don't trust the header, a bad peer could make us allocate gigabytes
    if size > MAX_FRAME:
        raise FrameTooBig(size)
    return recv_exact(sock, size)
