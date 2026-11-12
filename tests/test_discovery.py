import socket

import pytest
from zeroconf import ServiceInfo

from ponte.discovery import (
    BEACON_TTL,
    SERVICE,
    Peer,
    alive,
    broadcast_targets,
    device_id,
    make_beacon,
    parse_beacon,
    peer_from_info,
)


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


def test_beacon_roundtrip():
    data = make_beacon("abc123", "NOTEBOOK", 47474)
    assert parse_beacon(data, "192.168.0.20", "me") == Peer(
        "abc123", "NOTEBOOK", "192.168.0.20", 47474
    )


def test_beacon_from_myself_is_ignored():
    assert parse_beacon(make_beacon("me", "PC", 47474), "192.168.0.10", "me") is None


@pytest.mark.parametrize(
    "data",
    [
        b"lixo",
        b"\xff\xfe",
        b"[]",
        b'{"ponte":2,"id":"x","name":"a","port":1}',
        b'{"ponte":1,"name":"a","port":1}',
        b'{"ponte":1,"id":"x","name":"a","port":true}',
        b'{"ponte":1,"id":"x","name":"a","port":70000}',
    ],
)
def test_bad_beacons_are_ignored(data):
    assert parse_beacon(data, "192.168.0.20", "me") is None


def test_beacon_from_the_internet_is_ignored():
    assert parse_beacon(make_beacon("x", "a", 47474), "8.8.8.8", "me") is None


def test_quiet_machines_disappear():
    a = Peer("a", "A", "192.168.0.2", 1)
    b = Peer("b", "B", "192.168.0.3", 1)
    heard = {"a": (a, 100.0), "b": (b, 100.0 - BEACON_TTL - 1)}
    assert alive(heard, 100.0) == [a]


def test_broadcast_targets():
    assert broadcast_targets("192.168.0.42") == ["255.255.255.255", "192.168.0.255"]
    assert broadcast_targets("127.0.0.1") == ["255.255.255.255"]
