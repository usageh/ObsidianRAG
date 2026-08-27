"""知识图谱可视化: 图构建 + 前端数据。

build_graph() 从笔记 wikilink(显式)与主题聚类(隐式)构建节点-边图;
笔记增删后再次调用即可同步(增量重建, 数据从索引实时读)。
"""

from src.graph.build import build_graph

__all__ = ["build_graph"]
