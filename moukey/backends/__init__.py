import os
import sys


def load():
    if sys.platform == "win32":
        from moukey.backends import windows

        windows.init()
        return windows

    if sys.platform.startswith("linux"):
        # wayland sessions still set DISPLAY for old apps (xwayland), but fake input
        # through it never reaches the real desktop, so look at the session type
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            sys.exit(
                "o MouKey ainda nao funciona no Wayland. na tela de login, escolha a sessao "
                "'Xorg' (ou 'Ubuntu on Xorg') e abra de novo"
            )
        from moukey.backends import linux_x11

        return linux_x11

    # TODO: macos with pynput and the accessibility permission
    sys.exit("por enquanto o MouKey funciona no Windows e no Linux com X11")
