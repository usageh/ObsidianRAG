"""带引用生成: 召回片段作上下文 → 对话模型 → 回答附来源引用。

无相关内容时返回固定提示而非编造。提示词约束模型仅依据片段回答并标注来源序号。
"""

from src.llm_gateway import get_gateway

# 无相关内容时的固定回复, 不调用模型避免编造
NOT_FOUND_MSG = "未在知识库找到相关内容。"

_SYSTEM_PROMPT = (
    "你是知识库问答助手。仅根据提供的笔记片段回答用户问题, "
    "不得使用片段以外的知识编造信息。回答中引用到的内容用 [序号] 标注来源; "
    "若片段不足以回答问题, 直接回复'未在知识库找到相关内容。', 不要臆测。"
)


def generate_answer(question: str, hits: list[dict]) -> dict:
    """基于召回片段生成回答。

    返回 {"answer": str, "sources": [{"path","title","score"}]}。
    hits 为空时直接返回固定提示, 不调用模型。
    """
    if not hits:
        return {"answer": NOT_FOUND_MSG, "sources": []}

    # 拼上下文: 每条片段编号 + 来源元数据 + 内容
    context_blocks: list[str] = []
    sources: list[dict] = []
    for i, h in enumerate(hits, 1):
        context_blocks.append(
            f"[{i}] 来源笔记: {h.get('title', '')} ({h.get('path', '')})\n{h.get('content', '')}"
        )
        sources.append(
            {
                "path": h.get("path", ""),
                "title": h.get("title", ""),
                "score": round(float(h.get("score", 0.0)), 4),
                "source": h.get("source", "note"),
            }
        )
    context = "\n\n".join(context_blocks)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"以下是知识库中检索到的笔记片段:\n\n{context}\n\n"
            f"请基于以上片段回答问题: {question}",
        },
    ]
    gateway = get_gateway()
    answer = gateway.chat(messages)
    return {"answer": answer, "sources": sources}
