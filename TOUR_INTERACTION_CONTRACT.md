# A1-0：游览交互状态与事件契约（冻结版）

**状态：冻结于 A1-0。** 后续 A1-1、A1-2、A1-3、A1-4 必须以本文件为唯一交互契约；若需改动字段或事件语义，先更新本文件、补测试，再改代码。

## 1. 边界与所有权

- `TourState` 保留路线事实：路线、当前位置、已访问点、跳过点、剩余点、时间和兴趣。它不包含按钮、页面或模型输出。
- 交互状态由 `tour_interaction.py`（A1-1）维护，字段为：
  - `pending_stop_id`：正在等待游客到达或确认完成的正式讲解点；
  - `tour_mode`：`chat`、`button_guided`、`continuous`；
  - `stop_phase`：`navigating`、`explaining`、`awaiting_confirmation`、`finished`。
- **只有确定性事件处理器**可以调用 `tour_state.py` 并修改 `TourState`。
- LLM 只能给出事件建议（例如 `suggested_event="arrive_at_stop"`）；A1-2 的受控路由须验证参数后才可分发事件。LLM 不得写入 `visited_stop_ids`、`current_stop_id`、`remaining_stop_ids` 等状态字段。
- A1-0 不调用 RAG。`request_stop_detail()` 的状态语义始终是无副作用；B3 可在适配器成功后使用当前 StopProgram 和既有 RAG 返回展开讲解，但不得改变 TourState。

## 2. 状态语义与现有实现的兼容调整

现有 A 阶段首版中，`arrive_at_stop()` 会立即把点写入 `visited_stop_ids`。**从 A1-1 起该语义废止：**

```text
导航至 pending_stop_id
→ arrive_at_stop(node_id)：只确认当前位置，进入 explaining
→ 讲解结束：进入 awaiting_confirmation
→ confirm_stop_complete()：才写入 visited_stop_ids，并生成下一 pending_stop_id
```

因此 `visited_stop_ids` 始终表示“已完成讲解的真实站点”，而非“刚到达的站点”。`current_stop_id` 可以是当前尚未完成的站点。该调整不删除既有事实字段，只改变其在统一事件层中的写入时机。

初始化路线后：

```json
{
  "pending_stop_id": "路线第一个正式讲解点",
  "tour_mode": "chat",
  "stop_phase": "navigating"
}
```

`finish_tour()` 后，无论是否仍有未完成点，`stop_phase` 必为 `finished`；TourState 保留真实的 visited / skipped / remaining 记录。

### A1-3 生命周期事件补充：`explanation_finished()`

这是 UI 或系统在**本点讲解播放/文本展示结束**后发送的生命周期事件，不代表游客完成参观。它只允许在“计划内当前站已到达、`stop_phase=explaining`”时执行：

```text
explaining → explanation_finished → awaiting_confirmation
```

它不写入 `visited_stop_ids`，不移除 `remaining_stop_ids`，不改变 `current_stop_id`、`pending_stop_id`、路线顺序或 `route_status`。最后一站也必须在之后由 `confirm_stop_complete()` 明确确认，才能结束路线。已经处于 `awaiting_confirmation` 时重复提交返回幂等成功；其他阶段返回结构化错误。所有调用仍必须经过 `handle_tour_event()`。

## 3. 统一响应结构

每个事件处理器均返回同一结构；失败时也必须返回结构化结果，禁止静默吞掉请求。

```json
{
  "ok": true,
  "event": "arrive_at_stop",
  "code": "arrived",
  "message": "已到达月台，可开始讲解。",
  "tour_state": {},
  "interaction_state": {
    "pending_stop_id": "label_moon_platform",
    "tour_mode": "chat",
    "stop_phase": "explaining"
  },
  "data": {},
  "idempotent": false
}
```

字段约定：

| 字段 | 含义 |
| --- | --- |
| `ok` | 事件是否被接受；拒绝时为 `false`。 |
| `event` | 白名单中的规范事件名。 |
| `code` | 稳定机器可读结果码，供 Agent 和按钮 UI 判断。 |
| `message` | 可直接展示的中文提示，不能代替 `code` 判断逻辑。 |
| `tour_state` | 处理后的 TourState 快照；拒绝时为处理前的安全快照或 `null`。 |
| `interaction_state` | 处理后的交互状态快照；拒绝时为处理前快照或 `null`。 |
| `data` | 事件附加数据，例如下一站导航、可用操作或占位讲解提示。 |
| `idempotent` | 重复事件未产生额外状态变化时为 `true`。 |

建议统一错误码：`route_not_initialized`、`tour_finished`、`invalid_node_id`、`invalid_event`、`invalid_phase`、`not_current_stop`、`stop_not_in_route`、`no_remaining_stop`、`invalid_minutes`。

## 4. 事件白名单与状态转移

| 事件 | 前置条件 | 状态变化 | 成功码 / `data` | 典型拒绝 |
| --- | --- | --- | --- | --- |
| `arrive_at_stop(node_id)` | 路线已初始化、未结束、`node_id` 是合法空间点；常规导览应等于 `pending_stop_id`。 | 更新 `current_stop_id`；匹配待到达站时进入 `explaining`。**不写入** `visited_stop_ids`。 | `arrived`；当前点讲解占位与可用操作。 | `route_not_initialized`、`tour_finished`、`invalid_node_id`、`not_current_stop`。 |
| `explanation_finished()` | 路线已初始化、未结束，当前点是 `pending_stop_id`，且 phase 为 `explaining`。 | 仅将 `stop_phase` 从 `explaining` 改为 `awaiting_confirmation`；不改变任何 TourState 事实字段。 | `explanation_finished`；等待游客确认、展开或跳过。 | `route_not_initialized`、`tour_finished`、`invalid_phase`、`not_current_stop`。 |
| `next_stop()` | 路线已初始化、未结束。 | 不改 TourState；仅计算/返回 pending 站及最短导航。 | `next_stop_ready`；节点、边、步行时间、讲解焦点。 | `route_not_initialized`、`tour_finished`、`no_remaining_stop`。 |
| `skip_stop(node_id \| current_stop_id)` | 路线已初始化、未结束；目标为未完成的正式讲解点。省略参数时优先当前待完成点，否则 pending 点。 | 目标从 `remaining_stop_ids` 移到 `skipped_stop_ids`；若跳过当前/待到达点，刷新下一 `pending_stop_id`，回到 `navigating`。 | `skipped`；下一站导航。 | `route_not_initialized`、`tour_finished`、`invalid_node_id`、`stop_not_in_route`。 |
| `replan_time(available_minutes)` | 路线已初始化、未结束、正整数分钟。 | 仅由现有确定性重规划器改写未完成部分；保留 visited/skipped；刷新 pending，进入 `navigating`。 | `replanned`；剩余路线与时间拆分。 | `route_not_initialized`、`tour_finished`、`invalid_minutes`。 |
| `finish_tour()` | 路线已初始化；已结束时允许重复。 | 调用确定性结束逻辑；交互阶段设为 `finished`。 | `tour_finished`；真实游览汇总。 | `route_not_initialized`。 |
| `request_stop_detail()` | 路线已初始化、未结束，且当前处于 `explaining` 或 `awaiting_confirmation`。 | 不改 TourState；保持当前 phase。 | `detail_requested`；B3 可在事件后展开当前 StopProgram 的有来源讲解。 | `route_not_initialized`、`tour_finished`、`invalid_phase`。 |
| `confirm_stop_complete()` | 路线已初始化、未结束、`current_stop_id == pending_stop_id` 且 phase 为 `explaining` 或 `awaiting_confirmation`。 | 此时才将当前正式点写入 `visited_stop_ids`，移出 remaining，刷新 pending；有下一站则 `navigating`，否则 `finished`。 | `stop_completed`；下一站导航或完成汇总。 | `route_not_initialized`、`tour_finished`、`invalid_phase`、`not_current_stop`。 |

### “到达非路线点”的规则

为保持 A 阶段已有“自主到达”能力，`arrive_at_stop()` 可以接受一个合法但非 `pending_stop_id` 的空间点，但只记录当前位置并返回 `self_arrival`；不得把它加入 visited，也不得推进正式路线。按钮模式默认不暴露此操作；文本模式可提示游客“当前正式下一站仍为 …”。

## 5. 幂等性与禁止的隐式行为

- 同一 `arrive_at_stop(pending_stop_id)` 重复提交：成功返回当前 `explaining` 状态，`idempotent=true`，不重复加入访问记录。
- 同一计划内站点的 `explanation_finished()` 在 `awaiting_confirmation` 重复提交：成功返回 `explanation_already_finished`，`idempotent=true`，不改变 TourState。
- 同一已完成站的 `confirm_stop_complete()` 重复提交：成功返回 `already_completed`，`idempotent=true`，不推进第二次。
- 已跳过站重复跳过：成功返回 `already_skipped`，`idempotent=true`。
- 已结束路线重复 `finish_tour()`：成功返回 `tour_already_finished`，`idempotent=true`。
- 不按预测时间自动完成站点；讲解回复结束后只能将 phase 置为 `awaiting_confirmation`，等待游客主动确认、要求展开或跳过。
- 不允许对非当前正式站执行完成确认；不得为了“容错”而偷偷把它计为已访问。

## 6. A1 各任务的实现边界

| 任务 | 必须遵守本契约的内容 | 不在该任务实现 |
| --- | --- | --- |
| A1-1 | 统一适配、状态校验、纯确定性事件分发、所有成功/拒绝/幂等测试。 | Agent 文本识别、按钮文案、RAG。 |
| A1-2 | 将文本映射为白名单事件建议并交给 A1-1；禁止直接改 TourState。 | 连续导游文案或 RAG 讲解。 |
| A1-3 | 使用统一响应生成连续导游回复与 `available_actions` 按钮协议；增加仅切换讲解生命周期阶段的 `explanation_finished`。 | 直接写 TourState、改动路线/空间/知识卡，或把讲解结束误记为参观完成。 |
| A1-4 | 覆盖 chat 与 button/continuous 的端到端流，回归现有 RAG、路线与 TourState 测试。 | 新增未冻结的事件。 |

## 7. A1-0 验收清单

- [x] 明确 TourState 与交互状态的所有权；
- [x] 冻结 8 个白名单事件与参数（A1-3 补充 `explanation_finished` 生命周期事件）；
- [x] 为每个事件定义前置条件、状态变化、成功码和失败码；
- [x] 明确“到达不等于完成”的兼容改造；
- [x] 规定统一响应包、幂等性及禁止自动完成；
- [ ] A1-1 依据本文件实现 `tour_interaction.py` 和单元测试。
