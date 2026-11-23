import socket
import threading

import pytest

from moukey import session as session_mod
from moukey.discovery import device_id
from moukey.keys import load_identity, raw_public
from moukey.pairing import PairingFailed

SCREENS = [(0, 0, 1920, 1080)]


@pytest.fixture
def two_computers(tmp_path, monkeypatch):
    """each side gets its own config folder, like two real machines"""
    folders = {"pc": tmp_path / "pc", "note": tmp_path / "note"}
    who = threading.local()
    monkeypatch.setattr(session_mod, "config_dir", lambda: folders[who.name])
    return folders, who


def run_both(who, pc_kwargs, note_kwargs):
    a, b = socket.socketpair()
    a.settimeout(5)
    b.settimeout(5)
    out = {}

    def side(name, sock, initiator, kwargs):
        who.name = name
        try:
            out[name] = session_mod.session(sock, initiator, screens=SCREENS, **kwargs)
        except (PairingFailed, OSError, ConnectionError) as e:
            out[name] = e
        finally:
            sock.close()

    t = threading.Thread(target=side, args=("note", b, False, note_kwargs))
    t.start()
    side("pc", a, True, pc_kwargs)
    t.join(5)
    return out


def test_the_one_who_dials_also_has_to_confirm(two_computers):
    _, who = two_computers
    asked = []
    out = run_both(
        who,
        {"confirm": lambda code: asked.append(code) or False},
        {"confirm": lambda code: True},
    )
    # the stranger said yes on his side, but we didn't, so nothing got paired
    assert len(asked) == 1 and len(asked[0]) == 6
    assert out["pc"] is None


def test_both_confirm_and_they_pair(two_computers):
    folders, who = two_computers
    out = run_both(who, {"confirm": lambda c: True}, {"confirm": lambda c: True})
    note_key = raw_public(load_identity(folders["note"]))
    assert out["pc"].peer_id == device_id(note_key)
    assert out["note"].peer_id == device_id(raw_public(load_identity(folders["pc"])))


def test_reconnecting_on_its_own_never_pairs(two_computers):
    _, who = two_computers
    asked = []
    out = run_both(
        who,
        {"confirm": lambda c: True, "allow_pairing": False},
        {"confirm": lambda c: asked.append(c) or True},
    )
    assert isinstance(out["pc"], PairingFailed)
    assert asked == []


def test_a_stranger_using_the_id_of_our_notebook_is_refused(two_computers):
    _, who = two_computers
    asked = []
    out = run_both(
        who,
        # the id we clicked belongs to another key than the one that answered
        {"confirm": lambda c: asked.append(c) or True, "expected_id": "0123456789abcdef"},
        {"confirm": lambda c: True},
    )
    assert isinstance(out["pc"], PairingFailed)
    assert asked == []
