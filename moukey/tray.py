from pathlib import Path

import pystray
from PIL import Image


def start_tray(icon_path: Path, status, on_open, on_pause, on_quit) -> pystray.Icon:
    """the little icon next to the clock, so it's always visible that moukey is running"""
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: status(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Abrir MouKey", lambda: on_open(), default=True),
        pystray.MenuItem("Pausar controle", lambda: on_pause()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", lambda: on_quit()),
    )
    icon = pystray.Icon("moukey", Image.open(icon_path), "MouKey", menu)
    icon.run_detached()
    return icon
