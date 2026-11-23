import platform
import socket
from collections.abc import Callable
from dataclasses import dataclass

from moukey import __version__, pairing
from moukey.channel import Channel, NotPaired, open_channel
from moukey.discovery import device_id
from moukey.keys import add_peer, config_dir, load_identity, load_peers
from moukey.pairing import PairingFailed
from moukey.protocol import decode, encode


@dataclass
class Link:
    ch: Channel
    name: str
    version: str
    screens: list[tuple[int, int, int, int]]
    peer_id: str


def session(
    sock: socket.socket,
    initiator: bool,
    confirm: Callable[[str], bool],
    screens: list[tuple[int, int, int, int]],
    expected_id: str | None = None,
    allow_pairing: bool = True,
) -> Link | None:
    """handshake, pairing if needed and hello"""
    folder = config_dir()
    identity = load_identity(folder)

    try:
        ch, peer = open_channel(sock, identity, initiator, load_peers(folder))
    except NotPaired:
        # reconnecting on our own must never turn into a new pairing. otherwise anyone
        # on the wifi could pretend to be the remembered computer and get paired
        if not allow_pairing:
            raise PairingFailed("not paired, and nobody asked to pair") from None
        peer, code = pairing.pair(sock, identity, initiator)
        # the id we clicked is the hash of that computer's key. a stranger can copy the
        # name and the id, but not the key behind them
        if expected_id and device_id(peer) != expected_id:
            raise PairingFailed("that is not the computer we dialed") from None
        if not pairing.confirm(sock, confirm(code)):
            return None
        ch, _ = open_channel(sock, identity, initiator, {peer})
    if expected_id and device_id(peer) != expected_id:
        raise PairingFailed("that is not the computer we dialed")

    mine = [list(s) for s in screens]
    ch.send(encode("hello", name=platform.node(), version=__version__, screens=mine))
    hello = decode(ch.recv())
    add_peer(folder, peer, hello["name"])
    theirs = [tuple(s) for s in hello["screens"]]
    return Link(ch, hello["name"], hello["version"], theirs, device_id(peer))
