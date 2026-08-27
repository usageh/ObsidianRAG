"""检索召回: 问题向量化 → SQLite numpy 余弦检索 top-k, 过滤低相关片段。

低相关片段(score < rag_min_similarity)不作为上下文, 触发"未找到"分支而非编造。
"""

from src import storage
from src.config import get_settings
from src.llm_gateway import get_gateway


def retrieve(question: str, k: int | None = None) -> list[dict]:
    """召回与问题最相关的笔记片段, 过滤低于相关阈值的。

    返回列表按 score 降序, 每条含 path/title/content/score/source 等字段。
    """
    s = get_settings()
    top_k = k if k is not None else s.rag_top_k
    gateway = get_gateway()
    qvec = gateway.embed(question)
    hits = storage.search_chunks(qvec, k=top_k)
    # 过滤低相关: 防止用无关内容凑数生成编造回答
    return [h for h in hits if h["score"] >= s.rag_min_similarity]
