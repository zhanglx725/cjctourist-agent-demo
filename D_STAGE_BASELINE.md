# D 阶段协作基线（草案，待本机与 LangSmith 验证）

> 本文件是两位队友的共同起点。完整本机回归与固定 LangSmith 场景已由项目负责人完成；`handoff_commit` 将在 E1 提交产生后写入。

## 基线身份

```text
baseline_id: D_STAGE_BASELINE_V1
functional_baseline_commit: 079a1f1
branch: main
remote: origin / https://gitee.com/balegezhua/cjctourist_agent.git
git_verification_date: 2026-07-27
frozen_at: 2026-07-27
handoff_commit: pending
```

只读 Git 核查结果：`HEAD` 与 `origin/main` 均为 `079a1f1`，工作区干净；D7 验收 YAML、D7 测试和 D6 运行模块均已纳入该提交。`git diff --check` 已通过。

## 环境与测试状态

| 项目 | 当前记录 |
| --- | --- |
| 操作系统 | Windows 项目环境；具体版本待本机记录 |
| 虚拟环境解释器 | `D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe` |
| Python 版本 | 项目虚拟环境已在本机运行；详细版本待下次环境采集补充 |
| 主要依赖 | LangGraph / LangChain / LangChain-DeepSeek / ChromaDB / Sentence-Transformers / rank-bm25 / NetworkX / PyYAML |
| 完整测试入口 | `"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest discover -v` |
| 完整回归结果 | `OK` |
| 测试数量 / 通过 / 失败 / 时间 | `374 / 374 / 0 / 8.318s` |
| 执行日期 | 2026-07-27 |

当前受限执行环境仍无法启动该 `.venv`：它引用的 Windows Store 基础 Python 路径在该环境不可访问。本机 `374 tests / 8.318s / OK` 是项目负责人提供的正式基线结果，不应误写为沙箱执行结果。

本机记录命令：

```cmd
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -c "import sys; print(sys.executable); print(sys.prefix); print(sys.version)"
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest discover -v
git diff --check
git rev-parse HEAD
```

## LangSmith 验收状态

以下固定场景已由项目负责人在 LangSmith 完成并确认通过；本轮未保存可直接引用的 Trace URL，因此后续异常复现时应补填对应 Trace 或运行记录。

| 场景 | 固定输入/动作 | 预期节点或边界 | 当前结果 | Trace/记录 |
| --- | --- | --- | --- | --- |
| 路线规划 | 我有30分钟，喜欢灰塑，请规划路线 | profile_collection → direct_route | 通过 | 项目负责人 LangSmith 检查 |
| 到达与站点讲解 | 我到前院中部了 | tour_event → stop_guidance | 通过 | 项目负责人 LangSmith 检查 |
| 点位清单 | 这里有什么？ | tour_qa；不改进度 | 通过 | 项目负责人 LangSmith 检查 |
| 术语定义/英文 | 灰塑是什么？ / 栏杆英文怎么说？ | D2；英文受能力门控 | 通过 | 项目负责人 LangSmith 检查 |
| 研究观点与限制 | 从研究角度如何理解灰塑？ / 这个结论有什么限制？ | D3；归因与限制 | 通过 | 项目负责人 LangSmith 检查 |
| 普通/学术比较 | 灰塑和砖雕有什么区别？ / 从学术角度比较灰塑和砖雕 | D4；范围、维度与限制 | 通过 | 项目负责人 LangSmith 检查 |
| 打卡推荐 | 这里怎么拍？ / 推荐几个打卡点 | D6；仅编辑候选，不改路线 | 通过 | 项目负责人 LangSmith 检查 |
| 讲解结束与确认 | 本点讲解结束 / 确认完成本点 | explanation_finished → confirm_stop_complete | 通过 | 项目负责人 LangSmith 检查 |
| 多意图澄清 | 把这个打卡点加入路线，再告诉我怎么拍 | 仅澄清，不部分执行 | 通过 | 项目负责人 LangSmith 检查 |
| 连续对话 | 规划→到达→讲解→D2→D3→D4→D6→结束→确认 | thread 内状态连续、问答只读 | 通过 | 项目负责人 LangSmith 检查 |

## 已冻结候选能力（待验证后正式冻结）

- A1：唯一事件适配层、到达不等于完成、仅确认完成写入 `visited_stop_ids`。
- A2：游览中点位问答与导游上下文恢复，问答只读。
- B：StopProgram 仅从当前点审核文物中选物，受时间预算约束。
- C：VisitorProfile 是当前会话偏好事实源；GuidancePolicy 是其确定性执行策略。
- D1：异构卡片统一只读注册、资格门控与失败关闭。
- D2：术语字段/英文能力门控。
- D3：研究观点归因、范围与限制。
- D4：比较优先于术语，研究比较受资格门控。
- D5：打卡内容为项目编辑候选，平台观察仅内部使用。
- D6：明确拍照意图的只读推荐，不自动加入路线。
- D7：`dst_acc_001`--`dst_acc_017` 综合验收编号与状态边界；运行基线已验证，内容精进人工复核可继续。

## 已知限制

- 打卡内容是项目编辑建议，不是实时热门、最佳机位、馆方认证或现场开放承诺。
- 部分卡片仍需补充来源、现场复核或内容精进；`runtime_status` 的具体含义必须遵循 D1/D5 文档，不能自行扩大。
- 当前记忆主要是 `MemorySaver + thread_id` 的会话内 Checkpointer；服务重启后不保证恢复。
- 尚未建立生产级持久化数据库、跨会话长期画像或自动对话摘要。
- 风格素材库、主题路线、真实 UI、实时客流/开放信息、多语言与无障碍模块尚未正式接入。
- LangSmith 实际节点、来源和状态差异仍待人工验收。

## 允许优化范围

队友可提出或在独立分支实现：内容事实修正、来源补充、空间映射修正、卡片质量、回答表达、个性化、主题路线、新验收案例、UI 和体验建议。

## 禁止自行改变

未经“规划—实现冲突”报告与统一确认，不得自行改变：

```text
TourState 事件语义
到达不等于完成
VisitorProfile 唯一事实源
知识问答不修改路线
基础 RAG 与知识卡职责边界
空间图和审核 node_id
thread_id 会话隔离
卡片资格门控
D2 至 D6 路由边界
```

## 验收与后续规划引用

- D7 验收矩阵：`data/chen_clan_academy/evaluation/d_stage_acceptance_cases_v1.yaml`
- D7 契约测试：`test_d_stage_acceptance_cases.py`
- D1--D6 模块测试：`test_knowledge_card_registry.py`、`test_term_card_runtime.py`、`test_agent_research_qa.py`、`test_agent_comparison_qa.py`、`test_photo_spot_validation.py`、`test_photo_spot_runtime.py`、`test_agent_photo_qa.py`
- 人工验证标准：`POST_D_TEAM_EVALUATION_AND_OPTIMIZATION_STANDARD.md`
- 后续交接规划：`POST_D_TEAM_EXECUTION_AND_HANDOFF_PLAN_V0.md`

## 队友分支起点（等待 E1 验证后执行）

两位队友不得从旧分支继续开发。待 `handoff_commit` 填写后，均从该提交创建：

```text
codex/content-experience
codex/platform-productization
```

开始前必须报告：本地当前提交、目标基线提交、工作区状态、是否存在未提交修改。
