"""SQLite 存储: 笔记级元数据 + 块级向量检索。

纯 Python (numpy), 无原生 DLL 依赖, 绕过 Windows 应用控制策略对 pyarrow 的阻止。
同一 app.db: notes(笔记级, 去重/聚类) / chunks(块级, 检索召回)。
向量以 BLOB 存 numpy float32 字节, 读出还原。
"""

import sqlite3
from dataclasses import dataclass

import numpy as np

from src.config import get_settings


@dataclass
class NoteChunk:
    """笔记切分块: 一条向量 + 元数据。"""

    vector: list[float]
    path: str = ""  # 源笔记相对 vault 的路径
    title: str = ""
    chunk_id: str = ""  # 切分块唯一 id (path#index)
    content: str = ""  # 块文本
    links: str = ""  # [[wikilink]] 目标, 逗号分隔
    updated: str = ""  # 笔记修改时间 iso
    hash: str = ""  # 内容指纹
    source: str = "note"  # note / screenshot
    image_ref: str = ""  # 关联图片路径(截图笔记用)


def _connect() -> sqlite3.Connection:
    s = get_settings()
    s.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(s.sqlite_path))
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notes (
            path TEXT PRIMARY KEY,
            title TEXT,
            hash TEXT,
            note_vector BLOB,
            source TEXT,
            image_ref TEXT,
            topic_id TEXT,
            updated TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            path TEXT,
            title TEXT,
            content TEXT,
            links TEXT,
            updated TEXT,
            hash TEXT,
            source TEXT,
            image_ref TEXT,
            vector BLOB
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS topics (
            topic_id TEXT PRIMARY KEY,
            label TEXT,
            summary TEXT
        )"""
    )
    # 巩固: 卡片 / 复习历史 / 主题掌握度
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cards (
            card_id TEXT PRIMARY KEY,
            note_path TEXT,
            topic_id TEXT,
            question TEXT,
            answer TEXT,
            card_json TEXT,
            due TEXT,
            created TEXT,
            last_rating INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            rating INTEGER,
            reviewed_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS topic_mastery (
            topic_id TEXT PRIMARY KEY,
            mastery REAL,
            updated TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_topic ON cards(topic_id)")
    conn.commit()


# ---------- 笔记级 ----------


def upsert_note(
    path: str,
    title: str,
    hash_: str,
    vector: list[float],
    source: str = "note",
    image_ref: str = "",
    updated: str = "",
) -> None:
    """写入或更新笔记级元数据 + 向量。"""
    blob = _vector_to_blob(vector)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO notes (path, title, hash, note_vector, source, image_ref, topic_id, updated)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
               ON CONFLICT(path) DO UPDATE SET
                 title=excluded.title, hash=excluded.hash,
                 note_vector=excluded.note_vector, source=excluded.source,
                 image_ref=excluded.image_ref, updated=excluded.updated""",
            (path, title, hash_, blob, source, image_ref, updated),
        )
        conn.commit()
    finally:
        conn.close()


def remove_note(path: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM notes WHERE path = ?", (path,))
        conn.commit()
    finally:
        conn.close()


def all_notes() -> list[dict]:
    """全量笔记(含还原向量), 供去重 / 聚类。"""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM notes").fetchall()
        return [{**dict(r), "vector": _blob_to_vector(r["note_vector"])} for r in rows]
    finally:
        conn.close()


def all_notes_meta() -> list[dict]:
    """全量笔记元数据(不含向量), 轻量, 供合并视图按主题分组。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT path, title, source, topic_id, updated FROM notes"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_semantic_duplicates(
    vector: list[float], threshold: float, exclude_path: str = ""
) -> list[dict]:
    """找出与给定向量余弦相似度 >= threshold 的已有笔记。"""
    a = np.array(vector, dtype=np.float32)
    a_norm = a / (np.linalg.norm(a) or 1.0)
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM notes").fetchall()
        result = []
        for r in rows:
            if r["path"] == exclude_path:
                continue
            b = _blob_to_vector(r["note_vector"])
            if b is None:
                continue
            b_arr = np.array(b, dtype=np.float32)
            b_norm = b_arr / (np.linalg.norm(b_arr) or 1.0)
            sim = float(np.dot(a_norm, b_norm))
            if sim >= threshold:
                result.append({**dict(r), "similarity": sim})
        return result
    finally:
        conn.close()


def find_hash_duplicate(hash_: str, exclude_path: str = "") -> str | None:
    """按内容指纹查完全重复, 返回已存在的同 hash 笔记路径。"""
    conn = _connect()
    try:
        rows = conn.execute("SELECT path FROM notes WHERE hash = ?", (hash_,)).fetchall()
        for r in rows:
            if r["path"] != exclude_path:
                return r["path"]
        return None
    finally:
        conn.close()


def set_topic(path: str, topic_id: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE notes SET topic_id = ? WHERE path = ?", (topic_id, path))
        conn.commit()
    finally:
        conn.close()


# ---------- 主题 ----------


def upsert_topic(topic_id: str, label: str, summary: str = "") -> None:
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO topics (topic_id, label, summary) VALUES (?, ?, ?)
               ON CONFLICT(topic_id) DO UPDATE SET
                 label=excluded.label, summary=excluded.summary""",
            (topic_id, label, summary),
        )
        conn.commit()
    finally:
        conn.close()


def get_topic(topic_id: str) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute(
            "SELECT topic_id, label, summary FROM topics WHERE topic_id = ?",
            (topic_id,),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def get_topics() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT topic_id, label, summary FROM topics").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def notes_by_topic(topic_id: str) -> list[dict]:
    """某主题下的全部笔记(不含向量, 轻量)。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT path, title, source, updated FROM notes WHERE topic_id = ?",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- 巩固卡片 ----------


def upsert_card(
    card_id: str,
    note_path: str,
    topic_id: str,
    question: str,
    answer: str,
    card_json: str,
    due: str,
    created: str,
    last_rating: int | None = None,
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO cards (card_id, note_path, topic_id, question, answer,
               card_json, due, created, last_rating)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(card_id) DO UPDATE SET
                 note_path=excluded.note_path, topic_id=excluded.topic_id,
                 question=excluded.question, answer=excluded.answer,
                 card_json=excluded.card_json, due=excluded.due,
                 last_rating=excluded.last_rating""",
            (card_id, note_path, topic_id, question, answer, card_json, due, created, last_rating),
        )
        conn.commit()
    finally:
        conn.close()


def get_card(card_id: str) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def due_cards(limit: int = 20) -> list[dict]:
    """到期待复习卡片(due <= now), 按到期升序。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT card_id, note_path, topic_id, question, answer, due, last_rating "
            "FROM cards WHERE due <= ? ORDER BY due ASC LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def log_review(card_id: str, rating: int, reviewed_at: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO reviews (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
            (card_id, rating, reviewed_at),
        )
        conn.commit()
    finally:
        conn.close()


def cards_by_topic(topic_id: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT card_id, note_path, topic_id, question, answer, due, last_rating "
            "FROM cards WHERE topic_id = ?",
            (topic_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_topic_mastery(topic_id: str, mastery: float, updated: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO topic_mastery (topic_id, mastery, updated) VALUES (?, ?, ?)
               ON CONFLICT(topic_id) DO UPDATE SET mastery=excluded.mastery, updated=excluded.updated""",
            (topic_id, mastery, updated),
        )
        conn.commit()
    finally:
        conn.close()


def get_topic_mastery(topic_id: str) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute(
            "SELECT topic_id, mastery, updated FROM topic_mastery WHERE topic_id = ?",
            (topic_id,),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def all_topic_mastery() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT topic_id, mastery, updated FROM topic_mastery").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- 块级 ----------


def upsert_chunks(path: str, chunks: list[NoteChunk]) -> None:
    """删旧块后写新块, 保证修改幂等(同笔记只留最新版本)。"""
    conn = _connect()
    try:
        conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
        rows = [
            (
                c.chunk_id, c.path, c.title, c.content, c.links, c.updated,
                c.hash, c.source, c.image_ref, _vector_to_blob(c.vector),
            )
            for c in chunks
        ]
        conn.executemany(
            """INSERT INTO chunks (chunk_id, path, title, content, links, updated,
               hash, source, image_ref, vector)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def delete_chunks_by_path(path: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
        conn.commit()
    finally:
        conn.close()


def search_chunks(query_vec: list[float], k: int = 5) -> list[dict]:
    """numpy 余弦检索 top-k。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT chunk_id, path, title, content, links, updated, source, image_ref, vector FROM chunks"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return []
    mat = np.array([_blob_to_vector(r["vector"]) for r in rows], dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0] = 1.0
    q = np.array(query_vec, dtype=np.float32)
    qn = np.linalg.norm(q) or 1.0
    sims = (mat @ q) / (norms * qn)
    top = np.argsort(-sims)[:k]
    result = []
    for i in top:
        r = rows[int(i)]
        result.append(
            {
                "chunk_id": r["chunk_id"],
                "path": r["path"],
                "title": r["title"],
                "content": r["content"],
                "links": r["links"],
                "updated": r["updated"],
                "source": r["source"],
                "image_ref": r["image_ref"],
                "score": float(sims[i]),
            }
        )
    return result


def all_chunks() -> list[dict]:
    """全量块(含向量), 供聚类 / 图构建。"""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM chunks").fetchall()
        return [{**dict(r), "vector": _blob_to_vector(r["vector"])} for r in rows]
    finally:
        conn.close()


def chunks_by_path(path: str) -> list[dict]:
    """某笔记的全部块(不含向量), 轻量。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT chunk_id, path, title, content, links, updated, source, image_ref FROM chunks WHERE path = ?",
            (path,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def note_content(path: str) -> str:
    """笔记可检索正文(块拼接), 供生成问答对 / 出题; 笔记与截图均适用。"""
    parts = [c["content"] for c in chunks_by_path(path) if c.get("content")]
    return "\n\n".join(parts)


def note_links_map() -> dict[str, list[str]]:
    """每篇笔记的 wikilink 目标列表(从块聚合去重), 供图构建。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT path, links FROM chunks WHERE links IS NOT NULL AND links != ''"
        ).fetchall()
    finally:
        conn.close()
    m: dict[str, list[str]] = {}
    for r in rows:
        bucket = m.setdefault(r["path"], [])
        for t in r["links"].split(","):
            t = t.strip()
            if t and t not in bucket:
                bucket.append(t)
    return m


# ---------- 向量编解码 ----------


def _vector_to_blob(vec: list[float]) -> bytes:
    return np.array(vec, dtype=np.float32).tobytes()


def _blob_to_vector(blob) -> list[float] | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32).tolist()
