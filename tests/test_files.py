import base64
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from moukey.channel import open_channel
from moukey.files import Files, free_path, safe_name
from moukey.keys import raw_public
from moukey.protocol import decode, encode


def wired(tmp_path):
    """two sides talking straight to each other, like over a real session"""
    out = tmp_path / "recebidos"
    receiver = Files(out, lambda: None)
    sender = Files(tmp_path / "nada", lambda: None)
    sender.attach(lambda data: receiver.handle(decode(data)), "NOTEBOOK")
    receiver.attach(lambda data: sender.handle(decode(data)), "PC")
    return sender, receiver, out


def wait_done(files, tid):
    for _ in range(200):
        if files.transfers[tid].status != "active":
            return files.transfers[tid]
        time.sleep(0.01)
    raise AssertionError("transfer never finished")


def test_file_arrives_intact(tmp_path):
    sender, receiver, out = wired(tmp_path)
    original = tmp_path / "foto.bin"
    original.write_bytes(os.urandom(300_000))

    tid = sender.send_file(original)
    assert wait_done(sender, tid).status == "done"
    got = receiver.transfers[tid]
    assert got.status == "done"
    assert (out / "foto.bin").read_bytes() == original.read_bytes()
    assert not list(out.glob("*.part"))


def test_same_name_does_not_overwrite(tmp_path):
    sender, receiver, out = wired(tmp_path)
    out.mkdir()
    (out / "a.txt").write_text("antigo")
    f = tmp_path / "a.txt"
    f.write_text("novo")
    wait_done(sender, sender.send_file(f))
    assert (out / "a.txt").read_text() == "antigo"
    assert (out / "a (1).txt").read_text() == "novo"


def test_tampered_file_is_thrown_away(tmp_path):
    receiver = Files(tmp_path, lambda: None)
    receiver.attach(lambda data: None, "PC")
    receiver.handle(decode(encode("file_offer", id="x", name="doc.txt", size=3)))
    receiver.handle(decode(encode("file_chunk", id="x", data=base64.b64encode(b"abc").decode())))
    receiver.handle(decode(encode("file_end", id="x", sha256="0" * 64)))
    assert receiver.transfers["x"].status == "error"
    assert not list(tmp_path.iterdir())


def test_more_bytes_than_promised_is_refused(tmp_path):
    receiver = Files(tmp_path, lambda: None)
    sent = []
    receiver.attach(sent.append, "PC")
    receiver.handle(decode(encode("file_offer", id="x", name="doc.txt", size=2)))
    receiver.handle(decode(encode("file_chunk", id="x", data=base64.b64encode(b"abc").decode())))
    assert receiver.transfers["x"].status == "error"
    assert decode(sent[-1])["t"] == "file_cancel"
    assert not list(tmp_path.iterdir())


def test_connection_drop_cleans_up(tmp_path):
    receiver = Files(tmp_path, lambda: None)
    receiver.attach(lambda data: None, "PC")
    receiver.handle(decode(encode("file_offer", id="x", name="grande.zip", size=10)))
    receiver.detach()
    assert receiver.transfers["x"].status == "error"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "raw, clean",
    [
        ("relatorio.pdf", "relatorio.pdf"),
        ("..\\..\\Windows\\System32\\x.dll", "x.dll"),
        ("../../etc/passwd", "passwd"),
        ("CON.txt", "_CON.txt"),
        ('a<b>c:"d"|e?.txt', "a_b_c__d__e_.txt"),
        ("...", "arquivo"),
    ],
)
def test_safe_name(raw, clean):
    assert safe_name(raw) == clean


def test_free_path_counts_up(tmp_path):
    (tmp_path / "x.txt").write_text("1")
    (tmp_path / "x (1).txt").write_text("2")
    assert free_path(tmp_path, "x.txt").name == "x (2).txt"


def test_file_over_a_real_encrypted_channel(tmp_path):
    a, b = socket.socketpair()
    ka, kb = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    with ThreadPoolExecutor(1) as pool:
        other = pool.submit(open_channel, b, kb, False, {raw_public(ka)})
        cha, _ = open_channel(a, ka, True, {raw_public(kb)})
        chb, _ = other.result()

    receiver = Files(tmp_path / "in", lambda: None)
    receiver.attach(chb.send, "PC")
    sender = Files(tmp_path / "out", lambda: None)
    sender.attach(cha.send, "NOTE")

    def pump():
        try:
            while True:
                receiver.handle(decode(chb.recv()))
        except OSError:
            pass

    threading.Thread(target=pump, daemon=True).start()
    original = tmp_path / "video.mp4"
    original.write_bytes(os.urandom(2 * 1024 * 1024))
    tid = sender.send_file(original)
    wait_done(sender, tid)
    for _ in range(300):
        if receiver.transfers.get(tid) and receiver.transfers[tid].status == "done":
            break
        time.sleep(0.01)
    assert (tmp_path / "in" / "video.mp4").read_bytes() == original.read_bytes()
    a.close()
    b.close()
