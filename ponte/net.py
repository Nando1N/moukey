import ipaddress
import socket


def is_lan(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return ip.is_private or ip.is_link_local or ip.is_loopback


def local_ip() -> str:
    # connecting a udp socket sends nothing, it just makes the OS pick the
    # interface it would use to reach the outside, which is the lan one
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
