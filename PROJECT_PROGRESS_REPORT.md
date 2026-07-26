# 陈家祠金牌导游 Agent：现阶段技术进度与业务逻辑说明

> 学习、答辩和项目全貌说明已独立迁移至 `PROJECT_LEARNING_AND_DEFENSE_GUIDE.md`。本文件只维护当前实现进度、验证状态与后续事项，避免将“计划”误写为“已实现”。

> 报告日期：2026-07-25  
> 代码基线：当前工作区代码与已记录的本地测试输出  
> 阅读目的：小组协作、答辩讲解、面试复盘与后续迭代。  
> 重要原则：本报告将“已实现”“已验证”“数据准备中”“仅需求规划”分开描述，不将产品设想表述为已上线能力。

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

已新增 `TOUR_INTERACTION_CONTRACT.md`，作为 A1-1 至 A1-4 的唯一交互契约。它冻结了 7 个白名单事件、统一响应包、错误码、前置条件、状态转移、幂等规则和“禁止按时间自动完成”的约束。

现有 TourState 首版中“到达即计入已访问”的行为与连续导游记录语义不完全一致。契约已明确：从 A1-1 起改为“到达 → 讲解/等待确认 → `confirm_stop_complete()` 才计入 `visited_stop_ids`”；本 A1-0 阶段不改运行代码，因此已通过的 A 阶段测试仍保持有效。

### 13.7 A1-1 统一交互事件适配层

- 新增 `tour_interaction.py`：所有游览事件经 `handle_tour_event()` 进入，返回冻结契约规定的 `ok`、`event`、`code`、`message`、TourState、交互状态、`data` 与 `idempotent` 响应包。
- 交互状态独立保存 `pending_stop_id`、`tour_mode`、`stop_phase`；不污染 TourState 的路线事实字段。
- 已废止“到达即完成”：计划内到达仅记录当前位置并进入 `explaining`；只有 `confirm_stop_complete()` 会将该点从 remaining 移入 visited。最后一站也必须确认后才结束。
- 保留冻结契约的 `self_arrival`：合法但非 pending 的空间点会记录真实当前位置与 `last_arrival_kind=self_arrival`，但不改变正式路线顺序、已访问或跳过记录。
- 有当前未确认讲解点时，`next_stop` 会返回结构化 `invalid_phase`；重规划保留该点一次、不将其作为新候选重复加入；跳过当前点只进入 skipped。
- `agent_graph.py` 的既有确定性到达、下一站、跳过、改时间和结束节点已改为调用适配层。自然语言“确认完成”意图与按钮协议仍按阶段边界留给 A1-2/A1-3。
- 已使用项目虚拟环境完整路径运行 62 项回归测试，覆盖 TourState、A1 交互、导航、重规划、Agent、路线、空间图、动态路线、锚点基准与人工审核报告；结果均为 `OK`。
