import json
import os
import shutil
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def _base_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def config_dir() -> Path:
    if override := os.environ.get("MOUKEY_HOME"):
        return Path(override)
    folder = _base_dir() / "moukey"
    # the app was called ponte before. keep the old keys so nobody has to pair again
    old = _base_dir() / "ponte"
    if not folder.exists() and old.is_dir():
        shutil.copytree(old, folder)
    return folder


def raw_public(key: X25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def load_identity(folder: Path) -> X25519PrivateKey:
    path = folder / "identity.key"
    if path.exists():
        return X25519PrivateKey.from_private_bytes(path.read_bytes())

    key = X25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    folder.mkdir(parents=True, exist_ok=True)
    # create it already as 0600 so the key is never readable by other users, not even
    # for a moment. O_BINARY matters on windows, otherwise a 0x0a byte becomes \r\n
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as f:
        f.write(raw)
    return key


def load_peers(folder: Path) -> dict[bytes, str]:
    path = folder / "peers.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text("utf-8"))
    return {bytes.fromhex(k): v["name"] for k, v in data.items()}


def load_settings(folder: Path) -> dict:
    path = folder / "settings.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def save_settings(folder: Path, settings: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "settings.json").write_text(json.dumps(settings, indent=2), "utf-8")


def add_peer(folder: Path, public: bytes, name: str) -> None:
    peers = load_peers(folder)
    peers[public] = name
    data = {k.hex(): {"name": v} for k, v in peers.items()}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "peers.json").write_text(json.dumps(data, indent=2), "utf-8")
