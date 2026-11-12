import platform
import socket
from collections.abc import Callable

from moukey import __version__, pairing
from moukey.channel import Channel, NotPaired, open_channel
from moukey.keys import add_peer, config_dir, load_identity, load_peers
from moukey.protocol import decode, encode


def session(
    sock: socket.socket, initiator: bool, confirm: Callable[[str], bool]
) -> tuple[Channel, str, str] | None:
    """handshake, pairing if needed and hello. returns the channel, the other name and version"""
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
    return ch, hello["name"], hello["version"]
