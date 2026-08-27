"""主题聚类: 基于笔记向量的贪心单链聚类 + LLM 主题标签生成。

贪心单链: 以每篇未分配笔记为种子, 收集所有相似度 >= 阈值的笔记归入同主题。
多于 cluster_min_size 篇的簇调对话模型生成标签 + 摘要; 单篇笔记不分组(留空)。
"""

import numpy as np

from src import storage
from src.config import get_settings
from src.llm_gateway import get_gateway


def cluster_notes() -> dict:
    """对全部笔记聚类, 写入 topic_id 与主题标签。返回 {"topics": n, "notes": m}。"""
    s = get_settings()
    threshold = s.cluster_similarity_threshold
    min_size = s.cluster_min_size

    notes = storage.all_notes()
    if not notes:
        return {"topics": 0, "notes": 0}

    n = len(notes)
    norm_mat = _unit_matrix([nd["vector"] for nd in notes])
    sim = norm_mat @ norm_mat.T  # n×n 余弦相似度

    # 贪心单链聚类
    assigned = [False] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if assigned[i]:
            continue
        members: list[int] = [i]
        assigned[i] = True
        queue = [i]
        while queue:
            j = queue.pop()
            # 单链扩展: 任一成员的近邻都可入簇
            for k in range(n):
                if not assigned[k] and sim[j][k] >= threshold:
                    assigned[k] = True
                    members.append(k)
                    queue.append(k)
        clusters.append(members)

    # 分配 topic_id + 生成标签
    gateway = get_gateway()
    topic_count = 0
    for idx, members in enumerate(clusters):
        if len(members) >= min_size:
            topic_id = f"topic_{idx}"
            member_titles = [notes[m].get("title") or notes[m].get("path") for m in members]
            label, summary = _generate_label_summary(member_titles, gateway)
            storage.upsert_topic(topic_id, label, summary)
            for m in members:
                storage.set_topic(notes[m]["path"], topic_id)
            topic_count += 1
        else:
            # 单篇: 清空主题归属, 避免历史残留
            for m in members:
                storage.set_topic(notes[m]["path"], "")

    return {"topics": topic_count, "notes": n}


def _derive_label(titles: list[str]) -> str:
    """标签生成失败时的兜底: 取首个标题前 6 字。"""
    if not titles:
        return "未分类"
    return (titles[0] or "主题")[:6]


def _generate_label_summary(titles: list[str], gateway=None) -> tuple[str, str]:
    """调对话模型根据笔记标题列表生成 主题标签|||一句话摘要。

    单次标签调用失败(如瞬时 API 错误)时回退到标题派生标签, 不中断整体聚类。
    """
    if gateway is None:
        gateway = get_gateway()
    titles_str = "\n".join(f"- {t}" for t in titles[:20])
    messages = [
        {
            "role": "system",
            "content": (
                "你是主题归纳助手。根据笔记标题列表, 生成一个 2-6 字中文主题标签, "
                "和一句话(20 字内)主题摘要。严格只输出一行, 格式: 标签|||摘要, "
                "不要其他说明。",
            ),
        },
        {"role": "user", "content": f"笔记标题:\n{titles_str}"},
    ]
    try:
        out = gateway.chat(messages).strip()
    except Exception:
        return _derive_label(titles), ""
    if "|||" in out:
        label, summary = out.split("|||", 1)
        return label.strip()[:12], summary.strip()
    return out[:6].strip(), ""


def _unit_matrix(vectors: list[list[float]]) -> np.ndarray:
    """向量矩阵按行归一化, 便于余弦相似度 = 归一化矩阵相乘。"""
    mat = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1)
    norms[norms == 0] = 1.0
    return mat / norms[:, None]
