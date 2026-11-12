import threading

import pyperclip

from moukey.clipboard import LIMIT, Clipboard, watch


class FakeBoard:
    def __init__(self, text=""):
        self.text = text
        self.broken = False

    def read(self):
        if self.broken:
            raise pyperclip.PyperclipException("busy")
        return self.text

    def write(self, text):
        self.text = text


def make(text=""):
    board = FakeBoard(text)
    return board, Clipboard(board.read, board.write)


def test_old_content_is_not_sent():
    _, clip = make("copied yesterday")
    assert clip.poll() is None


def test_new_copy_is_sent_once():
    board, clip = make()
    board.text = "ola"
    assert clip.poll() == "ola"
    assert clip.poll() is None


def test_received_text_is_not_sent_back():
    board, clip = make()
    clip.set("veio do outro pc")
    assert board.text == "veio do outro pc"
    assert clip.poll() is None


def test_huge_text_is_skipped():
    board, clip = make()
    board.text = "x" * (LIMIT + 1)
    assert clip.poll() is None


def test_busy_clipboard_is_retried_later():
    board, clip = make()
    board.text = "depois"
    board.broken = True
    assert clip.poll() is None
    board.broken = False
    assert clip.poll() == "depois"


def test_watch_sends_changes():
    board, clip = make()
    sent = []
    stop = threading.Event()

    def send(text):
        sent.append(text)
        stop.set()

    board.text = "copiei"
    watch(clip, send, stop, every=0.01)
    assert sent == ["copiei"]
