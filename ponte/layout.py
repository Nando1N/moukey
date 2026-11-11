import tkinter as tk

from ponte.edges import side_from_offset

WIDTH, HEIGHT = 300, 200
BOX_W, BOX_H = 80, 54

# where the other screen sits around ours, relative to the center
_SPOTS = {"right": (86, 0), "left": (-86, 0), "top": (0, -60), "bottom": (0, 60)}


class LayoutPicker(tk.Canvas):
    """two little screens, drag the other one to where it really is"""

    def __init__(self, master, on_change):
        super().__init__(master, width=WIDTH, height=HEIGHT, highlightthickness=0, bg="#eef1f5")
        self.on_change = on_change
        self.cx, self.cy = WIDTH // 2, HEIGHT // 2
        self.side = "right"
        self.pos = (self.cx, self.cy)

        self._screen("me", "este PC", "#2f6fdf")
        self._screen("other", "outro", "#7b8794")
        self.set_side("right")

        self.tag_bind("other", "<B1-Motion>", self._drag)
        self.tag_bind("other", "<ButtonRelease-1>", self._drop)
        self.tag_bind("other", "<Enter>", lambda e: self.config(cursor="fleur"))
        self.tag_bind("other", "<Leave>", lambda e: self.config(cursor=""))

    def _screen(self, tag, label, color):
        x, y = self.cx, self.cy
        self.create_rectangle(
            x - BOX_W // 2,
            y - BOX_H // 2,
            x + BOX_W // 2,
            y + BOX_H // 2,
            fill=color,
            outline="",
            tags=(tag,),
        )
        self.create_text(x, y, text=label, fill="white", tags=(tag, f"{tag}_label"))

    def set_name(self, name: str) -> None:
        # long hostnames don't fit in the little box
        self.itemconfig("other_label", text=name if len(name) <= 11 else name[:10] + "…")

    def set_side(self, side: str) -> None:
        dx, dy = _SPOTS[side]
        target = (self.cx + dx, self.cy + dy)
        self.move("other", target[0] - self.pos[0], target[1] - self.pos[1])
        self.pos = target
        self.side = side

    def _drag(self, event):
        self.move("other", event.x - self.pos[0], event.y - self.pos[1])
        self.pos = (event.x, event.y)
        self.tag_raise("other")

    def _drop(self, event):
        side = side_from_offset(event.x - self.cx, event.y - self.cy)
        self.set_side(side)
        self.on_change(side)
