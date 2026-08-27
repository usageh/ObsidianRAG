"""问答对卡片生成 + FSRS 间隔重复调度 + 主题掌握度。

基于笔记调对话模型生成问答对卡片(关联源笔记); FSRS Scheduler 计算下次复习;
评级(Again/Hard/Good/Easy) 更新调度与主题掌握度。掌握度 = 该主题已复习卡片
最近评级均值(0-1), 用于薄弱主题判定。
"""

import json
import re
from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

from src import storage
from src.llm_gateway import get_gateway

_scheduler = Scheduler()

# 数字评级 → FSRS Rating 枚举(前端传数字便于序列化)
_RATING_MAP = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}

_GEN_PROMPT = (
    "你是巩固学习助手。根据给定笔记内容, 生成高质量问答对卡片用于间隔重复复习。"
    '严格只输出 JSON 数组, 每项形如 {"question":"...","answer":"..."}, '
    "不要输出任何其他说明。问答用中文, 答案简明。"
)


def generate_cards(note_path: str, topic_id: str = "", n: int = 3) -> list[dict]:
    """基于笔记内容生成 n 张问答对卡片, 关联源笔记, 返回生成卡片列表。"""
    content = storage.note_content(note_path)
    if not content.strip():
        return []
    gateway = get_gateway()
    raw = gateway.chat(
        [
            {"role": "system", "content": _GEN_PROMPT},
            {"role": "user", "content": content[:3000]},
        ]
    ).strip()
    pairs = _parse_qa(raw)[:n]
    return [create_card(note_path, topic_id, p["question"], p["answer"]) for p in pairs]


def create_card(note_path: str, topic_id: str, question: str, answer: str) -> dict:
    """创建单张卡片(新 FSRS Card, 立刻到期), 返回卡片信息。"""
    card = Card()
    cid = f"{note_path}#{card.card_id}"
    storage.upsert_card(
        card_id=cid,
        note_path=note_path,
        topic_id=topic_id,
        question=question,
        answer=answer,
        card_json=card.to_json(),
        due=card.due.isoformat(),
        created=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "card_id": cid,
        "question": question,
        "answer": answer,
        "note_path": note_path,
        "due": card.due.isoformat(),
    }


def due_cards(limit: int = 20) -> list[dict]:
    """到期待复习卡片。"""
    return storage.due_cards(limit=limit)


def review_card(card_id: str, rating: int) -> dict:
    """复习一张卡: FSRS 更新调度 + 记录历史 + 重算主题掌握度。"""
    rec = storage.get_card(card_id)
    if rec is None:
        return {"error": "not_found"}
    rating_enum = _RATING_MAP.get(rating, Rating.Good)
    card = Card.from_json(rec["card_json"])
    new_card, _log = _scheduler.review_card(card, rating_enum)
    now = datetime.now(timezone.utc).isoformat()
    storage.upsert_card(
        card_id=card_id,
        note_path=rec["note_path"],
        topic_id=rec.get("topic_id") or "",
        question=rec["question"],
        answer=rec["answer"],
        card_json=new_card.to_json(),
        due=new_card.due.isoformat(),
        created=rec["created"],
        last_rating=rating,
    )
    storage.log_review(card_id, rating, now)
    mastery = recompute_topic_mastery(rec.get("topic_id") or "")
    return {
        "card_id": card_id,
        "due": new_card.due.isoformat(),
        "last_rating": rating,
        "topic_mastery": mastery,
    }


def recompute_topic_mastery(topic_id: str) -> float | None:
    """主题掌握度 = 已复习卡片 last_rating 均值 / 4 (0-1); 无主题返回 None。"""
    if not topic_id:
        return None
    cards = storage.cards_by_topic(topic_id)
    rated = [c["last_rating"] for c in cards if c.get("last_rating") is not None]
    mastery = (sum(rated) / len(rated) / 4.0) if rated else 0.0
    storage.set_topic_mastery(topic_id, mastery, datetime.now(timezone.utc).isoformat())
    return mastery


def _parse_qa(raw: str) -> list[dict]:
    """解析模型返回的问答对 JSON; 容忍前后多余文字与边界空白。"""
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [
        x
        for x in arr
        if isinstance(x, dict) and x.get("question") and x.get("answer")
    ]
