import pytest

from moukey import __version__
from moukey.__main__ import main


def test_version_flag(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["moukey", "--version"])
    with pytest.raises(SystemExit):
        main()
    assert __version__ in capsys.readouterr().out


def test_listen_accepts_all_four_sides(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["moukey", "listen", "--help"])
    with pytest.raises(SystemExit):
        main()
    out = capsys.readouterr().out
    for side in ("right", "left", "top", "bottom"):
        assert side in out
