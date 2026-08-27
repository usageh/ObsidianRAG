"""系统托盘常驻 + 全局快捷键: 触发截图 / 看索引状态 / 退出。

托盘与快捷键是截图入口的两种触发方式, 等价。截图选区在独立线程跑,
避免阻塞托盘消息循环。on_quit 回调供统一启动入口挂接额外清理
(停 API 服务 / 停 watcher)。
"""

from collections.abc import Callable
import threading

import keyboard
import pystray
from PIL import Image, ImageDraw

from src import storage
from src.config import get_settings
from src.screenshot import trigger_screenshot


class TrayApp:
    """托盘应用: 注册全局快捷键, 提供菜单。start() 阻塞直至退出。

    on_quit: 退出前调用的清理回调(如停掉后台服务), 可空。
    """

    def __init__(self, on_quit: Callable[[], None] | None = None) -> None:
        self._icon: pystray.Icon | None = None
        self._on_quit_cb = on_quit

    def start(self) -> None:
        s = get_settings()
        # 全局快捷键: 任意应用中按下即触发截图
        keyboard.add_hotkey(s.screenshot_hotkey, self._on_screenshot)
        self._icon = pystray.Icon(
            "obsidian-rag",
            icon=self._make_icon(),
            title="Obsidian RAG",
            menu=pystray.Menu(
                pystray.MenuItem(
                    "截图", self._on_screenshot, default=True
                ),
                pystray.MenuItem("索引状态", self._on_status),
                pystray.MenuItem("退出", self._on_quit),
            ),
        )
        self._icon.run()

    # ---- 菜单回调 ----

    def _on_screenshot(self, _icon=None, _item=None) -> None:
        # 托盘 / 快捷键回调在非主线程, 截图选区在独立线程跑
        threading.Thread(target=self._run_screenshot, daemon=True).start()

    def _run_screenshot(self) -> None:
        try:
            r = trigger_screenshot()
            if self._icon is not None:
                if r.get("cancelled"):
                    self._icon.notify("已取消截图", "Obsidian RAG")
                elif r.get("ocr_empty"):
                    self._icon.notify("未识别到文字, 未入库", "Obsidian RAG")
                else:
                    self._icon.notify(
                        f"截图已入库 ({r.get('chunks', 0)} 块)", "Obsidian RAG"
                    )
        except Exception as e:  # 托盘线程异常不应崩主进程
            if self._icon is not None:
                self._icon.notify(f"截图失败: {e}", "Obsidian RAG")

    def _on_status(self, _icon, _item) -> None:
        try:
            notes = storage.all_notes()
            n_notes = len(notes)
            n_shots = sum(1 for n in notes if n.get("source") == "screenshot")
        except Exception:
            n_notes = n_shots = 0
        if self._icon is not None:
            self._icon.notify(
                f"已索引 {n_notes} 篇笔记(截图 {n_shots})", "Obsidian RAG"
            )

    def _on_quit(self, icon, _item) -> None:
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        # 统一启动入口挂接的清理: 停 API 服务 / 停 watcher
        if self._on_quit_cb is not None:
            try:
                self._on_quit_cb()
            except Exception:
                pass
        icon.stop()

    @staticmethod
    def _make_icon() -> Image.Image:
        """生成一个简单的托盘图标(蓝底白框)。"""
        img = Image.new("RGBA", (64, 64), (0, 113, 227, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((16, 16, 48, 48), outline=(255, 255, 255, 255), width=3)
        d.line((24, 44, 24, 36), fill=(255, 255, 255, 255), width=2)
        d.line((28, 44, 28, 30), fill=(255, 255, 255, 255), width=2)
        d.line((32, 44, 32, 24), fill=(255, 255, 255, 255), width=2)
        return img


def run() -> None:
    """启动托盘(阻塞)。"""
    TrayApp().start()


__all__ = ["TrayApp", "run"]
