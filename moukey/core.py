import base64
import io
import ipaddress
import itertools
import logging
import platform
import select
import shutil
import socket
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

import pyperclip

from moukey import __version__, edges, update
from moukey.channel import Channel, HandshakeFailed
from moukey.clipboard import Clipboard
from moukey.discovery import Peer, device_id, os_label, start_discovery
from moukey.files import Files, downloads_dir
from moukey.keys import config_dir, load_peers, load_settings, remove_peer, save_settings
from moukey.net import PORT, is_lan, local_ip
from moukey.pairing import PairingFailed
from moukey.protocol import CLIP_FILES, BadMessage, encode
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
# copied files bigger than this together don't go on their own, that's what Transferências is for
CLIP_LIMIT = 200 * 1024 * 1024
THUMB = 240
# a received picture bigger than this isn't opened. 8k is about 33 million
MAX_PIXELS = 50_000_000
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

    def __init__(self, backend, on_change, notify=None, quit=None):
        self.backend = backend
        self.on_change = on_change  # called from any thread when something changed
        self.notify = notify or (lambda text: None)  # a little popup next to the clock
        self.quit = quit or (lambda: None)  # closes the app, used after an update
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
        # a stranger who got a "no" (or no answer) can't pop the question again right away
        self._cooldown: dict[str, float] = {}
        self.clips: deque[dict] = deque(maxlen=HISTORY_SIZE)
        self.clip: Clipboard | None = None  # only while connected
        # pictures and files that went through ctrl+c. temp, and wiped on every start
        self.clip_dir = Path(tempfile.gettempdir()) / "MouKey" / "copiados"
        shutil.rmtree(self.clip_dir, ignore_errors=True)
        folder = Path(self.settings.get("downloads") or downloads_dir())
        self.files = Files(folder, self._changed, self.clip_dir / "recebidos")
        self.files.on_clip = self._clip_arrived
        self.files.on_received = self._file_arrived
        self.files.accept_clip = self.settings.get("clip_rich", True)
        self._clip_ids = itertools.count(1)

        # newer version on github, if any. "status" is what the window shows while it works
        self.update = {
            "version": "",
            "status": "",
            "busy": False,
            "can_install": update.can_install(),
        }
        self._found: dict | None = None
        threading.Thread(target=self._update_loop, daemon=True).start()

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
                "clip_rich": self.settings.get("clip_rich", True),
                "check_updates": self.settings.get("check_updates", True),
            },
            "update": dict(self.update),
            "rich_clip": self._rich() is not None,
            "autostart": self._autostart(),
            "clips": [clip_view(c) for c in reversed(list(self.clips))],
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
        if name not in ("auto_reconnect", "onboarded", "clip_rich", "check_updates"):
            return
        self.settings[name] = bool(value)
        save_settings(config_dir(), self.settings)
        if name == "clip_rich":
            self.files.accept_clip = bool(value)
        self._changed()

    def set_autostart(self, on: bool) -> None:
        if self._autostart()["available"]:
            self.backend.set_autostart(bool(on))
        self._changed()

    def forget(self, key_hex: str) -> None:
        # after this the other computer has to show the code and be confirmed again
        try:
            key = bytes.fromhex(key_hex)
        except ValueError:
            return
        remove_peer(config_dir(), key)
        gone = device_id(key)
        if self.settings.get("auto") == gone:
            self.settings.pop("auto")
            save_settings(config_dir(), self.settings)
        if self.link and self.link["peer_id"] == gone:
            self.disconnect()
        self._changed()

    def set_downloads(self, folder: str) -> None:
        path = Path(folder)
        if not path.is_dir():
            return
        self.files.folder = path
        self.settings["downloads"] = str(path)
        save_settings(config_dir(), self.settings)
        self._changed()

    def _update_loop(self) -> None:
        # not right at start, the window and the connection come first
        time.sleep(8)
        while True:
            if self.settings.get("check_updates", True):
                self.check_update()
            time.sleep(6 * 3600)

    def check_update(self, by_hand: bool = False) -> None:
        if self.update["busy"]:
            return
        self.update.update(busy=True, status="Procurando..." if by_hand else self.update["status"])
        self._changed()
        found = update.check()
        self._found = found
        self.update["version"] = found["version"] if found else ""
        if found:
            self.update["status"] = ""
            self.notify(f"Saiu o MouKey {found['version']}. Abra o MouKey para atualizar.")
        elif by_hand:
            self.update["status"] = f"Você já está na versão mais nova ({__version__})."
        self.update["busy"] = False
        self._changed()

    def install_update(self) -> None:
        found = self._found
        if not found or self.update["busy"] or not update.can_install():
            return
        self.update.update(busy=True, status="Baixando a versão nova...")
        self._changed()
        try:
            new = update.download(found, self.clip_dir.parent / "atualizacao")
            self.update["status"] = "Pronto. O MouKey vai reiniciar."
            self._changed()
            log.info("updating to %s", found["version"])
            update.install(new)
        except (OSError, ValueError) as e:
            log.warning("update failed: %s", e)
            self.update.update(
                busy=False, status="Não deu para atualizar. Tente de novo mais tarde."
            )
            self._changed()
            return
        self.quit()

    def _rich(self):
        # pictures and files on the clipboard need the OS side, windows only for now
        return self.backend if hasattr(self.backend, "clip_seq") else None

    def reveal_transfer(self, tid: str) -> None:
        path = self.files.path_of(tid)
        if path and hasattr(self.backend, "reveal"):
            self.backend.reveal(path)

    def reveal_clip(self, clip_id: int) -> None:
        clip = self._find_clip(clip_id)
        if clip is None:
            return
        path = clip.get("path") or (clip.get("paths") or [None])[0]
        if path and hasattr(self.backend, "reveal"):
            self.backend.reveal(path)

    def _find_clip(self, clip_id: int) -> dict | None:
        return next((c for c in self.clips if c["id"] == clip_id), None)

    def copy_clip(self, clip_id: int) -> None:
        clip = self._find_clip(clip_id)
        if clip is None:
            return
        # while connected, the clipboard watcher sends this to the other side too
        rich = self._rich()
        if clip["kind"] == "text":
            pyperclip.copy(clip["text"])
        elif clip["kind"] == "image" and rich:
            rich.write_image(clip["path"])
        elif clip["kind"] == "files" and rich:
            rich.write_files([p for p in clip["paths"] if Path(p).exists()])

    def send_files(self, paths: list[str]) -> int:
        if self.link is None:
            return 0
        sent = [self.files.send_file(Path(p)) for p in paths]
        return sum(1 for s in sent if s)

    def cancel_transfer(self, tid: str) -> None:
        self.files.cancel(tid)

    def clear_transfers(self) -> None:
        # in place: the receiving thread may be looking at this same dict right now
        for k, t in list(self.files.transfers.items()):
            if t.status != "active":
                self.files.transfers.pop(k, None)
        self._changed()

    def clear_clips(self) -> None:
        self.clips.clear()
        self._changed()

    def _remember(self, entry: dict, local: bool) -> dict:
        entry["id"] = next(self._clip_ids)
        entry["origin"] = (
            "Este computador" if local else (self.link or {}).get("name", "Outro computador")
        )
        entry["time"] = time.strftime("%H:%M")
        self.clips.append(entry)
        self._changed()
        return entry

    def _on_clip(self, kind: str, value, local: bool) -> None:
        # pictures and files copied here are handled by _copied, they need saving first
        if kind == "text":
            last = self.clips[-1] if self.clips else None
            if last and last["kind"] == "text" and last["text"] == value:
                return
            self._remember({"kind": "text", "text": value}, local)
        elif not local and kind == "image":
            self._remember({"kind": "image", "path": str(value), "thumb": thumb(value)}, False)
        elif not local and kind == "files":
            self._remember({"kind": "files", "paths": list(value)}, False)

    def _copied(self, kind: str, value) -> None:
        """a picture or files were copied here while connected"""
        send = self.settings.get("clip_rich", True)
        if kind == "image":
            out = self.clip_dir / "enviados"
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"imagem-{time.strftime('%H%M%S')}-{next(self._clip_ids)}.png"
            value.save(path, "PNG")
            entry = self._remember({"kind": "image", "path": str(path), "thumb": thumb(path)}, True)
            if send and not self.files.send_clip([path], image=True):
                entry["note"] = "Não foi para o outro computador"
            return
        paths = [Path(p) for p in value]
        entry = self._remember({"kind": "files", "paths": [str(p) for p in paths]}, True)
        if not send:
            return
        files = [p for p in paths if p.is_file()]
        if len(files) < len(paths):
            entry["note"] = "Pastas ainda não vão pelo Ctrl+C, use Transferências"
        if not files:
            self._changed()
            return
        total = sum(p.stat().st_size for p in files)
        if total > CLIP_LIMIT or len(files) > CLIP_FILES:
            entry["note"] = "Grande demais para ir pelo Ctrl+C, use Transferências"
            log.info("copied files too big for the clipboard, %d bytes", total)
            self._changed()
            return
        self.files.send_clip(files, image=False)
        self._changed()

    def _clip_arrived(self, paths: list[str], image: bool) -> None:
        clip = self.clip
        if clip is None or not self.settings.get("clip_rich", True):
            return
        if image and not picture_ok(paths[0]):
            log.warning("received picture is too big or broken, not put on the clipboard")
            return
        if image:
            clip.set_image(paths[0])
        else:
            clip.set_files(paths)

    def _file_arrived(self, t) -> None:
        self.notify(f"{t.name} chegou de {t.peer}.")

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
                self._start_dial(peer, auto=True)
            time.sleep(1)

    def _start_dial(self, peer: Peer, auto: bool = False) -> None:
        with self.lock:
            # a click and an incoming connection at the same moment would both get through
            if self.sock is not None or self.dialing:
                return
            self.dialing = True
        self._changed()
        threading.Thread(target=self._dial, args=(peer, auto), daemon=True).start()

    def _dial(self, peer: Peer, auto: bool = False) -> None:
        try:
            sock = socket.create_connection((peer.host, peer.port), timeout=10)
        except OSError:
            self.error = f"Não consegui falar com {peer.name}. O MouKey está aberto lá?"
            self.dialing = False
            self._changed()
            return
        sock.settimeout(None)
        # "ip-..." peers were typed by hand, there's no key hash to check them against
        expected = None if peer.id.startswith("ip-") else peer.id
        self._run(sock, True, peer.name, expected=expected, allow_pairing=not auto)

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
            with self.lock:
                # taking the slot here, not in the new thread, or two connections
                # arriving together would both get through
                busy = self.sock is not None or self.dialing
                cooling = time.monotonic() < self._cooldown.get(addr, 0)
                if not is_lan(addr) or busy or cooling:
                    sock.close()
                    continue
                self.sock = sock
            name = next((p.name for p in self.disco.found() if p.host == addr), "")
            # the name comes from the network, anyone can pick one. the ip is harder to fake
            who = f"{name} ({addr})" if name else addr
            threading.Thread(target=self._run, args=(sock, False, who, addr), daemon=True).start()

    def _run(
        self,
        sock: socket.socket,
        initiator: bool,
        who: str,
        addr: str = "",
        expected: str | None = None,
        allow_pairing: bool = True,
    ) -> None:
        with self.lock:
            self.sock = sock
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        prompted: list[str] = []
        connected = False
        try:
            # both sides confirm the code. if only the one who was asked did, a stranger
            # posing as our notebook could just say yes to himself
            def confirm(code):
                prompted.append(code)
                return self._ask(who, code, dialing=initiator, sock=sock)

            self.mine = self._my_screens()
            sock.settimeout(HANDSHAKE_TIMEOUT)
            link = session(sock, initiator, confirm, self.mine, expected, allow_pairing)
            sock.settimeout(None)
            self.pairing = None
            self.dialing = False
            if link is None:
                self.error = "Pareamento recusado."
                if addr:
                    self._cooldown[addr] = time.monotonic() + 30
                return
            log.info("connected with %r (version %r)", link.name, link.version)
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
            connected = True
            self.files.attach(link.ch.send, link.name)
            self.link = {"name": link.name, "peer_id": link.peer_id, "away": False, "guest": False}
            self._changed()
            self.clip = Clipboard(on_new=self._on_clip, rich=self._rich())
            run_link(
                link.ch,
                self.backend,
                self.clip,
                self.geo,
                on_event=self._link_event,
                on_file=self.files.handle,
                on_copy=self._copied,
            )
        except HandshakeFailed as e:
            log.warning("handshake with %s failed: %s", who, e)
            self.error = (
                f"{who} está com outra versão do MouKey, ou o Ponte antigo ainda está aberto lá. "
                "Feche os dois pelo Gerenciador de Tarefas e abra o MouKey mais novo."
            )
        except PairingFailed as e:
            log.warning("pairing with %r failed: %s", who, e)
            if addr:
                self._cooldown[addr] = time.monotonic() + 30
            if allow_pairing:
                self.error = "O pareamento não deu certo. Tente conectar de novo."
        except (OSError, BadMessage) as e:
            log.info("connection with %s ended: %s", who, type(e).__name__)
            if not self.paused:
                self.error = "A conexão caiu. Tentando de novo..."
        finally:
            # whatever the answer was, a stranger who made us ask waits before asking again.
            # hanging up while the question is on screen doesn't skip that
            if addr and prompted and not connected:
                self._cooldown[addr] = time.monotonic() + 30
            self.clip = None
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

    def _ask(self, who: str, code: str, dialing: bool = False, sock=None) -> bool:
        self._answered.clear()
        self._answer = {}
        self.pairing = {"who": who, "code": code, "asking": True, "dialing": dialing}
        self._changed()
        # nobody answering for two minutes counts as a no. and if the other side hung up,
        # the question disappears instead of waiting for nobody
        end = time.monotonic() + 120
        while not self._answered.wait(0.5):
            if time.monotonic() > end or (sock is not None and hung_up(sock)):
                break
        ok = self._answer.get("ok", False)
        self.pairing = None
        self._changed()
        return ok


def thumb(path) -> str:
    """a small picture for the history screen, as a data url"""
    from PIL import Image

    try:
        with Image.open(path) as img:
            if img.width * img.height > MAX_PIXELS:
                return ""
            img.thumbnail((THUMB, THUMB))
            buf = io.BytesIO()
            img.save(buf, "PNG")
    except (OSError, Image.DecompressionBombError):
        return ""
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def clip_view(c: dict) -> dict:
    view = {"id": c["id"], "kind": c["kind"], "origin": c["origin"], "time": c["time"]}
    view["note"] = c.get("note", "")
    if c["kind"] == "text":
        view["preview"] = c["text"][:PREVIEW]
        view["size"] = len(c["text"])
    elif c["kind"] == "image":
        view["thumb"] = c.get("thumb", "")
    else:
        view["names"] = [Path(p).name for p in c["paths"]]
    return view


def picture_ok(path) -> bool:
    from PIL import Image

    try:
        with Image.open(path) as img:
            return img.width * img.height <= MAX_PIXELS
    except (OSError, Image.DecompressionBombError):
        return False


def hung_up(sock: socket.socket) -> bool:
    """true when the other side closed the connection, without eating any of its data"""
    try:
        ready, _, _ = select.select([sock], [], [], 0)
        return bool(ready) and sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True
