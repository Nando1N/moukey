import base64
import binascii
import hashlib
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

    def __init__(self, folder: Path, on_change):
        self.folder = folder
        self.on_change = on_change
        self.transfers: dict[str, Transfer] = {}
        self._send = None
        self.peer = ""
        self._incoming: dict[str, _Incoming] = {}
        self._cancel: set[str] = set()
        self._last_push = 0.0

    def views(self) -> list[dict]:
        return [t.view() for t in reversed(list(self.transfers.values()))]

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
        self._push(True)

    def send_file(self, path: Path) -> str | None:
        if self._send is None or not path.is_file():
            return None
        t = Transfer(uuid.uuid4().hex, path.name, path.stat().st_size, False, self.peer)
        self.transfers[t.id] = t
        threading.Thread(target=self._send_file, args=(t, path), daemon=True).start()
        self._push(True)
        return t.id

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
        except OSError:
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
        self._drop_incoming(tid)
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

    def handle(self, msg: dict) -> None:
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
                t.status = "canceled"
                t.error = "Cancelado no outro computador"
                self._push(True)

    def _offer(self, tid: str, name: str, size: int) -> None:
        if tid in self.transfers:
            return
        t = Transfer(tid, safe_name(name), size, True, self.peer)
        self.transfers[tid] = t
        self.folder.mkdir(parents=True, exist_ok=True)
        # keep some room so a big file can't fill the disk to the last byte
        if shutil.disk_usage(self.folder).free < size + 200 * 1024 * 1024:
            self._refuse(tid, "Sem espaço no disco")
            self._push(True)
            return
        final = free_path(self.folder, t.name)
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
        else:
            inc.part.replace(inc.final)
            t.status = "done"
        self._push(True)
