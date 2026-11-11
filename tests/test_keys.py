import os
import sys

import pytest

from ponte.keys import add_peer, load_identity, load_peers, raw_public


def test_identity_is_created_once(tmp_path):
    first = load_identity(tmp_path)
    second = load_identity(tmp_path)
    assert raw_public(first) == raw_public(second)
    assert len((tmp_path / "identity.key").read_bytes()) == 32


@pytest.mark.skipif(sys.platform == "win32", reason="no unix permissions on windows")
def test_identity_file_is_private(tmp_path):
    load_identity(tmp_path)
    assert os.stat(tmp_path / "identity.key").st_mode & 0o777 == 0o600


def test_peers_roundtrip(tmp_path):
    assert load_peers(tmp_path) == {}
    add_peer(tmp_path, b"\x01" * 32, "NOTEBOOK")
    add_peer(tmp_path, b"\x02" * 32, "PC")
    add_peer(tmp_path, b"\x01" * 32, "NOTEBOOK-NOVO")
    assert load_peers(tmp_path) == {b"\x01" * 32: "NOTEBOOK-NOVO", b"\x02" * 32: "PC"}
