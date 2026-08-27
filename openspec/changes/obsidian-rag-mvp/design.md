## Context

全新空白代码库，从零搭建。Windows 单机，Obsidian vault 为唯一数据源。大模型经 AGICTO 中转（OpenAI 兼容格式），单一 `AGICTO_API_KEY` 环境变量 + `base_url=https://api.agicto.cn/v1/`。动机见 [proposal.md - Why](proposal.md)。

关键约束：
- vault 路径 `C:\Users\Yilia\Documents\Obsidian Vault` 含空格，代码用 `pathlib` 处理。
- `deepseek-v4-flash-vision-exp` 为实验版（2026-08-21 上线），需可切换。
- 嵌入维度 1536 固定，换模型须重建向量库。

## Goals / Non-Goals

**Goals:**

- 本地单机可跑，Windows 友好，无 Docker / 无独立服务依赖。
- 增量索引，避免每次全量重建。
- 模型渠道与各 model id 全部配置化，可无痛切换。
- 用户原笔记零改动（MOC 与运行时数据落独立位置）。
- 巩固（抽问 / 测验 / 图谱）闭环可独立运转。

**Non-Goals:**

- 多用户、云端部署、移动端、实时协作。
- 网页剪藏主动采集、AI 无中生有生成新知识卡片。
- rerank（MVP 不上，留扩展点）。
- 旧版本兼容（无老用户，不做 fallback）。

## Decisions

### D1: 技术栈 Python + FastAPI + 静态前端

理由：RAG 生态（嵌入 / 向量库 / OCR 适配）Python 最全；FastAPI 本地服务 + 前端不绑死 Obsidian 插件生态、跨端可迁移。
备选：TypeScript（RAG 生态弱于 Python）；Obsidian 插件（绑死 Obsidian、跨端受限）。

### D2: SQLite + numpy 向量检索

理由：本机 Windows 应用控制策略阻止 pyarrow（LanceDB 必依赖）的 DLL 加载，实测 `ImportError: DLL load failed`。改用 SQLite 存块级向量（BLOB float32）+ numpy 余弦检索，纯 Python 无原生 DLL，绕过策略。MVP 数据量（数百笔记 × 若干块 × 1536 维）numpy 暴力检索毫秒级，够用；后续数据量增长再评估换库。
备选：LanceDB（受 pyarrow DLL 策略阻止，弃）；Chroma / FAISS（同样依赖原生库，同风险）。

### D3: 嵌入 `text-embedding-3-small`（1536 维）

理由：AGICTO 提供、便宜、通用，用户选定。
备选：`text-embedding-v3`（通义，中文优化更强，但用户选 3-small）；本地 `bge-m3`（Win 上跑本地模型 CPU 慢，弃）。
不可逆：换嵌入模型须重建整个向量库（向量空间不同，维度相同也不能混用）。

### D4: 对话 `deepseek-v4-flash` + 视觉 `deepseek-v4-flash-vision-exp`

理由：用户偏好 deepseek 控成本；视觉模型刚上线正好覆盖截图 OCR。各 model id 抽成配置项，视觉是 exp 便于将来切正式版或备选 `qwen-vl-max` / `Doubao-1.5-vision-pro`（AGICTO 均提供）。

### D5: watchdog 增量监听 + 去抖

理由：实时增量，无需定时全量扫描。短时间多次保存合并为一次索引（去抖）；忽略 `.obsidian/` 内部文件。
备选：定时全量扫描（简单但浪费、召回延迟高）。

### D6: FSRS 间隔重复算法

理由：比 SM2 调度更科学，Anki 现代版采用，有 Python 实现。
备选：SM2（经典但调度质量稍逊）。

### D7: 知识图谱 vis.js

理由：轻量、浏览器跑得动、Win 友好。
备选：Cytoscape.js（更重）；D3 force（需更多自定义）。

### D8: MOC 写 vault 独立子目录，运行时数据落项目目录

理由：MOC 是 Obsidian 可见的 markdown 页（写 `vault/obsidian-rag/moc/`），用户能在 Obsidian 里直接浏览，但不污染原笔记结构。子目录名不带点前缀：Obsidian 默认忽略点开头目录，带点会让 MOC 与截图笔记在文件管理器 / 搜索 / 图谱中不可见，等于失去"Obsidian 可见"这一立身之本。运行时数据（SQLite 向量库 + 卡片库，统一 `data/app.db`）写项目运行目录 `data/`，不放 vault，避免污染且 vault 同步（如 OneDrive）时不带走。
备选：MOC 写 vault 外（Obsidian 不可见，失去意义）；MOC 写带点子目录（被 Obsidian 隐藏，可见性丧失）；运行时数据写 vault（污染 + 同步冗余）。

### D9: 去重 = 指纹 + 语义

完全重复用正文归一化后的内容指纹（hash）查；语义重复用嵌入余弦相似度（阈值默认 0.92，可配）。检测到：标记 + 生成合并建议，不删。

### D10: 截图触发 = 全局快捷键 + pystray 托盘

理由：快捷键任意场景一键截图；pystray 提供常驻托盘（触发截图 / 看状态 / 退出）。快捷键用 `keyboard` 或 `pynput`。

### D11: 模块划分

- `llm_gateway`：渠道封装（对话 / 视觉 / 嵌入）+ 配置加载。
- `ingestion`：vault watcher + md 解析 + 向量化 + 去重 + SQLite 写入；截图入口复用同一 ingestion pipeline。
- `clustering`：主题聚类 + MOC 生成 + 检索合并视图。
- `rag`：检索召回 + 带引用生成。
- `reinforcement`：FSRS 卡片库 + 掌握度 + AI 主动测验。
- `graph`：图构建 + vis.js 前端。
- `api`：FastAPI 路由聚合。
- `frontend`：静态前端（问答 / 抽问 / 图谱）。

## Risks / Trade-offs

- [deepseek 视觉模型 exp 不稳定或下线] → model id 抽配置项，可切 `qwen-vl-max` 等 AGICTO 备选。
- [AGICTO 中转可用性 / 计费变动] → `base_url` 抽配置，可切官方 deepseek 或其他中转。
- [嵌入换模型须重建向量库] → 文档化重建命令；选定 3-small 即不再改。
- [vault 路径含空格] → `pathlib` 处理，测试覆盖。
- [watchdog 在 OneDrive 同步 vault 上事件抖动] → 去抖 + 忽略 `.obsidian/` 与临时文件。
- [主题聚类质量不稳] → 聚类参数可调；MOC 用户手动编辑后检测差异、不盲目覆盖。
- [截图 OCR 重复成本] → 同图缓存，避免重复 OCR。
- [本地单机数据丢失] → 卡片库 / 掌握度 / 块级向量统一用 SQLite 持久化；可备份 `data/`。

## Migration Plan

全新部署，无迁移。

1. 安装 Python 依赖。
2. 设置 `AGICTO_API_KEY` 环境变量。
3. 配置 vault 路径（默认 `C:\Users\Yilia\Documents\Obsidian Vault`）。
4. 首次全量索引 vault。
5. 启动 FastAPI 服务 + 系统托盘。

回滚：删除项目目录与 `data/` 运行时数据即可；vault 原笔记未改动、`.obsidian-rag/moc/` 可单独删除。

## Open Questions

- 全局快捷键默认键位（建议 `Ctrl+Shift+S`，用户可配）——非阻塞，实现时定。
- SQLite 具体路径（统一 `data/app.db`）——已定，非阻塞。

均可延后，不改变 specs、架构或任务分解。
