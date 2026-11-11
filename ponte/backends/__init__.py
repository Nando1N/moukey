import sys


def load():
    if sys.platform == "win32":
        from ponte.backends import windows

        windows.init()
        return windows
    # TODO: linux (x11 with pynput, wayland with evdev) and macos
    sys.exit("por enquanto o ponte so funciona no windows. linux ta no roadmap")
