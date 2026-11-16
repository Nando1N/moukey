import ipaddress
import itertools
import logging
import platform
import socket
import threading
import time
from collections import deque
from pathlib import Path

import pyperclip

from moukey import __version__, edges
from moukey.channel import Channel, HandshakeFailed
from moukey.clipboard import Clipboard
from moukey.discovery import Peer, os_label, start_discovery
from moukey.files import Files, downloads_dir
from moukey.keys import config_dir, load_peers, load_settings, remove_peer, save_settings
from moukey.net import PORT, is_lan, local_ip
from moukey.pairing import PairingFailed
from moukey.protocol import BadMessage, encode
from moukey.remote import run_link
from moukey.session import session

log = logging.getLogger("moukey")

RETRY_EVERY = 5  # seconds between automatic reconnect attempts
# a bit more than the 2 minutes a person has to answer the pairing question. without it
# anyone on the wifi could open the port, say nothing and keep us busy forever
HANDSHAKE_TIMEOUT = 150
# copied texts only live in memory and only the last ones, people copy passwords too
HISTORY_SIZE = 30
PREVIEW = 400
# what we assume about a computer we never connected to yet
UNKNOWN_SCREEN = [(0, 0, 1920, 1080)]


def auto_target(
    auto_id: str | None, peers: list[Peer], busy: bool, paused: bool, my_id: str = ""
) -> Peer | None:
    """the peer we should reconnect to on our own, if any"""
    if busy or paused or not auto_id:
        return None
    peer = next((p for p in peers if p.id == auto_id), None)
    # both sides remember each other. only the smaller id dials, or they'd keep
    # calling each other at the same time and hanging up
    if peer is None or (my_id and my_id > peer.id):
        return None
    return peer


class App:
    """everything the window shows and does, without knowing what the window looks like"""

    def __init__(self, backend, on_change):
        self.backend = backend
        self.on_change = on_change  # called from any thread when something changed
        self.settings = load_settings(config_dir())
        self.lock = threading.Lock()
        self.mine = self._my_screens()

        self.peers: list[Peer] = []
        self.sock: socket.socket | None = None  # one connection at a time
        self.ch: Channel | None = None
        self.geo: dict | None = None  # shared with the running link, see remote.run_link
        self.dialing = False
        self.paused = False  # the Desconectar button was used, don't reconnect on our own
        self.last_try = 0.0
        self.error = ""
        self.version_warning = False

        # who we're talking to and what's going on, straight from the real session
        self.link: dict | None = None  # {"name", "peer_id", "away", "guest"}
        self.pairing: dict | None = None  # {"who", "code", "asking"}
        self._answer: dict = {}
        self._answered = threading.Event()
        self.clips: deque[dict] = deque(maxlen=HISTORY_SIZE)
        self.files = Files(downloads_dir(), self._changed)
        self._clip_ids = itertools.count(1)

        self.disco = start_discovery(PORT)
        self.server_ok = True
        threading.Thread(target=self._serve, daemon=True).start()
        threading.Thread(target=self._tick, daemon=True).start()

    def _my_screens(self) -> list[tuple]:
        if hasattr(self.backend, "monitors"):
            return self.backend.monitors()
        return [(0, 0, *self.backend.screen_size())]

    def _placement(self, peer_id: str) -> dict:
        return self.settings.setdefault("placement", {}).get(peer_id, {})

    def _their_screens(self, peer_id: str) -> list[tuple]:
        saved = self._placement(peer_id).get("screens")
        return [tuple(s) for s in saved] if saved else UNKNOWN_SCREEN

    def _offset(self, peer_id: str, theirs: list[tuple]) -> tuple[int, int]:
        saved = self._placement(peer_id).get("offset")
        if saved:
            # their screens may have changed since, keep the spot but make it touch again
            return edges.snap(self.mine, theirs, tuple(saved))
        # people who set a side before multi monitor support keep it
        side = self.settings.get("sides", {}).get(peer_id, "right")
        return edges.place(self.mine, theirs, side)

    def _save_placement(self, peer_id: str, theirs: list[tuple], offset: tuple) -> None:
        self.settings.setdefault("placement", {})[peer_id] = {
            "screens": [list(s) for s in theirs],
            "offset": list(offset),
        }
        save_settings(config_dir(), self.settings)

    def state(self) -> dict:
        busy = self.sock is not None or self.dialing
        peers = []
        layouts = {}
        for p in self.peers:
            linked = self.link is not None and self.link["peer_id"] == p.id
            peers.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "os": p.os,
                    "linked": linked,
                    "remembered": p.id == self.settings.get("auto"),
                }
            )
            theirs = self._their_screens(p.id)
            layouts[p.id] = {
                "screens": [list(s) for s in theirs],
                "offset": list(self._offset(p.id, theirs)),
                "known": bool(self._placement(p.id).get("screens")),
            }
        return {
            "me": {
                "name": platform.node(),
                "os": os_label(),
                "ip": local_ip(),
                "screens": self.mine,
            },
            "peers": peers,
            "layouts": layouts,
            "busy": busy,
            "dialing": self.dialing,
            "link": self.link,
            "pairing": self.pairing,
            "error": self.error,
            "server_ok": self.server_ok,
            "version_warning": self.version_warning,
            "transfers": self.files.views(),
            "downloads": str(self.files.folder),
            "options": {
                "auto_reconnect": self.settings.get("auto_reconnect", True),
                "onboarded": self.settings.get("onboarded", False),
            },
            "autostart": self._autostart(),
            "clips": [
                {
                    "id": c["id"],
                    "preview": c["text"][:PREVIEW],
                    "size": len(c["text"]),
                    "origin": c["origin"],
                    "time": c["time"],
                }
                for c in reversed(list(self.clips))
            ],
            "paired": [
                {"key": key.hex(), "name": name} for key, name in load_peers(config_dir()).items()
            ],
        }

    def _autostart(self) -> dict:
        if not hasattr(self.backend, "autostart_available"):
            return {"available": False, "on": False}
        return {
            "available": self.backend.autostart_available(),
            "on": self.backend.autostart_enabled(),
        }

    def _changed(self) -> None:
        self.on_change(self.state())

    def connect(self, peer_id: str) -> None:
        peer = next((p for p in self.peers if p.id == peer_id), None)
        if peer is None or self.sock is not None or self.dialing:
            return
        self.paused = False
        self.error = ""
        self._start_dial(peer)

    def connect_ip(self, text: str) -> str:
        """for networks that hide the other computer. returns an error message or ''"""
        try:
            ip = ipaddress.ip_address(text.strip())
        except ValueError:
            return "Isso não parece um IP. Ele tem o formato 192.168.0.10"
        if not is_lan(str(ip)):
            return "Só dá para conectar em computadores da sua rede local."
        if self.sock is not None or self.dialing:
            return "Já tem uma conexão em andamento."
        self.paused = False
        self.error = ""
        self._start_dial(Peer(f"ip-{ip}", str(ip), str(ip), PORT))
        return ""

    def disconnect(self) -> None:
        self.paused = True
        if self.pairing and self.pairing["asking"]:
            self.answer(False)
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def set_offset(self, peer_id: str, x: int, y: int) -> None:
        theirs = self._their_screens(peer_id)
        offset = edges.snap(self.mine, theirs, (int(x), int(y)))
        self._save_placement(peer_id, theirs, offset)
        if self.geo is not None and self.link and self.link["peer_id"] == peer_id:
            self.geo["offset"] = offset
            self._send_layout(offset)
        self._changed()

    def _send_layout(self, offset: tuple) -> None:
        # the other side keeps the same picture, seen from its own screens
        try:
            self.ch.send(encode("layout", dx=-offset[0], dy=-offset[1]))
        except (OSError, AttributeError):
            pass

    def set_option(self, name: str, value: bool) -> None:
        if name not in ("auto_reconnect", "onboarded"):
            return
        self.settings[name] = bool(value)
        save_settings(config_dir(), self.settings)
        self._changed()

    def set_autostart(self, on: bool) -> None:
        if self._autostart()["available"]:
            self.backend.set_autostart(bool(on))
        self._changed()

    def forget(self, key_hex: str) -> None:
        # after this the other computer has to show the code and be confirmed again
        try:
            remove_peer(config_dir(), bytes.fromhex(key_hex))
        except ValueError:
            return
        self._changed()

    def copy_clip(self, clip_id: int) -> None:
        clip = next((c for c in self.clips if c["id"] == clip_id), None)
        if clip is not None:
            # while connected, the clipboard watcher sends this to the other side too
            pyperclip.copy(clip["text"])

    def send_files(self, paths: list[str]) -> int:
        if self.link is None:
            return 0
        sent = [self.files.send_file(Path(p)) for p in paths]
        return sum(1 for s in sent if s)

    def cancel_transfer(self, tid: str) -> None:
        self.files.cancel(tid)

    def clear_transfers(self) -> None:
        self.files.transfers = {
            k: t for k, t in self.files.transfers.items() if t.status == "active"
        }
        self._changed()

    def clear_clips(self) -> None:
        self.clips.clear()
        self._changed()

    def _on_clip(self, text: str, local: bool) -> None:
        if self.clips and self.clips[-1]["text"] == text:
            return
        origin = "Este computador" if local else (self.link or {}).get("name", "Outro computador")
        self.clips.append(
            {
                "id": next(self._clip_ids),
                "text": text,
                "origin": origin,
                "time": time.strftime("%H:%M"),
            }
        )
        self._changed()

    def answer(self, ok: bool) -> None:
        self._answer["ok"] = bool(ok)
        self._answered.set()

    def close(self) -> None:
        self.disconnect()
        self.disco.close()

    def _tick(self) -> None:
        while True:
            peers = self.disco.found()
            if peers != self.peers:
                self.peers = peers
                self._changed()

            busy = self.dialing or self.sock is not None
            paused = self.paused or not self.settings.get("auto_reconnect", True)
            auto = self.settings.get("auto")
            peer = auto_target(auto, peers, busy, paused, self.disco.my_id)
            if peer and time.monotonic() - self.last_try > RETRY_EVERY:
                self.last_try = time.monotonic()
                self._start_dial(peer)
            time.sleep(1)

    def _start_dial(self, peer: Peer) -> None:
        self.dialing = True
        self._changed()
        threading.Thread(target=self._dial, args=(peer,), daemon=True).start()

    def _dial(self, peer: Peer) -> None:
        try:
            sock = socket.create_connection((peer.host, peer.port), timeout=10)
        except OSError:
            self.error = f"Não consegui falar com {peer.name}. O MouKey está aberto lá?"
            self.dialing = False
            self._changed()
            return
        sock.settimeout(None)
        self._run(sock, True, peer.name)

    def _serve(self) -> None:
        try:
            server = socket.create_server(("", PORT))
        except OSError:
            # most likely another MouKey (or the old Ponte) is already running here
            log.warning("port %s is taken", PORT)
            self.server_ok = False
            self._changed()
            return
        while True:
            sock, (addr, _) = server.accept()
            if not is_lan(addr) or self.sock is not None or self.dialing:
                sock.close()
                continue
            who = next((p.name for p in self.disco.found() if p.host == addr), addr)
            threading.Thread(target=self._run, args=(sock, False, who), daemon=True).start()

    def _run(self, sock: socket.socket, initiator: bool, who: str) -> None:
        with self.lock:
            self.sock = sock
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            confirm = self._show_code if initiator else (lambda code: self._ask(who, code))
            self.mine = self._my_screens()
            sock.settimeout(HANDSHAKE_TIMEOUT)
            link = session(sock, initiator, confirm, self.mine)
            sock.settimeout(None)
            self.pairing = None
            self.dialing = False
            if link is None:
                self.error = "Pareamento recusado."
                return
            log.info("connected with %s (version %s)", link.name, link.version)
            # different versions may not speak the same protocol, warn instead of failing silently
            self.version_warning = link.version != __version__
            self.error = ""
            # both sides remember each other, the smaller id reconnects (see auto_target)
            self.settings["auto"] = link.peer_id
            offset = self._offset(link.peer_id, link.screens)
            self._save_placement(link.peer_id, link.screens, offset)

            self.ch = link.ch
            self.geo = {"mine": self.mine, "theirs": link.screens, "offset": offset}
            if initiator:
                # whoever clicked Conectar decides where the screens sit
                self._send_layout(offset)
            self.files.attach(link.ch.send, link.name)
            self.link = {"name": link.name, "peer_id": link.peer_id, "away": False, "guest": False}
            self._changed()
            run_link(
                link.ch,
                self.backend,
                Clipboard(on_new=self._on_clip),
                self.geo,
                on_event=self._link_event,
                on_file=self.files.handle,
            )
        except HandshakeFailed as e:
            log.warning("handshake with %s failed: %s", who, e)
            self.error = (
                f"{who} está com outra versão do MouKey, ou o Ponte antigo ainda está aberto lá. "
                "Feche os dois pelo Gerenciador de Tarefas e abra o MouKey mais novo."
            )
        except PairingFailed as e:
            log.warning("pairing with %s failed: %s", who, e)
            self.error = "O pareamento não deu certo. Tente conectar de novo."
        except (OSError, BadMessage) as e:
            log.info("connection with %s ended: %s", who, type(e).__name__)
            if not self.paused:
                self.error = "A conexão caiu. Tentando de novo..."
        finally:
            self.files.detach()
            sock.close()
            with self.lock:
                self.sock = None
            self.ch = None
            self.geo = None
            if self.link is not None:
                log.info("disconnected from %s", self.link["name"])
            self.link = None
            self.pairing = None
            self.dialing = False
            self._changed()

    def _link_event(self, what: str) -> None:
        link = self.link
        if link is None:
            return
        if what == "away":
            link["away"] = True
        elif what == "home":
            link["away"] = False
        elif what == "guest":
            link["guest"] = True
        elif what == "guest_end":
            link["guest"] = False
        elif what == "layout" and self.geo is not None:
            self._save_placement(link["peer_id"], self.geo["theirs"], self.geo["offset"])
        self._changed()

    def _show_code(self, code: str) -> bool:
        # we asked for the connection, the other side decides
        self.pairing = {"who": "", "code": code, "asking": False}
        self._changed()
        return True

    def _ask(self, who: str, code: str) -> bool:
        self._answered.clear()
        self._answer = {}
        self.pairing = {"who": who, "code": code, "asking": True}
        self._changed()
        # nobody answering for two minutes counts as a no
        self._answered.wait(120)
        ok = self._answer.get("ok", False)
        self.pairing = None
        self._changed()
        return ok
