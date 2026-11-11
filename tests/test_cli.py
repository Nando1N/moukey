import pytest

from ponte import __version__
from ponte.__main__ import main


def test_version_flag(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ponte", "--version"])
    with pytest.raises(SystemExit):
        main()
    assert __version__ in capsys.readouterr().out


def test_runs_without_args(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ponte"])
    main()
    assert "rodando em" in capsys.readouterr().out
