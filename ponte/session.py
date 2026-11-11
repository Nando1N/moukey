import platform
import socket
from collections.abc import Callable

from ponte import __version__, pairing
from ponte.channel import Channel, NotPaired, open_channel
from ponte.keys import add_peer, config_dir, load_identity, load_peers
from ponte.protocol import decode, encode


def session(
    sock: socket.socket, initiator: bool, confirm: Callable[[str], bool]
) -> tuple[Channel, str] | None:
    """handshake, pairing if needed and hello. returns the channel and the other name"""
    folder = config_dir()
    identity = load_identity(folder)

    try:
        ch, peer = open_channel(sock, identity, initiator, load_peers(folder))
    except NotPaired:
        peer, code = pairing.pair(sock, identity, initiator)
        if not pairing.confirm(sock, confirm(code)):
            return None
        ch, _ = open_channel(sock, identity, initiator, {peer})

    ch.send(encode("hello", name=platform.node(), version=__version__))
    hello = decode(ch.recv())
    add_peer(folder, peer, hello["name"])
    return ch, hello["name"]
