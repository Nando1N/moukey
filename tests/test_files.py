import base64
import hashlib
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


def wait_until(check):
    for _ in range(300):
        if check():
            return
        time.sleep(0.01)
    raise AssertionError("never happened")


def test_copied_files_land_on_the_other_clipboard(tmp_path):
    sender, receiver, out = wired(tmp_path)
    receiver.clip_folder = tmp_path / "copiados"
    got = []
    receiver.on_clip = lambda paths, image: got.append((paths, image))
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("um")
    b.write_text("dois")

    assert sender.send_clip([a, b], image=False)
    wait_until(lambda: got)
    paths, image = got[0]
    assert not image
    assert [Path(p).read_text() for p in paths] == ["um", "dois"]
    # out of the downloads folder, and not listed as transfers once done
    assert not out.exists()
    assert receiver.views() == []


def test_a_normal_file_tells_us_it_arrived(tmp_path):
    sender, receiver, _ = wired(tmp_path)
    arrived = []
    receiver.on_received = arrived.append
    f = tmp_path / "doc.pdf"
    f.write_text("x")
    tid = sender.send_file(f)
    wait_until(lambda: arrived)
    assert arrived[0].name == "doc.pdf"
    assert receiver.path_of(tid).endswith("doc.pdf")


def test_clip_folder_name_cant_escape(tmp_path):
    evil = r"..\..\windows"
    receiver = Files(tmp_path / "dl", lambda: None, tmp_path / "copiados")
    receiver.attach(lambda data: None, "PC")
    receiver.handle(decode(encode("file_clip", ids=[evil], image=False)))
    receiver.handle(decode(encode("file_offer", id=evil, name="x.txt", size=1)))
    t = receiver.transfers[evil]
    assert (tmp_path / "copiados") in Path(t.path).parents
    receiver.detach()


def test_one_bad_piece_drops_the_whole_copy(tmp_path):
    receiver = Files(tmp_path / "dl", lambda: None, tmp_path / "copiados")
    receiver.attach(lambda data: None, "PC")
    got = []
    receiver.on_clip = lambda paths, image: got.append(paths)
    data = base64.b64encode(b"abc").decode()
    receiver.handle(decode(encode("file_clip", ids=["a", "b"], image=False)))
    for tid in ("a", "b"):
        receiver.handle(decode(encode("file_offer", id=tid, name=f"{tid}.txt", size=3)))
        receiver.handle(decode(encode("file_chunk", id=tid, data=data)))
    receiver.handle(decode(encode("file_end", id="a", sha256="0" * 64)))
    receiver.handle(decode(encode("file_end", id="b", sha256=hashlib.sha256(b"abc").hexdigest())))
    assert got == []


def test_invisible_characters_cant_disguise_the_extension():
    assert safe_name("fatura‮fdp.exe") == "faturafdp.exe"


def test_ctrl_c_switched_off_refuses_incoming_pictures_too(tmp_path):
    sent = []
    receiver = Files(tmp_path / "dl", lambda: None, tmp_path / "copiados")
    receiver.attach(sent.append, "PC")
    receiver.accept_clip = False
    got = []
    receiver.on_clip = lambda paths, image: got.append(paths)
    receiver.handle(decode(encode("file_clip", ids=["a"], image=True)))
    receiver.handle(decode(encode("file_offer", id="a", name="print.png", size=3)))
    # refused, and it didn't sneak into the downloads folder as a normal file
    assert decode(sent[-1]) == {"t": "file_cancel", "id": "a"}
    assert "a" not in receiver.transfers
    assert not (tmp_path / "dl").exists()


def test_receiver_enforces_the_ctrl_c_limit(tmp_path):
    receiver = Files(tmp_path / "dl", lambda: None, tmp_path / "copiados")
    receiver.attach(lambda d: None, "PC")
    receiver.handle(decode(encode("file_clip", ids=["a"], image=False)))
    receiver.handle(decode(encode("file_offer", id="a", name="x.bin", size=300 * 1024**2)))
    assert receiver.transfers["a"].status == "error"


def test_too_many_files_at_once_are_refused(tmp_path):
    receiver = Files(tmp_path / "dl", lambda: None)
    receiver.attach(lambda d: None, "PC")
    for i in range(25):
        receiver.handle(decode(encode("file_offer", id=f"f{i}", name=f"{i}.txt", size=10)))
    refused = [t for t in receiver.transfers.values() if t.status == "error"]
    assert len(refused) == 5
    receiver.detach()


def test_offers_that_together_dont_fit_are_refused(tmp_path, monkeypatch):
    receiver = Files(tmp_path / "dl", lambda: None)
    receiver.attach(lambda d: None, "PC")
    free = 1024**3
    monkeypatch.setattr("moukey.files.shutil.disk_usage", lambda p: type("U", (), {"free": free})())
    receiver.handle(decode(encode("file_offer", id="a", name="a.bin", size=600 * 1024**2)))
    receiver.handle(decode(encode("file_offer", id="b", name="b.bin", size=600 * 1024**2)))
    assert receiver.transfers["a"].status == "active"
    assert receiver.transfers["b"].status == "error"
    receiver.detach()


def test_rest_of_a_too_big_copy_doesnt_land_in_downloads(tmp_path):
    sent = []
    receiver = Files(tmp_path / "dl", lambda: None, tmp_path / "copiados")
    receiver.attach(sent.append, "PC")
    receiver.handle(decode(encode("file_clip", ids=["a", "b"], image=False)))
    receiver.handle(decode(encode("file_offer", id="a", name="a.bin", size=300 * 1024**2)))
    receiver.handle(decode(encode("file_offer", id="b", name="b.bin", size=10)))
    assert "b" not in receiver.transfers
    assert decode(sent[-1]) == {"t": "file_cancel", "id": "b"}
    assert not (tmp_path / "dl").exists()


def test_history_doesnt_grow_forever(tmp_path):
    receiver = Files(tmp_path / "dl", lambda: None)
    receiver.attach(lambda d: None, "PC")
    for i in range(400):
        tid = f"f{i}"
        receiver.handle(decode(encode("file_offer", id=tid, name=f"{i}.txt", size=0)))
        receiver.handle(decode(encode("file_end", id=tid, sha256=hashlib.sha256(b"").hexdigest())))
    assert len(receiver.transfers) <= 301


def test_hanging_up_forgets_refused_copies(tmp_path):
    receiver = Files(tmp_path / "dl", lambda: None)
    receiver.attach(lambda d: None, "PC")
    receiver.accept_clip = False
    receiver.handle(decode(encode("file_clip", ids=["a", "b"], image=False)))
    receiver.detach()
    assert receiver._refused == set()
