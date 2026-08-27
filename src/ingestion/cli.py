"""全量索引 CLI: 对现有 vault 跑一次全量索引。

用法: python -m src.ingestion.cli
"""

import sys
from pathlib import Path

from src.config import get_settings, should_ignore_path
from src.ingestion.indexer import index_file


def main() -> int:
    s = get_settings()
    vault = s.vault_path
    if not vault.exists():
        print(f"vault 不存在: {vault}")
        return 1
    count = 0
    for md in vault.rglob("*.md"):
        # 跳过 .obsidian 等点目录与运行时子目录 obsidian-rag(moc/screenshots)
        if should_ignore_path(md):
            continue
        try:
            r = index_file(md)
            print(
                f"[{r['path']}] chunks={r['chunks']} links={r['links']} "
                f"ocr={r['images_ocr']} dup={len(r['duplicates'])}"
            )
            count += 1
        except Exception as e:
            print(f"[{md}] 失败: {e}")
    print(f"完成: 索引 {count} 篇笔记")
    return 0


if __name__ == "__main__":
    sys.exit(main())
