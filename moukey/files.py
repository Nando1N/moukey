import base64
import binascii
import hashlib
import logging
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from moukey.protocol import encode

# small pieces so mouse and keyboard messages never wait long behind a file
CHUNK = 64 * 1024
# file names never go to the log, only sizes and what went wrong
log = logging.getLogger("moukey")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def downloads_dir() -> Path:
    return Path.home() / "Downloads" / "MouKey"


def safe_name(name: str) -> str:
    # only the file name itself. "..\..\windows\x" becomes "x", no folders, ever
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    if name.split(".")[0].upper() in RESERVED:
        name = "_" + name
    return name[:200] or "arquivo"


def free_path(folder: Path, name: str) -> Path:
    path = folder / name
    n = 1
    while path.exists() or path.with_name(path.name + ".part").exists():
        path = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return path


@dataclass
class Transfer:
    id: str
    name: str
    size: int
    incoming: bool
    peer: str
    done: int = 0
    status: str = "active"  # active, done, error, canceled
    error: str = ""
    path: str = ""
    clip: bool = False  # part of something copied with ctrl+c, not a transfer
    started: float = field(default_factory=time.monotonic)

    def view(self) -> dict:
        elapsed = max(time.monotonic() - self.started, 0.001)
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "done": self.done,
            "incoming": self.incoming,
            "peer": self.peer,
            "status": self.status,
            "error": self.error,
            "speed": self.done / elapsed if self.status == "active" else 0,
        }


@dataclass
class _Incoming:
    file: object
    hash: object
    part: Path
    final: Path


class Files:
    """sends and receives files over whatever session is open right now"""

    def __init__(self, folder: Path, on_change, clip_folder: Path | None = None):
        self.folder = folder
        self.on_change = on_change
        # copied files and pictures land here, out of the way, then go on the clipboard
        self.clip_folder = clip_folder or folder
        self.on_clip = lambda paths, image: None
        self.on_received = lambda t: None
        self._groups: dict[str, dict] = {}  # transfer id -> the ctrl+c it belongs to
        self.transfers: dict[str, Transfer] = {}
        self._send = None
        self.peer = ""
        self._incoming: dict[str, _Incoming] = {}
        self._cancel: set[str] = set()
        self._last_push = 0.0

    def views(self) -> list[dict]:
        # a finished ctrl+c shows up in the clipboard history, not here
        shown = [t for t in self.transfers.values() if not (t.clip and t.status == "done")]
        return [t.view() for t in reversed(shown)]

    def path_of(self, tid: str) -> str | None:
        t = self.transfers.get(tid)
        return t.path if t is not None and t.status == "done" and t.path else None

    def _push(self, force: bool = False) -> None:
        # progress comes in fast, the window only needs a few updates per second
        now = time.monotonic()
        if force or now - self._last_push > 0.2:
            self._last_push = now
            self.on_change()

    def attach(self, send, peer: str) -> None:
        self._send = send
        self.peer = peer

    def detach(self) -> None:
        self._send = None
        for t in self.transfers.values():
            if t.status == "active":
                t.status = "error"
                t.error = "A conexão caiu"
        for tid in list(self._incoming):
            self._drop_incoming(tid)
        self._groups.clear()
        self._push(True)

    def send_file(self, path: Path) -> str | None:
        if self._send is None:
            log.info("file not sent: not connected")
            return None
        if not path.is_file():
            log.info("file not sent: not a file (folder or missing)")
            return None
        t = Transfer(uuid.uuid4().hex, path.name, path.stat().st_size, False, self.peer)
        self.transfers[t.id] = t
        threading.Thread(target=self._send_file, args=(t, path), daemon=True).start()
        self._push(True)
        return t.id

    def send_clip(self, paths: list[Path], image: bool) -> bool:
        """sends what was copied here so it lands on the other clipboard"""
        send = self._send
        if send is None or not paths:
            return False
        jobs = [
            (Transfer(uuid.uuid4().hex, p.name, p.stat().st_size, False, self.peer), p)
            for p in paths
        ]
        for t, _ in jobs:
            t.clip = True
            self.transfers[t.id] = t
        try:
            send(encode("file_clip", ids=[t.id for t, _ in jobs], image=image))
        except OSError:
            return False

        def run():
            # one after the other, a copy of 50 files shouldn't start 50 threads
            for t, p in jobs:
                self._send_file(t, p)

        threading.Thread(target=run, daemon=True).start()
        self._push(True)
        return True

    def _send_file(self, t: Transfer, path: Path) -> None:
        send = self._send
        digest = hashlib.sha256()
        try:
            send(encode("file_offer", id=t.id, name=t.name, size=t.size))
            with path.open("rb") as f:
                while chunk := f.read(CHUNK):
                    if t.id in self._cancel or t.status != "active":
                        send(encode("file_cancel", id=t.id))
                        t.status = "canceled"
                        return
                    digest.update(chunk)
                    send(encode("file_chunk", id=t.id, data=base64.b64encode(chunk).decode()))
                    t.done += len(chunk)
                    self._push()
            send(encode("file_end", id=t.id, sha256=digest.hexdigest()))
            t.status = "done"
            log.info("file sent, %d bytes", t.size)
        except OSError as e:
            log.warning("file send failed: %s", type(e).__name__)
            if t.status == "active":
                t.status = "error"
                t.error = "Não deu para enviar"
        finally:
            self._cancel.discard(t.id)
            self._push(True)

    def cancel(self, tid: str) -> None:
        t = self.transfers.get(tid)
        if t is None or t.status != "active":
            return
        if t.incoming:
            self._refuse(tid, "Cancelado")
            t.status = "canceled"
        else:
            self._cancel.add(tid)
        self._push(True)

    def _refuse(self, tid: str, why: str) -> None:
        log.warning("incoming file refused: %s", why)
        self._drop_incoming(tid)
        self._drop_group(tid)
        t = self.transfers.get(tid)
        if t is not None and t.status == "active":
            t.status = "error"
            t.error = why
        if self._send is not None:
            try:
                self._send(encode("file_cancel", id=tid))
            except OSError:
                pass

    def _drop_incoming(self, tid: str) -> None:
        inc = self._incoming.pop(tid, None)
        if inc is not None:
            inc.file.close()
            inc.part.unlink(missing_ok=True)

    def _drop_group(self, tid: str) -> None:
        # one piece of a ctrl+c failed, putting only the rest on the clipboard would confuse
        group = self._groups.get(tid)
        if group is not None:
            for i in group["ids"]:
                self._groups.pop(i, None)

    def handle(self, msg: dict) -> None:
        if msg["t"] == "file_clip":
            group = {
                "ids": list(msg["ids"]),
                "image": msg["image"],
                "paths": {},
                # the id comes from the other side, only hex digits become a folder name
                "folder": self.clip_folder / (re.sub(r"[^0-9a-f]", "", msg["ids"][0])[:12] or "x"),
            }
            for i in group["ids"]:
                self._groups[i] = group
            return
        kind, tid = msg["t"], msg["id"]
        if kind == "file_offer":
            self._offer(tid, msg["name"], msg["size"])
        elif kind == "file_chunk":
            self._chunk(tid, msg["data"])
        elif kind == "file_end":
            self._end(tid, msg["sha256"])
        elif kind == "file_cancel":
            t = self.transfers.get(tid)
            if t is not None and t.status == "active":
                if t.incoming:
                    self._drop_incoming(tid)
                    self._drop_group(tid)
                t.status = "canceled"
                t.error = "Cancelado no outro computador"
                self._push(True)

    def _offer(self, tid: str, name: str, size: int) -> None:
        if tid in self.transfers:
            return
        t = Transfer(tid, safe_name(name), size, True, self.peer)
        group = self._groups.get(tid)
        t.clip = group is not None
        folder = group["folder"] if group else self.folder
        self.transfers[tid] = t
        folder.mkdir(parents=True, exist_ok=True)
        # keep some room so a big file can't fill the disk to the last byte
        if shutil.disk_usage(folder).free < size + 200 * 1024 * 1024:
            self._refuse(tid, "Sem espaço no disco")
            self._push(True)
            return
        final = free_path(folder, t.name)
        part = final.with_name(final.name + ".part")
        self._incoming[tid] = _Incoming(part.open("wb"), hashlib.sha256(), part, final)
        t.path = str(final)
        t.name = final.name
        self._push(True)

    def _chunk(self, tid: str, data: str) -> None:
        inc = self._incoming.get(tid)
        t = self.transfers.get(tid)
        if inc is None or t is None:
            return
        try:
            chunk = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            self._refuse(tid, "Arquivo chegou corrompido")
            return
        if t.done + len(chunk) > t.size:
            self._refuse(tid, "Arquivo maior do que o combinado")
            return
        inc.file.write(chunk)
        inc.hash.update(chunk)
        t.done += len(chunk)
        self._push()

    def _end(self, tid: str, sha256: str) -> None:
        inc = self._incoming.pop(tid, None)
        t = self.transfers.get(tid)
        if inc is None or t is None:
            return
        inc.file.close()
        if t.done != t.size or inc.hash.hexdigest() != sha256:
            inc.part.unlink(missing_ok=True)
            t.status = "error"
            t.error = "O arquivo chegou diferente do original, descartei"
            log.warning("incoming file didn't match its hash, dropped")
            self._drop_group(tid)
        else:
            inc.part.replace(inc.final)
            t.status = "done"
            log.info("file received, %d bytes", t.size)
            self._arrived(t)
        self._push(True)

    def _arrived(self, t: Transfer) -> None:
        group = self._groups.pop(t.id, None)
        if group is None:
            self.on_received(t)
            return
        group["paths"][t.id] = t.path
        if len(group["paths"]) == len(group["ids"]):
            # same order they were copied in
            self.on_clip([group["paths"][i] for i in group["ids"]], group["image"])
