import threading

import pyperclip

# characters, keeps the message well under the 1 MiB frame limit
LIMIT = 300_000
# a picture or file list that can't be read after this many tries is given up on
TRIES = 3


class Clipboard:
    """
    notices what was copied here and puts on the clipboard what came from the other side.

    text works everywhere through pyperclip. images and files need a backend that knows
    the OS clipboard (clip_seq, clip_kind, read_*, write_*), without one it's text only.
    poll() gives ("text", str), ("image", PIL image) or ("files", [paths]).
    """

    def __init__(self, read=pyperclip.paste, write=pyperclip.copy, on_new=None, rich=None):
        self.read = read
        self.write = write
        # on_new(kind, value, local) for the history screen. local=False means it came from
        # the other side
        self.on_new = on_new or (lambda kind, value, local: None)
        self.rich = rich
        self.tries = 0
        # whatever was copied before we started isn't news
        self.seq = rich.clip_seq() if rich else None
        self.last = self._read()

    def _read(self) -> str | None:
        try:
            return self.read()
        except pyperclip.PyperclipException:
            # windows refuses while another app has the clipboard open, try next round
            return None

    def poll(self):
        if self.rich:
            seq = self.rich.clip_seq()
            if seq == self.seq:
                return None
            kind = self.rich.clip_kind()
            if kind in ("files", "image"):
                value = self.rich.read_files() if kind == "files" else self.rich.read_image()
                if value is None:
                    self.tries += 1
                    if self.tries >= TRIES:
                        self.seq, self.tries = seq, 0
                    return None
                self.seq, self.tries = seq, 0
                self.on_new(kind, value, True)
                return kind, value
        text = self._read()
        if text is None:
            return None
        if self.rich:
            self.seq = self.rich.clip_seq()
        if text == self.last:
            return None
        self.last = text
        if not text or len(text) > LIMIT:
            return None
        self.on_new("text", text, True)
        return "text", text

    def _mine(self) -> None:
        # remember what we just wrote, or the next poll would send it right back
        if self.rich:
            self.seq = self.rich.clip_seq()

    def set(self, text: str) -> None:
        self.last = text
        self.on_new("text", text, False)
        try:
            self.write(text)
        except pyperclip.PyperclipException:
            pass
        self._mine()

    def set_image(self, path) -> None:
        self.on_new("image", path, False)
        if self.rich:
            self.rich.write_image(path)
            self._mine()

    def set_files(self, paths: list[str]) -> None:
        self.on_new("files", paths, False)
        if self.rich:
            self.rich.write_files(paths)
            self._mine()


def watch(clip: Clipboard, send, stop: threading.Event, every: float = 0.5) -> None:
    # polling is dumb but works the same on every OS. on windows it's only a counter check
    while not stop.wait(every):
        got = clip.poll()
        if got is not None:
            send(*got)
