import pytest

from moukey.net import is_lan, local_ip


@pytest.mark.parametrize("addr", ["192.168.0.10", "10.0.0.5", "172.16.3.4", "169.254.1.1", "::1"])
def test_lan_addresses(addr):
    assert is_lan(addr)


@pytest.mark.parametrize("addr", ["8.8.8.8", "200.147.67.142"])
def test_internet_addresses(addr):
    assert not is_lan(addr)


def test_local_ip_looks_like_an_ip():
    assert local_ip().count(".") == 3
