"""知识图谱构建: 节点=笔记, 边=显式 wikilink + 隐式同主题。

显式边: 笔记的 [[wikilink]] 目标解析为笔记路径(按 stem / 标题匹配)。
隐式边: 同主题笔记星形连到主题代表节点, 避免全连接边爆炸。
节点携带 topic_id 供前端按主题着色。
"""

from pathlib import Path

from src import storage


def build_graph() -> dict:
    """构建知识图谱, 返回 {"nodes":[...], "edges":[...]}。"""
    notes = storage.all_notes_meta()  # path, title, source, topic_id
    topics = {t["topic_id"]: t for t in storage.get_topics()}
    links_map = storage.note_links_map()

    # wikilink 目标解析: 文件名 stem 优先, 标题兜底
    stem_map = {}
    title_map = {}
    for n in notes:
        stem_map[Path(n["path"]).stem] = n["path"]
        if n.get("title"):
            title_map.setdefault(n["title"], n["path"])

    def resolve(target: str) -> str | None:
        return stem_map.get(target) or title_map.get(target)

    nodes = []
    for n in notes:
        tid = n.get("topic_id") or ""
        t = topics.get(tid)
        nodes.append(
            {
                "id": n["path"],
                "label": n.get("title") or Path(n["path"]).stem,
                "group": tid or "unsorted",
                "topic": (t.get("label") if t else "") or "",
                "path": n["path"],
                "source": n.get("source", "note"),
            }
        )

    edges = []
    seen: set[tuple] = set()

    def add_edge(a: str, b: str, etype: str) -> None:
        if not a or not b or a == b:
            return
        key = tuple(sorted((a, b))) + (etype,)
        if key in seen:
            return
        seen.add(key)
        edges.append({"from": a, "to": b, "type": etype})

    # 显式边: wikilink 目标
    for path, targets in links_map.items():
        for tgt in targets:
            tp = resolve(tgt)
            if tp:
                add_edge(path, tp, "link")

    # 隐式边: 同主题星形连到代表节点
    by_topic: dict[str, list[str]] = {}
    for n in notes:
        tid = n.get("topic_id") or ""
        if tid:
            by_topic.setdefault(tid, []).append(n["path"])
    for tid, paths in by_topic.items():
        if len(paths) < 2:
            continue
        hub = paths[0]
        for p in paths[1:]:
            add_edge(hub, p, "topic")

    return {"nodes": nodes, "edges": edges}
