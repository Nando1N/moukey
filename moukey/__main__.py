import argparse
import ipaddress
import socket
import sys

from moukey import APP_NAME, __version__, backends
from moukey.clipboard import Clipboard
from moukey.discovery import Peer, start_discovery
from moukey.net import PORT, is_lan
from moukey.remote import run_controller, run_receiver
from moukey.session import session

LADOS = {"right": "direita", "left": "esquerda", "top": "de cima", "bottom": "de baixo"}


def pick_peer(peers: list[Peer], wanted: str | None) -> Peer | None:
    if wanted:
        peers = [p for p in peers if p.name.lower().startswith(wanted.lower())]
    if len(peers) == 1:
        return peers[0]
    if not peers:
        print("nenhum computador encontrado. o moukey ta aberto no outro?")
    else:
        print("achei mais de um, diga qual:")
        for p in peers:
            print(f"  moukey connect {p.name}")
    return None


def ask_in_terminal(code: str) -> bool:
    print(f"\ncodigo de pareamento: {code}")
    answer = input("aparece o mesmo codigo no outro computador? [s/N] ")
    ok = answer.strip().lower() in ("s", "sim", "y", "yes")
    if not ok:
        print("pareamento cancelado")
    return ok


def listen(port: int, side: str) -> None:
    backend = backends.load()
    disco = start_discovery(port)
    try:
        with socket.create_server(("", port)) as server:
            print("esperando o outro computador... (no outro rode: moukey connect)")
            while True:
                sock, (addr, _) = server.accept()
                if not is_lan(addr):
                    print(f"recusando {addr}, fora da rede local")
                    sock.close()
                    continue
                with sock:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    result = session(sock, False, ask_in_terminal)
                    if result:
                        ch, name = result
                        print(f"conectado com {name}")
                        print(f"leve o mouse pra borda {LADOS[side]} da tela")
                        run_controller(ch, side, backend, Clipboard())
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
        result = session(sock, True, ask_in_terminal)
        if result:
            ch, name = result
            print(f"conectado com {name}")
            run_receiver(ch, backend, Clipboard())


def main() -> None:
    parser = argparse.ArgumentParser(prog="moukey")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("listen", help="espera o outro computador conectar")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument(
        "--side",
        choices=list(LADOS),
        default="right",
        help="de que lado da tela fica o outro computador",
    )
    p = sub.add_parser("connect", help="acha o outro computador na rede e conecta")
    p.add_argument("target", nargs="?", help="nome ou IP, so se tiver mais de um")
    p.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    # TODO: english messages
    if args.cmd == "listen":
        listen(args.port, args.side)
    elif args.cmd == "connect":
        connect(args.target, args.port)
    else:
        from moukey import webapp

        webapp.main()


if __name__ == "__main__":
    main()
