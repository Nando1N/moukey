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

    if sys.platform == "darwin":
        from moukey.backends import macos

        # asks for the accessibility permission if it's missing, nothing works without it
        macos.init()
        return macos

    sys.exit("o MouKey funciona no Windows, no Linux com X11 e (experimental) no macOS")
