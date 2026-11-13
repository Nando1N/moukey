import threading

import pyperclip

# characters, keeps the message well under the 1 MiB frame limit
LIMIT = 300_000


class Clipboard:
    def __init__(self, read=pyperclip.paste, write=pyperclip.copy, on_new=None):
        self.read = read
        self.write = write
        # on_new(text, local) for the history screen. local=False means it came from the other side
        self.on_new = on_new or (lambda text, local: None)
        # whatever was copied before we started isn't news
        self.last = self._read()

    def _read(self) -> str | None:
        try:
            return self.read()
        except pyperclip.PyperclipException:
            # windows refuses while another app has the clipboard open, try next round
            return None

    def poll(self) -> str | None:
        text = self._read()
        if text is None or text == self.last:
            return None
        self.last = text
        if not text or len(text) > LIMIT:
            return None
        self.on_new(text, True)
        return text

    def set(self, text: str) -> None:
        # remember it first, or the next poll would send it right back
        self.last = text
        self.on_new(text, False)
        try:
            self.write(text)
        except pyperclip.PyperclipException:
            pass


def watch(clip: Clipboard, send, stop: threading.Event, every: float = 0.5) -> None:
    # polling is dumb but works the same on every OS, no clipboard events needed
    while not stop.wait(every):
        text = clip.poll()
        if text is not None:
            send(text)
