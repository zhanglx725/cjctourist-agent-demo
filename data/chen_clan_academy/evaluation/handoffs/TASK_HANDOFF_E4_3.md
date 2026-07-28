# TASK_HANDOFF_E4_3：统一中文时长解析与游览中重规划

## 任务状态

- 阶段：E4-3
- 实现状态：已完成
- 本机回归：项目负责人已确认通过
- LangSmith：待按本文件场景复核
- 提交状态：尚未提交；请勿把本交接文件单独当作已冻结基线

## 解决的问题

路线初始化、画像收集、文本意图识别与游览中剩余时间更新曾各自维护时长识别规则。中文表达如“一个小时”“半小时”或“一个半小时”可能在不同入口得到不同结果，进而影响路线预算和重规划一致性。

## 根因

时长语义分散在 `agent_graph.py`、`profile_dialogue.py`、`tour_intent.py` 与 `profile_update.py` 的局部规则中；其中部分规则只覆盖阿拉伯数字，且缺少统一的歧义处理和业务语境判断。

## 实现方法

1. 新增 `duration_parser.py`，以纯函数 `parse_duration_minutes()` 输出整数分钟、`no_duration` 或 `ambiguous_duration`。
2. 提供 `has_route_duration_context()` 与 `has_remaining_duration_context()`，将“识别时长”与“是否可用于路线/重规划”分离。
3. 让路线初始化、画像收集、文本事件与画像更新时间统一调用该模块。
4. 仍复用 C1 的 VisitorProfile 合法性校验与既有 A1 `replan_time`；本任务不改变空间图、路线算法或 A1 站点完成语义。

## 支持的表达

| 表达 | 分钟 |
|---|---:|
| `30分钟`、`三十分钟`、`半小时` | 30 |
| `一个小时`、`一小时` | 60 |
| `一个半小时`、`一小时半`、`1.5小时` | 90 |
| `两小时`、`两个小时` | 120 |
| `一刻钟`、`三刻钟` | 15、45 |

## 修改文件

- `duration_parser.py`
- `agent_graph.py`
- `profile_dialogue.py`
- `profile_update.py`
- `tour_intent.py`
- `test_duration_parser.py`
- `test_e4_duration_integration.py`
- `data/chen_clan_academy/evaluation/d_stage_optimization_backlog_v1.yaml`
- `PROJECT_PROGRESS_REPORT.md`
- `COLLABORATION_GUIDE.md`
- `PROJECT_LEARNING_AND_DEFENSE_GUIDE.md`

## 不支持或仍需澄清的边界

- 没有路线或剩余时间语境的数字不作为导览时长使用。
- 冲突表达（例如“我有三十分钟或一个小时”）不会部分更新，必须澄清。
- 解析出的分钟数不自动代表产品可服务：仍由 VisitorProfile 和路线预算范围验证；例如已解析但不符合当前范围的值会安全拒绝。
- 本任务不支持由 LLM 猜测“差不多”“稍后”“久一点”等非精确时长，也不实现秒级、日期或跨会话时间记忆。

## 测试命令

在 Windows CMD 中使用项目虚拟环境：

```cmd
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest -v test_duration_parser.py test_e4_duration_integration.py test_tour_intent.py test_agent_tour_state.py test_tour_interaction_e2e.py
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest discover -v
git diff --check
```

项目负责人已报告上述定向测试及完整回归均通过；本受限执行环境不能启动项目虚拟环境，因此未将本机结果伪称为沙箱测试结果。

## LangSmith 待验证场景

1. `我有一个小时，喜欢灰塑，标准讲解，帮我规划路线。`
   - 期望：收集/初始化使用 60 分钟；无多余 RAG；TourState 快照为 60。
2. 在已到达但未确认完成的站点输入：`我现在只剩半小时。`
   - 期望：走画像更新与确定性重规划；保留 current/pending、visited、skipped 与 A1 阶段语义。
3. `给我规划一条半小时路线。`
   - 期望：30 分钟进入画像/路线流程，缺少的兴趣或深度继续定向追问。
4. `我有三十分钟或一个小时，帮我规划路线。`
   - 期望：澄清，不生成半份画像或路线。
5. `陈家祠建了多少年？`
   - 期望：保持事实问答链路，不误判为时长路线请求。

## 对队友数据工作的影响

无。该任务不修改知识卡、来源、空间节点、空间边、路线模板、点位映射或卡片 ID。新增时长表达时，请只修改公共解析器并补测试，不要在数据卡或各自模块中复制时长规则。

## 下一步

完成上述 LangSmith 验证后，更新问题池 `e3_002_duration_normalization_and_replanning` 的验证信息并与本轮代码一并提交。E4 其余问题仍应按已冻结 backlog 的优先级处理，不能借本次改动改变 A1 交互契约。
