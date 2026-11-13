from moukey.core import auto_target
from moukey.discovery import Peer

NOTE = Peer("aaa", "NOTEBOOK", "192.168.0.20", 47474)
OTHER = Peer("bbb", "OUTRO", "192.168.0.30", 47474)


def test_reconnects_to_the_remembered_peer():
    assert auto_target("aaa", [OTHER, NOTE], busy=False, paused=False) == NOTE


def test_nothing_remembered_means_no_reconnect():
    assert auto_target(None, [NOTE], busy=False, paused=False) is None


def test_waits_until_the_peer_shows_up():
    assert auto_target("aaa", [OTHER], busy=False, paused=False) is None


def test_not_while_connected_or_after_disconnect_button():
    assert auto_target("aaa", [NOTE], busy=True, paused=False) is None
    assert auto_target("aaa", [NOTE], busy=False, paused=True) is None


def test_only_the_smaller_id_dials_on_its_own():
    # NOTE has id "aaa". a computer with a bigger id waits to be called
    assert auto_target("aaa", [NOTE], busy=False, paused=False, my_id="zzz") is None
    assert auto_target("aaa", [NOTE], busy=False, paused=False, my_id="000") == NOTE
