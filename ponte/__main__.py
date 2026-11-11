import argparse
import ipaddress
import platform
import socket

from ponte import APP_NAME, __version__, pairing
from ponte.channel import NotPaired, open_channel
from ponte.keys import add_peer, config_dir, load_identity, load_peers
from ponte.protocol import decode, encode

PORT = 47474


def is_lan(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return ip.is_private or ip.is_link_local or ip.is_loopback


def ask_pairing(sock, identity, initiator) -> bytes | None:
    peer, code = pairing.pair(sock, identity, initiator)
    print(f"\ncodigo de pareamento: {code}")
    answer = input("aparece o mesmo codigo no outro computador? [s/N] ")
    if not pairing.confirm(sock, answer.strip().lower() in ("s", "sim", "y", "yes")):
        print("pareamento cancelado")
        return None
    return peer


def session(sock: socket.socket, initiator: bool) -> None:
    folder = config_dir()
    identity = load_identity(folder)
    peers = load_peers(folder)

    try:
        ch, peer = open_channel(sock, identity, initiator, peers)
    except NotPaired:
        peer = ask_pairing(sock, identity, initiator)
        if peer is None:
            return
        ch, _ = open_channel(sock, identity, initiator, {peer})

    ch.send(encode("hello", name=platform.node(), version=__version__))
    hello = decode(ch.recv())
    add_peer(folder, peer, hello["name"])
    print(f"conectado com {hello['name']}")


def listen(port: int) -> None:
    with socket.create_server(("", port)) as server:
        print(f"esperando conexao na porta {port}...")
        while True:
            sock, (addr, _) = server.accept()
            if not is_lan(addr):
                print(f"recusando {addr}, fora da rede local")
                sock.close()
                continue
            with sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                session(sock, initiator=False)
            return


def connect(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        session(sock, initiator=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ponte")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("listen", help="espera o outro computador conectar")
    p.add_argument("--port", type=int, default=PORT)
    p = sub.add_parser("connect", help="conecta no outro computador pelo IP")
    p.add_argument("host")
    p.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    # TODO: english messages
    # TODO: drop listen/connect once discovery finds the other side by itself
    if args.cmd == "listen":
        listen(args.port)
    elif args.cmd == "connect":
        connect(args.host, args.port)
    else:
        print(f"{APP_NAME} {__version__} rodando em {platform.system()} {platform.release()}")


if __name__ == "__main__":
    main()
