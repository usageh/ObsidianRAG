"""屏幕区域截图: tkinter 全屏半透明选区 + mss 抓取, 取消不产生截图。

选区在调用方线程内创建独立 Tk root, 选完即销毁。Esc / 右键取消。
"""

from datetime import datetime
from pathlib import Path

import mss
import tkinter as tk

from src.config import get_settings

# 小于该尺寸视为误触, 忽略
_MIN_SIZE = 4


def select_and_capture() -> Path | None:
    """弹出全屏选区窗口, 拖拽选定区域后截图保存。

    返回保存的 PNG 路径; 用户取消(Esc / 右键 / 过小选区)返回 None。
    """
    bbox = _select_region()
    if bbox is None:
        return None
    return _grab(bbox)


def _select_region() -> tuple[int, int, int, int] | None:
    """全屏半透明覆盖窗, 拖拽选区, 返回 (left, top, right, bottom) 或 None。"""
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.25)
    root.attributes("-topmost", True)
    root.configure(bg="black")

    canvas = tk.Canvas(root, cursor="cross", highlightthickness=0, bg="#000000")
    canvas.pack(fill="both", expand=True)

    state: dict = {"box": None, "start": None, "rect": None}

    def on_press(e):
        state["start"] = (e.x_root, e.y_root)
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#e33", width=2)

    def on_drag(e):
        if state["start"] is not None:
            sx, sy = state["start"]
            # 画布相对坐标 = 屏幕坐标(全屏窗口原点 0,0)
            canvas.coords(state["rect"], sx, sy, e.x_root, e.y_root)

    def on_release(e):
        if state["start"] is not None:
            sx, sy = state["start"]
            ex, ey = e.x_root, e.y_root
            x1, y1, x2, y2 = min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)
            if (x2 - x1) > _MIN_SIZE and (y2 - y1) > _MIN_SIZE:
                state["box"] = (x1, y1, x2, y2)
        root.destroy()

    def on_cancel(_=None):
        state["box"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<Button-3>", on_cancel)  # 右键取消
    root.bind("<Escape>", on_cancel)
    root.mainloop()
    return state["box"]


def _grab(bbox: tuple[int, int, int, int]) -> Path:
    """用 mss 抓取 bbox 区域并保存为 PNG。"""
    left, top, right, bottom = bbox
    s = get_settings()
    # 原图直接写 vault/obsidian-rag/screenshots/, 供 Obsidian 查看
    save_dir = s.screenshot_vault_path
    save_dir.mkdir(parents=True, exist_ok=True)
    out = save_dir / f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    monitor = {"left": left, "top": top, "width": right - left, "height": bottom - top}
    with mss.mss() as sct:
        shot = sct.grab(monitor)
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
    return out
