## Why

Obsidian 笔记在持续增长，但没有自动检索与巩固机制：笔记写了就忘、同一主题散落多篇、截图里的信息无法被搜索。需要一个本地 RAG 系统——自动索引 vault（含截图 OCR）、按主题聚合、支持问答与主动巩固，让笔记真正可检索、可复习。大模型经 AGICTO 中转走 DeepSeek，控制成本。

## What Changes

- 新增 vault 被动增量索引：watchdog 监听 vault，新增/修改的笔记自动解析（正文 + `[[wikilink]]` 链接 + 内嵌图片）、向量化（`text-embedding-3-small`）、去重（内容指纹 + 语义相似度）、入 SQLite 向量库。
- 新增截图入口：全局快捷键 + 系统托盘触发截图，调 `deepseek-v4-flash-vision-exp` 视觉模型 OCR 转文字后并入同一条索引管线。
- 新增主题聚合与 MOC：逻辑聚合（不动原笔记），主题聚类生成 MOC 索引页写回 vault 独立子目录（`.obsidian-rag/moc/`），检索时同主题笔记合并视图展示。
- 新增去重：检测到重复时标记 + 给出合并建议，不自动删除（Obsidian 笔记是用户资产）。
- 新增 RAG 问答：SQLite + numpy 向量检索 + `deepseek-v4-flash` 生成回答。
- 新增巩固知识：间隔重复抽问（FSRS 调度 + deepseek 生成问答对 + 掌握度追踪）、AI 主动测验（基于薄弱主题 deepseek 出题）、知识图谱可视化（vis.js，从 `[[wikilink]]` + 主题聚类构建节点图）。
- **不做**：网页剪藏主动采集；AI 无中生有生成新知识卡片（幻觉风险）。

## Capabilities

### New Capabilities

- `llm-gateway`: 统一 AGICTO 渠道封装（对话 / 视觉 / 嵌入 / rerank 预留）与全局配置（vault 路径、API key、各 model id 抽配置项）。
- `vault-ingestion`: Obsidian vault 被动增量采集、解析、向量化、去重、入 SQLite 向量库。
- `screenshot-ingestion`: 截图 OCR 入库（快捷键 / 系统托盘触发 + 视觉模型 OCR + 并入索引管线）。
- `topic-clustering`: 主题聚类、MOC 索引页生成（写回 vault 独立子目录）、检索时同主题合并视图。
- `rag-qa`: 向量检索 + 生成问答。
- `reinforcement`: 巩固知识——间隔重复抽问（FSRS 调度、问答对生成、掌握度追踪）+ AI 主动测验（基于薄弱主题出题）。
- `knowledge-graph`: 知识图谱可视化（节点图构建与交互，vis.js）。

### Modified Capabilities

无（全新项目，无既有 spec）。

## Impact

- 新增代码：Python 项目（FastAPI 后端 + 前端），全新目录结构，从零搭建。
- 依赖：`numpy`、`watchdog`、`pystray`、`openai` SDK（AGICTO 兼容 OpenAI 格式）、`fastapi`、`uvicorn`、FSRS 库、vis.js（前端）。
- 外部 API：AGICTO（`deepseek-v4-flash` 对话、`deepseek-v4-flash-vision-exp` 视觉、`text-embedding-3-small` 嵌入）。需 `AGICTO_API_KEY` 环境变量。
- 文件系统：只读 Obsidian vault（`C:\Users\Yilia\Documents\Obsidian Vault`）；向 vault 的 `.obsidian-rag/moc/` 子目录写 MOC 索引页；本地 SQLite 数据目录（`data/app.db`）。
- 不修改用户原笔记（MOC 与运行时数据均落在独立子目录）。
