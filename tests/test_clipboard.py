import threading

import pyperclip

from moukey.clipboard import LIMIT, TRIES, Clipboard, watch


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


class FakeRich:
    """the OS clipboard with pictures and files, like the windows backend"""

    def __init__(self, board):
        self.board = board
        self.seq = 1
        self.kind = "text"
        self.value = None
        self.busy = False
        self.written = []

    def copy(self, kind, value=None):
        self.seq += 1
        self.kind = kind
        self.value = value
        if kind == "text":
            self.board.text = value

    def clip_seq(self):
        return self.seq

    def clip_kind(self):
        return self.kind

    def read_files(self):
        return None if self.busy else self.value

    def read_image(self):
        return None if self.busy else self.value

    def write_image(self, path):
        self.written.append(("image", path))
        self.copy("image", "picture")

    def write_files(self, paths):
        self.written.append(("files", paths))
        self.copy("files", paths)


def make(text=""):
    board = FakeBoard(text)
    return board, Clipboard(board.read, board.write)


def make_rich(text=""):
    board = FakeBoard(text)
    rich = FakeRich(board)
    heard = []
    clip = Clipboard(board.read, board.write, lambda *a: heard.append(a), rich)
    return rich, clip, heard


def test_old_content_is_not_sent():
    _, clip = make("copied yesterday")
    assert clip.poll() is None


def test_new_copy_is_sent_once():
    board, clip = make()
    board.text = "ola"
    assert clip.poll() == ("text", "ola")
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
    assert clip.poll() == ("text", "depois")


def test_watch_sends_changes():
    board, clip = make()
    sent = []
    stop = threading.Event()

    def send(kind, value):
        sent.append((kind, value))
        stop.set()

    board.text = "copiei"
    watch(clip, send, stop, every=0.01)
    assert sent == [("text", "copiei")]


def test_history_hears_both_directions():
    board = FakeBoard()
    heard = []
    clip = Clipboard(board.read, board.write, on_new=lambda *args: heard.append(args))
    board.text = "copiei aqui"
    clip.poll()
    clip.set("veio de la")
    clip.poll()
    assert heard == [("text", "copiei aqui", True), ("text", "veio de la", False)]


def test_a_print_goes_as_a_picture():
    rich, clip, _ = make_rich()
    rich.copy("image", "print")
    assert clip.poll() == ("image", "print")
    assert clip.poll() is None


def test_copied_files_go_as_files():
    rich, clip, _ = make_rich()
    rich.copy("files", [r"C:\a.pdf", r"C:\b.png"])
    assert clip.poll() == ("files", [r"C:\a.pdf", r"C:\b.png"])


def test_text_still_works_with_the_rich_clipboard():
    rich, clip, _ = make_rich()
    rich.copy("text", "oi")
    assert clip.poll() == ("text", "oi")
    assert clip.poll() is None


def test_received_picture_and_files_are_not_sent_back():
    rich, clip, heard = make_rich()
    clip.set_image("recebida.png")
    assert clip.poll() is None
    clip.set_files(["x.zip"])
    assert clip.poll() is None
    assert rich.written == [("image", "recebida.png"), ("files", ["x.zip"])]
    assert heard == [("image", "recebida.png", False), ("files", ["x.zip"], False)]


def test_busy_picture_is_retried_then_given_up():
    rich, clip, _ = make_rich()
    rich.copy("image", "print")
    rich.busy = True
    for _ in range(TRIES):
        assert clip.poll() is None
    rich.busy = False
    # gave up on that copy, it isn't sent late out of nowhere
    assert clip.poll() is None
    rich.copy("image", "outro print")
    assert clip.poll() == ("image", "outro print")


def test_busy_picture_comes_through_on_retry():
    rich, clip, _ = make_rich()
    rich.copy("image", "print")
    rich.busy = True
    assert clip.poll() is None
    rich.busy = False
    assert clip.poll() == ("image", "print")


def test_same_print_put_twice_goes_once():
    # the snipping tool writes the same picture to the clipboard twice
    rich, clip, _ = make_rich()
    rich.copy("image", "print")
    assert clip.poll() == ("image", "print")
    rich.copy("image", "print")
    assert clip.poll() is None


def test_same_print_after_something_else_goes_again():
    rich, clip, _ = make_rich()
    rich.copy("image", "print")
    clip.poll()
    rich.copy("text", "oi")
    clip.poll()
    rich.copy("image", "print")
    assert clip.poll() == ("image", "print")


def test_same_files_copied_twice_go_once():
    rich, clip, _ = make_rich()
    rich.copy("files", ["a.pdf"])
    assert clip.poll() == ("files", ["a.pdf"])
    rich.copy("files", ["a.pdf"])
    assert clip.poll() is None
    rich.copy("files", ["a.pdf", "b.pdf"])
    assert clip.poll() == ("files", ["a.pdf", "b.pdf"])
