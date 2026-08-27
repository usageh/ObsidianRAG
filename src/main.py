"""统一启动入口: FastAPI 服务 + watchdog 监听 + pystray 托盘同进程。

单命令启动三部分:
- 桌面模式(默认): python -m src.main
  后台线程跑 API 与 watcher, 主线程跑托盘(阻塞); 托盘退出时停掉其余两部分。
- 无桌面 / 服务模式: python -m src.main --headless
  主线程跑 uvicorn(阻塞), watcher 在后台; Ctrl+C 退出后停 watcher。
"""

import argparse
import threading

import uvicorn

from src.api.app import app
from src.config import get_settings
from src.ingestion.watcher import VaultWatcher
from src.screenshot.tray import TrayApp


def _start_api_background(host: str, port: int) -> uvicorn.Server:
    """后台线程跑 uvicorn, 返回 Server 以便退出时置 should_exit。"""
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="api").start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Obsidian RAG 统一启动")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无托盘模式: 只跑 API + watcher, 不启动系统托盘(用于服务/验证)",
    )
    args = parser.parse_args()

    s = get_settings()
    # watchdog 监听在后台线程(Observer 自带线程), 两种模式都需要
    watcher = VaultWatcher()
    watcher.start()

    if args.headless:
        # 主线程跑 uvicorn(阻塞), uvicorn 自带 Ctrl+C 处理; 退出后停 watcher
        config = uvicorn.Config(
            app, host=s.api_host, port=s.api_port, log_level="info"
        )
        server = uvicorn.Server(config)
        print(f"Obsidian RAG (无托盘) 已启动: http://{s.api_host}:{s.api_port}")
        try:
            server.run()
        finally:
            watcher.stop()
        return 0

    # 桌面模式: API 与 watcher 后台, 托盘主线程阻塞
    server = _start_api_background(s.api_host, s.api_port)

    def on_quit() -> None:
        # 托盘退出: 停 API 服务 + 停 watcher
        server.should_exit = True
        watcher.stop()

    print(f"Obsidian RAG 已启动: http://{s.api_host}:{s.api_port} (托盘运行中)")
    TrayApp(on_quit=on_quit).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
