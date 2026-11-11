import argparse
import ipaddress
import platform
import socket
import sys

from ponte import APP_NAME, __version__, backends, pairing
from ponte.channel import Channel, NotPaired, open_channel
from ponte.discovery import Discovery, Peer, device_id
from ponte.keys import add_peer, config_dir, load_identity, load_peers, raw_public
from ponte.net import is_lan, local_ip
from ponte.protocol import decode, encode
from ponte.remote import run_controller, run_receiver

PORT = 47474
LADOS = {"right": "direita", "left": "esquerda"}


def start_discovery(port: int) -> Discovery:
    identity = load_identity(config_dir())
    return Discovery(device_id(raw_public(identity)), platform.node(), local_ip(), port)


def pick_peer(peers: list[Peer], wanted: str | None) -> Peer | None:
    if wanted:
        peers = [p for p in peers if p.name.lower().startswith(wanted.lower())]
    if len(peers) == 1:
        return peers[0]
    if not peers:
        print("nenhum computador encontrado. o ponte ta aberto no outro?")
    else:
        print("achei mais de um, diga qual:")
        for p in peers:
            print(f"  ponte connect {p.name}")
    return None


def ask_pairing(sock, identity, initiator) -> bytes | None:
    peer, code = pairing.pair(sock, identity, initiator)
    print(f"\ncodigo de pareamento: {code}")
    answer = input("aparece o mesmo codigo no outro computador? [s/N] ")
    if not pairing.confirm(sock, answer.strip().lower() in ("s", "sim", "y", "yes")):
        print("pareamento cancelado")
        return None
    return peer


def session(sock: socket.socket, initiator: bool) -> Channel | None:
    folder = config_dir()
    identity = load_identity(folder)
    peers = load_peers(folder)

    try:
        ch, peer = open_channel(sock, identity, initiator, peers)
    except NotPaired:
        peer = ask_pairing(sock, identity, initiator)
        if peer is None:
            return None
        ch, _ = open_channel(sock, identity, initiator, {peer})

    ch.send(encode("hello", name=platform.node(), version=__version__))
    hello = decode(ch.recv())
    add_peer(folder, peer, hello["name"])
    print(f"conectado com {hello['name']}")
    return ch


def listen(port: int, side: str) -> None:
    backend = backends.load()
    disco = start_discovery(port)
    try:
        with socket.create_server(("", port)) as server:
            print("esperando o outro computador... (no outro rode: ponte connect)")
            while True:
                sock, (addr, _) = server.accept()
                if not is_lan(addr):
                    print(f"recusando {addr}, fora da rede local")
                    sock.close()
                    continue
                with sock:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    ch = session(sock, initiator=False)
                    if ch:
                        print(f"leve o mouse pra borda da {LADOS[side]} da tela")
                        run_controller(ch, side, backend)
                return
    finally:
        disco.close()


def connect(target: str | None, port: int) -> None:
    backend = backends.load()
    try:
        ipaddress.ip_address(target or "")
        host = target
    except ValueError:
        print("procurando na rede...")
        disco = start_discovery(port)
        try:
            peer = pick_peer(disco.wait_for(3), target)
        finally:
            disco.close()
        if peer is None:
            sys.exit(1)
        host, port = peer.host, peer.port
        print(f"achei {peer.name}")

    with socket.create_connection((host, port), timeout=10) as sock:
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        ch = session(sock, initiator=True)
        if ch:
            run_receiver(ch, backend)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ponte")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("listen", help="espera o outro computador conectar")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument(
        "--side",
        choices=["right", "left"],
        default="right",
        help="de que lado da tela fica o outro computador",
    )
    p = sub.add_parser("connect", help="acha o outro computador na rede e conecta")
    p.add_argument("target", nargs="?", help="nome ou IP, so se tiver mais de um")
    p.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    # TODO: english messages
    # TODO: replace listen/connect with the window and its connect button
    if args.cmd == "listen":
        listen(args.port, args.side)
    elif args.cmd == "connect":
        connect(args.target, args.port)
    else:
        print(f"{APP_NAME} {__version__} rodando em {platform.system()} {platform.release()}")


if __name__ == "__main__":
    main()
