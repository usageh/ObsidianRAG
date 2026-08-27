"""主题聚合与 MOC: 聚类 → 主题标签 → MOC 索引页 → 检索合并视图。

recluster() 为离线入口(全量重聚类 + 重写 MOC); merge_view() 用于检索时
同主题命中合并展示。
"""

from src.clustering.cluster import cluster_notes
from src.clustering.merge import merge_view
from src.clustering.moc import write_mocs


def recluster() -> dict:
    """全量重聚类 + 重写所有 MOC, 保证 MOC 与索引同步。

    增删笔记后调一次即可同步主题归属与 MOC 页。
    """
    c = cluster_notes()
    m = write_mocs()
    return {"topics": c["topics"], "notes": c["notes"], "mocs": m["written"]}


__all__ = ["recluster", "merge_view", "cluster_notes", "write_mocs"]
