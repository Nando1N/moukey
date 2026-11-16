import ctypes
import io
import struct
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageGrab

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

CF_BITMAP = 2
CF_DIB = 8
CF_UNICODETEXT = 13
CF_HDROP = 15
CF_DIBV5 = 17
GMEM_MOVEABLE = 0x0002


def clip_seq() -> int:
    # bumps on every change, so we only look inside when something was actually copied
    return user32.GetClipboardSequenceNumber()


def clip_kind() -> str | None:
    has = user32.IsClipboardFormatAvailable
    # files first, then text. excel and word also put a picture of what you copied,
    # but people expect the text there, so the picture only counts when it's alone
    if has(CF_HDROP):
        return "files"
    if has(CF_UNICODETEXT):
        return "text"
    if has(CF_DIB) or has(CF_DIBV5) or has(CF_BITMAP):
        return "image"
    return None


def _grab():
    try:
        return ImageGrab.grabclipboard()
    except OSError:
        # another app has the clipboard open, try on the next round
        return None


def read_files() -> list[str] | None:
    got = _grab()
    return got if isinstance(got, list) else None


def read_image() -> Image.Image | None:
    got = _grab()
    return got if isinstance(got, Image.Image) else None


def _put(formats: list[tuple[int, bytes]]) -> bool:
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        for fmt, data in formats:
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            ptr = kernel32.GlobalLock(handle)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            # after SetClipboardData the memory belongs to windows, only free it if that failed
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
        return True
    finally:
        user32.CloseClipboard()


def write_image(path: Path) -> bool:
    img = Image.open(path)
    bmp = io.BytesIO()
    img.convert("RGB").save(bmp, "BMP")
    # a DIB is a .bmp without its 14 byte file header. png goes along for the apps
    # that keep transparency
    png = user32.RegisterClipboardFormatW("PNG")
    return _put([(CF_DIB, bmp.getvalue()[14:]), (png, Path(path).read_bytes())])


def write_files(paths: list[str]) -> bool:
    # DROPFILES header: where the names start, a point, two flags (the last one = wide chars).
    # then every path, each ending in \0, and one more \0 at the end
    head = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    names = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    effect = user32.RegisterClipboardFormatW("Preferred DropEffect")
    # 1 = copy. without it explorer may think it's a cut and delete our copy after pasting
    return _put([(CF_HDROP, head + names), (effect, struct.pack("<I", 1))])


def reveal(path: str) -> None:
    # opens explorer with the file already selected
    subprocess.Popen(f'explorer /select,"{path}"')
