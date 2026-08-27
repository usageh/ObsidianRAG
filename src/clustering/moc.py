"""MOC 索引页生成: 每个主题写一个 markdown 页到 vault/obsidian-rag/moc/。

子目录不带点前缀, 否则 Obsidian 会忽略; 详见 design.md D8。
不修改原笔记。每次重生成前清空旧 MOC, 保证与索引一致(增删笔记后同步)。
"""

import re
from pathlib import Path

from src import storage
from src.config import get_settings


def write_mocs() -> dict:
    """为每个主题生成 MOC 索引页, 返回 {"written": n}。"""
    s = get_settings()
    moc_dir: Path = s.moc_path
    moc_dir.mkdir(parents=True, exist_ok=True)

    # 增量同步: 先清空旧 MOC, 再按当前索引重写
    _clear_moc_dir(moc_dir)

    topics = storage.get_topics()
    written = 0
    for t in topics:
        notes = storage.notes_by_topic(t["topic_id"])
        if not notes:
            continue
        content = _render_moc(t, notes)
        fname = _slug(t.get("label") or t["topic_id"]) + ".md"
        (moc_dir / fname).write_text(content, encoding="utf-8")
        written += 1
    return {"written": written}


def _render_moc(topic: dict, notes: list[dict]) -> str:
    """渲染单个主题的 MOC markdown。"""
    label = topic.get("label") or topic["topic_id"]
    lines = [f"# {label}", ""]
    summary = topic.get("summary") or ""
    if summary:
        lines += [f"> {summary}", ""]

    lines.append("## 笔记列表")
    lines.append("")
    # 用文件名 stem 作 wikilink 目标, Obsidian 可解析; 显示用标题
    for nd in notes:
        stem = Path(nd["path"]).stem
        title = nd.get("title") or stem
        tag = " [截图]" if nd.get("source") == "screenshot" else ""
        lines.append(f"- [[{stem}|{title}]]{tag}")
    lines.append("")
    return "\n".join(lines)


def _clear_moc_dir(moc_dir: Path) -> None:
    """删除 MOC 目录下所有 .md, 保留目录本身。"""
    if not moc_dir.exists():
        return
    for f in moc_dir.glob("*.md"):
        f.unlink()


def _slug(text: str) -> str:
    """文件名安全化: 保留中文/字母数字, 其余转 _。"""
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text).strip("_")
    return safe or "topic"
