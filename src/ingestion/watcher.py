"""Obsidian vault 增量监听: watchdog + 去抖, 忽略 .obsidian 等内部目录。"""

from pathlib import Path
from threading import Timer
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.config import get_settings, should_ignore_path
from src.ingestion.indexer import index_file, remove_index

# 短时间多次保存合并为一次索引
_DEBOUNCE = 1.0
_pending: dict[str, Timer] = {}


def _ignored(path: Path) -> bool:
    """忽略 .obsidian 等点目录与运行时子目录 obsidian-rag; 规则见 config.should_ignore_path。"""
    return should_ignore_path(path)


def _schedule(path: Path) -> None:
    if _ignored(path) or path.suffix.lower() != ".md":
        return
    key = str(path)
    if key in _pending:
        _pending[key].cancel()
    t = Timer(_DEBOUNCE, _do_index, args=(path,))
    t.daemon = True
    _pending[key] = t
    t.start()


def _do_index(path: Path) -> None:
    _pending.pop(str(path), None)
    if not path.exists():
        remove_index(path)
        return
    try:
        index_file(path)
    except Exception as e:
        print(f"[watcher] 索引失败 {path}: {e}")


class _VaultHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            _schedule(Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory:
            _schedule(Path(event.src_path))

    def on_deleted(self, event):
        if not event.is_directory:
            p = Path(event.src_path)
            if _ignored(p) or p.suffix.lower() != ".md":
                return
            _pending.pop(str(p), None)
            remove_index(p)

    def on_moved(self, event):
        if not event.is_directory:
            remove_index(Path(event.src_path))
            _schedule(Path(event.dest_path))


class VaultWatcher:
    """vault 监听器。start() 阻塞前先排程, stop() 优雅退出。"""

    def __init__(self) -> None:
        s = get_settings()
        self._observer = Observer()
        self._observer.schedule(_VaultHandler(), str(s.vault_path), recursive=True)

    def start(self) -> None:
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
