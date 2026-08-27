"""截图入口编排: 选区截图 → 视觉 OCR → 作为截图笔记入库。

复用 ingestion.index_screenshot 管线, 让截图与笔记走同一条索引 / 去重 / 聚合路径。
"""

from datetime import datetime

from src.config import get_settings
from src.ingestion.indexer import index_screenshot
from src.llm_gateway import get_gateway
from src.screenshot.capture import select_and_capture

# 视觉模型 OCR 提示词: 仅提取文字, 不加解释
_OCR_PROMPT = "提取图中所有文字, 仅输出文字内容, 不要解释或补充"


def trigger_screenshot() -> dict:
    """触发一次截图流程: 选区 → OCR → 入库。

    返回:
      取消: {"cancelled": True}
      OCR 空: {"path": str, "ocr_empty": True}
      成功: {"path": str, "chunks": int, "ocr_len": int}
    """
    img_path = select_and_capture()
    if img_path is None:
        return {"cancelled": True}

    gateway = get_gateway()
    ocr_text = gateway.vision(img_path, _OCR_PROMPT)
    if not ocr_text.strip():
        return {"path": str(img_path), "ocr_empty": True}

    updated = datetime.now().isoformat()
    result = index_screenshot(img_path, ocr_text, updated=updated)
    return {**result, "path": str(img_path), "ocr_len": len(ocr_text)}


__all__ = ["trigger_screenshot", "select_and_capture"]
