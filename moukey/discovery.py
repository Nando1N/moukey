import hashlib
import json
import logging
import platform
import re
import socket
import threading
import time
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from moukey.keys import config_dir, load_identity, raw_public
from moukey.net import is_lan, local_ip

SERVICE = "_moukey._tcp.local."

# plan b for networks that block mdns (lots of routers and office wifi do):
# every couple of seconds we shout "here I am" over udp broadcast, like LocalSend
BEACON_PORT = 47475
BEACON_EVERY = 2
BEACON_TTL = 8  # forget a machine after this long without hearing from it
MDNS_RETRY = 15

log = logging.getLogger("moukey")


@dataclass(frozen=True)
class Peer:
    id: str
    name: str
    host: str
    port: int
    os: str = ""


def os_label() -> str:
    # "Windows 11" reads better than "Windows 10.0.26200"
    system = platform.system()
    if system == "Windows":
        build = int(platform.version().split(".")[-1] or 0)
        return "Windows 11" if build >= 22000 else "Windows 10"
    if system == "Darwin":
        return "macOS"
    return system


def device_id(public: bytes) -> str:
    # short and stable, so a paired machine is recognized even if its ip changes
    return hashlib.sha256(public).hexdigest()[:16]


def clean_name(name: str) -> str:
    # names come from the network: no control characters, no 300 character names
    return "".join(c for c in name if c.isprintable())[:64].strip()


def valid_id(peer_id) -> bool:
    return isinstance(peer_id, str) and re.fullmatch(r"[0-9a-f]{16}", peer_id) is not None


def peer_from_info(info: ServiceInfo) -> Peer | None:
    try:
        props = {k.decode(): (v or b"").decode() for k, v in info.properties.items()}
    except UnicodeDecodeError:
        return None
    if not valid_id(props.get("id")) or not info.port:
        return None
    hosts = [a for a in info.parsed_addresses() if is_lan(a)]
    if not hosts:
        return None
    name = clean_name(props.get("name", "")) or props["id"]
    return Peer(props["id"], name, hosts[0], info.port, clean_name(props.get("os", ""))[:32])


def make_beacon(my_id: str, name: str, port: int, os_name: str = "") -> bytes:
    msg = {"moukey": 1, "id": my_id, "name": name, "port": port, "os": os_name}
    return json.dumps(msg).encode()


def parse_beacon(data: bytes, addr: str, my_id: str) -> Peer | None:
    try:
        msg = json.loads(data)
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("moukey") != 1:
        return None
    peer_id, name, port = msg.get("id"), msg.get("name"), msg.get("port")
    if not valid_id(peer_id) or peer_id == my_id:
        return None
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        return None
    if not is_lan(addr):
        return None
    name = clean_name(name) if isinstance(name, str) else ""
    os_name = clean_name(msg["os"]) if isinstance(msg.get("os"), str) else ""
    return Peer(peer_id, name or peer_id, addr, port, os_name[:32])


def alive(heard: dict[str, tuple[Peer, float]], now: float) -> list[Peer]:
    return [peer for peer, seen in heard.values() if now - seen < BEACON_TTL]


def broadcast_targets(ip: str) -> list[str]:
    # 255.255.255.255 sometimes leaves through the wrong adapter (vpn, hyper-v),
    # so also hit the /24 broadcast of our own address. most home networks are /24
    targets = ["255.255.255.255"]
    parts = ip.split(".")
    if len(parts) == 4 and not ip.startswith("127."):
        targets.append(".".join(parts[:3] + ["255"]))
    return targets


class Discovery:
    def __init__(self, my_id: str, name: str, ip: str, port: int):
        self.my_id = my_id
        self.peers: dict[str, Peer] = {}
        self._names: dict[str, str] = {}  # zeroconf name -> peer id
        self._lock = threading.Lock()
        self._heard: dict[str, tuple[Peer, float]] = {}
        self._stop = threading.Event()

        self.zc: Zeroconf | None = None
        self.info = ServiceInfo(
            SERVICE,
            f"{name}-{my_id[:6]}.{SERVICE}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"id": my_id, "name": name, "os": os_label()},
        )
        # registering can take 10+ seconds on a busy machine and then give up with
        # EventLoopBlocked. doing it here used to kill the whole app on startup
        threading.Thread(target=self._start_mdns, daemon=True).start()

        self._beacon = make_beacon(my_id, name, port, os_label())
        self._targets = broadcast_targets(ip)
        self.udp = self._open_udp()
        if self.udp is not None:
            threading.Thread(target=self._shout, daemon=True).start()
            threading.Thread(target=self._listen, daemon=True).start()

    def _start_mdns(self) -> None:
        # the beacon keeps finding machines meanwhile, so just keep trying
        while not self._stop.is_set():
            zc = None
            try:
                zc = Zeroconf()
                zc.register_service(self.info)
                ServiceBrowser(zc, SERVICE, handlers=[self._on_change])
            except Exception as e:
                log.warning("mdns failed, trying again: %s", type(e).__name__)
                if zc is not None:
                    zc.close()
                self._stop.wait(MDNS_RETRY)
                continue
            with self._lock:
                if not self._stop.is_set():
                    self.zc = zc
                    return
            zc.close()
            return

    def _open_udp(self) -> socket.socket | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind(("", BEACON_PORT))
        except OSError:
            # mdns still works, the beacon is just a backup
            sock.close()
            return None
        sock.settimeout(1)
        return sock

    def _shout(self) -> None:
        while True:
            for target in self._targets:
                try:
                    self.udp.sendto(self._beacon, (target, BEACON_PORT))
                except OSError:
                    pass
            if self._stop.wait(BEACON_EVERY):
                return

    def _listen(self) -> None:
        while not self._stop.is_set():
            try:
                data, (addr, _) = self.udp.recvfrom(2048)
            except TimeoutError:
                continue
            except OSError:
                return
            peer = parse_beacon(data, addr, self.my_id)
            if peer is not None:
                with self._lock:
                    self._heard[peer.id] = (peer, time.monotonic())

    def _on_change(self, zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Removed:
            with self._lock:
                peer_id = self._names.pop(name, None)
                self.peers.pop(peer_id, None)
            return
        # resolving blocks, and blocking inside a zeroconf callback freezes the browser
        threading.Thread(target=self._resolve, args=(zeroconf, name), daemon=True).start()

    def _resolve(self, zc: Zeroconf, name: str) -> None:
        info = ServiceInfo(SERVICE, name)
        if not info.request(zc, 3000):
            return
        peer = peer_from_info(info)
        if peer is None or peer.id == self.my_id:
            return
        with self._lock:
            self._names[name] = peer.id
            self.peers[peer.id] = peer

    def found(self) -> list[Peer]:
        with self._lock:
            peers = {p.id: p for p in alive(self._heard, time.monotonic())}
            # mdns wins when both found the same machine
            peers.update(self.peers)
        return sorted(peers.values(), key=lambda p: p.name.lower())

    def wait_for(self, seconds: float) -> list[Peer]:
        time.sleep(seconds)
        return self.found()

    def close(self) -> None:
        self._stop.set()
        if self.udp is not None:
            self.udp.close()
        with self._lock:
            zc, self.zc = self.zc, None
        if zc is not None:
            zc.unregister_service(self.info)
            zc.close()


def start_discovery(port: int) -> Discovery:
    identity = load_identity(config_dir())
    return Discovery(device_id(raw_public(identity)), platform.node(), local_ip(), port)
