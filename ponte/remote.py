import queue
import threading

from ponte import edges
from ponte.channel import Channel
from ponte.protocol import decode, encode


def run_controller(ch: Channel, side: str, backend) -> None:
    w, h = backend.screen_size()
    outbox: queue.Queue[bytes | None] = queue.Queue()

    def on_local_move(x, y) -> bool:
        if not edges.crossing(x, w, side):
            return False
        cap.grab()
        outbox.put(encode("enter", y=edges.ratio(y, h), edge=edges.opposite(side)))
        print("controle no outro computador")
        return True

    def on_remote_event(kind, **fields):
        outbox.put(encode(kind, **fields))

    # the hook thread can't wait on the network, so it drops events here and
    # this thread does the sending
    def sender():
        while (data := outbox.get()) is not None:
            try:
                ch.send(data)
            except OSError:
                return

    def panic():
        if cap.remote:
            cap.release(*cap.park)
            print("atalho de emergencia, mouse de volta aqui")

    cap = backend.Capture(on_local_move, on_remote_event)
    cap.start()
    hotkey = backend.emergency_hotkey(panic)
    threading.Thread(target=sender, daemon=True).start()
    try:
        while True:
            msg = decode(ch.recv())
            if msg["t"] == "leave" and cap.remote:
                cap.release(*edges.entry_point(side, msg["y"], w, h))
                print("controle de volta aqui")
    except (ConnectionError, OSError):
        print("conexao caiu, mouse de volta aqui")
    finally:
        outbox.put(None)
        if cap.remote:
            cap.release(*cap.park)
        cap.stop()
        hotkey.stop()


def run_receiver(ch: Channel, backend) -> None:
    w, h = backend.screen_size()
    edge = None  # set while the other side is driving our cursor

    while True:
        try:
            msg = decode(ch.recv())
        except (ConnectionError, OSError):
            print("conexao caiu")
            return

        kind = msg["t"]
        if kind == "enter":
            edge = msg["edge"]
            backend.move_to(*edges.entry_point(edge, msg["y"], w, h))
        elif edge is None:
            # leftovers sent before the other side got our "leave"
            continue
        elif kind == "move":
            backend.move(msg["dx"], msg["dy"])
            x, y = backend.position()
            if edges.leaving(x, msg["dx"], w, edge):
                ch.send(encode("leave", y=edges.ratio(y, h)))
                edge = None
        elif kind == "button":
            backend.button(msg["button"], msg["down"])
        elif kind == "scroll":
            backend.scroll(msg["dx"], msg["dy"])
