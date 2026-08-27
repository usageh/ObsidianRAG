## 1. 项目脚手架与配置

- [x] 1.1 初始化 Python 项目结构（src/ 下分模块 `llm_gateway` / `ingestion` / `clustering` / `rag` / `reinforcement` / `graph` / `api`，`frontend/` 静态目录，`data/` 运行时目录），写 `pyproject.toml` 与 `requirements.txt`；验证 `python -c "import src.llm_gateway"` 等空模块可导入
- [x] 1.2 配置加载（`config.py` + `.env`）：vault 路径、`AGICTO_API_KEY`、`base_url`、各 model id（对话/视觉/嵌入）、去重阈值、快捷键；验证未设 `AGICTO_API_KEY` 时启动报错并停止（llm-gateway 场景1）
- [x] 1.3 `.gitignore` 加 `.env` / `data/` / `__pycache__`；验证 `git status` 不含敏感文件

## 2. LLM 网关（llm_gateway）

- [x] 2.1 实现 OpenAI 兼容客户端封装，三方法：`embed(text)->vector` / `vision(image,prompt)->text` / `chat(messages)->text`；手动用一段文本调 `embed` 验证返回 1536 维向量
- [x] 2.2 视觉 OCR 验证：用一张含文字的测试截图调 `vision` 提取文字，验证返回含图中文字
- [x] 2.3 对话生成验证：用问答消息调 `chat`，验证返回回答文本
- [x] 2.4 model id 可切换验证：改配置中视觉 model id 后调用仍成功（llm-gateway 场景2）

## 3. Vault 增量采集索引（ingestion + SQLite）

- [x] 3.1 建 SQLite 表（`data/app.db`，1536 维向量 BLOB + 元数据列 path/title/links/updated/hash），验证可写入读取
- [x] 3.2 md 解析器：提取正文、`[[wikilink]]` 目标、内嵌图片引用、元数据（路径/标题/修改时间）；对含链接与图片的样例笔记手动验证解析正确
- [x] 3.3 内容切分 + 向量化 + 入库（带 hash 指纹）；手动验证新笔记入库后可按向量检索召回（vault-ingestion 新笔记场景）
- [x] 3.4 修改幂等：同一笔记多次保存只留最新版本向量；手动验证无重复条目（vault-ingestion 修改幂等场景）
- [x] 3.5 去重：指纹完全重复 + 语义相似度 ≥0.92 标记疑似重复并输出合并建议、不删；手动验证两篇近重复笔记被标记且均保留（vault-ingestion 语义重复场景）
- [x] 3.6 内嵌图片 OCR：笔记含截图时 OCR 文字并入可检索内容；手动验证搜图中词命中该笔记（vault-ingestion 含截图场景）
- [x] 3.7 watchdog 监听：新增/修改触发索引（去抖、忽略 `.obsidian/`）、删除移除索引；手动操作文件后验证索引同步（vault-ingestion 新笔记/删除场景）
- [x] 3.8 首次全量索引 CLI 命令，对现有 vault 跑一次全量；验证 vault 全部 `.md` 入库且可检索

## 4. RAG 问答 + 最小前后端（主闭环）

- [x] 4.1 检索召回：问题 `embed` → numpy 余弦检索 top-k；手动验证相关笔记被召回排序（rag-qa 相关召回场景）
- [x] 4.2 带引用生成：召回片段作上下文 + 对话模型生成，附来源路径/标题；手动验证回答含来源引用（rag-qa 正常问答场景）
- [x] 4.3 无内容不编造：召回不足时返回"未在知识库找到相关内容"；手动验证空库提问返回该提示而非编造（rag-qa 无相关内容场景）
- [x] 4.4 FastAPI 路由 `POST /api/ask`（问题→回答 JSON）；用 `curl` 验证返回带引用回答
- [x] 4.5 前端问答页（输入框 + 回答 + 来源列表）；浏览器手动提问验证得到带引用回答

## 5. 截图入口（screenshot-ingestion）

- [x] 5.1 全局快捷键 + pystray 托盘常驻（触发截图/看状态/退出）；手动验证按快捷键或点托盘进入截图选择（screenshot-ingestion 快捷键/托盘场景）
- [x] 5.2 截图区域选择 + 取消处理；手动验证取消不入库（screenshot-ingestion 取消场景）
- [x] 5.3 截图送 `vision` OCR → 作为"截图笔记"入库（带原图引用、时间戳），纳入去重与聚合；手动验证搜 OCR 词召回截图原图（screenshot-ingestion 截图入库场景）

## 6. 主题聚合与 MOC（topic-clustering）

- [x] 6.1 主题聚类（基于向量聚类 + 主题标签生成）；手动验证相关笔记归入同主题（topic-clustering 自动分组场景）
- [x] 6.2 MOC 生成写 `vault/.obsidian-rag/moc/`、不修改原笔记；手动验证 MOC 生成且原笔记内容不变（topic-clustering MOC 写入场景）
- [x] 6.3 MOC 增量更新：笔记增删后更新对应 MOC；手动验证笔记删除后 MOC 同步（topic-clustering 增量更新场景）
- [x] 6.4 检索合并视图：同主题多篇命中返回合并视图（相关列表 + 主题摘要）；手动验证同主题命中返回合并视图（topic-clustering 同主题命中场景）

## 7. 间隔重复抽问（reinforcement）

- [x] 7.1 问答对生成：基于笔记调对话模型生成问答对卡片、关联源笔记；手动验证卡片可溯源（reinforcement 从笔记生成卡片场景）
- [x] 7.2 卡片库 SQLite（`data/app.db`：卡片/复习历史/掌握度）+ FSRS 调度；手动验证新卡片入库有下次复习时间（reinforcement 到期复习场景）
- [x] 7.3 间隔重复抽问交互（前端弹卡片→用户评级→更新调度）；手动验证"掌握差"评级缩短间隔（reinforcement 评级影响调度场景）

## 8. AI 主动测验（reinforcement）

- [x] 8.1 薄弱主题判定（掌握度低 → 薄弱）；手动验证存在薄弱主题时可触发（reinforcement 主动出题场景）
- [x] 8.2 主动出题交互（针对薄弱主题调对话模型出题→用户作答→更新掌握度）；手动验证作答后掌握度更新（reinforcement 主动出题场景）

## 9. 知识图谱可视化（knowledge-graph）

- [x] 9.1 图构建：`[[wikilink]]` 显式边 + 主题聚类隐式边，节点=笔记；手动验证图含两类边（knowledge-graph 构建场景）
- [x] 9.2 前端 vis.js 节点图（拖拽/缩放/点击跳转、按主题着色）；手动验证点击节点跳转、同主题同色（knowledge-graph 节点跳转/主题着色场景）
- [x] 9.3 增量同步：笔记增删后图更新；手动验证笔记新增后图新增节点边（knowledge-graph 增量同步场景）

## 10. 集成与启动

- [x] 10.1 统一启动入口（FastAPI 服务 + watchdog 监听 + pystray 托盘同进程）；验证单命令启动后三部分均运行
- [x] 10.2 端到端冒烟（新笔记→自动入库→问答命中→截图入库可搜→抽问生成）；手动验证全链路打通
