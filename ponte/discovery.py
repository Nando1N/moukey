import hashlib
import platform
import socket
import threading
import time
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from ponte.keys import config_dir, load_identity, raw_public
from ponte.net import is_lan, local_ip

SERVICE = "_ponte._tcp.local."


@dataclass(frozen=True)
class Peer:
    id: str
    name: str
    host: str
    port: int


def device_id(public: bytes) -> str:
    # short and stable, so a paired machine is recognized even if its ip changes
    return hashlib.sha256(public).hexdigest()[:16]


def peer_from_info(info: ServiceInfo) -> Peer | None:
    props = {k.decode(): (v or b"").decode() for k, v in info.properties.items()}
    if "id" not in props or not info.port:
        return None
    hosts = [a for a in info.parsed_addresses() if is_lan(a)]
    if not hosts:
        return None
    return Peer(props["id"], props.get("name") or props["id"], hosts[0], info.port)


class Discovery:
    def __init__(self, my_id: str, name: str, ip: str, port: int):
        self.my_id = my_id
        self.peers: dict[str, Peer] = {}
        self._names: dict[str, str] = {}  # zeroconf name -> peer id
        self._lock = threading.Lock()

        self.zc = Zeroconf()
        self.info = ServiceInfo(
            SERVICE,
            f"{name}-{my_id[:6]}.{SERVICE}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={"id": my_id, "name": name},
        )
        self.zc.register_service(self.info)
        self.browser = ServiceBrowser(self.zc, SERVICE, handlers=[self._on_change])

    def _on_change(self, zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Removed:
            with self._lock:
                peer_id = self._names.pop(name, None)
                self.peers.pop(peer_id, None)
            return
        # resolving blocks, and blocking inside a zeroconf callback freezes the browser
        threading.Thread(target=self._resolve, args=(name,), daemon=True).start()

    def _resolve(self, name: str) -> None:
        info = ServiceInfo(SERVICE, name)
        if not info.request(self.zc, 3000):
            return
        peer = peer_from_info(info)
        if peer is None or peer.id == self.my_id:
            return
        with self._lock:
            self._names[name] = peer.id
            self.peers[peer.id] = peer

    def found(self) -> list[Peer]:
        with self._lock:
            return sorted(self.peers.values(), key=lambda p: p.name.lower())

    def wait_for(self, seconds: float) -> list[Peer]:
        time.sleep(seconds)
        return self.found()

    def close(self) -> None:
        self.zc.unregister_service(self.info)
        self.zc.close()


def start_discovery(port: int) -> Discovery:
    identity = load_identity(config_dir())
    return Discovery(device_id(raw_public(identity)), platform.node(), local_ip(), port)
