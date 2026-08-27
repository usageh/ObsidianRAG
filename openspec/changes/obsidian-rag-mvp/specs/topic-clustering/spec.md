## Purpose

按主题聚合笔记，生成 MOC 索引页写回 vault 独立子目录，并在检索时合并同主题视图，全程不改动用户原笔记。

## ADDED Requirements

### Requirement: 主题聚类

系统 SHALL 基于笔记向量进行主题聚类，识别主题分组并为每个分组生成可读的主题标签。

#### Scenario: 自动主题分组

- **WHEN** 索引中存在多篇相关笔记
- **THEN** 系统将其归入相应主题分组并赋予主题标签

### Requirement: MOC 索引页生成

系统 SHALL 为每个主题生成 MOC 索引页，列出该主题下所有笔记的链接，写入 vault 的 `.obsidian-rag/moc/` 独立子目录；SHALL NOT 修改 vault 中用户原有笔记文件。

#### Scenario: MOC 写入独立子目录

- **WHEN** 主题聚类完成
- **THEN** 在 `.obsidian-rag/moc/` 下生成对应 MOC 页，原笔记文件内容不变

#### Scenario: 增量更新 MOC

- **WHEN** 笔记增删导致主题归属变化
- **THEN** 系统更新对应 MOC 页内容，保持与索引一致

### Requirement: 检索合并视图

检索命中同主题多篇笔记时，系统 SHALL 返回合并视图，包含相关笔记列表与该主题的摘要。

#### Scenario: 同主题命中合并

- **WHEN** 检索命中同一主题的多篇笔记
- **THEN** 返回合并视图含相关笔记列表与主题摘要，而非零散单条结果
