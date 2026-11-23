# the mac clipboard (NSPasteboard) for pictures and files. text still goes through
# pyperclip, which talks to this same pasteboard when pyobjc is around.
# appkit is imported inside the functions so this file loads on any OS for the tests

import io
from pathlib import Path

from PIL import Image


def _board():
    import AppKit

    return AppKit, AppKit.NSPasteboard.generalPasteboard()


def _pool():
    # these run on the clipboard thread every half second, without a pool of their own
    # every autoreleased object from appkit would pile up
    import objc

    return objc.autorelease_pool()


def clip_seq() -> int:
    # bumps on every change, same idea as windows' sequence number
    with _pool():
        _, board = _board()
        return int(board.changeCount())


def clip_kind() -> str | None:
    with _pool():
        kit, board = _board()
        types = [str(t) for t in board.types() or []]
    # finder also puts the file's icon and name there, so files win over text and image.
    # and apps like excel add a picture of the cells, people expect the text
    if kit.NSPasteboardTypeFileURL in types:
        return "files"
    if kit.NSPasteboardTypeString in types:
        return "text"
    if kit.NSPasteboardTypePNG in types or kit.NSPasteboardTypeTIFF in types:
        return "image"
    return None


def read_files() -> list[str] | None:
    with _pool():
        kit, board = _board()
        only_files = {kit.NSPasteboardURLReadingFileURLsOnlyKey: True}
        urls = board.readObjectsForClasses_options_([kit.NSURL], only_files)
        paths = [str(u.path()) for u in urls or []]
    return paths or None


def read_image() -> Image.Image | None:
    with _pool():
        kit, board = _board()
        # screenshots come as png, older apps and preview often only give tiff
        for kind in (kit.NSPasteboardTypePNG, kit.NSPasteboardTypeTIFF):
            data = board.dataForType_(kind)
            if data is not None:
                raw = bytes(data)
                break
        else:
            return None
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except OSError:
        # half written or a format pillow doesn't know, try on the next round
        return None
    return img


def write_image(path: Path) -> bool:
    img = Image.open(path)
    png, tiff = io.BytesIO(), io.BytesIO()
    img.save(png, "PNG")
    # tiff too, some older mac apps only paste that
    img.save(tiff, "TIFF")
    with _pool():
        kit, board = _board()
        both = {kit.NSPasteboardTypePNG: png.getvalue(), kit.NSPasteboardTypeTIFF: tiff.getvalue()}
        board.declareTypes_owner_(list(both), None)
        return all(
            board.setData_forType_(kit.NSData.dataWithBytes_length_(data, len(data)), kind)
            for kind, data in both.items()
        )


def write_files(paths: list[str]) -> bool:
    with _pool():
        kit, board = _board()
        urls = [kit.NSURL.fileURLWithPath_(str(p)) for p in paths]
        board.clearContents()
        # file urls are what finder pastes as a copy of the files
        return bool(board.writeObjects_(urls))
