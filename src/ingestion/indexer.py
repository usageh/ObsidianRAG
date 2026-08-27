"""索引编排: 解析 -> 图片OCR并入正文 -> 切分 -> 向量化 -> 去重 -> 入库。"""

import hashlib
import re
from pathlib import Path

from src.config import get_settings
from src.llm_gateway import get_gateway
from src.ingestion.parser import parse_note, resolve_image
from src import storage

# 单块字符数, 嵌入有 token 上限, 切分提升召回粒度
CHUNK_SIZE = 500


def index_file(file_path: Path) -> dict:
    """索引一篇笔记, 返回结果摘要(含去重标记)。"""
    s = get_settings()
    vault = s.vault_path
    gateway = get_gateway()
    parsed = parse_note(file_path, vault)

    # 内嵌图片 OCR, 文字并入可检索内容
    ocr_parts: list[str] = []
    for img in parsed.images:
        img_path = resolve_image(img, file_path, vault)
        if img_path is None:
            continue
        try:
            t = gateway.vision(img_path, "提取图中所有文字, 仅输出文字内容")
            if t.strip():
                ocr_parts.append(t.strip())
        except Exception as e:
            print(f"[indexer] 图片 OCR 失败 {img_path}: {e}")
    content = parsed.content
    if ocr_parts:
        content = content + "\n\n" + "\n\n".join(ocr_parts)

    # 笔记级向量(去重 / 聚类用), 截断防超嵌入 token 上限
    note_vec = gateway.embed(content[:3000])

    # 去重: 完全重复(指纹) + 语义相似, 标记不删
    hash_dup = storage.find_hash_duplicate(parsed.hash, exclude_path=parsed.path)
    sem_dups = storage.find_semantic_duplicates(
        note_vec, s.dedup_similarity_threshold, exclude_path=parsed.path
    )
    duplicates: list[dict] = []
    if hash_dup:
        duplicates.append({"path": hash_dup, "reason": "exact"})
    duplicates.extend(
        {"path": d["path"], "reason": "semantic", "sim": d["similarity"]} for d in sem_dups
    )

    # 切分块 + 批量向量化
    chunks = _split(content)
    vectors = gateway.embed_batch(chunks) if chunks else []
    chunk_models = [
        storage.NoteChunk(
            vector=vectors[i],
            path=parsed.path,
            title=parsed.title,
            chunk_id=f"{parsed.path}#{i}",
            content=chunks[i],
            links=",".join(parsed.links),
            updated=parsed.updated,
            hash=parsed.hash,
            source="note",
        )
        for i in range(len(chunks))
    ]
    storage.upsert_chunks(parsed.path, chunk_models)

    storage.upsert_note(
        path=parsed.path,
        title=parsed.title,
        hash_=parsed.hash,
        vector=note_vec,
        source="note",
        updated=parsed.updated,
    )
    return {
        "path": parsed.path,
        "title": parsed.title,
        "chunks": len(chunks),
        "links": len(parsed.links),
        "images_ocr": len(ocr_parts),
        "duplicates": duplicates,
    }


def index_screenshot(image_path: Path, ocr_text: str, updated: str = "") -> dict:
    """截图笔记入库: 视觉 OCR 文本作为一条笔记, 关联原图。

    同时写一份 markdown 笔记(原图嵌入 + 时间戳 + OCR 文本)到
    vault/obsidian-rag/screenshots/, 供 Obsidian 直接查看; OCR 文本切片入索引,
    纳入主题聚类(与普通笔记共用向量库)。截图按时间戳唯一, 不走去重。
    """
    s = get_settings()
    stem = image_path.stem
    # vault 相对路径: .png 原图与同名 .md 笔记, 作为索引 path 与图笔记标识
    try:
        rel_png = str(image_path.relative_to(s.vault_path)).replace("\\", "/")
    except ValueError:
        rel_png = "screenshots/" + image_path.name
    rel_md = rel_png[:-4] + ".md" if rel_png.endswith(".png") else rel_png + ".md"

    # 写 Obsidian 可见的 .md 图笔记(标题 + 原图嵌入 + 时间戳 + OCR 文本)
    _write_screenshot_md(
        s.screenshot_vault_path / f"{stem}.md", image_path, stem, ocr_text, updated
    )

    gateway = get_gateway()
    note_vec = gateway.embed(ocr_text[:3000])

    chunks = _split(ocr_text)
    vectors = gateway.embed_batch(chunks) if chunks else []
    hash_ = _text_hash(ocr_text)
    chunk_models = [
        storage.NoteChunk(
            vector=vectors[i],
            path=rel_md,
            title=f"截图 {stem}",
            chunk_id=f"{rel_md}#{i}",
            content=chunks[i],
            links="",
            updated=updated,
            hash=hash_,
            source="screenshot",
            image_ref=str(image_path),
        )
        for i in range(len(chunks))
    ]
    storage.upsert_chunks(rel_md, chunk_models)
    storage.upsert_note(
        path=rel_md,
        title=f"截图 {stem}",
        hash_=hash_,
        vector=note_vec,
        source="screenshot",
        image_ref=str(image_path),
        updated=updated,
    )
    return {"path": rel_md, "chunks": len(chunks)}


def _write_screenshot_md(
    md_path: Path, image_path: Path, stem: str, ocr_text: str, updated: str
) -> None:
    """写 Obsidian 可见的截图笔记: 标题 + 原图嵌入 + 时间戳 + OCR 文本。"""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [f"# 截图 {stem}", "", f"![[{image_path.name}]]", ""]
    if updated:
        lines += [f"> {updated}", ""]
    if ocr_text.strip():
        lines += ["## OCR 文本", "", ocr_text.strip(), ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def remove_index(file_path: Path) -> None:
    """删除笔记的全部块与元数据。"""
    s = get_settings()
    try:
        rel = str(file_path.relative_to(s.vault_path)).replace("\\", "/")
    except ValueError:
        rel = str(file_path).replace("\\", "/")
    storage.delete_chunks_by_path(rel)
    storage.remove_note(rel)


def _split(text: str) -> list[str]:
    """按段落切分, 长段落再按字符数切。"""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for p in paras:
        for i in range(0, len(p), CHUNK_SIZE):
            chunks.append(p[i : i + CHUNK_SIZE])
    if not chunks and text.strip():
        chunks = [text.strip()]
    return chunks


def _text_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
