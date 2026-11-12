import sys


def load():
    if sys.platform == "win32":
        from moukey.backends import windows

        windows.init()
        return windows
    # TODO: linux (x11 with pynput, wayland with evdev) and macos
    sys.exit("por enquanto o moukey so funciona no windows. linux ta no roadmap")
