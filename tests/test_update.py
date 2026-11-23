import hashlib
import io
import json

import pytest

from moukey import update

EXE = b"MZ fake exe"
GOOD = hashlib.sha256(EXE).hexdigest()


class FakeResp(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_github(monkeypatch, files, redirect=None):
    """files: url -> bytes. redirect: where every request 'lands'"""
    seen = []

    def urlopen(req, timeout=0):
        url = req.full_url
        seen.append(url)
        return FakeResp(files[url], redirect or url)

    monkeypatch.setattr(update.urllib.request, "urlopen", urlopen)
    return seen


def release(tag, assets=True):
    base = f"https://github.com/Nando1N/moukey/releases/download/{tag}"
    info = {"tag_name": tag, "assets": []}
    if assets:
        info["assets"] = [
            {"name": "MouKey.exe", "browser_download_url": f"{base}/MouKey.exe"},
            {"name": "MouKey.exe.sha256", "browser_download_url": f"{base}/MouKey.exe.sha256"},
        ]
    return json.dumps(info).encode()


@pytest.mark.parametrize(
    "latest, current, newer",
    [
        ("v0.3.0", "0.2.2", True),
        ("v0.2.10", "0.2.9", True),
        ("v0.2.2", "0.2.2", False),
        ("v0.2.1", "0.2.2", False),
        ("nightly", "0.2.2", False),
    ],
)
def test_only_newer_versions_count(latest, current, newer):
    assert update.is_newer(latest, current) is newer


def test_finds_a_newer_release(monkeypatch):
    fake_github(monkeypatch, {update.LATEST: release("v99.0.0")})
    found = update.check()
    assert found["version"] == "99.0.0"
    assert found["exe"].endswith("/v99.0.0/MouKey.exe")


def test_same_or_older_release_is_nothing_to_do(monkeypatch):
    fake_github(monkeypatch, {update.LATEST: release("v0.0.1")})
    assert update.check() is None


def test_no_internet_is_not_an_error(monkeypatch):
    def offline(req, timeout=0):
        raise OSError("no route")

    monkeypatch.setattr(update.urllib.request, "urlopen", offline)
    assert update.check() is None


def test_downloads_and_checks_the_hash(monkeypatch, tmp_path):
    base = "https://github.com/Nando1N/moukey/releases/download/v99.0.0"
    found = {"version": "99.0.0", "exe": f"{base}/MouKey.exe", "sha": f"{base}/MouKey.exe.sha256"}
    fake_github(
        monkeypatch,
        {found["exe"]: EXE, found["sha"]: f"{GOOD}  MouKey.exe\n".encode()},
        redirect="https://release-assets.githubusercontent.com/x",
    )
    path = update.download(found, tmp_path)
    assert path.read_bytes() == EXE


def test_tampered_exe_is_refused(monkeypatch, tmp_path):
    base = "https://github.com/Nando1N/moukey/releases/download/v99.0.0"
    found = {"version": "99.0.0", "exe": f"{base}/MouKey.exe", "sha": f"{base}/MouKey.exe.sha256"}
    fake_github(monkeypatch, {found["exe"]: b"something else", found["sha"]: GOOD.encode()})
    with pytest.raises(ValueError):
        update.download(found, tmp_path)
    assert not list(tmp_path.iterdir())


def test_never_downloads_from_outside_github(monkeypatch, tmp_path):
    found = {
        "version": "99.0.0",
        "exe": "https://evil.example/MouKey.exe",
        "sha": "https://evil.example/h",
    }
    seen = fake_github(monkeypatch, {})
    with pytest.raises(ValueError):
        update.download(found, tmp_path)
    assert seen == []


def test_redirect_away_from_github_is_refused(monkeypatch, tmp_path):
    base = "https://github.com/Nando1N/moukey/releases/download/v99.0.0"
    found = {"version": "99.0.0", "exe": f"{base}/MouKey.exe", "sha": f"{base}/MouKey.exe.sha256"}
    fake_github(
        monkeypatch,
        {found["exe"]: EXE, found["sha"]: GOOD.encode()},
        redirect="https://evil.example/file",
    )
    with pytest.raises(ValueError):
        update.download(found, tmp_path)


def test_plain_http_is_refused(monkeypatch, tmp_path):
    found = {"version": "9", "exe": "http://github.com/a", "sha": "http://github.com/b"}
    with pytest.raises(ValueError):
        update.download(found, tmp_path)


def test_release_without_assets_cant_be_installed(monkeypatch, tmp_path):
    fake_github(monkeypatch, {update.LATEST: release("v99.0.0", assets=False)})
    found = update.check()
    with pytest.raises(ValueError):
        update.download(found, tmp_path)


def test_install_swaps_the_exe_and_starts_the_new_one(monkeypatch, tmp_path):
    current = tmp_path / "MouKey.exe"
    current.write_bytes(b"old")
    new = tmp_path / "baixado.exe"
    new.write_bytes(b"new")
    started = []
    monkeypatch.setattr(update.sys, "executable", str(current))
    monkeypatch.setattr(update.subprocess, "Popen", lambda args, **kw: started.append(args))
    update.install(new)
    assert current.read_bytes() == b"new"
    assert (tmp_path / "MouKey.antigo.exe").read_bytes() == b"old"
    assert started == [[str(current), update.AFTER_UPDATE]]


def test_old_exe_is_cleaned_up_later(monkeypatch, tmp_path):
    current = tmp_path / "MouKey.exe"
    current.write_bytes(b"new")
    (tmp_path / "MouKey.antigo.exe").write_bytes(b"old")
    monkeypatch.setattr(update.sys, "executable", str(current))
    monkeypatch.setattr(update, "can_install", lambda: True)
    update.clean_old()
    assert not (tmp_path / "MouKey.antigo.exe").exists()
