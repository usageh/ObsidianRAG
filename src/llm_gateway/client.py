"""LLM 网关: 统一封装对话 / 视觉 / 嵌入三类调用, 经 AGICTO 中转。

三类调用共用同一 base_url 与 API key, 各 model id 在配置中独立可替换。
"""

import base64
from pathlib import Path

from openai import OpenAI

from src.config import get_settings


class LLMGateway:
    """OpenAI 兼容客户端封装。"""

    def __init__(self) -> None:
        s = get_settings()
        self._client = OpenAI(api_key=s.agicto_api_key, base_url=s.llm_base_url)
        self._chat_model = s.llm_model_chat
        self._vision_model = s.llm_model_vision
        self._embedding_model = s.llm_model_embedding
        self._embedding_dim = s.embedding_dim

    def embed(self, text: str) -> list[float]:
        """文本转向量, 返回固定维度嵌入。"""
        resp = self._client.embeddings.create(
            model=self._embedding_model, input=text
        )
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入, 减少请求次数。"""
        resp = self._client.embeddings.create(
            model=self._embedding_model, input=texts
        )
        # 按返回的 index 排序, 保证与输入顺序一致
        data = sorted(resp.data, key=lambda d: d.index)
        return [d.embedding for d in data]

    def vision(self, image: str | Path, prompt: str) -> str:
        """视觉模型: 接受本地图片路径 + 文本提示, 返回文本 (OCR / 图片理解)。

        本地文件用 base64 内联。
        """
        p = Path(image)
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        # 按扩展名推断 mime; DeepSeek 视觉按实际内容检测, 这里仅给个合理值
        suffix = p.suffix.lower().lstrip(".")
        if suffix in ("jpg", "jpeg"):
            mime = "jpeg"
        elif suffix in ("png", "gif", "webp"):
            mime = suffix
        else:
            mime = "png"
        resp = self._client.chat.completions.create(
            model=self._vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
        )
        return resp.choices[0].message.content or ""

    def chat(self, messages: list[dict]) -> str:
        """对话生成: 接受消息序列返回文本。"""
        resp = self._client.chat.completions.create(
            model=self._chat_model, messages=messages
        )
        return resp.choices[0].message.content or ""

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim


_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    """单例网关。"""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
