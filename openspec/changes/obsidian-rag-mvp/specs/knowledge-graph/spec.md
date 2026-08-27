## Purpose

可视化笔记间的主题与链接关系，辅助理解个人知识结构，可交互跳转。

## ADDED Requirements

### Requirement: 图构建

系统 SHALL 从笔记的 `[[wikilink]]` 显式链接与主题聚类产生的隐式链接构建节点-边图，节点为笔记、边为链接关系。

#### Scenario: 构建显式与隐式边

- **WHEN** 索引中存在含 `[[wikilink]]` 的笔记与同主题聚类
- **THEN** 图中同时包含显式链接边与主题聚类隐式链接边

### Requirement: 可视化交互

系统 SHALL 在前端以交互式节点图展示知识图谱，支持拖拽、缩放、点击节点跳转到对应笔记或主题。

#### Scenario: 节点跳转

- **WHEN** 用户点击图中某节点
- **THEN** 跳转到对应笔记或主题视图

### Requirement: 按主题着色

节点 SHALL 按所属主题聚类着色，不同主题视觉可区分。

#### Scenario: 主题着色

- **WHEN** 渲染知识图谱
- **THEN** 同主题节点同色，不同主题节点异色

### Requirement: 增量同步

笔记或链接变化时，图 SHALL 增量更新，无需全量重建。

#### Scenario: 笔记增删后图更新

- **WHEN** vault 笔记新增或删除
- **THEN** 图对应节点与边增删更新
