from moukey import edges
from moukey.clipboard import Clipboard
from moukey.protocol import decode, encode
from moukey.remote import run_link

PC = [(0, 0, 3440, 1440), (-1920, 0, 1920, 1080)]
NOTE = [(0, 0, 1920, 1080)]


class FakeChannel:
    def __init__(self, incoming, before_each=None):
        self.incoming = [encode(kind, **fields) for kind, fields in incoming]
        self.before_each = before_each
        self.sent = []

    def recv(self):
        if self.before_each:
            self.before_each()
        if not self.incoming:
            raise ConnectionError
        return self.incoming.pop(0)

    def send(self, data):
        self.sent.append(decode(data))


class FakeCapture:
    last = None

    def __init__(self, on_local_move, on_remote_event, on_panic):
        self.on_local_move = on_local_move
        self.on_panic = on_panic
        self.remote = False
        self.park = (1720, 720)
        self.released_at = None
        FakeCapture.last = self

    def start(self):
        pass

    def stop(self):
        pass

    def grab(self):
        self.remote = True

    def release(self, x, y):
        self.remote = False
        self.released_at = (x, y)


class FakeDesk:
    """the computer we're on, with the screens of the notebook"""

    Capture = FakeCapture

    def __init__(self, screens=NOTE):
        self.screens = screens
        self.x, self.y = 0, 0
        self.calls = []

    def position(self):
        return self.x, self.y

    def move_to(self, x, y):
        self.x, self.y = x, y

    def move(self, dx, dy):
        # clamp like a real screen does
        rx, ry, rw, rh = edges.inside(self.screens, self.x, self.y) or self.screens[0]
        self.x = min(max(self.x + dx, rx), rx + rw - 1)
        self.y = min(max(self.y + dy, ry), ry + rh - 1)

    def button(self, name, down):
        self.calls.append(("button", name, down))

    def scroll(self, dx, dy):
        self.calls.append(("scroll", dx, dy))

    def key(self, name, down):
        self.calls.append(("key", name, down))


def quiet_clip(board=None):
    board = board if board is not None else {"text": ""}
    return Clipboard(lambda: board["text"], lambda t: board.update(text=t))


def note_geo():
    # on the notebook: the pc sits to the left
    offset = edges.place(NOTE, PC, "left")
    return {"mine": NOTE, "theirs": PC, "offset": offset}


def run(incoming, desk=None, geo=None, events=None, before_each=None):
    desk = desk or FakeDesk()
    ch = FakeChannel(incoming, before_each)
    seen = events if events is not None else []
    run_link(ch, desk, quiet_clip(), geo or note_geo(), on_event=seen.append)
    return ch, desk, seen


def test_guest_cursor_lands_where_it_was_sent():
    _, desk, seen = run([("enter", {"x": 2, "y": 520})])
    assert (desk.x, desk.y) == (2, 520)
    assert seen[0] == "guest"


def test_clicks_and_keys_only_while_guest():
    _, desk, _ = run(
        [
            ("button", {"button": "left", "down": True}),
            ("enter", {"x": 2, "y": 0}),
            ("key", {"key": "ctrl_l", "down": True}),
            ("key", {"key": "c", "down": True}),
            ("key", {"key": "c", "down": False}),
            ("scroll", {"dx": 0, "dy": -1}),
        ]
    )
    assert desk.calls[:4] == [
        ("key", "ctrl_l", True),
        ("key", "c", True),
        ("key", "c", False),
        ("scroll", 0, -1),
    ]
    # ctrl was still down when the link ended, it gets released
    assert desk.calls[-1] == ("key", "ctrl_l", False)


def test_release_lets_go_of_everything():
    _, desk, seen = run(
        [
            ("enter", {"x": 2, "y": 500}),
            ("key", {"key": "shift_l", "down": True}),
            ("button", {"button": "left", "down": True}),
            ("release", {}),
        ]
    )
    assert ("key", "shift_l", False) in desk.calls
    assert ("button", "left", False) in desk.calls
    assert "guest_end" in seen


def test_guest_goes_back_through_the_edge_it_came_from():
    geo = note_geo()
    ch, desk, seen = run(
        [
            ("enter", {"x": 2, "y": 520}),
            ("move", {"dx": -10, "dy": 0}),
            ("move", {"dx": -5, "dy": 0}),
            ("move", {"dx": 300, "dy": 0}),  # arrives late, must be ignored
        ],
        geo=geo,
    )
    leave = [m for m in ch.sent if m["t"] == "leave"]
    assert len(leave) == 1
    # back on the pc, in pc coordinates: right edge of the ultrawide
    assert (leave[0]["x"], leave[0]["y"]) == (3439, 700)
    assert desk.x == 0
    assert seen[-1] == "guest_end"


def test_our_mouse_crosses_and_comes_back():
    geo = {"mine": PC, "theirs": NOTE, "offset": edges.place(PC, NOTE, "right")}

    def poke():
        cap = FakeCapture.last
        if cap is not None and not cap.remote and cap.released_at is None:
            assert cap.on_local_move(3439, 700) is True

    ch, _, seen = run([("leave", {"x": 3439, "y": 700})], FakeDesk(PC), geo, before_each=poke)
    enter = [m for m in ch.sent if m["t"] == "enter"]
    assert (enter[0]["x"], enter[0]["y"]) == (2, 520)
    assert FakeCapture.last.released_at == (3437, 700)
    assert seen == ["away", "home"]


def test_no_crossing_on_an_edge_without_a_neighbour():
    geo = {"mine": PC, "theirs": NOTE, "offset": edges.place(PC, NOTE, "right")}
    hits = []

    def poke():
        hits.append(FakeCapture.last.on_local_move(3439, 50))

    run([], FakeDesk(PC), geo, before_each=poke)
    assert hits == [False]


def test_layout_message_moves_the_other_computer():
    geo = note_geo()
    _, _, seen = run([("layout", {"dx": 5, "dy": 6})], geo=geo)
    assert geo["offset"] == (5, 6)
    assert seen == ["layout"]


def test_clipboard_is_applied_even_without_the_mouse():
    board = {"text": ""}
    ch = FakeChannel([("clipboard", {"text": "senha do wifi"})])
    run_link(ch, FakeDesk(), quiet_clip(board), note_geo())
    assert board["text"] == "senha do wifi"
