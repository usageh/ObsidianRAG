# ObsidianRAG 项目面试问答库

> 本文档面向"基于本项目讲清 RAG / LLM 应用工程取舍"的面试场景。每题结合 ObsidianRAG 的真实实现给出参考答案，而非泛泛背诵。代码引用均附文件路径，便于回溯。
>
> 热点方向参考 2026 年 RAG 面试高频考点：RAG 全链路 / Chunking / Embedding 选型 / 向量库选型 / 检索准确率 / 幻觉治理 / 评估体系 / GraphRAG / 生产工程。

## 项目速览

ObsidianRAG = 面向 Obsidian 笔记的本地 RAG + 间隔重复巩固系统。

- 单进程三合一：FastAPI + watchdog + pystray
- 入口：`python -m src.main`（桌面）/ `python -m src.main --headless`（服务）
- LLM：经 AGICTO 中转的 OpenAI 兼容协议（DeepSeek 系）
- 存储：单一 SQLite + numpy，无向量库依赖
- 巩固：FSRS 调度 + AI 主动测验
- 技术栈：Python / FastAPI / watchdog / pystray / keyboard / mss / tkinter / numpy / fsrs / openai / pydantic

---

## 一、RAG 基础与流程

### Q1.1 什么是 RAG？解决了 LLM 哪些痛点？本项目如何体现？

RAG（Retrieval-Augmented Generation，检索增强生成）= 先从外部知识库检索相关片段，再连同问题交给 LLM 生成，让模型"基于真实资料作答"而非凭参数记忆硬编。

解决三大痛点：

1. 时效性 — 模型训练有截止日，无法回答新事件；
2. 私有知识空白 — 企业 / 个人笔记从未进过训练集；
3. 幻觉 — 知识缺失时模型硬编。

本项目体现：用户的 Obsidian 笔记是私有、持续变动的知识，从未进过任何模型训练集。`/api/ask`（`src/api/app.py`）先 `retrieve()` 召回笔记片段再 `generate_answer()`，正是 RAG 范式。

**追问：RAG vs 微调？** RAG 不动模型参数、知识可热更新、答案可溯源；微调把知识烧进参数、成本高、不可溯源。本项目选 RAG，因为笔记天天在改、重训不现实。

### Q1.2 RAG 完整流程？本项目每一步的具体实现？

分索引阶段（离线 / 增量）与查询阶段。

**索引阶段**（`src/ingestion/indexer.py`）：

1. 文档解析 — `src/ingestion/parser.py` 用正则解析 `[[wikilink]]` / `![[img]]` / 标题 / 正文 / sha256 指纹；
2. OCR 并入 — 内嵌图片调视觉模型 OCR，文字并入正文；
3. 笔记级向量 — `embed(content[:3000])` 用于去重 / 聚类；
4. 分块 — `_split`：按段落 `split("\n\n")`，长段落按 `CHUNK_SIZE=500` 字符切；
5. 块向量 — `embed_batch` 批量嵌入；
6. 去重 — 哈希 + 语义双路，仅标记不删；
7. 入库 — `upsert_chunks` + `upsert_note`。

**查询阶段**（`src/rag/retrieve.py` + `src/rag/generate.py`）：

1. 问题向量化 — `embed(question)`；
2. 召回 — `search_chunks` top-k（k=5）；
3. 过滤低相关 — `score < 0.35` 丢弃；
4. 上下文拼装 — `[i] 来源笔记 + content`；
5. 生成 — `chat`（system prompt 约束 + 上下文 + 问题）；
6. 合并视图 — `merge_view` 同主题命中合并。

---

## 二、解析与分块

### Q2.1 Chunk 怎么切？切大切小的 trade-off？本项目的选择？

切大 → 信息稀释、检索精度降；切小 → 上下文割裂、召回半句话。

策略：固定长度 / 递归切分 / 语义切分 / 滑动窗口。

本项目（`src/ingestion/indexer.py` `_split`，`CHUNK_SIZE=500`）：

- 先按段落（`\n\n`）切，长段落再按 500 字符切；
- 选择理由：Obsidian 笔记段落天然是语义边界（一个想法一段），按段落切尊重语义；500 字符兼顾嵌入 token 上限与召回粒度；
- 未用滑动窗口 overlap：笔记级向量已用于去重 / 聚类，块级检索靠 top-k 多块召回，单块切半不至于丢上下文（多块一起返回给 LLM）。

**追问：为什么不按 token 切而按字符？** Obsidian 笔记是中文为主混合内容，字符数与 token 数无稳定换算，按字符切实现简单且可控；嵌入模型（text-embedding-3-small）单块 500 字符远在其 token 上限内。

### Q2.2 如何避免切在语义中间？

本项目思路是"从两个方向缓解"：

1. 切的时候尊重自然边界 — 先段落再字符，不在段落中间硬切（除非段落超长）；
2. 检索时把上下文补回 — top-k=5 多块同返回，同篇笔记多块命中取最高分聚合（`merge_view` `by_note`），LLM 看到的是多篇多块拼成的完整上下文，而非单半句。

未做父子块 / 句子窗口检索（笔记体量小，top-k 已够），但 `merge_view` 的按笔记聚合本质是"小块检索 + 大块输出"的轻量版。

---

## 三、Embedding 与向量存储

### Q3.1 Embedding 选型考虑什么？本项目用哪个？

四个因素：语言支持 / 维度 / 上下文长度 / 评测指标（MTEB Recall@k）。

本项目：`text-embedding-3-small`（经 AGICTO），`dim=1536`（`src/config.py` `embedding_dim`）。

- 中文支持 OK，1536 维表达力够；
- 截断 `content[:3000]` 防超嵌入 token 上限；
- 单块 500 字符远在上下文长度内。

### Q3.2 向量数据库怎么选？本项目为什么不用 Milvus / Chroma？

主流：Faiss（本地库）/ Milvus（分布式）/ pgvector（复用 PG）/ Chroma / Pinecone。

本项目不用任何向量库，自建 SQLite + numpy（`src/storage.py`）：

- 单一 `app.db` 存 `notes` / `chunks` / `topics` / `cards` / `reviews` / `topic_mastery` 六张表，向量以 BLOB 存 numpy float32 字节，读出 `np.frombuffer` 还原；
- 检索 `search_chunks`：全量加载 chunks 向量 → 矩阵化余弦（`mat @ q / norms`）→ `np.argsort` top-k。

理由：

1. 无原生 DLL 依赖 — 绕过 Windows 应用控制策略对 pyarrow（Milvus / Chroma 依赖）的阻止；
2. 单用户本地笔记体量小（千级笔记 × 几十块），暴力矩阵余弦 numpy 一次 dot 就出，延迟可接受，引入 ANN 索引是过度优化；
3. 单文件 SQLite 便于备份 / 迁移，与卡片库共用一个库。

**追问：数据量上去了怎么办？** 切换到 sqlite-vss / Faiss 本地索引即可，`storage.search_chunks` 是唯一检索入口，替换面很小。

**追问：HNSW vs IVF？** HNSW 基于图，构建慢查询快，适合静态；IVF 基于倒排，构建快查询稍慢，适合动态更新。本项目笔记天天变（watcher 增量），更偏动态场景，若上 ANN 倾向 IVF，但目前量级用不上。

---

## 四、检索与召回

### Q4.1 如何提升 RAG 检索准确率？本项目做了哪些？还差什么？

四维提升：查询侧 / 索引侧 / 检索侧 / 后处理。

本项目已做：

- 检索侧门控 — `rag_min_similarity=0.35`，低于阈值的片段直接丢，不凑数（`src/rag/retrieve.py`），防"垃圾上下文 → 垃圾回答"；
- 后处理聚合 — `merge_view` 同篇笔记多块取最高分，同主题合并。

本项目未做（可讲为后续优化）：

- 查询改写 / HyDE / Multi-Query — 用户问题口语化时收益大，目前直查；
- 混合检索 BM25 + 向量 + RRF — 笔记含专有名词 / 人名时关键词检索更准，纯向量易漏；
- Rerank — 召回 top-k=5 较小，重排收益有限，但加 cross-encoder 重排可进一步提精。

### Q4.2 为什么设 rag_min_similarity=0.35 这么低？不会放进噪声吗？

0.35 是"相关下限"不是"高质量门槛"。作用是过滤明显不相关的（比如问题与笔记完全无关时余弦 ~0.1-0.2），避免 LLM 看到无关内容硬编。

真正防噪声靠两层：

1. retrieve 过滤 — `score < 0.35` 丢弃；
2. generate 兜底 — hits 空时直接返回 `NOT_FOUND_MSG` 不调模型（`src/rag/generate.py`），从源头断幻觉。

**追问：阈值怎么定？** 经验值 + 实测调整。text-embedding-3-small 的余弦分布，相关笔记片段通常 >0.4，0.35 留余量防漏召回；若发现噪声多可调高到 0.45。

### Q4.3 召回数 top-k=5 怎么定？

top-k 太小易漏、太大稀释上下文 + 成本升。

本项目默认 5（`rag_top_k`），API `/api/ask` 支持传 `k` 覆盖。笔记场景单问题相关片段通常 2-4 块，5 够用；`merge_view` 会按主题合并，即使多篇命中也聚合成少量视图，不撑爆上下文。

---

## 五、生成与幻觉治理

### Q5.1 RAG 幻觉怎么治？本项目的多层防御？

幻觉分：内在（与检索矛盾）/ 外在（编造检索没有的）。

本项目四层（`src/rag/generate.py`）：

1. 检索门控 — 低相关片段过滤，不让无关内容进上下文；
2. 空结果短路 — hits 空直接返回 `NOT_FOUND_MSG`，不调模型，从源头断"无米硬编"；
3. Prompt 强约束 — system："仅根据片段回答，不得用片段外知识编造，不足则回'未在知识库找到相关内容'，不要臆测"；
4. 引用溯源 — 要求 `[序号]` 标注来源，`sources` 返回 path / title / score，用户可点开核实。

**追问：还差什么？** 可加事实校验层（让 LLM 自检答案每句是否被片段支持），但笔记问答场景前四层已够。

### Q5.2 上下文怎么拼？为什么不直接拼原文？

本项目拼法（`generate_answer`）：

```
[1] 来源笔记: title (path)
content

[2] ...
```

带来源元数据 + 序号，便于 LLM 引用 `[1][2]` 且用户可溯源。

不直接拼原文因为：① 块级检索召回的是切分后的片段，拼片段更贴检索结果；② 带编号让 LLM 引用有抓手，答案可解释。

---

## 六、去重机制

### Q6.1 怎么判重复？为什么标记不删？

本项目双路去重（`src/ingestion/indexer.py` + `src/storage.py` `find_*`）：

- 完全重复 — 正文归一化（空白合并 + lower）后 sha256 指纹精确匹配 → `find_hash_duplicate`；
- 语义重复 — 笔记级向量余弦 >= `dedup_similarity_threshold`（0.92）→ `find_semantic_duplicates`，全量扫 notes 表。

只标记 + 返回 `duplicates` 列表（含 reason: exact / semantic + sim），不删。

理由：笔记是用户资产，系统不能擅自删；标记后由用户 / 合并流程决策。0.92 高阈值防误判（同主题不等于重复）。

### Q6.2 语义去重为什么用笔记级向量而不是块级？

笔记级向量 `embed(content[:3000])` 代表整篇主旨，用于聚类 / 去重；块级向量用于检索召回。

去重要回答"这篇笔记是不是和已有某篇讲同一件事"，是篇级判断，用笔记级向量；用块级会被局部段落主导，误判高。

---

## 七、主题聚类与 MOC

### Q7.1 聚类算法？为什么选单链？

本项目贪心单链聚类（`src/clustering/cluster.py` `cluster_notes`）：

- n×n 余弦矩阵 → 从每篇未分配笔记为种子 BFS 扩展，任一成员的近邻（sim >= 0.55）可入簇。

为什么单链：笔记主题是"网状关联"不是"球状聚簇"，单链允许链式传递归入同主题，适合知识笔记；KMeans 需预定簇数且假设球状，不适合。

`threshold=0.55`，`min_size=2`：少于 2 篇不建主题（单篇留空 topic_id）。

**追问：单链的链式效应会不会把不相关的串一起？** 0.55 阈值 + 笔记向量区分度足够，实测可控；若发现可改 average-link 或调高阈值。

### Q7.2 MOC 是什么？怎么生成？为什么写回 vault？

MOC = Map of Content，主题索引页。

本项目（`src/clustering/moc.py` `write_mocs`）：每主题一个 `.md`，内容 = `# 标签` / `> 摘要` / `## 笔记列表` / `- [[stem|title]]`，写到 `vault/obsidian-rag/moc/`。

增量：先清空旧 MOC `.md` 再重写，保证与索引同步。

写回 vault 理由（D8 决策）：

- MOC 是 Obsidian 可见的 markdown 页，用户能在 Obsidian 直接浏览；
- 子目录 `obsidian-rag/` 不带点前缀 — Obsidian 默认忽略点开头目录，带点 MOC 不可见；
- 运行时数据（SQLite）不写 vault，避免污染 + 同步冗余。

主题标签由 LLM 生成 `标签|||摘要`，失败兜底取首标题前 6 字。

### Q7.3 检索合并视图解决什么？

问题：top-k 命中多篇同主题笔记时，平铺展示重复啰嗦。

`merge_view`（`src/clustering/merge.py`）：先按笔记聚合（同篇多块取最高分）→ 按 topic_id 分组 → >=2 篇同主题合并为一个 `merged` 视图（含主题摘要 + 笔记列表），否则 `single`。

效果：用户看到"这个主题下有 3 篇相关笔记 + 主题摘要"，而非 3 条独立片段。

---

## 八、知识图谱

### Q8.1 图谱的边怎么建？为什么不全连接？

本项目（`src/graph/build.py`）两种边：

- 显式边（link）— 笔记的 `[[wikilink]]` 目标，`stem_map` 优先 / `title_map` 兜底解析为笔记路径；
- 隐式边（topic）— 同主题笔记星形连到代表节点（`hub=paths[0]`），避免全连接 O(n²) 边爆炸。

节点带 topic_id 供前端按主题着色。去重边：`sorted(tuple) + etype`。vis.js 前端渲染。

---

## 九、间隔重复与巩固

### Q9.1 为什么用 FSRS 不用 SM2 / Anki 默认？

FSRS 更科学（基于记忆三段模型 + 最优间隔），Anki 现代版采用，有 Python 实现。

本项目用 `fsrs` 库（`src/reinforcement/cards.py`）：`Scheduler.review_card(card, Rating)` 算下次 due，Rating 枚举 Again / Hard / Good / Easy（前端传数字 1-4 映射）。

卡片状态 `card.to_json()` 存 `cards.card_json`，复习时 `Card.from_json` 还原 — 卡片记忆状态不在表结构里硬编码，而是序列化整个 FSRS Card 对象，便于算法升级。

### Q9.2 主题掌握度怎么算？薄弱主题怎么判？

掌握度（`recompute_topic_mastery`）= 该主题已复习卡片 `last_rating` 均值 / 4 → 0-1。

薄弱主题（`weak_topics`）= `mastery < weak_mastery_threshold`（0.6）且有复习记录，按掌握度升序。

AI 主动测验（`generate_quiz`）：拼主题下全部笔记内容 `[:3000]` → LLM 出一题 `{question, reference_answer}`；用户作答后 `submit_quiz` 把测验题建卡 + 复用 `review_card` 更新掌握度。

闭环：笔记 → 卡片 → 复习 → 掌握度 → 薄弱主题 → AI 出题 → 建卡 → 复习……形成巩固飞轮。

---

## 十、增量索引与 watcher

### Q10.1 watcher 怎么避免重复索引 + 防抖？

`src/ingestion/watcher.py`：

- watchdog Observer 递归监听整个 vault；
- `_DEBOUNCE=1.0s` Timer：同一文件短时间多次保存（Obsidian 自动保存 / 连续编辑）合并为一次索引，`_pending` 字典按 path 存 Timer，新事件 cancel 旧 Timer；
- 只处理 `.md`，非 `.md` 忽略；
- `should_ignore_path`（`src/config.py`）：点开头目录（`.obsidian` 等）+ `obsidian-rag` 运行时目录共用忽略，watcher 增量 + cli 全量同一份规则，防运行时目录（MOC / 截图）被当普通笔记重复索引。

事件：created / modified → schedule 去抖索引；deleted → pop + `remove_index`；moved → remove 旧 + schedule 新。

### Q10.2 watcher 只捕获运行时变更，离线改动怎么办？

watcher 监听器只在进程运行时生效，Obsidian 关闭时改的笔记不会被捕获。

解决：`python -m src.ingestion.cli` 全量索引（遍历 `vault.rglob("*.md")`，跳过忽略目录），用于冷启动补齐。

**追问：能不能启动时自动对账？** 可加启动时 reconcile 扫描（比对 notes 表与文件系统差异），目前未做，靠用户手动跑 cli。

---

## 十一、截图 OCR 入口

### Q11.1 截图怎么触发 + OCR 怎么入库？

触发两种（`src/screenshot/tray.py`）：① 全局快捷键 `ctrl+shift+s`；② pystray 托盘菜单"截图"。

流程（`trigger_screenshot`，`src/screenshot/__init__.py`）：

1. `select_and_capture`：tkinter 全屏半透明（alpha=0.25）选区 + mss 抓 PNG，Esc / 右键 / 过小选区取消；
2. 视觉模型 OCR：提取图中所有文字；
3. `index_screenshot`：OCR 文本作为一条笔记（`source="screenshot"`，`image_ref=原图路径`）入库，同时写 `.md` 图笔记到 `vault/obsidian-rag/screenshots/`（标题 + 原图嵌入 + 时间戳 + OCR 文本）供 Obsidian 查看。

关键设计：截图复用 ingestion 同一管线 → 与普通笔记共用向量库 / 聚类 / 检索，截图按时间戳唯一不走去重。

### Q11.2 为什么 OCR 文本而不是图片直接向量检索？

图片向量化（CLIP 等）需要专门模型 + 标注，且检索精度对文字内容不敏感。

本项目场景是"截图里多是文字"（代码片段 / 文档截图 / 聊天记录），OCR 后转文本走同一套嵌入 / 检索链路最直接，且 Obsidian 可见可搜索。

若未来以图片内容（非文字）为主，可再接 CLIP 向量。

---

## 十二、工程化与架构

### Q12.1 单进程怎么跑三件事（API + watcher + 托盘）？

`src/main.py`：

- 桌面模式：API（uvicorn）+ watcher 后台 daemon 线程，托盘主线程阻塞；托盘退出 → `server.should_exit=True` + `watcher.stop()`；
- headless 模式：主线程跑 uvicorn 阻塞，watcher 后台；Ctrl+C → finally `watcher.stop()`。

watchdog Observer 自带线程，不占主线程；pystray 必须主线程跑（系统托盘限制），所以桌面模式主线程给托盘。

### Q12.2 配置怎么管？密钥缺失怎么办？

pydantic-settings `BaseSettings`（`src/config.py`）：`env_file=.env`，`AGICTO_API_KEY` 用 `Field(..., required)` 必填，缺失实例化抛 `ValidationError` 启动停止 — 杜绝无密钥空跑。

单例 `get_settings()` 全局复用。

### Q12.3 低延迟 RAG 怎么做？本项目的取舍？

通用手段：Embedding 本地推理 / HNSW 索引 / 控召回数 / Rerank 减候选 / 精简上下文 / 流式输出 / 查询缓存 / 异步队列。

本项目取舍：

- 单用户本地场景，延迟瓶颈在 LLM 调用（AGICTO 网关 + DeepSeek），不在检索（numpy 矩阵余弦千级块毫秒级）；
- 未做缓存（笔记天天变，缓存失效成本高）；
- 未做流式（问答交互可接受秒级）；
- 控召回数 top-k=5 + 低相关过滤，上下文精简；
- watcher 增量索引走后台线程不阻塞 API。

若上量：优先加查询缓存（同问题短时复用）+ 流式输出。

---

## 关键参数速查

| 参数 | 默认 | 位置 | 作用 |
|---|---|---|---|
| CHUNK_SIZE | 500 字符 | `src/ingestion/indexer.py` | 单块字符数 |
| embedding_dim | 1536 | `src/config.py` | 嵌入维度 |
| dedup_similarity_threshold | 0.92 | `src/config.py` | 语义去重阈值 |
| rag_min_similarity | 0.35 | `src/config.py` | 检索相关下限 |
| rag_top_k | 5 | `src/config.py` | 召回片段数 |
| cluster_similarity_threshold | 0.55 | `src/config.py` | 聚类同主题阈值 |
| cluster_min_size | 2 | `src/config.py` | 成簇最少笔记数 |
| weak_mastery_threshold | 0.6 | `src/config.py` | 薄弱主题判定 |
| screenshot_hotkey | ctrl+shift+s | `src/config.py` | 截图全局快捷键 |
| api_port | 8765 | `src/config.py` | FastAPI 端口 |
| _DEBOUNCE | 1.0s | `src/ingestion/watcher.py` | watcher 防抖 |

## SQLite 表结构

| 表 | 主键 | 用途 |
|---|---|---|
| notes | path | 笔记级元数据 + 向量（去重 / 聚类） |
| chunks | chunk_id | 块级向量 + 元数据（检索召回） |
| topics | topic_id | 主题标签 + 摘要 |
| cards | card_id | 问答对卡片 + FSRS 状态 + due |
| reviews | review_id | 复习历史 |
| topic_mastery | topic_id | 主题掌握度 |

## 热点对照（本项目 vs 前沿）

| 前沿方向 | 本项目状态 | 说明 |
|---|---|---|
| Naive RAG | 已实现 | 解析 → 嵌入 → 检索 → 生成 |
| Advanced RAG | 部分 | 有低相关门控 + 合并视图，无 query 改写 / 混合检索 / Rerank |
| Graph RAG | 轻量版 | `src/graph/build.py` 显式 wikilink + 隐式同主题星形图，非微软 GraphRAG 全局摘要路线 |
| Self-RAG / CRAG | 未实现 | 无检索自我评估 / 纠错分支 |
| Agentic RAG | 未实现 | 无 LLM 自主决策多轮检索 |
| 混合检索（BM25 + 向量 + RRF） | 未实现 | 纯向量检索 |
| Rerank | 未实现 | top-k=5 小，重排收益有限 |
| 评估体系 | 未实现 | 无 RAGAS / Recall@k / MRR 离线评测 |
