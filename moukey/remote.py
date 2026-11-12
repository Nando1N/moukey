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


def run_controller(
    ch: Channel, side: str, backend, clip: Clipboard, say=print, on_mouse=None
) -> None:
    # on_mouse(True) when the cursor goes to the other computer, False when it comes back
    on_mouse = on_mouse or (lambda away: None)
    w, h = backend.screen_size()
    outbox: queue.Queue[bytes | None] = queue.Queue()

    def on_local_move(x, y) -> bool:
        if not edges.crossing(x, y, w, h, side):
            return False
        cap.grab()
        at = edges.along(x, y, w, h, side)
        outbox.put(encode("enter", at=at, edge=edges.opposite(side)))
        say("controle no outro computador")
        on_mouse(True)
        return True

    def on_remote_event(kind, **fields):
        outbox.put(encode(kind, **fields))

    def on_panic():
        if cap.remote:
            cap.release(*cap.park)
            # tell the other side to let go of whatever is still pressed there
            outbox.put(encode("leave", at=0.5))
            say("atalho de emergencia, controle de volta aqui")
            on_mouse(False)

    # the hook thread can't wait on the network, so it drops events here and
    # this thread does the sending
    def sender():
        while (data := outbox.get()) is not None:
            try:
                ch.send(data)
            except OSError:
                return

    cap = backend.Capture(on_local_move, on_remote_event, on_panic)
    cap.start()
    threading.Thread(target=sender, daemon=True).start()
    stop_clip = start_clipboard(clip, lambda text: outbox.put(encode("clipboard", text=text)))
    try:
        while True:
            msg = decode(ch.recv())
            if msg["t"] == "leave" and cap.remote:
                cap.release(*edges.entry_point(side, msg["at"], w, h))
                say("controle de volta aqui")
                on_mouse(False)
            elif msg["t"] == "clipboard":
                clip.set(msg["text"])
    except (ConnectionError, OSError):
        say("conexao caiu, controle de volta aqui")
    finally:
        stop_clip.set()
        outbox.put(None)
        if cap.remote:
            cap.release(*cap.park)
        cap.stop()


def run_receiver(ch: Channel, backend, clip: Clipboard, say=print) -> None:
    w, h = backend.screen_size()
    edge = None  # set while the other side is driving our cursor
    keys: set[str] = set()
    buttons: set[str] = set()

    # if control leaves while ctrl is held down, ctrl would stay stuck here
    def let_go():
        for k in keys:
            backend.key(k, False)
        for b in buttons:
            backend.button(b, False)
        keys.clear()
        buttons.clear()

    def send_clip(text):
        try:
            ch.send(encode("clipboard", text=text))
        except OSError:
            pass

    stop_clip = start_clipboard(clip, send_clip)

    while True:
        try:
            msg = decode(ch.recv())
        except (ConnectionError, OSError):
            stop_clip.set()
            let_go()
            say("conexao caiu")
            return

        kind = msg["t"]
        if kind == "clipboard":
            # not tied to who has the mouse, a copy on either side gets synced
            clip.set(msg["text"])
        elif kind == "enter":
            edge = msg["edge"]
            backend.move_to(*edges.entry_point(edge, msg["at"], w, h))
        elif kind == "leave":
            let_go()
            edge = None
        elif edge is None:
            # leftovers sent before the other side got our "leave"
            continue
        elif kind == "move":
            backend.move(msg["dx"], msg["dy"])
            x, y = backend.position()
            if edges.leaving(x, y, msg["dx"], msg["dy"], w, h, edge):
                let_go()
                ch.send(encode("leave", at=edges.along(x, y, w, h, edge)))
                edge = None
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
