"""主题重聚类 CLI: 对当前索引重跑聚类 + 重写 MOC。

用法: python -m src.clustering.cli
"""

import sys

from src.clustering import recluster


def main() -> int:
    r = recluster()
    print(
        f"完成: {r['topics']} 个主题, {r['notes']} 篇笔记, "
        f"写入 {r['mocs']} 个 MOC 页"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
