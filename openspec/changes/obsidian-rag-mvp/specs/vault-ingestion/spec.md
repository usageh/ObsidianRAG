## Purpose

被动监听 Obsidian vault，将笔记解析、向量化、去重后写入索引，支撑检索、聚合与图谱，且不改动用户原笔记。

## ADDED Requirements

### Requirement: 增量监听索引

系统 SHALL 监听 vault 目录的文件变化，对新增或修改的 markdown 笔记自动触发索引；对删除的笔记 SHALL 从索引中移除。

#### Scenario: 新笔记自动入库

- **WHEN** vault 中新增一篇 markdown 笔记
- **THEN** 系统自动解析、向量化并写入索引，可被后续检索召回

#### Scenario: 删除笔记移除索引

- **WHEN** vault 中一篇已索引笔记被删除
- **THEN** 系统从索引移除其相关向量与元数据

### Requirement: 笔记解析

系统 SHALL 从 markdown 笔记提取正文文本、`[[wikilink]]` 链接目标、内嵌图片引用，并保留路径、标题、修改时间作为元数据。

#### Scenario: 解析含链接的笔记

- **WHEN** 笔记正文含 `[[概念A]]` 链接
- **THEN** 索引记录该链接指向的目标笔记，供图谱与聚合使用

### Requirement: 去重不自动删除

系统 SHALL 对新内容做内容指纹与语义相似度双重检测；发现疑似重复时 SHALL 标记并生成合并建议，SHALL NOT 自动删除任何用户笔记。

#### Scenario: 语义重复检测

- **WHEN** 新笔记与已有笔记的语义相似度超过阈值
- **THEN** 系统标记为疑似重复并输出合并建议，两篇笔记均保留可检索

### Requirement: 内嵌图片 OCR

系统 SHALL 提取笔记内嵌图片，经视觉模型 OCR 后将文字并入该笔记的可检索内容。

#### Scenario: 含截图的笔记

- **WHEN** 笔记内嵌一张含文字的截图
- **THEN** 截图中的文字被 OCR 并入该笔记可检索内容，搜截图中的词能命中该笔记

### Requirement: 修改幂等

系统 SHALL 对同一笔记的多次修改以最新内容更新索引，不产生重复条目。

#### Scenario: 反复修改

- **WHEN** 已索引笔记在短时间内被多次保存
- **THEN** 索引最终只保留最新版本对应的向量与元数据
