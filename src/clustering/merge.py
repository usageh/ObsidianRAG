"""检索合并视图: 同主题多篇命中合并为一个视图(相关列表 + 主题摘要), 否则单条返回。

先按笔记聚合(同篇笔记多个片段取最高分), 再按主题分组, >=2 篇的主题合并展示。
"""

from src import storage


def merge_view(hits: list[dict]) -> list[dict]:
    """把检索命中按主题合并, 返回 [{type, ...}]。

    type=merged: {topic, summary, notes:[{path,title,score}]}
    type=single:  {path, title, score}
    """
    if not hits:
        return []

    # 1. 按笔记聚合: 同篇笔记多个命中片段取最高分
    by_note: dict[str, dict] = {}
    for h in hits:
        p = h.get("path", "")
        if p not in by_note or h.get("score", 0) > by_note[p].get("score", 0):
            by_note[p] = {
                "path": p,
                "title": h.get("title", ""),
                "score": round(float(h.get("score", 0.0)), 4),
                "content": h.get("content", ""),
                "source": h.get("source", "note"),
            }

    # 2. 按 topic_id 分组
    meta = {n["path"]: n for n in storage.all_notes_meta()}
    by_topic: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for nd in by_note.values():
        tid = meta.get(nd["path"], {}).get("topic_id")
        if tid:
            by_topic.setdefault(tid, []).append(nd)
        else:
            singles.append(nd)

    # 3. >=2 篇的主题合并, 否则作单条
    result: list[dict] = []
    for tid, group in by_topic.items():
        if len(group) >= 2:
            t = storage.get_topic(tid) or {}
            result.append(
                {
                    "type": "merged",
                    "topic": t.get("label") or tid,
                    "summary": t.get("summary", ""),
                    "notes": group,
                }
            )
        else:
            singles.extend(group)

    for nd in singles:
        result.append(
            {
                "type": "single",
                "path": nd["path"],
                "title": nd["title"],
                "score": nd["score"],
                "content": nd["content"],
            }
        )

    # 按最高分降序
    result.sort(
        key=lambda x: max(n["score"] for n in x["notes"]) if x["type"] == "merged" else x["score"],
        reverse=True,
    )
    return result
