"""Obsidian markdown 笔记解析: 正文 / wikilink / 图片引用 / 元数据 / 指纹。"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# [[目标]] 或 [[目标|别名]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
# ![[xxx.png]] Obsidian 图片引用
_WIKI_IMAGE_RE = re.compile(r"!\[\[([^\]]+\.(?:png|jpg|jpeg|gif|webp))\]\]", re.I)
# ![alt](url) 标准 md 图片
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)", re.I)


@dataclass
class ParsedNote:
    path: str  # 相对 vault 的相对路径 (正斜杠)
    title: str
    content: str  # 正文(去图片语法后的可检索文本)
    links: list[str] = field(default_factory=list)  # [[wikilink]] 目标
    images: list[str] = field(default_factory=list)  # 图片引用
    updated: str = ""
    hash: str = ""  # 正文归一化指纹


def parse_note(file_path: Path, vault_root: Path) -> ParsedNote:
    """解析一篇 markdown 笔记。"""
    rel = str(file_path.relative_to(vault_root)).replace("\\", "/")
    text = file_path.read_text(encoding="utf-8", errors="replace")

    # 标题: 首个一级标题, 否则用文件名
    title = file_path.stem
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            title = m.group(1).strip()
            break

    links = list(dict.fromkeys(_WIKILINK_RE.findall(text)))
    images = _WIKI_IMAGE_RE.findall(text) + _MD_IMAGE_RE.findall(text)

    # 正文: 去图片语法, 保留文字
    content = _WIKI_IMAGE_RE.sub("", text)
    content = _MD_IMAGE_RE.sub("", content)

    # 指纹: 归一化空白后 sha256, 判完全重复
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    return ParsedNote(
        path=rel,
        title=title,
        content=content,
        links=links,
        images=images,
        updated=datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        hash=h,
    )


def resolve_image(img_ref: str, note_path: Path, vault_root: Path) -> Path | None:
    """把笔记里的图片引用解析为本地路径。"""
    # 标准 md 图片可能含相对路径或 http
    if img_ref.startswith(("http://", "https://")):
        return None
    candidates = [
        vault_root / img_ref,
        note_path.parent / img_ref,
        vault_root / "attachments" / Path(img_ref).name,
        note_path.parent / Path(img_ref).name,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None
