"""AI 主动测验: 薄弱主题判定 + 针对薄弱主题出题考查。

薄弱主题 = 掌握度 < 阈值 且已有复习记录的主题。针对薄弱主题调对话模型
生成测验题; 用户作答后把测验题建成卡片并按评级复习, 复用 review_card
流程更新掌握度。
"""

from src import storage
from src.config import get_settings
from src.llm_gateway import get_gateway
from src.reinforcement.cards import create_card, review_card

_QUIZ_PROMPT = (
    "你是测验出题助手。根据给定笔记内容, 针对该主题出一道考查题(中文), "
    '用于检验用户掌握程度。严格只输出 JSON: {"question":"...","reference_answer":"..."}, '
    "不要输出其他说明。题目应是该主题的核心知识点。"
)


def weak_topics() -> list[dict]:
    """返回薄弱主题(掌握度 < 阈值且已复习过)列表, 按掌握度升序。"""
    s = get_settings()
    threshold = s.weak_mastery_threshold
    out: list[dict] = []
    for tm in storage.all_topic_mastery():
        if tm.get("mastery") is None:
            continue
        if tm["mastery"] >= threshold:
            continue
        # 仅保留确实有复习记录的主题(mastery 来自复习评级)
        topic = storage.get_topic(tm["topic_id"])
        if not topic:
            continue
        cards = storage.cards_by_topic(tm["topic_id"])
        if not any(c.get("last_rating") is not None for c in cards):
            continue
        out.append(
            {
                "topic_id": tm["topic_id"],
                "label": topic.get("label") or tm["topic_id"],
                "mastery": round(float(tm["mastery"]), 3),
            }
        )
    out.sort(key=lambda x: x["mastery"])
    return out


def generate_quiz(topic_id: str) -> dict:
    """针对薄弱主题生成一道测验题 + 参考答案。"""
    topic = storage.get_topic(topic_id) or {}
    notes = storage.notes_by_topic(topic_id)
    content_parts = []
    for nd in notes:
        c = storage.note_content(nd["path"])
        if c.strip():
            content_parts.append(c)
    content = "\n\n".join(content_parts)[:3000]
    if not content.strip():
        return {"error": "no_content", "topic_id": topic_id}

    gateway = get_gateway()
    raw = gateway.chat(
        [
            {"role": "system", "content": _QUIZ_PROMPT},
            {"role": "user", "content": content},
        ]
    ).strip()
    q, a = _parse_quiz(raw)
    return {
        "topic_id": topic_id,
        "topic": topic.get("label") or topic_id,
        "question": q,
        "reference_answer": a,
        "note_paths": [nd["path"] for nd in notes],
    }


def _parse_quiz(raw: str) -> tuple[str, str]:
    """解析 {question, reference_answer} JSON; 容忍前后多余文字。"""
    import json
    import re

    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return raw.strip()[:200], ""
    try:
        d = json.loads(m.group(0))
        return str(d.get("question", "")).strip(), str(d.get("reference_answer", "")).strip()
    except json.JSONDecodeError:
        return raw.strip()[:200], ""


def submit_quiz(topic_id: str, question: str, reference_answer: str, rating: int) -> dict:
    """用户作答后: 把测验题建成卡片并按评级复习, 更新主题掌握度。"""
    notes = storage.notes_by_topic(topic_id)
    note_path = notes[0]["path"] if notes else ""
    card = create_card(note_path, topic_id, question, reference_answer)
    return review_card(card["card_id"], rating)
