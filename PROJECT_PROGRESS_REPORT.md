# 陈家祠金牌导游 Agent：现阶段技术进度与业务逻辑说明

> 学习、答辩和项目全貌说明已独立迁移至 `PROJECT_LEARNING_AND_DEFENSE_GUIDE.md`。本文件只维护当前实现进度、验证状态与后续事项，避免将“计划”误写为“已实现”。

> 报告日期：2026-07-25；最近状态同步：2026-08-02
> 代码基线：`main == origin/main == 56688f7d9bda505da2b426021553afb54a05c5ce`；工作树干净。
> 阅读目的：小组协作、答辩讲解、面试复盘与后续迭代。  
> 重要原则：本报告将“已实现”“已验证”“数据准备中”“仅需求规划”分开描述，不将产品设想表述为已上线能力。

---

## 当前执行状态（2026-08-02）

- 当前处于 P0“可信基线与正确性收口”；CA-00 行为矩阵已建立，但尚未启动 AgentDecision、Tool Registry、Policy Gate 或 Executor 生产迁移。
- `56688f7` 上完整回归 `770/770` 通过，P0 定向安全/游客输出矩阵 `59/59` 通过。Gate 0 为 `conditional_pass`，原因是当前提交尚缺 LangSmith 实链证据，且 P1-04 仍有外部空间数据阻塞。
- P1-12C1（到达同义）与 C4（完成本站同义）均已独立提交并完成自动化回归；两者仍待当前提交的 LangSmith 复测。P1-04 继续是空间数据负责人确认前的外部阻塞。
- 既有“已实现/待 LangSmith”记录保持其原始验证范围；没有实际 commit、thread ID 和 Trace URL 的人工结果仍只作为待复核证据。

---

## P0-03 / CA-00 Gate 0 行为基线（2026-08-02）

- 基线提交：`56688f7d9bda505da2b426021553afb54a05c5ce`；完整回归 `770/770`、P0 安全/游客输出矩阵 `59/59` 均通过。
- 行为矩阵：`data/chen_clan_academy/evaluation/p0_gate_0_behavior_matrix_v1.yaml`，覆盖状态、画像、安全、控制、重规划、问答证据、游客输出、线程隔离和多意图边界。
- 结论：`conditional_pass`。未将缺少当前 Trace 的项写作已人工验收；P1-04 空间别名/审核节点冲突保持 `blocked_external_data_review`。
- 下一步：负责人审核该冻结内容并补齐矩阵对应的 LangSmith 记录后，才可判定是否提升为 `passed` 并开启受控 Agent 架构阶段。

---

## 1. 项目一句话定位

本项目是一个以**陈家祠静态、人工整理知识快照**为事实边界的“金牌导游 Agent”原型。当前已完成本地中文 RAG、LangGraph Agent 接入、来源/时效元数据、离线质量评估与性能剖析；同时完成了路线规划所需的第一版人工审核空间网络和装饰位置映射候选表。

当前系统最稳定、可演示的核心能力是：

```text
游客提问 → 本地混合检索 → 返回带来源的证据 → DeepSeek 整理为导游式回答
```

路线网络目前可以求“已审核边中的最短预计步行路径”，但**尚未接入 Agent 自动生成完整游览路线**；多语言、拍照、论文比较、周边推荐、成就寄语均仍是需求或数据准备阶段。

---

## 2. 当前架构总览

```text
                     ┌──────────────────────────────┐
                     │      游客问题 / 对话历史      │
                     └──────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │ LangGraph Agent 状态图          │
                    │ direct_rag / llm_think / tool  │
                    └───────┬─────────────────┬──────┘
                            │                 │
                 明确馆内事实│                 │开放式/非馆内问题
                            │                 │
                    ┌───────▼───────┐   ┌─────▼──────┐
                    │ 本地 RAG 工具  │   │ DeepSeek LLM│
                    └───────┬───────┘   └─────┬──────┘
                            │                 │
              ┌─────────────▼─────────────────▼─────────────┐
              │ BGE 稠密检索 + BM25 + RRF + 条件 CrossEncoder │
              └─────────────┬───────────────────────────────┘
                            │
              ┌─────────────▼───────────────────────────────┐
              │ Chroma 持久化向量索引 + 内存 BM25 + Markdown   │
              └─────────────────────────────────────────────┘

并行建设中的空间数据链路：

```text
官网 720 导览图 / 官网路线
        ↓ 人工核验
marker_inventory_v0.csv（节点） + edges_v0.csv（可行边）
        ↓
NetworkX 最短路径（预计步行时间）
        ↓
装饰位置候选表（待人工审核） → 后续点位讲解与路线规划器
```

---

## 3. 已实现业务逻辑

### 3.1 静态知识库与事实边界

**实现状态：已完成。**

知识库位于 `data/chen_clan_academy/knowledge/`，当前涵盖：

- 基础信息、历史建筑、参观服务；
- 票务/公告快照；
- 七类建筑装饰工艺；
- 装饰单件条目（`08_ornament_items.md`）；
- 约 105 条装饰题材与位置索引（`09_ornament_locations.md`）。

`rag_ingestion.py` 只加载 `knowledge/` 下的 Markdown：

- `raw/` 是原始资料，默认不参与问答；
- `evaluation/` 是评测集，默认不参与问答；
- 这避免评测问题或未加工原始资料“泄漏”进检索答案。

每个 `KnowledgeChunk` 保存：

```text
chunk_id / content / document / title_path / category / source_ids
status / valid_from / valid_to / verified_at
```

这使回答不仅能给出内容，还能说明来源编号、文件来源与资料快照的时效限制。

### 3.2 分块策略

**实现状态：已完成。**

分块以 Markdown 标题边界为主，而非固定字数切片：

- 普通知识文档按 H2 分块；
- `08_ornament_items.md`：每个 `## 装饰名称` 是一个独立块；
- `09_ornament_locations.md`：每条“名称（工艺）”位置索引是独立块；
- `07_ornament_crafts.md`：每种工艺是独立块；
- `04_events_notices.md` 额外按 H3 拆分，避免不同日期公告混入同一块。

此设计解决了两个实际问题：

1. “百鸟朝凤”“梁山聚义”等专名可以直接定位到单件装饰；
2. 同名但工艺不同的条目不会因共享大段文本而混淆。

历史建筑文档还有节级来源映射。例如“历史沿革”和“建筑格局与参观亮点”会绑定比整篇文档更精确的 `source_ids`。

### 3.3 本地混合检索

**实现状态：已完成。**

检索模块为 `rag_retrieval.py`，当前是“BM25 + 稠密检索 + RRF + 条件精排”的混合 RAG。

| 层次 | 技术 | 作用 |
| --- | --- | --- |
| 向量检索 | `BAAI/bge-small-zh-v1.5` + Chroma | 处理“灰塑是什么”“建筑布局特点”等语义相近但词面不完全相同的问题 |
| 关键词检索 | `rank-bm25` | 处理专名、工艺名、年份、地名等精确词 |
| 中文轻量分词 | 自定义 Han 字串 + 2–6 字 n-gram | 保留“百鸟朝凤”完整专名，同时保留“百鸟”等子串召回 |
| 融合 | Reciprocal Rank Fusion（RRF，默认 `k=60`） | 只融合排序名次，避免 BM25 分数与向量相似度分数无法直接比较 |
| 精排 | `BAAI/bge-reranker-base` CrossEncoder | 对少量候选做 query–document 相关性重排 |
| 向量库 | Chroma PersistentClient，余弦空间 | 本地持久化向量索引；索引可由 `build_index.py` 重建 |

可检索文本不是只放正文，而是将“叶子标题、类别、来源编号、正文”组合为 `retrieval_text`。这样既能按“百鸟朝凤”检索，又不会把所有条目共享的 H1 总标题重复注入、造成泛化噪声。

工程规则：`RAG 检索与回答规则`、`来源与核验` 等编辑说明不作为游客事实证据入库，防止模型把内部操作说明回答给游客。

### 3.4 结果证据化与生成约束

**实现状态：已完成。**

检索结果封装为 `RetrievedEvidence`，返回：

```text
chunk_id / content / score / retrieval_methods / document / title_path
category / source_ids / status / valid_from / valid_to / verified_at
```

`agent_graph.py` 的 RAG 工具 `chen_clan_academy_rag_search` 返回 JSON 结构化证据。系统提示词明确约束：

- 陈家祠历史、建筑、工艺、服务、票务、公告等事实必须先检索；
- 最终回答只能基于工具返回的 `evidence`；
- 资料冲突、快照、过期、缺证据时必须说明限制；
- 实时信息提醒以馆方最新信息为准；
- 默认回答控制在约 150–300 个中文字符、最多 3 个要点。

这不是数学上绝对保证模型零幻觉，但通过“证据工具 + 系统规则 + 来源展示 + 测试集”降低了无依据扩写风险。

### 3.5 LangGraph Agent 编排

**实现状态：已完成。**

图定义于 `agent_graph.py`：

```text
START
 ├─ 明确馆内事实词 → direct_rag → llm_think（直接基于证据作答）
 └─ 其他问题       → llm_think
                           ├─ LLM 请求 RAG 工具 → rag_tool → llm_think
                           └─ 无工具调用 / 到达上限 → END
```

关键实现：

- `StateGraph` + `AgentState` 保存 `messages`、检索证据、工具循环数和性能指标；
- CLI 对话使用 `MemorySaver`，按 `thread_id` 保存短期会话；
- 给 LangGraph Studio 导出的 `studio_agent_graph` 不带自定义 checkpointer，避免与平台持久化冲突；
- `MAX_TOOL_LOOPS=3` 防止工具循环失控；
- DeepSeek 模型为 `deepseek-chat`，温度 `0`，默认最多 `450` tokens；
- `webapp.py` 是 LangGraph 本地开发服务的 lifespan hook，用于启动时 RAG 预热；
- `langgraph.json` 将 Agent 图和 HTTP app 暴露给 `langgraph dev`。

### 3.6 已实现性能优化与原因

**实现状态：已完成，并有基准脚本。**

最初性能问题主要来自 CPU 加载嵌入模型、CrossEncoder 重排和 Agent 在每轮前额外调用一次 LLM 判断是否需要工具。现有优化如下：

| 优化模块 | 具体方法 | 解决的问题 |
| --- | --- | --- |
| 专名快路 | 当问题包含长度至少 3 的完整条目标题时，直接返回 `exact_title` 匹配 | “百鸟朝凤是什么装饰”不加载嵌入模型与 reranker，实测接近 0 秒 |
| 延迟加载 | 模型、reranker、Chroma collection 在实际需要时才加载 | 导入模块、启动测试不承担模型加载成本 |
| 条件 reranker | `should_rerank()` 仅对“是什么、对比、差异、来源、特点、意义”等歧义/开放问题启用精排 | 普通事实题只跑 BM25 + 向量 + RRF |
| 小候选池 | `DEFAULT_CANDIDATE_LIMIT=4`，只重排前 4 个候选 | CPU CrossEncoder 计算量从先前更大的候选池下降；当前 8 条评测仍为 100% |
| reranker 限制 | `max_length=256`、`batch_size=8` | 控制 CPU 内存和长文本推理成本 |
| 直接 RAG 路由 | 对“陈家祠、灰塑、木雕、月台、百鸟朝凤”等明确领域词跳过首次 LLM 工具选择 | 减少一次网络 LLM 往返与可能的重复工具调用 |
| 服务预热 | `warm_rag_models()` 在 Agent Server lifespan 中加载 embedding 与 reranker | 将首次访客请求的模型冷启动移到服务启动阶段 |
| 回答预算 | 默认 `450` tokens、导游回答提示限制长度 | 降低生成延迟和冗余输出 |
| 性能可观测性 | `performance_metrics` 记录 `direct_rag`、`rag_tool`、`llm_think` 节点耗时 | 能区分“检索慢”还是“LLM 慢” |

已记录的本机基准结果（不同机器、缓存状态和模型下载状态会变化，不能作为通用 SLA）：

| 场景 | 首次 | 同进程热启动 | 解释 |
| --- | ---:| ---:| --- |
| 专名快路：百鸟朝凤 | 约 0.00 s | 约 0.00 s | 不走嵌入和精排 |
| 普通事实：建成年份 | 约 7.21 s | 约 0.03 s | 首次主要包含 embedding 模型惰性加载 |
| 歧义身份：陈家祠是什么 | 约 4.46 s | 约 0.98 s | 条件 reranker 生效 |
| 建筑特点问题 | 约 1.06 s | 约 1.05 s | 条件 reranker 生效 |
| 完整 Agent：陈家祠是什么 | 约 17.39 s | 约 4.19 s | 后者由直接 RAG + 热缓存 + 一次回答生成组成 |

应在答辩中说明：本项目的“首次慢、后续快”是本地 Transformer 模型冷启动的典型特征；预热改善首问体验，但增加服务启动时间和内存占用。

### 3.7 离线质量评估与回归测试

**实现状态：已完成。**

`rag_evaluation.py` 用 8 条独立于知识库正文的查询评估检索，不直接比较生成文本，而是判断正确文档和标题是否出现在结果中。这避免“评测答案被写进语料”造成虚高。

当前固定评测覆盖：

- 陈家祠身份与“书院”名称；
- 1893/1894 建成年份来源差异；
- 建筑布局；
- 月台石雕与灰塑工艺；
- 百鸟朝凤与梁山聚义。

已记录结果：

```text
条件 reranker：Top-1 accuracy 100.0%，Top-3 recall 100.0%（8/8）
关闭 reranker：Top-1 accuracy 87.5%，Top-3 recall 100.0%
强制 reranker：Top-1 accuracy 100.0%，Top-3 recall 100.0%
```

这说明当前小评测集上 reranker 改善了一个“陈家祠是什么”类的歧义排序问题；但 8 条样本很小，不能外推为真实游客问题的总体准确率。

现有单元/回归测试覆盖：

- 摄取范围、独立装饰块、同名不同工艺、过期公告元数据、历史节级来源；
- 中文专名 token、RRF、索引文本、非证据章节排除、精确标题快路、候选池/精排参数；
- 评测匹配规则；
- Agent 工具结构化返回、工具循环上限、直接 RAG 路由、性能指标追加；
- 基准场景覆盖；
- 空间图双向边、入口可达性、官网主链；
- 105 条装饰位置候选完整保留、月台/方向性/未建廊门映射规则。

常用验证命令：

```cmd
python -m unittest -v test_rag_ingestion.py test_rag_retrieval.py test_rag_evaluation.py test_agent_rag.py test_agent_profile.py test_rag_benchmark.py test_spatial_graph.py test_ornament_spatial_mapping.py
python rag_evaluation.py
python rag_benchmark.py
python agent_profile.py "陈家祠是什么？"
```

---

## 4. 空间网络、路线与装饰位置映射

### 4.1 空间网络 v0

**实现状态：数据与最短路径工具已完成；Agent 路线规划未接入。**

文件：

- `data/chen_clan_academy/spatial/marker_inventory_v0.csv`：地图节点；
- `data/chen_clan_academy/spatial/edges_v0.csv`：双向可通行关系；
- `data/chen_clan_academy/spatial/map_manifest_v0.json`：底图来源、像素坐标系与授权提示；
- `spatial_graph.py`：NetworkX 图构建、最短路径、可达性检查；
- `inspect_spatial_graph.py`：命令行人工检查工具。

当前恢复到人工合并前的版本：**40 个节点、39 条边**。边都要求 `direction=both`；当前由 `networkx.Graph` 建模，因此是无向图。

节点以 `node_id` 为稳定主键，中文 `name` 是人工审核辅助名称。边的 `walk_seconds` 为地图/官网路线估算，`time_basis=estimated_from_map_and_official_route` 明确表示“待现场复核”，不能表述为真实计步数据。

示例：

```cmd
python inspect_spatial_graph.py
```

已得到：

```text
大门外 → 前院中部 → 首进正厅 → 月台 → 中进聚贤堂
预计步行时间约 85 秒（地图估算，待现场复核）
```

空间图的当前业务边界：

- 可以在已录入边中按步行秒数选择最短路径；
- 可以检查所有 `guide_stop` 是否从入口连通；
- 尚未考虑开放/封闭、单向限制、无障碍、拥挤、游客偏好、停留讲解时长；
- 估算时间不等于官方或实测导航时间；
- 当前并非室内定位系统，也不根据游客 GPS 自动判断所在点位。

### 4.2 装饰位置到地图点位的候选映射

**实现状态：自动候选生成已完成，人工审核进行中。**

`build_ornament_spatial_candidates.py` 从 `09_ornament_locations.md` 读取每个 H2 条目的原始“摆放位置”，生成：

```text
ornament_id / raw_heading / raw_location / detail_lookup_key
candidate_node_id / candidate_node_name / match_confidence / review_state
reviewer_decision / final_node_id / review_notes
```

最新一次生成统计：

```text
105 条位置记录
candidate_ready=22
review_required=63
needs_manual_mapping=20
```

这是**保守候选**而非自动真值：

- “月台正面”“中进聚贤堂屏风”等明确位置可匹配已有点位；
- “首进西路北面”“后进中路南面”等只映射到厅堂级候选，需要官网地图/图文复核；
- “庆基廊门、昌妫廊门、蔚颖廊门、德表门廊、连廊”等无对应节点时，不强行映射，交给人工选择 `add_node` 或 `skip`。

人工核验规范在 `data/chen_clan_academy/spatial/ANNOTATION_STANDARD.md`。核验逻辑是：

```text
官网 720 导览图 / 官网图文
        ↓
确认装饰实际位置
        ↓
marker_inventory_v0.csv 的 name、node_id、x、y
        ↓
填写 final_node_id 或 add_node / skip
```

`08_ornament_items.md` 用于拿到装饰的详细讲解，不是确定地图点位的唯一依据；程序通过 `detail_lookup_key=题材名（工艺）` 预留后续连接。

### 4.3 当前数据协作风险

工作区存在 `ornament_spatial_candidates_v1.xlsx`。它是方便人工审核的 Excel 文件，但**当前 Python 代码不会读取 Excel，也不会把其人工修改同步回 CSV**。同时，重新运行 `build_ornament_spatial_candidates.py` 会覆盖默认 CSV 输出。

因此在多人审核前，应先约定唯一事实源：

1. 若以 CSV 为主：关闭 Excel 后，将人工结果保存回 `ornament_spatial_candidates_v0.csv`；
2. 若以 Excel 为主：下一步需要实现“Excel 导入/导出或审核结果合并脚本”；
3. 未完成同步前，不应让路线 Agent 使用 Excel 中的人工审核结果。

---

## 5. 当前未实现或未接入能力

以下功能出现在 `PROJECT_REQUIREMENTS.md`，但不能在答辩中说成“当前代码已实现”：

| 能力 | 当前状态 | 缺少内容 |
| --- | --- | --- |
| 完整路线 Agent | 数据基础已开始，未接入 Agent | 点位讲解卡、停留时长、路线选择算法、会话字段 |
| 30/60/深度游 | 官网路线和空间图已录入部分依据 | 标准路线数据、讲解预算、路线评测 |
| 当前点位自动讲解 | 未实现 | `current_stop_id`、审核后的装饰—点位映射、点位 RAG 过滤 |
| 动态联网公告 | 未实现 | 官网抓取/API、日期过滤、变更监控、人工审核 |
| 文献论文知识 | 未实现 | 合法获取、研究摘要卡、观点/证据/限制字段 |
| 建筑比较卡 | 未实现 | 比较对象、维度、来源与不宜下结论边界 |
| 英文/多语言 | 未实现 | 术语表、双语知识卡、翻译质量评测 |
| 拍照打卡与姿势建议 | 未实现 | 审核打卡点卡、场馆规则、构图提示数据 |
| 游览后周边推荐 | 未实现 | POI 卡、实时性提示与来源核验 |
| 游览总结、成就、寄语 | 未实现 | visited 状态、计数规则、成就库、模板库 |
| 真正在线 Web API | 仅有开发服务 hook | 产品前端、用户鉴权、部署与观测方案 |

---

## 6. 当前数据与代码的维护流程

### 6.1 更新静态知识库

```text
来源核验 → 更新 Markdown / source registry → 运行摄取与检索测试
→ python build_index.py → python rag_evaluation.py → 人工检查回答
```

知识 Markdown 改动后必须重建本地索引；`data/chen_clan_academy/index/` 已在 `.gitignore` 中，属于可再生成产物。

### 6.2 更新空间节点或边

```text
先改 marker_inventory_v0.csv 的名称/坐标/类型
→ 检查 edges_v0.csv 是否引用这些 node_id
→ 合并节点时重定向边和已审核 final_node_id
→ 删除自环与重复边
→ test_spatial_graph.py + inspect_spatial_graph.py
```

不要仅凭中文 `name` 重复自动删除节点：蓝点可能代表讲解停留位置，文字标签可能代表建筑空间。是否合并仍需人工结合官网图确认。

### 6.3 更新装饰位置候选

```text
更新节点表后 → 生成候选 CSV → 官网人工核验 → 填 final_node_id
→ 校验 final_node_id 都存在于节点表 → 形成可供路线 Agent 使用的正式映射
```

### 6.4 Git 与敏感信息

- `.env` 不可提交；API Key 仅从环境变量读取；
- 当前 `.gitignore` 已忽略虚拟环境、模型/缓存、Chroma 索引和 LangGraph 本地状态；
- 官网 720 地图在 `map_manifest_v0.json` 中被标注为“公开展示但仓库再发布授权待确认”；提交图片到公开仓库前应确认版权/授权；
- 当前工作区仍可能有未提交的空间代码、地图或 Excel 文件，提交前应执行 `git status` 检查。

---

## 7. 答辩/面试可讲的关键技术点

### 7.1 为什么不用“只做向量检索”

中文景区知识同时包含专名、年份、工艺术语和开放式文化问题。只用向量检索容易损失精确专名；只用 BM25 又会损失语义近似召回。因此采用：

```text
精确标题快路（高精度）
→ BM25（词面召回） + BGE（语义召回）
→ RRF（稳健融合）
→ 条件 CrossEncoder（复杂问题精排）
```

### 7.2 为什么 RRF 不直接加权分数

BM25 分数、余弦相似度、CrossEncoder 分数来自不同模型和量纲，直接相加通常不稳定。RRF 只依据“排名第几”，公式可写为：

```text
RRF(d) = Σ 1 / (k + rank_i(d))，当前 k=60
```

若一个知识块同时被关键词检索和语义检索排在前面，它会获得更高融合分。

### 7.3 为什么是“条件 reranker”

CrossEncoder 更准确但 CPU 成本高。当前规则把它留给“是什么、对比、差异、来源、特点”等容易出现多段候选竞争的问题；专名和简单事实题走快路径。该策略通过评测集确认质量未下降，并使用 benchmark 观察延迟变化。

### 7.4 为什么空间图必须人工审核

平面图像素距离不能证明真实可通行：可能存在门洞、围栏、展厅封闭、台阶和单向管理。因此图模型只录入人工确认或官网路线支持的边；未知信息不伪造为导航事实。NetworkX 只负责在可信边集合中求最短路径。

### 7.5 为什么把论文和比较卡放到后续模块

论文全文涉及版权、观点差异和阅读成本；直接塞入同一个 RAG 会稀释游客事实问答。正确做法是先将论文加工为“研究摘要卡”，包含研究问题、作者观点、证据类型、可讲结论和限制；比较卡也要明确比较维度和证据边界，再按意图单独检索或注入讲解。

### 7.6 建议检索/学习关键词

```text
Retrieval-Augmented Generation (RAG)
BM25 / Okapi BM25
Dense Passage Retrieval (DPR)
Reciprocal Rank Fusion (RRF)
Cross-Encoder Re-ranking / BGE reranker
RAG evaluation: Recall@K, MRR, nDCG, faithfulness, groundedness
LangGraph StateGraph / tool calling / checkpointing
Chroma HNSW cosine similarity
NetworkX shortest path / graph data model
entity resolution / data provenance / human-in-the-loop annotation
```

---

## 8. 推荐的下一步（按依赖顺序）

1. **完成装饰—点位人工审核闭环**：先处理 22 条高置信候选，再处理方向性条目和缺失廊门节点；解决 Excel 与 CSV 的唯一事实源问题。
2. **建立首批点位讲解卡**：优先官网半小时路线的首进正厅、月台、聚贤堂、后进正厅、后进东厅、中进东厅；每张卡绑定 `stop_id`、RAG 条件、必讲主题、30 秒/2 分钟讲解预算。
3. **建立三条固定路线数据**：半小时、一小时、深度游。先用人工路线保证可解释性，再让 Agent 在固定路线内做裁剪与推荐。
4. **把空间图接入 Agent 状态**：新增 `current_stop_id`、`visited_stop_ids`、`selected_route_id`，但仅使用 `approved` 的装饰映射和路线数据。
5. **增加路线评测**：可达性、总时间预算、必看点覆盖、重复回路、闭馆/未知边的安全降级。
6. **再进入差异化内容**：比较卡、论文摘要卡、英文术语表、拍照点卡、周边 POI 和游览总结均应先结构化数据、再接入生成模型。

---

## 9. 当前结论

项目已从“只有需求与资料”的阶段进入“**可运行、可评测、可追溯的静态 RAG Agent 原型**”阶段。RAG 的检索、来源、冲突表达、性能优化和基础 Agent 编排已具备演示价值；空间网络和装饰位置映射为下一阶段路线导游闭环提供了数据基础。

下一阶段的重点不应继续堆叠模型，而应完成：**人工审核空间数据 → 点位讲解卡 → 固定路线 → Agent 状态接入 → 路线评测**。这条路径可控、可展示，也最容易逐步扩展到论文比较、多语言和个性化导游。

---

## 10. 现阶段代码说明

本节按“代码在整体流程中的位置”说明当前文件。标记含义：

- **[核心]**：当前运行链路必经；
- **[优化]**：包含已启用的速度或资源优化；
- **[验证]**：质量、回归或性能验证；
- **[数据]**：人工维护或程序读取的数据契约；
- **[后续接口]**：已做基础准备，但尚未接入完整导游业务。

### 10.1 RAG 构建与检索链路

| 文件 | 所在步骤 | 实现功能 | 关键技术 / 优化 |
| --- | --- | --- | --- |
| `rag_ingestion.py` | 知识文件 → Chunk | 读取 `knowledge/*.md`，按 H2（公告额外按 H3）分块，生成 `KnowledgeChunk`；补充类别、来源、状态、有效期和核验日期。 | **[核心]** 标题语义分块；节级 `source_ids`；排除 `raw/`、`evaluation/`。 |
| `rag_retrieval.py` | Chunk → 索引 / 问题 → 证据 | 构建、加载和查询 Chroma；同时执行 BM25、向量检索、RRF、可选 CrossEncoder 精排；返回 `RetrievedEvidence`。 | **[核心][优化]** `BAAI/bge-small-zh-v1.5`、Chroma cosine、BM25、中文 2–6 字 n-gram、RRF(k=60)、`BAAI/bge-reranker-base`；专名精确标题快路；条件 reranker；候选池 4；模型惰性加载；reranker 长度/批次限制。 |
| `build_index.py` | 知识更新后 | 调用 retriever 的 `build()`，将当前知识 Markdown 重建为 Chroma 持久化索引与 `manifest.json`。 | **[核心]** 索引是可再生成产物，不提交 Git。 |
| `inspect_retrieval.py` | 人工检查 | 用预置问题打印前三条证据、来源、检索方法和摘要。 | **[验证]** 用于发现“召回了什么”，不替代自动评测。 |
| `rag_evaluation.py` | 离线质量评估 | 以 8 个独立查询检查目标文档与标题是否进入 Top-1 / Top-3；支持关闭、强制 rerank 和调整候选池。 | **[验证]** 指标为 Top-1 accuracy、Top-3 recall；用于检验优化是否损害当前基准。 |
| `rag_benchmark.py` | 检索性能评估 | 分别测专名快路、普通事实、歧义精排、比较问题的首次与热启动耗时。 | **[验证][优化]** 区分模型冷启动与同进程缓存后的实际查询耗时。 |

RAG 的典型执行顺序：

```text
knowledge/*.md
→ rag_ingestion.py
→ build_index.py
→ Chroma + manifest.json
→ rag_retrieval.py.search()
→ RetrievedEvidence
```

### 10.2 Agent、模型调用与性能观测

| 文件 | 所在步骤 | 实现功能 | 关键技术 / 优化 |
| --- | --- | --- | --- |
| `agent_graph.py` | 游客问题 → 最终回答 | 定义 `AgentState`、RAG 工具、`direct_rag`、`llm_think`、`rag_tool` 三个节点及路由；调用 DeepSeek，并保留会话和节点耗时。 | **[核心][优化]** LangGraph `StateGraph`；`MemorySaver`；工具循环上限 3；证据约束提示词；`should_direct_rag()` 关键词直达检索，跳过一次工具选择 LLM；默认 450 tokens；性能指标 `performance_metrics`。 |
| `agent_profile.py` | 完整链路性能检查 | 连续执行同一问题，输出总耗时、每个图节点的耗时和回答。 | **[验证][优化]** 判断瓶颈来自 `direct_rag`/`rag_tool`、LLM 工具决策还是最终回答生成。 |
| `webapp.py` | 本地 Agent Server 启动 | 注册 Starlette lifespan；在服务 worker 启动时执行 `warm_rag_models()`。 | **[优化]** 预加载 embedding 与 reranker，将冷启动从首个游客请求移至服务启动阶段。 |
| `langgraph.json` | LangGraph Studio / dev server 配置 | 声明依赖、`.env`、导出的 `studio_agent_graph` 和 HTTP app。 | **[核心]** Studio 版本图不使用自定义 checkpointer，由平台负责持久化。 |
| `.env` | 本地运行配置 | 保存 `DEEPSEEK_API_KEY`、可选 LangSmith / RAG 参数。 | **[配置]** 不得提交。 |
| `.env.example` | 配置模板 | 提醒所需环境变量，不应包含真实密钥。 | **[配置]** 用于团队复制配置。 |

Agent 的典型执行顺序：

```text
用户消息
→ should_direct_rag() 命中明确馆内事实词？
   ├─ 是：direct_rag → llm_think（基于已有 evidence 回答）
   └─ 否：llm_think → 可能调用 rag_tool → llm_think
→ 最终回答
```

### 10.3 空间网络与路线数据准备

| 文件 | 所在步骤 | 实现功能 | 关键技术 / 注意事项 |
| --- | --- | --- | --- |
| `spatial_graph.py` | 空间节点 + 边 → 路径 | 从 CSV 构建 NetworkX 无向图；提供 `shortest_route()` 与 `unreachable_guide_stops()`。 | **[核心][后续接口]** 以 `walk_seconds` 为权重；`time_basis` 标明估算/实测；只接受双向边；不臆造室内导航。 |
| `inspect_spatial_graph.py` | 人工空间检查 | 从入口到目标点打印节点、边、预计步行时间和不可达讲解点。 | **[验证]** 用于审核连边及地图估时。 |
| `data/chen_clan_academy/spatial/marker_inventory_v0.csv` | 空间数据源 | 保存节点的 `node_id`、`name`、类型、像素坐标、来源、备注。 | **[数据]** `node_id` 是稳定主键；边和最终装饰映射必须引用它。 |
| `data/chen_clan_academy/spatial/edges_v0.csv` | 空间数据源 | 保存 `from_node_id`、`to_node_id`、双向关系、估算步行秒数、时间依据和证据。 | **[数据]** 路线图的真实依据；删改节点前必须先处理引用。 |
| `data/chen_clan_academy/spatial/map_manifest_v0.json` | 地图溯源 | 保存官网图来源、图片尺寸、坐标系、方位审核状态与版权提示。 | **[数据]** 官网公开展示不等于可公开再发布。 |
| `data/chen_clan_academy/spatial/spatial_review_log.md` | 人工审核记录 | 记录蓝点、红点、方位和可通行性审核事项。 | **[数据]** 防止图像识别推断被误当作现场事实。 |
| `data/chen_clan_academy/spatial/README.md` | 数据说明 | 说明空间节点、边、坐标与人工核验约束。 | **[数据]** 供后续维护人员理解。 |

### 10.4 装饰位置映射与人工审核

| 文件 | 所在步骤 | 实现功能 | 关键技术 / 注意事项 |
| --- | --- | --- | --- |
| `build_ornament_spatial_candidates.py` | 装饰位置 → 候选地图点 | 解析 `09_ornament_locations.md` 的 H2 条目与“摆放位置”；用保守规则生成候选节点、节点中文名、置信度和人工审核列。 | **[核心][后续接口]** 105 条保留；不匹配的廊门/连廊不会被强行归点；可重复运行。 |
| `data/chen_clan_academy/spatial/ornament_spatial_candidates_v0.csv` | 人工审核工作表 | 保存原始位置、程序候选、最终节点和人工备注。 | **[数据]** 只有人工确认的 `final_node_id` 将来才应进入路线 Agent。重新生成会覆盖默认 CSV。 |
| `data/chen_clan_academy/spatial/ANNOTATION_STANDARD.md` | 人工审核规范 | 定义 `accept`、`change`、`add_node`、`skip` 和官网核验步骤。 | **[数据]** 最终点位只能选自 `marker_inventory_v0.csv` 的 `node_id`。 |
| `ornament_spatial_candidates_v1.xlsx` | 人工审核辅助文件 | 方便用 Excel 筛选和填写。 | **[数据][风险]** 当前代码不读取 Excel；其人工修改不会自动回写 CSV。 |

### 10.5 测试文件

| 文件 | 验证对象 | 主要断言 |
| --- | --- | --- |
| `test_rag_ingestion.py` | 摄取与元数据 | 只加载 curated knowledge；装饰独立块；同名不同工艺可区分；过期公告保留日期；历史节来源精确。 |
| `test_rag_retrieval.py` | 检索辅助逻辑 | 中文专名 token、RRF、检索文本、非证据规则、专名快路、条件 reranker、候选池和 CPU 参数。 |
| `test_rag_evaluation.py` | 评测规则 | 目标必须同时匹配文件和标题，防止“同主题但错文档”通过。 |
| `test_rag_benchmark.py` | 性能基准覆盖 | 保证 benchmark 保留快路、普通路径和精排路径。 |
| `test_agent_rag.py` | Agent 工具 | RAG 工具返回结构化 JSON evidence。 |
| `test_agent_profile.py` | Agent 优化逻辑 | 性能指标不修改原状态；回答预算；工具循环上限；明确馆内事实词直达 RAG。 |
| `test_spatial_graph.py` | 空间网络 | 双向边、入口到所有讲解点可达、官网主链经过首进正厅/月台。 |
| `test_ornament_spatial_mapping.py` | 位置候选生成 | 105 条位置均保留；月台高置信候选；方向性条目待审核；未建廊门不强行匹配。 |

### 10.6 项目、依赖与说明文件

| 文件 | 作用 |
| --- | --- |
| `requirements.txt` | 运行依赖：LangGraph、LangChain、DeepSeek 集成、Chroma、sentence-transformers、BM25、NetworkX。 |
| `pyproject.toml` | Python 项目元信息；声明可打包模块。 |
| `README.md` | 快速运行、索引构建、评测、性能检查和 Git/Gitee 基本入口。 |
| `PROJECT_REQUIREMENTS.md` | 产品需求、未来模块、验收标准和路线图；不是当前能力实现清单。 |
| `PROJECT_PROGRESS_REPORT.md` | 本报告；说明当前真实代码状态、优化、边界和后续顺序。 |
| `.gitignore` | 排除密钥、虚拟环境、模型缓存、Chroma 索引、LangGraph 本地状态和编辑器文件。 |

### 10.7 代码阅读推荐顺序

新成员最适合按下列顺序阅读：

```text
README.md
→ PROJECT_PROGRESS_REPORT.md
→ rag_ingestion.py
→ rag_retrieval.py
→ build_index.py / rag_evaluation.py / rag_benchmark.py
→ agent_graph.py / agent_profile.py / langgraph.json
→ marker_inventory_v0.csv / edges_v0.csv / spatial_graph.py
→ build_ornament_spatial_candidates.py / ANNOTATION_STANDARD.md
→ 对应 test_*.py
```

这样能先理解“事实如何进入 RAG”，再理解“Agent 如何调用 RAG”，最后理解“路线数据如何为下一阶段准备”。

## 11. 优化策略流程补充
应以“用户实际使用的端到端体验”为主，也就是以 LangGraph / LangSmith 调试界面发消息的耗时作为最终优化目标；控制台测试用于定位到底是哪一层慢。
两者测到的不是同一件事。
控制台 chat()
用户问题
→ Agent 图
→ RAG / DeepSeek
→ 输出
LangGraph / LangSmith 界面
浏览器提交
→ 本地 LangGraph Server HTTP 接收
→ 可能触发 reload / worker / lifespan
→ Agent 图
→ RAG / DeepSeek
→ LangSmith trace 上报
→ HTTP/SSE 返回浏览器并渲染
主要差异：
维度	控制台 agent_profile.py	LangSmith / 调试界面
Python 进程	同一进程连续运行，可利用热缓存	可能是服务 worker；改代码后 reload 会重启
RAG 模型	第二次通常已在内存	若 worker 重启，需重新加载 embedding / reranker
HTTP 网络层	没有	有本地 HTTP、浏览器传输和页面渲染
LangSmith	通常不一定记录完整 trace	记录节点、输入输出与 trace，上报有额外开销
适合回答的问题	哪个模块慢	游客实际等待多久

所以优化策略应当是：
用 agent_profile.py 分解耗时
看 direct_rag、rag_tool、llm_think 分别耗时多少，定位瓶颈。

用 LangSmith 界面验证真实体验
看首次提问与第二次提问，并且不要在刚改完代码、服务正在 reload 时下结论。

记录两套指标  
组件性能：RAG 冷启动 / 热启动、reranker 耗时、LLM 生成耗时  
端到端性能：浏览器发送到页面显示完整回答的时间

你目前项目已经做了检索侧优化。若控制台热启动约 4 秒，但界面明显更慢，优先怀疑：
langgraph dev 因文件变化自动 reload，导致 RAG 重新预热；
服务启动时 warm_rag_models() 尚未完成；
LangSmith trace 上报网络慢；
浏览器界面等待完整回答后才一次性显示，而不是流式展示；
DeepSeek API 本身波动。
结论是：控制台结果不能替代界面体验，但它最适合找原因；界面耗时才是最终优化验收指标。下一步可在 LangSmith trace 中分别查看 direct_rag / rag_tool / llm_think 的节点时长，与 agent_profile.py 输出逐项对比。

## 12. 路线规划与点位讲解包阶段总结（2026-07-25）

### 12.1 已完成能力

路线模块已从“人工审核空间网络”推进为可执行的确定性路线规划 v1：

```text
游客时长/兴趣请求
→ 已审核路线模板选择
→ NetworkX 最短路径展开
→ 步行、讲解、观察、互动、缓冲时间预算
→ LangGraph direct_route 输出完整路线
```

路线不依赖语言模型猜测地图。模型只在后续事实问答或点位讲解中使用；当前路线输出由
`direct_route` 确定性生成，因此不会遗漏站点、编造边或因模型输出截断而失去后半段路线。

### 12.2 数据与路线规则

- `ornament_spatial_mapping_v1.csv` 已有 105 条经人工审核的装饰—点位关联。
- `route_stop_catalog_v1.csv` 按文物密度筛选：6 个核心讲解站（9 件以上文物）、6 个可选站（4–7 件文物）和入口开场点。
- 前庭与月台属于同一“前轴观察组”；每条路线只能选择一个作为正式讲解停留站，途经另一个节点不等于重复讲解。
- 0 件已关联讲解文物的官方展厅、临展厅和文创空间不作为路线讲解候选，仅可作为通行空间。
- 所有边仍标识为官网地图/路线估算；对外必须提示待现场复核。

### 12.3 三条路线与验证结果

| 路线 | 正式讲解站 | 当前总时间 | 结论 |
| --- | --- | --- | --- |
| 30 分钟高密度精华线 | 前院中部、月台、前东庭 | 约 28 分钟 | 通过 |
| 60 分钟装饰工艺与故事线 | 前院中部、前庭、前西庭、后西庭、后庭 | 约 59 分钟 | 通过 |
| 90 分钟高密度装饰深度线 | 前院中部、月台、前东庭、后东庭、后庭、后西庭 | 约 89 分钟 | 通过 |

总时长由步行、讲解、游客观察、提问/比较互动和换站缓冲组成。它比仅按讲解文本长度估算更接近实际导览体验。

### 12.4 Agent 接入与配置修正

- `agent_graph.py` 增加 `direct_route` 节点、`selected_route_id` 和 `active_route_plan` 状态。
- 用户提出路线、时长或游览顺序需求时跳过 LLM 工具选择，先运行确定性规划器；路线回答不依赖 LLM 二次改写。
- `.env` 现由 `python-dotenv` 自动加载；`DEEPSEEK_MODEL` 可配置，默认 `deepseek-v4-flash`，以适配当前服务端模型名。
- 路线输出已人工 smoke test：30 分钟与 60 分钟请求均返回完整站点、时间拆分和现场复核提示。

### 12.5 点位讲解包与未来扩展

`build_node_guide_cards.py` 已生成 `node_guide_cards_v1.json`，包含 12 个已审核讲解点的文物清单、工艺分布、讲解焦点和 RAG 查询提示。最终事实仍必须使用现有 RAG 取证。

每个讲解包均预留以下空接口：

```text
research_summary_card_ids
comparison_card_ids
term_card_ids
photo_spot_card_ids
glossary_ids
```

这些接口让学术摘要、比较卡、术语卡、打卡点卡和多语言术语能逐步接入；除经审核的打卡点外，扩展卡默认不改变路线走法。

### 12.6 本阶段新增文件

| 文件 | 功能 |
| --- | --- |
| `route_planner.py` | 选择路线模板、展开最短路径、计算时间预算。 |
| `inspect_route_plan.py` | 打印完整节点、边与时间，供人工审核。 |
| `build_node_guide_cards.py` | 从审核映射表生成点位讲解包。 |
| `test_route_planner.py` | 验证路线可达、互斥规则、时间模型与推荐结果。 |
| `test_node_guide_cards.py` | 验证讲解包数量、月台文物、RAG 规则和扩展接口。 |
| `data/chen_clan_academy/routes/` | 路线点位目录、模板、策略、讲解包和未来评估数据。 |
| `COLLABORATION_GUIDE.md` | 三人协作的文件中文名、边界、卡片接口与交接流程。 |

### 12.7 下一阶段

路线执行状态：记录 `current_stop_id`、`visited_stop_ids` 与 `skipped_stop_ids`；游客到达某点后，按该点讲解包约束 RAG 检索；支持“我在月台”“跳过这里”“还剩 20 分钟”等重规划请求，并新增端到端路线评估集。

## 13. A0 动态路线与 Agent 接入阶段（2026-07-25）

### 13.1 已完成能力

- 动态路线限定在 20–120 分钟、已审核且文物数量不少于 4 件的讲解点；支持兴趣词、排除讲解点、点位互斥、路径可达和时间上限。
- 选点不由 LLM 决定。算法按“文物/工艺/兴趣价值－当前绕路成本”进行束搜索，再使用单点局部替换和 2-opt 调整顺序。
- 讲解、观察、互动和步行分别计时；完整路径统一回到前院出口区 `stop_front_courtyard_center`，回程只算通行，不重复讲解。
- 基准用例验证了 30/60/90 分钟人工锚点与 45/75 分钟动态组合：锚点时长如遗漏人工关键点则回退人工路线，非锚点时长使用动态组合。
- `agent_graph.py` 的 `direct_route` 已接入：精确 30/60/90 分钟走人工锚点，其他合法时长走动态路线；二者均绕过 LLM 选点。

### 13.2 A0-5 / A0-6 验收资产

| 文件 | 用途 |
| --- | --- |
| `route_benchmark.py` | 输出动态路线与人工锚点的预算、关键点覆盖、兴趣得分及回退结论。 |
| `route_review.py` | 生成 JSON 与 Excel 可打开的 CSV 人工审核表。 |
| `route_benchmark_cases_v1.json` | 30、60、90 分钟锚点和 45、75 分钟动态路线基准用例。 |
| `route_review_results_v1.csv` | 人工审核：讲解价值、顺序、无意义折返、主题重复与时间真实性。 |

### 13.3 当前边界

路线规划只使用空间图、点位目录和文物—点位映射。论文摘要卡、比较卡、术语卡和打卡点卡尚未进入选点评分；它们后续只能通过已审核 `card_id` 为讲解内容增益，不能改变空间边和 `node_id`。

### 13.4 TourState 阶段 A 当前进度

- 已完成会话内 `TourState`：路线初始化、到达、下一站、跳过、结束与状态不变量测试。
- 已完成确定性下一站导航：从当前位置以已审核空间边计算路径、步行时间和 `guide_focus`。
- 已完成有限重规划：仅处理跳过点和剩余时间变化；保留原路线后续顺序，不重新加入访问/跳过点，预算不足时按 optional、低优先级 core 的顺序删减。
- 已接入 LangGraph：`direct_route` 初始化状态；`arrive_at_stop`、`next_stop`、`skip_stop`、`replan_time`、`finish_tour` 为确定性节点。当前点的详细事实讲解尚未接 RAG，留待下一阶段讲解编排器。

### 13.5 后续路线图

详见 `TOUR_GUIDE_ROADMAP.md`：后续将先补按钮/连续导游交互与“游览中 RAG 问答后恢复导游”，再建设 `StopProgram` 讲解编排器、最小用户画像和按 `card_id` 接入的研究/比较/术语/打卡知识卡。

### 13.6 A1-0 交互契约冻结

已新增 `TOUR_INTERACTION_CONTRACT.md`，作为 A1-1 至 A1-4 的唯一交互契约。它冻结了 8 个白名单事件、统一响应包、错误码、前置条件、状态转移、幂等规则和“禁止按时间自动完成”的约束；其中 A1-3 补充的 `explanation_finished` 只表示讲解播放结束，不表示游客完成参观。

现有 TourState 首版中“到达即计入已访问”的行为与连续导游记录语义不完全一致。契约已明确：从 A1-1 起改为“到达 → 讲解/等待确认 → `confirm_stop_complete()` 才计入 `visited_stop_ids`”；本 A1-0 阶段不改运行代码，因此已通过的 A 阶段测试仍保持有效。

### A1-2 文本导游意图路由（已实现并验证）

项目负责人已使用项目 `.venv` 执行本轮验证：A1-2 核心文本识别与 Agent 集成共 38 项通过；完整回归共 90 项通过。因此 A1-2 可以表述为“已实现并完成当前回归验证”。

- `tour_intent.py` 新增纯结构化 `TourIntentDecision`、审核节点解析、歧义/多意图澄清，以及供未来 schema 化 LLM 建议使用的事件/参数验证器；
- `agent_graph.py` 路由固定为：导游事件优先，其次新路线、RAG、开放对话或澄清；
- `tour_event` 只调用 `tour_interaction.handle_tour_event()` 并采纳其返回快照；`clarification` 不输出 TourState 更新；
- 已新增 `test_tour_intent.py`、更新 Agent 路由集成测试；当前 38 项核心测试和 90 项完整回归均为 `OK`。

### A1-3 连续导游回复与按钮协议（已实现并验证）

- 契约新增 `explanation_finished`：只将 `explaining` 切换至 `awaiting_confirmation`，不写入已访问、不删除剩余点，也不会结束最后一站；
- 新增 `tour_presenter.py`，以纯函数将适配层结果转为稳定的 `message / phase / actions` 协议；每个 `actions[].id` 都是冻结事件，中文文案不参与前端逻辑判断；
- `agent_graph.py` 新增 `tour_presentation` 响应字段，路线初始化、事件结果和澄清结果均可提供 UI 中立展示数据；
- `replan_time` 动作附带 `input_schema.available_minutes`，A1-3 不新增“再停留一会”状态事件；
- 项目负责人已使用 `.venv` 完成 101 项本机回归，结果均为 `OK`。

### 13.7 A1-1 统一交互事件适配层

- 新增 `tour_interaction.py`：所有游览事件经 `handle_tour_event()` 进入，返回冻结契约规定的 `ok`、`event`、`code`、`message`、TourState、交互状态、`data` 与 `idempotent` 响应包。
- 交互状态独立保存 `pending_stop_id`、`tour_mode`、`stop_phase`；不污染 TourState 的路线事实字段。
- 已废止“到达即完成”：计划内到达仅记录当前位置并进入 `explaining`；只有 `confirm_stop_complete()` 会将该点从 remaining 移入 visited。最后一站也必须确认后才结束。
- 保留冻结契约的 `self_arrival`：合法但非 pending 的空间点会记录真实当前位置与 `last_arrival_kind=self_arrival`，但不改变正式路线顺序、已访问或跳过记录。
- 有当前未确认讲解点时，`next_stop` 会返回结构化 `invalid_phase`；重规划保留该点一次、不将其作为新候选重复加入；跳过当前点只进入 skipped。
- `agent_graph.py` 的既有确定性到达、下一站、跳过、改时间和结束节点已改为调用适配层。A1-2 已实现自然语言“确认完成”意图；A1-3 已完成并验证连续导游展示协议，按钮只使用冻结事件 ID。
- 已使用项目虚拟环境完整路径运行 62 项回归测试，覆盖 TourState、A1 交互、导航、重规划、Agent、路线、空间图、动态路线、锚点基准与人工审核报告；结果均为 `OK`。

### 13.8 A1-4 导游交互端到端验收（已实现并验证）

- 新增 `test_tour_interaction_e2e.py`，以离线方式串联确定性路线初始化、`tour_intent`、`agent_graph` 受控路由、唯一事件适配层和 A1-3 展示协议；不调用真实 LLM、RAG 或前端。
- 验收场景覆盖：计划内到达到确认完成的完整生命周期、最后一站确认前不自动结束、自主到达后继续正式路线、跳过后按剩余时间重规划、文本事件经 Agent 到适配层、歧义/多意图/未知点位零状态修改、详情占位无副作用，以及三类重复事件幂等。
- 本轮不新增生产能力，不修改稳定 `node_id`、空间边、路线模板、路线算法或任何知识卡。项目负责人已完成完整 141 项本机回归，结果均为 `OK`；A1 阶段正式完成，A2 尚未开始。

### 13.9 A2 游览中 RAG 问答与导游上下文恢复（已实现并验证）

- 新增 `tour_qa.py`：对“这里有什么 / 月台有哪些装饰 / 当前点主要看什么”确定性读取 `node_guide_cards_v1.json` 的已审核关联清单、工艺分布和 `guide_focus`，无需 RAG；对工艺、寓意、故事或某件文物的解释性问题，才将点位名称和候选文物作为检索提示调用既有 `chen_clan_academy_rag_search`。
- `agent_graph.py` 新增 `tour_qa` 确定性节点：活动导览中的事实问题走该节点后结束；明确点位清单即使无活动路线也可走该节点；一般无路线事实保持原 `direct_rag → llm_think` 行为；“我到月台了”仍优先走 A1 事件。
- A2 问答节点不返回任何 TourState 或交互状态更新；检索无证据或异常时明确资料不足，不依据点位提示补造事实。
- 新增纯 mock 单元测试和 Agent 集成测试，覆盖当前/明确点清单、RAG 解释、未知点、缺包、状态不变和异常；本轮不接入论文、比较、术语或打卡卡，不实现阶段 B 讲解编排。
- 项目负责人已完成 A2 相关 106 项回归和完整 155 项本机回归，结果均为 `OK`。

#### A2 当前点工艺特点输出修复（待本机验证）

- LangSmith 实测发现原 `tour_qa` 是最终输出节点而非中间 evidence；它在“这里的灰塑有什么特点”中直出全库灰塑块，不能证明条目属于当前点。
- 现新增当前点工艺特点分支：指代表达强制读取 `current_stop_id`，先确定本点同工艺审核实例，再检索工艺总述及逐件实例；实例 evidence 必须命中实例名称，否则只保留其审核关联、不生成解释。
- 最终输出改为导游式“工艺特点 + 本点实例 + 证据来源 + 继续导览操作”，不再原样倾倒 chunk；无本点工艺时安全说明，不从全馆补充现场实例。问答前后 TourState 仍完全不变。

### 13.10 B1 点位讲解编排器基础（已实现并验证）

- 新增 `guide_program_planner.py`：对已审核 `node_id` 读取 `node_guide_cards_v1.json`，在当前点候选文物中确定性选择 1–3 件，输出可审计 `StopProgram`。
- 每个 `selected_item` 含稳定 `ornament_id`、名称、工艺、角色、`planned_seconds`、选择理由和由既有 `rag_queries` 生成的 `rag_query_hints`；研究/比较卡 ID 保留为空接口。
- 首版排序为“兴趣匹配分数降序 → `ornament_id` 升序”，相同输入必得相同结果；时间先在已选对象间基础分配。B2 再处理内容多样性、观察/互动时长和更精细预算。
- 不连接 Agent、不调用 RAG/LLM、不改路线或 TourState；未知点与空候选返回结构化安全结果。
- 项目负责人已完成 B1 相关 112 项回归和完整 161 项本机回归，结果均为 `OK`。

### 13.11 B2 StopProgram 时间预算与内容排序（已实现并验证）

- `guide_program_planner.py` 将全部可调数字集中到 `STOP_PROGRAM_POLICY`：详略等级的对象数量阈值、推荐单项讲解时长、兴趣权重，以及“相关性接近时”的工艺/题材多样性加分。
- `budget_seconds` 被明确标记为 `stop_explanation_content_only`：B2 只为本站已选对象分配讲解内容时间，绝不读取或占用空间网络中的步行时间。
- 预算低时安全降级为一个“简短概览”；`standard` 和 `deep` 只在达到集中阈值时扩展至 2 或 3 件。`allocated_content_seconds + unallocated_content_seconds = budget_seconds`，并保证已分配时间不超预算。
- 新增 `test_guide_program_budget.py`，覆盖预算边界、兴趣优先、相关性接近时的多样性、稳定排序和所有详略等级的超时保护。B2 不改变路线、空间图、审核讲解包或任何知识卡。
- 项目负责人已完成完整 166 项本机回归，耗时 1.740 秒，结果为 `OK`。

### 13.12 B3 StopProgram 取证与 Agent 点位讲解（已实现并验证）

- 新增 `guide_program_evidence.py`：只在游客已计划内到达当前正式站点时，读取本站已审核内容预算，调用 B1/B2 生成 StopProgram，并按选中对象的 `rag_query_hints` 复用既有 RAG；空间关联只决定对象，工艺、寓意和故事解释只来自返回 evidence。
- `agent_graph.py` 新增确定性 `stop_guidance` 节点。计划内到达与 `request_stop_detail` 成功后进入该节点；该节点只写 `active_stop_program`、证据、消息和展示协议，不写 TourState 或交互状态。
- 无 evidence、RAG 格式异常或调用异常时，明确说明资料不足，并拒绝按文物名称补造事实。自主到达不被当作正式站点讲解。
- `request_stop_detail` 仍是无副作用事件；其返回码更新为 `detail_requested`，之后可使用当前 StopProgram 输出展开讲解。`explanation_finished`、确认完成和 visited 语义均保持 A1 冻结契约。
- 项目负责人已完成完整 173 项本机回归，耗时 1.775 秒，结果为 `OK`。

### 13.13 B4 阶段 B 端到端验收（待本机与 LangSmith 验证）

- 新增 `test_stage_b_e2e.py`，离线覆盖：本站审核候选边界、short/standard/deep 的数量与内容预算、兴趣排序的可复现性、到达后 StopProgram 取证、A2 插入问答和恢复 `explaining`、无证据安全降级、空的研究/比较卡接口不阻塞基础讲解，以及最后的显式确认完成。
- B4 不新增业务能力、不变更路线、空间边、知识卡或 RAG 索引；其目的仅是证明 B1/B2/B3 与 A1/A2 能形成受控闭环。
- 本机回归通过后，必须在 LangSmith 核对真实链路中的 `tour_event → stop_guidance → tour_qa → tour_event`、RAG evidence、StopProgram 内容预算及 TourState 的 `visited_stop_ids` 仅在确认完成后改变。

#### 13.14.2 B3 最后一次表达优化（待本机验证）

游客文本不再出现“审核位置”“类型：”“简介：”等数据标签。`raw_location` 仍只读地生成观察提示，不进入候选评分、排序、路线或时间预算。灰塑兴趣下，灰塑对象优先作为核心观察；若预算允许且只保留一件非灰塑对象，则该项以 `工艺对照` 角色及 `comparison_reason` 记录，并在游客文本中说明对照目的。

#### 13.14.1 B3.1 优化：审核位置提示（待本机验证）

在确定性讲解层加入“对象在哪里看”的可追溯提示。生成链为：已审核 `ornament_spatial_mapping_v1.csv` → `build_node_guide_cards.py` → `node_guide_cards_v1.json` → `SelectedItem.observation_location` → 游客讲解。只有 `mapping_decision=change/add_node` 且 `final_node_id` 与当前 StopProgram 节点相同的对象可携带位置；空值或仅等于点位名的粗粒度描述回退为通用观察提示。该字段不参与路线、时间预算、TourState 或导航。

### 13.14 B3.1 游客导游讲解渲染（待本机验证）

- 新增 `guide_narration.py`，把 B3 的 StopProgram 与逐件 RAG evidence 转为游客可读的当前点开场、1–2 个重点对象、观察提示、简短事实、来源编号和下一步操作。
- `guide_program_evidence.py` 继续保留 `StopProgram`、角色、计划秒数、完整 evidence、逐件 evidence 与 `source_ids` 作为结构化审计数据；游客消息不展示文件路径、原始 chunk、内部角色或时间字段，也不以截断半句作为事实。
- `request_stop_detail` 使用同一 StopProgram 生成不同的“再看细一点”讲解，不写 TourState；当前 Agent 默认采用确定性渲染。可选 LLM narrator 仅接收审核对象和 RAG evidence，若调用失败或输出疑似原始 dump 则回退确定性文本。

## 14. B3 术语卡、术语—点位关联与点位检索提示（2026-07-26）

### 14.1 已完成能力

- 新建 `data/chen_clan_academy/glossary/glossary_zh_en_v0.yaml`：当前包含 82 个研究型术语，全部填写 `domain`；术语按领域分组，覆盖建筑构件、装饰材料、雕塑技法、装饰题材与题记、宗族与教育、礼制与祖先、文保、机构与场所等。
- 术语卡不把“月台、正厅、东厅”等路线讲解点当作术语；它服务于研究建筑、工艺、制度和保护问题的游客。每张卡保留定义、陈家祠关联、检索词、来源引用与中英译法状态。
- 已新增术语检索规则 `glossary_retrieval_rules_v0.yaml`：按领域指定优先知识文件、适用问法和回答边界；雀替、龛罩、透雕/通雕等高频概念另有覆盖规则。
- 已从已审核装饰—点位映射生成 `term_stop_associations_v1.json`，得到 12 个讲解点、181 条术语—点位关联；12 个 `node_guide_cards_v1.json` 讲解包均已写入 `glossary_ids`。
- 已新增 `glossary_retrieval.py`，并接入 `tour_qa.py`：游客在当前点询问解释性问题时，相关术语只作为 RAG 检索提示；“这里有什么”类清单同时展示可继续追问的专业术语。最终事实回答仍必须来自已有检索证据。
- `requirements.txt` 已显式加入 `PyYAML`；新增术语数据、术语—点位关联和点位术语检索提示测试。项目负责人已报告本轮相关测试通过。

### 14.2 当前边界与人工审核项

- `research_references.md` 已登记雕刻技法参考文献，但尚未摘录页码、原文要点或可直接引用的研究摘要；因此它不是“学术研究摘要卡”完成状态。
- 82 个术语中 48 个译法为 `reviewed`，34 个仍为 `draft`；英文自动生成与最终中英术语审核尚未完成。
- 181 条点位关联均为“从已审核装饰映射推导”的候选上下文，不等同于游客在该处必然可见的对象，也不代表室内定位。应优先核查月台、前庭北侧、前庭中部和前庭西侧的关联，再逐点确认。
- 宗族、科举、保护等级等全局性概念不强行绑定单一点位，仍通过 RAG 与当前问题上下文回答。
- 研究摘要卡、比较卡、照片/打卡点卡尚未接入 `StopProgram` 的内容选择；它们保留的 `card_id` 接口仍为空。

### 14.3 后续维护流程

1. 新增或修改术语卡后，先确认 `domain`、定义、来源和译法状态。
2. 运行术语关联生成脚本，审阅 `term_stop_associations_v1.json` 的变更，再由人工确认可见性和表述范围。
3. 运行 `test_glossary.py`、`test_term_stop_associations.py`、`test_glossary_retrieval.py`，并做“当前点 + 术语问题”的 A2 端到端问答验收。
4. 只有取得可核查页码/摘录和结论边界后，才将参考文献升级为研究摘要卡，并按稳定 `card_id` 接入讲解编排。

### 15. C1/C2 统一游客画像（已实现并完成本机回归）

- C1 新增 `visitor_profile.py`：纯、不可变的 `VisitorProfile`，统一校验 20–120 分钟、兴趣归一化、`short/standard/deep` 讲解深度和稳定序列化。它没有导入 AgentState、TourState、路线或 StopProgram。
- C2 新增 `profile_dialogue.py`：对路线请求按“时间 → 兴趣 → 深度”收集游客明确表达；“都可以/不确定”只解决当前正在追问的字段，采用透明中性默认，不推断兴趣或未来画像字段。
- Agent 只新增 `visitor_profile` 和 `profile_collection`：前者是唯一画像值，后者只记录已解决字段；C2 不复制到 TourState、不启动路线，也不改变 StopProgram。普通 RAG、到达与 A1 操作优先于画像收集。
- 项目负责人已运行 C1/C2 目标测试及完整 226 项回归，结果均为 `OK`。C3 才让路线和 StopProgram 从同一已验证画像读取字段。

### 15.1 C3 画像快照接入路线与 StopProgram（已实现并完成本机回归）

- `agent_graph.py` 的 `direct_route_node` 优先读取 C1/C2 已校验的 `visitor_profile`，不再在路线节点重新猜测时间、兴趣或讲解深度。完整输入“30分钟、喜欢灰塑、标准讲解、规划路线”会在同一图执行中经过 `profile_collection → direct_route`。
- 路线成功后，`start_tour(plan, interests, detail_level)` 将画像中实际采用的 `available_minutes`、`interests`、`detail_level` 固化到 TourState；这份快照是游览执行期的唯一依据。
- 现有 `guide_program_evidence._program_from_state()` 只读 TourState 的兴趣和详略等级，因此 StopProgram 不会在游览中因 `visitor_profile` 被修改而漂移。30/60/90 分钟仍优先使用人工审核锚点，兴趣可能只影响模板选择或站内选物；系统不会夸大为“每个锚点站序都会改变”。
- 画像校验或路线生成失败时，`direct_route_node` 仅返回结构化错误与性能指标，不返回新的 `tour_state` 或 `active_route_plan`，避免半初始化状态。旧脚本式直接调用保留安全兼容：用原有文本提取结果一次性构造 `standard` 画像，但不新增第二个持久画像存储。
- 新增 `test_agent_profile_route_integration.py`，覆盖画像—TourState 快照一致、动态 45 分钟灰塑选物、详略等级影响对象数、失败不留半状态、遗留无画像调用及编译图内同轮收集后启动路线。项目负责人已使用项目虚拟环境执行目标测试、路线/交互/讲解回归和完整回归，结果均为 `OK`。

### 15.2 C4 游览中画像更新与受控重规划（已实现，待验证）

- 新增 `profile_update.py`：它是游览中的唯一偏好更新适配层，复用 `profile_dialogue.extract_profile_patch()` 的同义表达规则和 C1 `update_visitor_profile()` 的不可变校验，不新建一套兴趣、时间或详略规则。
- “只剩 N 分钟”先校验新画像；只有 A1 `handle_tour_event(..., "replan_time")` 成功后，才调用 `tour_state.apply_profile_snapshot()` 同时保存新的 VisitorProfile、TourState 时间/兴趣/详略快照和重规划结果。任何失败均返回原画像、原 TourState、原交互状态。
- “接下来想多看木雕”“后面简单讲”“我想听深入一点”只同步后续 StopProgram 所读的 TourState 兴趣、详略字段，不改已访问、跳过、当前点、正式路线或确认状态。用户如明确另起一条路线，仍走既有路线初始化流程。
- 新增 `test_profile_update.py`、`test_agent_profile_update.py`、`test_profile_update_e2e.py`，覆盖原子更新时间、选物变化、详略变化、冲突无部分写入、控制操作混合澄清、问答不回流进度与已跳过点不重加。待项目负责人执行完整回归与 LangSmith 多轮链路检查后再标记 C 阶段完成。

### 15.3 C5 扩展游客画像契约（已实现并完成本机回归）

- `VisitorProfile` 新增四项当次参观偏好：`audience_mode`（standard / child_friendly / family / study / mixed_group）、`knowledge_level`（general / enthusiast / professional）、`explanation_style`（standard / story / technical / interactive / expert）、`interaction_mode`（listen_only / normal / interactive_tasks）。
- 四项均有中性默认值，支持旧画像缺失字段；默认不等于系统推断了用户身份。C5 当前只提供不可变校验、增量更新和稳定序列化，不主动追问、不从自然语言推断，也不读取年龄、性别、职业、收入、疾病或关系等敏感数据。
- 旧 `visitor_type` 被废止：新建/更新时会被拒绝；读取包含该字段的旧快照时安全丢弃，而不是把它猜测映射为家庭、研学等模式。这样保留历史会话兼容，同时避免继续使用含义混杂的标签。
- C5 不接入路线、TourState、StopProgram 或讲解生成，全部字段只在当前会话 AgentState 的 `visitor_profile` 中存在。C6/C7 才会在独立验收后决定哪些字段能够影响讲解表达和互动任务。
- `test_visitor_profile.py` 与 `test_profile_dialogue.py` 增加合法值、非法值、不可变更新、稳定序列化、中性默认、旧画像兼容和“不因完整路线请求推断 C5 偏好”的覆盖。项目负责人已完成 C5 目标测试和完整回归，结果均为 `OK`。

### 15.4 C6 VisitorProfile → GuidancePolicy（已实现并完成本机回归）

- 新增 `guidance_policy.py`：`build_guidance_policy()` 是一个无副作用纯函数，输入经 C5 校验的 `VisitorProfile` 或序列化字典，输出冻结的 `GuidancePolicy`。它不导入 Agent、TourState、路线、StopProgram、RAG 或知识卡加载器。
- 策略集中定义详略等级、受众模式、知识基础、表达风格和互动模式的映射。`detail_level` 决定 1/2/3 件上限、长度和展开深度；儿童/家庭/混合群体使用简单主讲解；混合群体保留可选深入补充；专业知识基础可以增加引用详细度，但不会把 short 自动变成 deep。
- `listen_only` 关闭观察任务和主动提问，即使表达风格为 interactive。故事/技术/专家等 `narrative_mode` 只影响未来内容组织方式，不生成新事实。比较、研究扩展、术语解释字段仅是 D 阶段接口，当前不加载任何卡片。
- 策略始终输出 `fact_evidence_required=True` 与 `budget_cap_mode=min_with_stop_budget`：未来 C7 必须取“策略对象上限”和已审核站点预算的较小值，且所有事实仍需 RAG evidence。
- 新增 `test_guidance_policy.py` 覆盖默认、儿童故事互动、家庭、研学、混合群体、专业短讲、listen_only 冲突覆盖、未来知识卡接口、输入不可变和非法画像拒绝。项目负责人已完成 C6 目标测试和完整回归，结果均为 `OK`。

### 15.5 C7 GuidancePolicy 接入点位编排与讲解（已实现，待本机与 LangSmith 验证）

- `guide_program_evidence.build_stop_guidance()` 现从当前会话 `visitor_profile` 生成 C6 策略；旧会话没有该字段时，仅以 TourState 已采用的时间、兴趣、详略临时重建中性画像，不保存第二份画像。策略随本次 `StopProgram` 写入 `active_stop_program.guidance_policy`，可审计但不回写 TourState。
- `plan_stop_program()` 新增可选 `guidance_policy` 参数。它先维持 B1/B2 的“审核点位候选 + 兴趣排序 + 实际站点预算”，再取 `min(B2预算可容纳对象数, policy.max_items_per_stop)`；分配秒数继续不超过 `budget_seconds`。策略无法添加文物、跨点选物、改变路线或占用步行时间。
- 确定性讲解渲染读取 `vocabulary_level`、`narrative_mode`、`interaction_task_enabled`、`citation_detail` 和受众边界：儿童短句与一个观察任务、家庭共同观察、研学观察目标、专业技术表达、混合群体通俗主讲解与可选补充；`listen_only` 关闭一切主动任务。故事模式仅改变开场组织，不补写证据外剧情。
- 同一组选中对象的 RAG evidence 与 `source_ids` 不因表达模式变化；来源只按 `citation_detail` 改变展示标签。`comparison_enabled`、`research_extension_enabled`、`term_explanation_enabled` 保留为审计接口，C7 不读取尚未接入的知识卡。
- 新增 `test_guidance_policy_integration.py`，并扩展 Agent 点位讲解测试，覆盖默认、儿童故事互动、家庭、研学、专业精简、混合群体、listen_only、预算与候选边界、来源一致性、TourState 不变及策略审计保存。待项目负责人执行本机完整回归和 LangSmith 检查后标记验证完成。
- **当前交互边界**：C5 只完成字段契约，未新增四项偏好的自然语言收集或 UI 选择器。因此真实聊天当前只会使用 C5 中性默认策略；儿童、家庭、研学、专业和互动变体已在离线测试中以显式 `visitor_profile` 注入验证。若要在真实 LangSmith 聊天中让游客选择这些变体，需单列后续“偏好显式选择/确认”任务，不能由 LLM 或文本猜测替代。
## C8 扩展画像的显式选择与会话控制（已实现，待本机与 LangSmith 验证）

- 新增 `extended_profile_control.py`：只识别明确偏好表达，先形成结构化 patch，再复用 `VisitorProfile` 的不可变校验与 `build_guidance_policy()`；LLM、RAG 与展示层均不直接写画像或策略。
- 支持儿童、亲子、研学、专业/爱好者、故事/技术/互动/专家表达、只听不问、查看画像、恢复扩展中性默认和删除本次会话偏好。模糊的“我们/一起”等表达不会推断家庭、儿童或其他身份。
- “恢复标准讲解”只重置四项扩展字段，不覆盖时间、兴趣和深度；“删除本次偏好”只清空 Agent 会话画像与收集草稿，保留 TourState 的路线与游览进度。
- 游览中更新只影响后续 StopProgram/讲解；显式要求按新方式重讲当前内容时，仅复用当前选物和既有 evidence 重渲染，不重新选物、检索或改变进度。

## C9 画像、会话记忆与编排端到端验收（待本机与 LangSmith 验证）

- 新增离线验收覆盖画像→策略→路线快照→StopProgram 策略审计、风格切换不改游览进度、确认完成唯一写入 visited 以及模糊措辞不触发画像。
- 当前命令行 Agent 使用 `MemorySaver + thread_id` 保存短期会话：同一 thread 可保留 messages、VisitorProfile、TourState、活动路线和当前讲解包；不同 thread 不共享这些状态。服务重启后不保证恢复，项目尚未实现数据库、跨会话长期画像或对话摘要。
## D1 异构知识卡统一注册与安全适配层（已实现，待本机验证）

- 新增 `knowledge_card_contract.py` 与 `knowledge_card_registry.py`：不迁移、不改写术语、研究、比较、打卡、姿势和平台原始文件；各类数据只通过适配器生成统一、只读的内部 `KnowledgeCard` 视图。
- 统一字段为 `card_id`、`card_type`、`runtime_status`、能力/场景、来源、适用节点、限制、原始 payload 与校验错误。资格缺失、来源/节点无效、类型不一致或状态冲突时一律失败关闭；状态优先级为 `disabled > attributed_only > enabled`。
- 术语、研究、比较和体验卡仍保留各自检索/读取结构，不建立混合向量库；平台观察仅供内部审计，永不作为游客端知识卡结果。D1 尚未接入 Agent、Tour QA、StopProgram 或基础 RAG。

## D2 游览中术语卡接入 Tour QA（已实现，待本机验证）

- 新增 `term_card_runtime.py`：术语问答先从 D1 `knowledge_card_registry` 读取已获运行资格的 `glossary_term`，再输出定义、拼音、领域、英文或已审核英文别名；它不直接读取资格 YAML，也不新建术语向量库。
- `glossary_retrieval.point_glossary_context()` 仍仅提供“当前点位—术语”的排序提示。回答会说明“存在审核关联、是否看清以现场为准”，绝不将关联说成眼前必然可见的事实。
- 英文输出额外检查 `en_translation` 能力；草稿术语只返回“未通过英文输出审核”，不会泄露草稿译名，也不会交由模型猜测。术语未命中、注册表异常或定义能力不可用时回退原有基础 RAG。
- `tour_qa` 在现有点位清单和“这里的某工艺特点”分支之后调用术语适配器；比较句（如“灰塑和砖雕有什么区别”）明确不由 D2 接管，仍保留给既有 RAG/后续比较卡。所有术语问答均不写 TourState、StopProgram 或路线进度。

## D3 游览中研究摘要卡接入 Tour QA（已实现，待本机验证）

- 新增 `research_card_retrieval.py`，只从 D1 注册表筛选 `research_summary` 卡；原始 `status=reviewed` 不可自行开放卡片，`disabled`、`background`、`pending` 及缺少归因能力的卡均不会运行。
- 仅“论文如何解释”“从学术/研究角度”“研究方法/限制”等明确研究意图触发 D3；比较句明确留给 D4，术语、点位清单、故事与到达事件保留原有分支。
- 每次最多使用两张卡，按问题标签、支持问题和当前节点关联排序；空 `applicable_node_ids` 不获得当前位置加分，也不被说成游客眼前可见。
- D3 始终调用基础 RAG 作为事实交叉核对，同时把研究内容表述为“某研究指出”，保留方法（仅爱好者/专业表达）与适用范围/限制；不会输出卡片 ID、运行状态、本地 PDF 路径或检索分数，也不会改变 TourState 或画像。

## D4 游览中比较卡接入 Tour QA（已实现，待本机验证）

- `comparison_retrieval.py` 新增 D1 门控的比较读取接口；D4 不使用原始 YAML 作为运行时入口。八张比较卡仍均为 `attributed_only / research_only`，因此普通比较只会调用基础 RAG，不会泄露研究卡内容。
- 比较意图在 `tour_qa` 内先于 D3 与 D2 处理。明确研究比较、或画像为研学/专业的明确比较，才可使用一张主比较卡；回答固定包含比较范围、维度、相同点、差异、限制及“相关研究”归因。
- 两个对象都命中优先于主题/维度/单对象命中；同分按稳定卡 ID 排序。对象不明确的“它们有什么区别”只澄清，不让模型猜测前文对象；当前点从不被当作比较对象必然可见的证据。
- `on_site_observation_prompt` 仅以“观察建议”呈现。D4 不输出卡片 ID、状态、路径或分数，也不修改 TourState、StopProgram、路线或 VisitorProfile。
## D5-B 打卡卡轻量编辑推荐门控（已实现，待本机验证）

- `runtime_status=enabled` 在体验资格清单中表示“项目编辑选择的候选”，不等同于馆方推荐、现场审核、热门机位或实时可拍。`partial/pending` 审核字段保留原样，不能被伪造为 `verified`。
- 新版 `photo_spot_validation.py` 只拒绝结构性不安全或不可用数据：节点不存在、姿势/平台/证据引用断裂、姿势为禁用状态、卡片或姿势缺少安全边界、对象—点位关联不成立或文件损坏。通过者返回 `availability_tier=editorial_candidate`，并固定携带“以现场开放、客流、光线、标识和工作人员要求为准”的提示。
- D1 仍登记打卡卡、姿势和平台观察，但通用 `query_registered_cards()` 永不返回这三类体验资产。未来 D6 只能经 `query_available_photo_spots()` 在明确拍照意图下读取候选；姿势仅随选中的打卡卡间接返回，平台观察永远不进入游客内容。
- 专用查询不直接返回混合的 `recommended_capture_zh`，因此不会把“最佳角度”“热门”或未经复核的现场条件原样传给游客。`editorial_recommended` 的唯一允许表述是“项目编辑建议”。D5-B 不改 `tour_qa`、StopProgram、路线、TourState 或 VisitorProfile。

## D6 打卡点与拍照建议接入 Tour QA（已实现，待本机验证）

- 新增 `photo_spot_runtime.py`：用确定性关键词识别拍照、打卡、构图、合影、自拍等明确请求，并只调用 D5-B 的专用候选接口。D6 不调用 LLM、不建立新 RAG、不读取平台观察，也不将 `recommended_capture_zh` 原样输出。
- `tour_qa` 内的优先级为 D6 拍照 → D4 比较 → D3 研究 → D2 术语 → 原有点位/RAG；但顶层到达、跳过、确认、画像更新和路线控制仍优先。拍照与“加入路线/改路线”同句时只澄清，不部分执行。
- 推荐最多三处，优先当前节点、再优先当前路线剩余节点、最后按明确主题/同行需求和稳定 ID 排序；同一节点不重复。家庭、个人、合影等当前句需求只影响本轮排序，绝不写回 VisitorProfile。
- 输出只包含编辑候选的点位标题、确定性构图关注方向、一个间接安全姿势、边界与固定现场提示。禁止“热门、最佳、一定能拍到、馆方推荐、已现场核验”等表述；无候选时只提供通用非接触拍摄安全建议。
- D6 是只读问答：不得更新路线、TourState、VisitorProfile、StopProgram 或 RAG evidence。当前只完成代码接入与离线测试，真实候选数量须由本机 D5/D6 测试确认。

## D7 知识卡综合验收与阶段冻结（验收矩阵已建立，待本机与 LangSmith 验证）

- 新增 `data/chen_clan_academy/evaluation/d_stage_acceptance_cases_v1.yaml` 与 `test_d_stage_acceptance_cases.py`。矩阵冻结 `dst_acc_001` 至 `dst_acc_017`，覆盖术语定义/英文草稿阻止、研究归因与限制、普通/研究比较、当前点与全馆拍照、家庭与个人排序、平台观察隔离、无候选回退、导游事件、多意图澄清、数据损坏降级和线程隔离。
- 矩阵不复制卡片正文；它只记录输入、前置 TourState/画像、预期路由、卡片类型、应出现/禁止出现的游客可见文本、允许的状态变化、来源类别和人工审核状态。
- 除 `tour_event_lifecycle` 外，D2--D6 的所有案例 `allowed_state_changes=[]`；到达案例也不允许直接写入 `visited_stop_ids`。当前 `review_status=pending_local_and_langsmith_validation`，未经本机完整回归、固定 LangSmith 多轮检查和人工审阅前，不能称 D 阶段已验证或已冻结。

## E1 D 阶段协作基线（本机与 LangSmith 已验证，待生成交接提交）

- `D_STAGE_BASELINE.md` 以 `079a1f1` 作为功能基线提交；项目负责人已完成本机完整回归 `374 tests / 8.318s / OK`，并确认固定 LangSmith 场景全部通过。
- 当前受限环境不能启动项目 `.venv`，因此不把本机测试结果误记为沙箱执行。E1 仍待生成并推送 `handoff_commit`；完成后两位队友必须从同一提交建立正式协作分支。

## E4-3 统一中文时长解析与游览中重规划（已实现，本机测试通过；待 LangSmith 验证）

- 新增唯一公共解析器 `duration_parser.py`：把明确的中文/阿拉伯数字时长归一化为分钟。支持 `30分钟`、`三十分钟`、`半小时`、`一个小时/一小时`、`一个半小时/一小时半/1.5小时`、`两小时/两个小时`、`一刻钟` 与 `三刻钟`。
- `agent_graph.py`、`profile_dialogue.py`、`tour_intent.py` 和 `profile_update.py` 均改为调用该解析器；路线初始化、画像收集与游览中“只剩/改成”时间更新不再各自维护正则规则。
- 解析器只识别显式时长，调用方仍须检查路线或剩余时间语境。历史问题如“陈家祠建了多少年”不进入路线；冲突时长会澄清，不做部分更新；解析后的分钟数仍由既有 VisitorProfile/路线预算范围校验。
- 游览中修改时间继续通过现有确定性 `replan_time` 适配层：保留已访问与跳过记录，不重复当前未确认站点，也不改变 A1 的到达、讲解结束和确认完成语义。
- 已新增 `test_duration_parser.py` 与 `test_e4_duration_integration.py`。项目负责人已确认定向测试和完整 `unittest discover -v` 本机通过；本轮仍需以 LangSmith 检查“一个小时初始化”和“只剩半小时重规划”的真实节点链路。

## E4-3B 多目标路线选择与严格预算（已本机验证）

### E4-3B1 点位对象—兴趣证据一致性验收（已本机验证）

- 路线兴趣覆盖读取 `node_guide_cards_v1.json` 时，重复核验对象的 `final_node_id` 必须等于实际 guide stop，且 `mapping_decision` 只能是 `change` 或 `add_node`；手工改写或过期卡片中的其他对象不能参与路线评分。
- `test_node_guide_cards.py` 将重新执行 `build_cards()`，按 `node_id` 比较路线评分所依赖的对象投影（稳定排序后的 `ornament_id`、名称、工艺、审核节点和映射决定）、`ornament_count` 与 `craft_distribution`。术语构建器后续追加的 `glossary_ids`、`extensions` 不参与此项验收。
- 当前讲解包采用“基础点位卡生成 → 术语关联回写”的两阶段流水线；未来可统一为单一可复现构建命令，现阶段作为技术债记录，不在本次路线评分验收中重构。
- 当前 `interest_coverage` 只表达“用户兴趣是否在实际停靠点的审核对象中被覆盖”，不表示文物丰富度、典型性、权威排名或文化事实。文化特点、年代、寓意和故事仍须由 RAG evidence 支撑。

### E4-3B2 时间利用率评分校准（已本机验证）

- 严格预算仍是资格层硬约束：超出用户秒数预算的候选直接淘汰，不参与评分。
- `time_utilization` 只表达偏好：在各深度目标区间内得最高分；从区间上限 0.95 到预算上限 1.00 线性由约 0.9 降至约 0.7，不再把刚好用满预算的合格路线打成 0 分。

## E4-4B 点位问答短期上下文（已本机验证）

- 新增只读 `qa_context`：只在成功且有可继续依据的点位问答后保存结构化检索条件；无证据、失败或澄清回答不会留下可用上下文。它不保存 RAG 正文，也不进入 TourState、VisitorProfile 或 StopProgram。
- “再讲详细一点”在上一轮为 `tour_qa` 时进入独立 `qa_follow_up_detail`，重新检索上一轮限定点位；上一轮为 `stop_guidance` 时仍严格保留 A1 `request_stop_detail` 语义。
- “石雕呢？”只在紧邻的有效点位问答后继承唯一问答点位；“这里呢？”始终回到真实 `current_stop_id`。
- 路线事件、重规划、完成、路线初始化和其他非问答操作都会清除 `qa_context`。
- 项目负责人已确认 E4-4B 定向测试与完整回归通过；后续只允许在不改变 A1、TourState 和知识卡事实边界的前提下优化表达与检索质量。

## E4-3C 阿拉伯小数小时解析（已本机验证）

- `duration_parser.py` 现以精确 `Decimal` 完成小数小时到分钟的换算：`1.5小时/1.5个小时 → 90`、`0.5小时/0.5个小时 → 30`、`1.25小时 → 75`。
- 小数分钟不再从尾部误识别，例如 `1.5分钟` 不会被拆成 `5分钟`；`2.5小时 → 150` 仍由既有 VisitorProfile 的 20--120 分钟范围校验拒绝，不截断也不改路线选择。
- 项目负责人已确认定向测试、完整 `unittest discover -v` 与 LangSmith 小数小时路线输入均通过。

## E4-5B 知识子路由精确匹配、点位硬范围与安全优先（待本机验证）

- D4 比较卡改为“双对象精确命中”门控：主题、维度或单一工艺命中都不能补足缺失比较对象。无精确合格卡时分别检索用户明确说出的双方基础资料，并说明证据不足时不作差异结论。
- D3 明确研究意图在没有 D1 合格且直接匹配的研究卡时，改为 `research_rag_fallback`：游客消息保留基础 RAG 的实际来源，并明确该回答不是研究卡结论。
- 明确点位概览（如“讲讲月台”）进入该点的审核讲解包，点位仅限定本轮查询，不改变 `current_stop_id`。当前点工艺术语先核对本点审核对象；不存在时返回 `current_craft_absent`，不以全馆资料补造眼前实例。
- 顶层对“明确危险动作 + 明确拍照意图”先送入 D6 安全拒绝，再进行到达或多意图仲裁；拒绝不会查询打卡候选，也不会写入 TourState。

## P1-21 游客文本与内部审计来源分离（已实现，待 LangSmith 验证）

- 工艺总述的游客渲染不再拼接内部来源编号；工艺和对象来源继续保留在 `evidence`、术语元数据与 Trace 审计结构中。
- P1-13/P1-16 将同一公共门控扩展到票务、参观服务、当前点工艺摘要、比较与研究基础资料回退：游客文本拒绝文件名、`Sxx`、本地快照/知识库描述、原始 chunk、URL、节点/对象 ID 与检索字段；结构化 evidence、`source_ids` 与 `used_source_ids` 不删除。
- 忘带、丢失/遗失、找不到、不在身上、酒店遗留或未带实体身份证的入馆请求统一使用已审核替代检票流程；身份证挂失、补办等政务问题不进入票务 RAG。P1 定向 87 项、兼容性扩展 98 项和完整回归 737 项通过，LangSmith 尚待验证。
- `controlled_knowledge` 保持无证据不调用模型、危险候选整段失败关闭，并新增文件名、URL、检索字段和内部对象/节点/术语标识的拒绝覆盖；不会通过字符串删除后继续展示候选文本。
- 已完成 81 项主定向、50 项相关回归和完整 675 项 `unittest discover -v`；状态为 `implemented_pending_langsmith_verification`，尚未把本地测试写成 Studio 通过。

## P1-20 规划前对象故事的对象级证据门控（`verified_fixed`）

- P1-20A 复现确认：对象级 `08_ornament_items.md` 过滤本身会拒绝纯 `07_ornament_crafts.md` 与其他对象的条目；风险来自无路线时落入 `direct_rag`，以及宽泛 `ornament_item/story` 计划可能早于对象身份门控执行。
- 现在“明确审核对象 + 故事/人物/情节”在有无路线时均进入 `tour_qa` 的精确对象链路。只有同一审核对象、同一 `08` 条目且身份字段一致的证据能够进入故事渲染；混入对象或无对象证据均失败关闭。
- “只根据某工艺”明确限制证据范围时，不查询对象资料或调用 LLM，而是说明工艺总述不能证明单件对象传说，并请求允许使用该对象审核资料。TourState、VisitorProfile 和路线状态保持只读。
- 同名对象子项已完成审核实体规范化：项目负责人确认木雕《踏雪寻梅》`orn_051/orn_052` 为同一物理对象，审核记录保留 `orn_051` canonical 与 `orn_052` alias 关系；正式点位卡只投影 canonical，故游客候选为唯一木雕版本与独立石雕版本。旧线程候选在选择前重新读取当前注册表，不能继续使用重复快照。
- 验收记录：2026-07-31 项目负责人已确认 LangSmith 新线程场景“讲讲踏雪寻梅。→ 木雕”与“讲讲木雕《踏雪寻梅》。”通过；本地完整回归为 `689 tests / OK`。本次操作未提供可存档的 thread ID 或 Trace URL，故记录为 `thread_id=not_recorded`、`trace_url=not_recorded`，不伪造标识。

## E5-0 个性化讲解质量、首次工艺介绍与文物深度契约（已冻结，未接入生产行为）

- 新增 `E5_NARRATION_CONTRACT.md`，冻结从 VisitorProfile、GuidancePolicy、StopProgram、NarrationCoverage、RAG evidence 到确定性游客讲解的职责边界。
- `NarrationCoverage` 被设计为独立线程内覆盖记录：只有成功、有 evidence 的讲解才标记 introduced；新路线清空，游览中到达、跳过、重规划和确认完成不清空。它不写入 TourState 或 VisitorProfile。

## P1-11 显式当前位置的确认式后续重规划（自动化已验证，待 LangSmith 验证）

- 活跃路线中，任何明确到达且不同于正式 pending 的审核点位都视为路线偏航：先以审核解析结果写入唯一位置事实 `TourState.current_stop_id`，再进入 `replan_time_confirmation` 询问游客本轮还剩多少时间；显式“重新安排后续行程”仍支持，但不再是必要条件。不得以初始路线总时长生成候选。
- 解析到明确分钟数后，才从 `current_stop_id` 生成 `awaiting_route_confirmation` 候选；候选的 `origin_node_id` 与 `physical_node_snapshot` 都只是审计快照。A1 `apply_replan_proposal` 验证二者仍一致后才原子替换剩余路线并保留 visited/skipped；取消只清除待确认动作。
- `pending_action_kind` 明确区分时间确认与路线确认。两阶段的“下一站”都会被拦截，不能调用 `next_stop`、静默应用候选或把路线写为 completed；路线确认阶段使用统一控制表达归一化和“否定 → 疑问/查看 → freshness → 确认”仲裁，支持“确认新路线”“使用新路线”“就按新路线走”等，否定或问句不会应用候选。
- 2026-07-31 修复两项阻塞：审核正式点位“后西庭”先以 `self_arrival` 写入 `current_stop_id`，再清除旧候选并生成绑定新位置的时间确认；“没标名字的小院”等未知起点在画像收集前失败关闭为 `unresolved_replan_origin`，不会退化为默认入口路线。P1-11 定向 93 项、完整回归 743 项通过；仍待 LangSmith 新线程实测，尚不得标记 `verified_fixed`。
- 首次工艺必须先有 `07_ornament_crafts.md` 证据并连接当前点审核实例；首次文物要求位置、工艺、可见细节和有来源的题材/寓意/故事。预算不足时少讲对象而不截断证据链。
- 本步只新增契约与测试骨架；未实现覆盖状态写入、首次讲解编排、风格素材库或质量评测引擎。后续 E5-A/B/C 的冻结接口与验收编号见契约文件。

- 新增 `route_selection.py`：审核锚点与动态路线进入统一候选池。候选必须满足 `estimated_total_seconds <= available_minutes * 60`；无合格候选返回结构化 `no_qualified_route`，不再提供超时路线。
- 兴趣覆盖不再比较路线标题主题。选择器从实际 `guide_stop_ids` 对应的 `node_guide_cards_v1.json` 已审核对象中，按文物名称和工艺确定性派生证据；不会新增第二份人工 `interest_tags` 事实源。
- `detail_level` 同时影响动态路线每站的讲解/观察/互动预算与候选时间利用率区间。`deep` 优先选择约 80%--95% 时间利用率的候选；在该合理时间池中，再综合兴趣覆盖、细节适配、步行成本和小幅锚点奖励。
- 已废止“精确 30/60/90 分钟强制锚点”及路线选择中的 10% 超时容忍。锚点仍可在时间、兴趣和细节均合适时胜出；45/75 分钟保持动态路线。权重是可审计的 v1 调参项，不是永久冻结事实。
- 新增 `test_route_selection.py`，并扩展路线与动态规划测试。当前实现尚待项目负责人本机完整回归和 LangSmith 验证；不得据此宣称路线质量问题已关闭。

### P1-12C1 到达同义表达受控接入（实现已补强，待本机回归与 LangSmith）

- 语义层现在只能提出带原话 `evidence_span` 和可选原话 `location_text` 的 arrival 候选；它不能产生 `node_id`、路线或状态更新。审核节点仍只由 `resolve_reviewed_node()` 解析，最终到达仍通过 A1 `tour_event`。
- 未指明地点的“走到这一站跟前”“到目的地”“到位”等表达，只有在活跃路线、`navigating` 阶段且存在唯一 pending 时才绑定该 pending；无路线或无唯一 pending 一律澄清。2026-07-31 已补入“我已经抵达这里了”“我人到了”“终于走到了”“已经来到这一站了”“我们走到跟前了”等高频完成体表达。
- 明确到达非 pending 审核点位时复用 P1-11 `self_arrival → replan_time_confirmation`；不创建第二套重规划，也不把到达写成完成。意愿、途中、否定、假设/疑问、知识问答、第三人称和混合操作均失败关闭。
- 新增只读 `looks_like_arrival_control()` 护栏：控制形态但不能安全归一时直接结构化澄清，禁止落入语义模型失败后的 `llm_think`／RAG；“到达月台后能看到什么”等时间条件知识问句不受该护栏拦截。本轮定向与完整回归待本机执行后记录。

### P1-12C4 下一站控制受控接入（自动化已验证，待 LangSmith）

- “下一个”“下一处”“接下来去哪”“带我去下一站”等路线控制表达现在只会映射到既有 A1 `request_next_stop`／`next_stop` 语义；候选不携带站点名称、`node_id`、路线、导航文案或任何状态写入。
- 重规划等待优先于下一站：等待剩余时间时提示先说明时间，等待路线候选时提示确认或保留原路线；当前站处于 `explaining` 或 `awaiting_confirmation` 时，“下一个”不能代替完成或跳过。无活跃路线时提示先规划路线。
- 已确认新路线后，下一站导航只读取已应用的 active route、`current_stop_id`、`pending_stop_id` 和审核空间图。控制形态无法安全映射时走结构化澄清，禁止落入 `llm_think` 或 `rag_tool` 生成自由导航。
- C4 定向回归 99 项通过，完整回归 730 项通过；仍待以独立 LangSmith 线程完成“偏航 → 剩余时间 → 确认新路线 → 下一个”及阻断场景复测。
