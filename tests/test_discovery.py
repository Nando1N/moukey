import socket

from zeroconf import ServiceInfo

from ponte.discovery import SERVICE, Peer, device_id, peer_from_info


def make_info(ip="192.168.0.20", props=None, port=47474):
    if props is None:
        props = {"id": "abc123", "name": "NOTEBOOK"}
    return ServiceInfo(
        SERVICE,
        f"x.{SERVICE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties=props,
    )


def test_device_id_is_stable():
    assert device_id(b"k" * 32) == device_id(b"k" * 32)
    assert device_id(b"k" * 32) != device_id(b"j" * 32)
    assert len(device_id(b"k" * 32)) == 16


def test_reads_peer():
    assert peer_from_info(make_info()) == Peer("abc123", "NOTEBOOK", "192.168.0.20", 47474)


def test_name_falls_back_to_id():
    assert peer_from_info(make_info(props={"id": "abc123"})).name == "abc123"


def test_ignores_service_without_id():
    assert peer_from_info(make_info(props={"name": "x"})) is None


def test_ignores_public_address():
    assert peer_from_info(make_info(ip="8.8.8.8")) is None
