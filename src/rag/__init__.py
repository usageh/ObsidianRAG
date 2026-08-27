"""RAG 问答: 检索召回 + 带引用生成。

answer() 为对外入口: 问题 → 召回相关片段 → 生成带来源引用的回答;
无相关内容时返回固定提示而非编造。
"""

from src.rag.generate import generate_answer
from src.rag.retrieve import retrieve


def answer(question: str, k: int | None = None) -> dict:
    """问答主流程, 返回 {"answer": str, "sources": list[dict]}。"""
    hits = retrieve(question, k=k)
    return generate_answer(question, hits)


__all__ = ["answer", "retrieve", "generate_answer"]
