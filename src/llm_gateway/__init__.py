"""LLM 网关: 统一封装对话 / 视觉 / 嵌入, 经 AGICTO 中转。"""

from src.llm_gateway.client import LLMGateway, get_gateway

__all__ = ["LLMGateway", "get_gateway"]
