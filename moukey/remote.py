import queue
import threading

from moukey import edges
from moukey.channel import Channel
from moukey.clipboard import Clipboard, watch
from moukey.protocol import decode, encode


def start_clipboard(clip: Clipboard, send) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=watch, args=(clip, send, stop), daemon=True).start()
    return stop


def run_link(ch: Channel, backend, clip: Clipboard, geo: dict, on_event=None, on_file=None):
    """
    both computers drive each other. our mouse crossing our edge goes over there ("away"),
    their mouse crossing their edge shows up here ("guest").

    geo holds "mine" (our screens), "theirs" (their screens in their own coordinates) and
    "offset" (their point + offset = our point). it can change while we run.
    """
    on_event = on_event or (lambda what: None)
    outbox: queue.Queue[bytes | None] = queue.Queue()
    guest = {"on": False}
    keys: set[str] = set()
    buttons: set[str] = set()

    def on_local_move(x, y) -> bool:
        # while they drive our cursor, our own edges stay quiet
        if guest["on"]:
            return False
        target = edges.cross(geo["mine"], geo["theirs"], geo["offset"], x, y)
        if target is None:
            return False
        cap.grab()
        outbox.put(encode("enter", x=target[0], y=target[1]))
        on_event("away")
        return True

    def on_remote_event(kind, **fields):
        outbox.put(encode(kind, **fields))

    def on_panic():
        if cap.remote:
            cap.release(*cap.park)
            # tell the other side to let go of whatever is still pressed there
            outbox.put(encode("release"))
            on_event("home")

    # the hook thread can't wait on the network, so it drops events here and
    # this thread does the sending
    def sender():
        while (data := outbox.get()) is not None:
            try:
                ch.send(data)
            except OSError:
                return

    # if control leaves while ctrl is held down, ctrl would stay stuck here
    def let_go():
        for k in keys:
            backend.key(k, False)
        for b in buttons:
            backend.button(b, False)
        keys.clear()
        buttons.clear()

    def come_home(x, y):
        rect = edges.inside(geo["mine"], x, y) or geo["mine"][0]
        cap.release(*edges.land(rect, x, y))
        on_event("home")

    cap = backend.Capture(on_local_move, on_remote_event, on_panic)
    cap.start()
    sending = threading.Thread(target=sender, daemon=True)
    sending.start()
    stop_clip = start_clipboard(clip, lambda text: outbox.put(encode("clipboard", text=text)))
    try:
        while True:
            msg = decode(ch.recv())
            kind = msg["t"]
            if kind == "clipboard":
                # not tied to who has the mouse, a copy on either side gets synced
                clip.set(msg["text"])
            elif kind.startswith("file_"):
                if on_file:
                    on_file(msg)
            elif kind == "layout":
                geo["offset"] = (msg["dx"], msg["dy"])
                on_event("layout")
            elif kind == "leave":
                if cap.remote:
                    come_home(msg["x"], msg["y"])
            elif kind == "enter":
                rect = edges.inside(geo["mine"], msg["x"], msg["y"]) or geo["mine"][0]
                backend.move_to(*edges.land(rect, msg["x"], msg["y"]))
                guest["on"] = True
                on_event("guest")
            elif kind == "release":
                let_go()
                if guest["on"]:
                    guest["on"] = False
                    on_event("guest_end")
            elif not guest["on"]:
                # leftovers sent before the other side got our "leave"
                continue
            elif kind == "move":
                backend.move(msg["dx"], msg["dy"])
                x, y = backend.position()
                out = edges.pushing_out(geo["mine"], x, y, msg["dx"], msg["dy"])
                ox, oy = geo["offset"]
                placed = edges.shift(geo["theirs"], ox, oy)
                if out is not None and edges.inside(placed, *out):
                    let_go()
                    guest["on"] = False
                    outbox.put(encode("leave", x=out[0] - ox, y=out[1] - oy))
                    on_event("guest_end")
            elif kind == "button":
                backend.button(msg["button"], msg["down"])
                if msg["down"]:
                    buttons.add(msg["button"])
                else:
                    buttons.discard(msg["button"])
            elif kind == "scroll":
                backend.scroll(msg["dx"], msg["dy"])
            elif kind == "key":
                backend.key(msg["key"], msg["down"])
                if msg["down"]:
                    keys.add(msg["key"])
                else:
                    keys.discard(msg["key"])
    except (ConnectionError, OSError):
        pass
    finally:
        stop_clip.set()
        outbox.put(None)
        # give queued messages (like a last leave) a moment to go out
        sending.join(timeout=1)
        let_go()
        if cap.remote:
            cap.release(*cap.park)
        cap.stop()
