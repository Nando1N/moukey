import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ponte import APP_NAME, backends
from ponte.channel import HandshakeFailed
from ponte.clipboard import Clipboard
from ponte.discovery import Peer, start_discovery
from ponte.keys import config_dir, load_settings, save_settings
from ponte.layout import LayoutPicker
from ponte.net import PORT, is_lan
from ponte.pairing import PairingFailed
from ponte.protocol import BadMessage
from ponte.remote import run_controller, run_receiver
from ponte.session import session

SEARCHING = "procurando computadores na rede..."
READY = "escolha um computador e clique em Conectar"
SIDE_NAMES = {"right": "direita", "left": "esquerda", "top": "de cima", "bottom": "de baixo"}


class App:
    def __init__(self, root: tk.Tk, backend):
        self.root = root
        self.backend = backend
        self.settings = load_settings(config_dir())
        self.sock: socket.socket | None = None  # one connection at a time
        self.peers: list[Peer] = []

        root.title(APP_NAME)
        root.minsize(360, 520)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)

        self.status = tk.StringVar(value=SEARCHING)
        ttk.Label(
            frame, textvariable=self.status, wraplength=320, font=("Segoe UI", 11, "bold")
        ).pack(anchor="w")

        ttk.Label(frame, text="Computadores na rede").pack(anchor="w", pady=(16, 4))
        self.listbox = tk.Listbox(frame, height=4, activestyle="none", exportselection=False)
        self.listbox.pack(fill="x")
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._load_side())

        ttk.Label(frame, text="Arraste o outro computador pra onde ele fica").pack(
            anchor="w", pady=(16, 4)
        )
        self.layout = LayoutPicker(frame, on_change=self._save_side)
        self.layout.pack()

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(16, 0))
        self.connect_btn = ttk.Button(row, text="Conectar", command=self.connect)
        self.connect_btn.pack(side="left", expand=True, fill="x")
        self.stop_btn = ttk.Button(row, text="Desconectar", command=self.disconnect)
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(8, 0))
        self.stop_btn.state(["disabled"])

        ttk.Label(
            frame,
            text="Na primeira vez o Windows pergunta sobre o firewall, clique em Permitir.\n"
            "Se algo travar: Ctrl+Alt+Shift+Esc",
            foreground="#6b7280",
            wraplength=320,
        ).pack(anchor="w", pady=(16, 0))

        self.disco = start_discovery(PORT)
        threading.Thread(target=self._serve, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self._refresh()

    # tkinter only likes being touched from its own thread
    def _ui(self, fn) -> None:
        self.root.after(0, fn)

    def say(self, text: str) -> None:
        self._ui(lambda: self.status.set(text))

    def _selected(self) -> Peer | None:
        idx = self.listbox.curselection()
        return self.peers[idx[0]] if idx else None

    def _refresh(self) -> None:
        peers = self.disco.found()
        if peers != self.peers:
            chosen = self._selected()
            self.peers = peers
            self.listbox.delete(0, "end")
            for p in peers:
                self.listbox.insert("end", f"  {p.name}")
            if chosen in peers:
                self.listbox.selection_set(peers.index(chosen))
            elif len(peers) == 1:
                self.listbox.selection_set(0)
            self._load_side()

        if self.sock is None and self.status.get() in (SEARCHING, READY):
            self.status.set(READY if peers else SEARCHING)
        self.root.after(1000, self._refresh)

    def _load_side(self) -> None:
        peer = self._selected()
        if peer:
            self.layout.set_name(peer.name)
            self.layout.set_side(self.settings.get("sides", {}).get(peer.id, "right"))

    def _save_side(self, side: str) -> None:
        peer = self._selected()
        if peer:
            self.settings.setdefault("sides", {})[peer.id] = side
            save_settings(config_dir(), self.settings)

    def _busy(self, busy: bool) -> None:
        self.connect_btn.state(["disabled"] if busy else ["!disabled"])
        self.stop_btn.state(["!disabled"] if busy else ["disabled"])

    def connect(self) -> None:
        peer = self._selected()
        if peer is None:
            messagebox.showinfo(APP_NAME, "Escolha um computador da lista primeiro.")
            return
        self.status.set(f"conectando em {peer.name}...")
        threading.Thread(target=self._dial, args=(peer, self.layout.side), daemon=True).start()

    def _dial(self, peer: Peer, side: str) -> None:
        try:
            sock = socket.create_connection((peer.host, peer.port), timeout=10)
        except OSError:
            self.say(f"nao consegui falar com {peer.name}. o Ponte ta aberto la?")
            return
        sock.settimeout(None)
        self._run(sock, True, peer.name, side)

    def _serve(self) -> None:
        try:
            server = socket.create_server(("", PORT))
        except OSError:
            self._ui(lambda: messagebox.showerror(APP_NAME, "O Ponte ja esta aberto?"))
            return
        while True:
            sock, (addr, _) = server.accept()
            if not is_lan(addr) or self.sock is not None:
                sock.close()
                continue
            who = next((p.name for p in self.disco.found() if p.host == addr), addr)
            threading.Thread(target=self._run, args=(sock, False, who), daemon=True).start()

    def _run(self, sock: socket.socket, initiator: bool, who: str, side: str = "right") -> None:
        # whoever clicked Conectar is sitting in front of the mouse, so they drive
        self.sock = sock
        self._ui(lambda: self._busy(True))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            confirm = self._show_code if initiator else (lambda code: self._ask(who, code))
            result = session(sock, initiator, confirm)
            if result is None:
                self.say("pareamento recusado")
                return
            ch, name = result
            if initiator:
                self.say(f"conectado com {name}. leve o mouse pra borda {SIDE_NAMES[side]}")
                run_controller(ch, side, self.backend, Clipboard(), say=self.say)
            else:
                self.say(f"{name} esta controlando este computador")
                run_receiver(ch, self.backend, Clipboard(), say=self.say)
            self.say("desconectado")
        except (OSError, HandshakeFailed, PairingFailed, BadMessage):
            self.say("a conexao falhou, tente de novo")
        finally:
            sock.close()
            self.sock = None
            self._ui(lambda: self._busy(False))

    def _show_code(self, code: str) -> bool:
        self.say(f"confira se o codigo {code} apareceu no outro computador e clique Sim la")
        return True

    def _ask(self, who: str, code: str) -> bool:
        answer = {}
        done = threading.Event()

        def ask():
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            answer["ok"] = messagebox.askyesno(
                APP_NAME,
                f"{who} quer usar o mouse e o teclado neste computador.\n\n"
                f"Codigo: {code}\n\n"
                "O mesmo codigo aparece no outro computador?",
            )
            self.root.attributes("-topmost", False)
            done.set()

        self._ui(ask)
        done.wait()
        return answer["ok"]

    def disconnect(self) -> None:
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def quit(self) -> None:
        self.disconnect()
        self.disco.close()
        self.root.destroy()


def main() -> None:
    # load the backend before tk, it sets dpi awareness and the window comes out sharp
    backend = backends.load()
    root = tk.Tk()
    App(root, backend)
    root.mainloop()


if __name__ == "__main__":
    main()
