import itertools
import platform
import socket
import threading
import time
from collections import deque
from pathlib import Path

import pyperclip

from moukey import __version__
from moukey.channel import HandshakeFailed
from moukey.clipboard import Clipboard
from moukey.discovery import Peer, os_label, start_discovery
from moukey.files import Files, downloads_dir
from moukey.keys import config_dir, load_peers, load_settings, remove_peer, save_settings
from moukey.net import PORT, is_lan
from moukey.pairing import PairingFailed
from moukey.protocol import BadMessage
from moukey.remote import run_controller, run_receiver
from moukey.session import session

RETRY_EVERY = 5  # seconds between automatic reconnect attempts
# copied texts only live in memory and only the last ones, people copy passwords too
HISTORY_SIZE = 30
PREVIEW = 400


def auto_target(auto_id: str | None, peers: list[Peer], busy: bool, paused: bool) -> Peer | None:
    """the peer we should reconnect to on our own, if any"""
    if busy or paused or not auto_id:
        return None
    return next((p for p in peers if p.id == auto_id), None)


class App:
    """everything the window shows and does, without knowing what the window looks like"""

    def __init__(self, backend, on_change):
        self.backend = backend
        self.on_change = on_change  # called from any thread when something changed
        self.settings = load_settings(config_dir())
        self.lock = threading.Lock()

        self.peers: list[Peer] = []
        self.sock: socket.socket | None = None  # one connection at a time
        self.dialing = False
        self.paused = False  # the Desconectar button was used, don't reconnect on our own
        self.last_try = 0.0
        self.error = ""
        self.version_warning = False

        # who we're talking to and what's going on, straight from the real session
        self.link: dict | None = None  # {"name", "role": "controlling"|"controlled", "away"}
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

    def state(self) -> dict:
        sides = self.settings.get("sides", {})
        busy = self.sock is not None or self.dialing
        peers = []
        for p in self.peers:
            linked = self.link is not None and self.link["name"] == p.name
            peers.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "os": p.os,
                    "side": sides.get(p.id, "right"),
                    "linked": linked,
                    "remembered": p.id == self.settings.get("auto"),
                }
            )
        return {
            "me": {"name": platform.node(), "os": os_label()},
            "peers": peers,
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
        # remember the choice, next time this computer reconnects by itself
        self.settings["auto"] = peer.id
        save_settings(config_dir(), self.settings)
        self._start_dial(peer)

    def disconnect(self) -> None:
        self.paused = True
        if self.pairing and self.pairing["asking"]:
            self.answer(False)
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def set_side(self, peer_id: str, side: str) -> None:
        if side not in ("left", "right", "top", "bottom"):
            return
        self.settings.setdefault("sides", {})[peer_id] = side
        save_settings(config_dir(), self.settings)
        self._changed()

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
            peer = auto_target(self.settings.get("auto"), peers, busy, paused)
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
        side = self.settings.get("sides", {}).get(peer.id, "right")
        self._run(sock, True, peer.name, side)

    def _serve(self) -> None:
        try:
            server = socket.create_server(("", PORT))
        except OSError:
            # most likely another MouKey is already running on this computer
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

    def _run(self, sock: socket.socket, initiator: bool, who: str, side: str = "right") -> None:
        # whoever clicked Conectar is sitting in front of the mouse, so they drive
        with self.lock:
            self.sock = sock
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            confirm = self._show_code if initiator else (lambda code: self._ask(who, code))
            result = session(sock, initiator, confirm)
            self.pairing = None
            self.dialing = False
            if result is None:
                self.error = "Pareamento recusado."
                return
            ch, name, their_version = result
            # different versions may not speak the same protocol, warn instead of failing silently
            self.version_warning = their_version != __version__
            self.error = ""
            self.files.attach(ch.send, name)
            if initiator:
                self.link = {"name": name, "role": "controlling", "away": False}
                self._changed()
                run_controller(
                    ch,
                    side,
                    self.backend,
                    Clipboard(on_new=self._on_clip),
                    say=lambda t: None,
                    on_mouse=self._mouse,
                    on_file=self.files.handle,
                )
            else:
                self.link = {"name": name, "role": "controlled", "away": False}
                self._changed()
                run_receiver(
                    ch,
                    self.backend,
                    Clipboard(on_new=self._on_clip),
                    say=lambda t: None,
                    on_file=self.files.handle,
                )
        except (OSError, HandshakeFailed, PairingFailed, BadMessage):
            if not self.paused:
                self.error = "A conexão falhou. Tentando de novo..."
        finally:
            self.files.detach()
            sock.close()
            with self.lock:
                self.sock = None
            self.link = None
            self.pairing = None
            self.dialing = False
            self._changed()

    def _mouse(self, away: bool) -> None:
        if self.link is not None:
            self.link["away"] = away
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
