# 陈家祠智能导游 Agent

面向陈家祠实地游览场景的受控智能导游系统。项目以审核知识、确定性路线和可追踪游览状态为可信底座，通过“内容计划 → 角色生成 → 安全校验 → Active 发布或确定性回退”机制，在不改变事实、路线和状态的前提下提供角色化讲解。

当前开发分支为 `experiment/agent-orchestration-v2`。比赛版本已经跑通完整导游主流程，并实现 18 种风格在审核点位讲解场景中的有限 Active 闭环。

比赛资料已于 2026-08-15 按代码基线 `5ffa38a` 冻结为历史快照。后续开发以完整产品功能为目标，不再为 Demo、路演或比赛展示范围调整功能；比赛文档只保留当时事实，不跟随后续产品版本更新。

## 项目定位

系统不是让大模型自由规划路线或编造讲解，而是把职责拆分为三个层次：

```text
Agent：理解游客表达，生成受控语义和角色表达候选
Workflow：决定路线、状态变化、事实范围和业务执行
Validator：检查事实、风格、安全、预算和游客输出边界
```

核心链路如下：

```text
游客输入
→ 语义归一与意图仲裁
→ VisitorProfile / 路线 / TourState / 审核知识
→ 确定性权威正文
→ 结构化 ContentPlan
→ 角色表达候选
→ Schema、事实、安全、风格和预算校验
→ 通过且命中白名单：有限 Active
→ Shadow 或校验失败：保留确定性旧链正文
→ Coverage 单次提交与 LangSmith 审计
```

## 已实现能力

### 导游主流程

- 游客画像收集：语言、游览时长、兴趣、讲解深度和角色偏好；
- 自然语言归一、语义候选和确定性意图仲裁；
- 审核路线选择、路线规划和游览开场；
- `TourState` 状态管理和线程隔离；
- 到达、完成、跳过、下一站和受控重规划；
- 审核空间关系下的定位与引路；
- 点位讲解、游览总结、称号和祝福；
- 周边 POI、拍照点位和安全建议。

### 审核知识与问答

- 本地混合检索：BGE 稠密检索、BM25、RRF 融合与条件重排；
- 建筑、工艺、纹样、装饰对象和术语问答；
- 对象级审核证据、工艺实例、比较、研究和观察引导；
- 游客正文与内部来源、文件路径、节点名和审计字段隔离；
- 证据不足、对象不一致或事实越界时失败关闭。

### 角色化讲解

- 18 种角色表达策略和角色连续性审计；
- 空间、工艺、纹样/构件三类点位内容的差异化表达；
- 统一连续导览正文，不输出资料卡标题、Markdown 列表或内部字段；
- 模型只提交审核事实令牌，角色连接语由服务端确定性渲染；
- 事实保持原字、原顺序和原次数；
- 非法 JSON、事实漂移、内部字段泄漏、预算超限或互动违规时自动回退；
- `Coverage` 原子提交和幂等审计，避免重复讲解。

## Active、Shadow 与功能边界

角色能力默认关闭，只有同时满足总开关、能力开关、风格/场景白名单和候选校验时才会接管游客正文。

以下是已冻结比赛版本的历史展示口径，不代表后续产品版的最终开放范围：

| 场景 | 当前状态 |
|---|---|
| 18 种审核风格的点位讲解 | 有限 Active |
| 古风书生的路线规划与游览开场 | 比赛主展示 Active |
| 其他风格的路线规划与开场 | 按白名单控制，非比赛主展示范围 |
| 角色化问答与追问 | Shadow |
| 角色化引路、结束语和重规划说明 | Shadow 或确定性旧链 |
| 自由 Planner 修改路线或状态 | 禁止 |
| 语音、多场馆和生产级全量灰度 | 尚未实现 |

Shadow 会生成并校验候选用于审计，但游客继续看到确定性正文。角色生成和验证节点不得修改 `TourState`、`VisitorProfile`、路线、Proposal、StopProgram 或审核事实。

## 当前验证状态

仓库中最近记录的验收结果：

```text
完整回归：1170/1170 passed_by_operator（99.014 秒）
最新 Active 定向验证：59/59 passed_by_operator
18 风格 × 3 内容类型矩阵：54/54 passed
最新连续排版相关离线回归：134/134 passed
高风险角色人工抽样：7/7 passed_by_operator
P0 游客输出与安全矩阵：3/3 passed_by_operator
```

上述结果是仓库保存的阶段验收记录。2026-08-15 的完整回归确认 1170 项全部通过；长点位讲解在角色 scaffold 超出剩余预算时会失败关闭并保留完整旧链正文，不写入游览状态。新版 18 风格完整 Studio 人工矩阵和连续排版改造后的远程 LangSmith 数据集复测仍待完成，不能据此宣称所有角色和场景已经全面上线。

已冻结的比赛口径见：

- `data/chen_clan_academy/evaluation/handoffs/competition_scope_and_demo_baseline.md`
- `data/chen_clan_academy/evaluation/handoffs/role_narration_continuous_layout_and_typed_style_handoff.md`

## 技术栈

- Python 3.11+
- LangGraph / LangChain
- DeepSeek Chat Model
- ChromaDB
- Sentence Transformers / BGE
- BM25 + RRF
- NetworkX
- LangSmith
- Streamlit

## 本地运行

### 1. 创建环境并安装依赖

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

不要提交本地 `.env`。至少按实际运行目标配置模型密钥；需要 LangSmith 观测时再配置相应 tracing 环境变量。

### 2. 构建本地知识索引

```powershell
.\.venv\Scripts\python.exe build_index.py
```

### 3. 启动 LangGraph Studio

```powershell
.\run_langgraph_studio.cmd
```

也可以直接启动开发服务：

```powershell
.\.venv\Scripts\langgraph.exe dev
```

LangGraph 配置位于 `langgraph.json`，主图入口为 `agent_graph.py:studio_agent_graph`。

### 4. 启动比赛演示前端

```powershell
.\.venv\Scripts\python.exe -m streamlit run demo\streamlit_app.py `
  --server.address 127.0.0.1 `
  --server.port 8502
```

`webapp.py` 是 Agent Server 应用，不是 Streamlit 页面。完整部署配置见 `demo/README_DEPLOY.md`。

## 角色能力开关

默认关闭角色 Active：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "off"
```

开启 Shadow：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "shadow"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration"
```

有限 Active 除 rollout 配置外，还必须显式配置：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration,role_qa"
$env:PRODUCT_ROLE_ACTIVE_ENABLED = "true"
$env:PRODUCT_ROLE_ACTIVE_STYLES = "child,ancient_scholar"
$env:PRODUCT_ROLE_ACTIVE_SCENES = "route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail"
$env:PRODUCT_ROLE_ROLLOUT_PERCENTAGE = "100"
$env:PRODUCT_ROLE_KILL_SWITCH = "false"
$env:PRODUCT_ROLE_VALIDATION_LEVEL = "strict"
$env:PRODUCT_ROLE_FALLBACK_POLICY = "legacy"
```

实际演示前应根据已经验收的风格和场景设置最小白名单。18 风格全矩阵验收的完整列表见 `demo/README_DEPLOY.md`。任何配置不完整、未知风格或未知场景都会失败关闭。修改 Active 配置后必须重启 Streamlit 并新建会话。

## 测试

运行完整单元测试：

```powershell
$env:LANGCHAIN_TRACING_V2 = "false"
$env:LANGSMITH_TRACING = "false"
.\.venv\Scripts\python.exe -m unittest discover
```

运行角色讲解相关定向测试：

```powershell
.\.venv\Scripts\python.exe -m unittest `
  test_role_narration_continuous_layout.py `
  test_role_narration_style_matrix.py `
  test_role_narration_generation.py `
  test_role_narration_graph.py
```

在线 LangSmith 与模型集成测试需要有效网络和 API 配置；离线自动测试不能替代 Studio 人工验收。

## 目录说明

```text
agent_graph.py                     LangGraph 主图与业务节点
controlled_rollout.py              Shadow / Active / 白名单控制
rag_ingestion.py                   知识切分与索引构建
rag_retrieval.py                   混合检索与重排
route_planner.py                   审核路线规划
tour_state.py                      游览状态合同
narration_content_plan.py          点位讲解内容计划
role_narration_generation.py       角色候选生成
narration_validation.py            事实、风格、安全和排版校验
narration_rendering.py             确定性讲解渲染
data/chen_clan_academy/            审核知识、路线、风格和验收证据
tools/                             数据构建与评估工具
test_*.py                          单元、集成和回归测试
```

## 下一步

1. 在后续代码或配置变更后持续重跑 1170 项完整回归；
2. 实现长点位讲解的预算自适应与安全分轮输出；
3. 将角色化问答从 Shadow 推进到经过验证的产品 Active；
4. 完成角色化引路、游览结束语和重规划说明；
5. 将比赛专用白名单演进为按风格、场景和验证等级控制的产品配置；
6. 补齐完整游览流程的多轮角色连续性与线上观测。

## 安全与提交约定

- `.env`、API Key、Trace 凭据和本地运行日志不得提交；
- 角色模型不得新增未经审核的人物、年代、故事、路线或空间关系；
- 不得把 Shadow 候选描述成游客已经看到的 Active 正文；
- 修改角色配置后至少重跑 54 条风格矩阵和故障回退测试；
- 修改路线、状态或 Coverage 前必须补充对应状态不变量测试。

远端仓库：<https://gitee.com/balegezhua/cjctourist_agent>
