# Role Narration Shadow Handoff

## 当前基线

- branch: experiment/agent-orchestration-v2
- tested_commit: 72e16e0 + verified uncommitted role-text Shadow worktree
- active_takeover: disabled
- legacy_chain: preserved

## 已完成范围

- presentation_content_plan 已覆盖五类场景：
  - route_planning
  - route_opening
  - stop_guidance
  - navigation
  - tour_closing
- 角色模式已支持：
  - standard
  - scholar_style（实现 ID：`ancient_scholar`）
  - child_friendly（实现 ID：`child`）
  - listen_only
- 当前已实现并自动化验证的角色化正文 Shadow：
  - route_planning
  - route_opening
  - navigation
  - tour_closing
- 角色候选只做 Shadow 审计，不替换旧链游客正文。

## 安全与事实边界

- 路线、节点、时长、顺序、路径和安全要求仍来自确定性旧链。
- 角色只能改变语气、句式、节奏和内容组织。
- 不新增未经证据支持的事实、故事、对象或位置。
- 儿童模式不降低安全要求。
- 静听模式不增加主动提问和互动任务。
- 失败时回退旧链。
- 不写入 TourState、VisitorProfile、路线、proposal 或 StopProgram。

## 验证结果

- 早期角色定向测试：22/22 passed
- 最新 Navigation 定向测试：25/25 passed
- 最新 Tour Closing 定向测试：38/38 passed
- 最新五场景角色连续性：25/25 passed
- 最新 P0/结束态回归：31/31 passed
- 最新 P0/讲解/导航回归：32/32 passed
- 最新完整回归：1072/1072 passed
- 原有 5 个基线问题已在独立的 baseline cleanup 提交中解决。
- Trace 元数据：metadata_unavailable（本阶段尚未保存人工 Trace 元数据）。

## Navigation Shadow 补充实现

- `route_role_narration_shadow` 已扩展到 `navigation` 场景；
- 在受控 `tour_event` 产生导航正文后，由 `atomic_read_plan_shadow` 生成候选和审计；
- `standard`、`ancient_scholar`、`child`、`listen_only` 均有封闭的导航表达前缀；
- 候选必须逐字完整包含旧导航正文，因此点位、方向、路径、时间及安全提醒均可机械比较；
- 修改路径、删除旧正文、增加内部字段、超过预算或违反静听约束都会拒绝候选；
- Shadow 不发布候选，不写 TourState、VisitorProfile、路线、Coverage 或其他业务状态。

本轮自动化结果：

```text
navigation_role_targeted: 25/25 passed
p0_navigation_regression: 80/80 passed
full_regression: 1064/1064 passed
git_diff_check: passed
```

## Tour Closing Shadow 补充实现

- `tour_closing` 已接入 `post_visit_title_blessing → atomic_read_plan_shadow` 边界；
- 角色候选只包装已生成的结束正文，不读取或修改总结、称号策略与业务状态；
- 完成点位、内容覆盖、提问次数、兴趣、称号依据、称号和祝福仍完全由旧确定性链生成；
- 候选必须完整保留旧结束正文，任何数字、称号或安全边界漂移都会拒绝；
- 静听模式禁止角色层新增互动，但允许原有旧链周边推荐询问原样保留；
- 失败时继续使用旧结束正文，不写 TourState、VisitorProfile、Coverage、`visit_summary`、`post_visit_award` 或 `post_visit_nearby_offer`。

本轮自动化结果：

```text
tour_closing_targeted: 38/38 passed
p0_closing_regression: 31/31 passed
full_regression: 1067/1067 passed
git_diff_check: passed
```

## 五场景角色连续性验证

自动化测试已按真实节点顺序覆盖：

```text
route_planning
→ route_opening
→ stop_guidance
→ navigation
→ tour_closing
```

`ancient_scholar`、`child`、`listen_only` 三种已审核角色均满足：

- 五个场景使用同一 `selected_style_id`，不丢失、不串换；
- 普通问题后的角色继承来源为 `inherited_shadow`，不写 VisitorProfile；
- 冲突角色请求进入 `clarification`，不覆盖先前已选角色；
- 所有 Shadow 审计 `active_takeover=false`、`state_writes=[]`；
- VisitorProfile 与已选路线保持不变；
- 点位候选仍经过事实、预算、游客输出和静听约束验证。

本轮同时修复了一个连续性缺陷：历史 `active_narration_render_audit` 会在完成点位后遮蔽新的导航事件。场景识别现只依据最新 AI 消息的 `stop_guidance` 标记判断点位讲解，因此新的导航回复可正确记录为 `navigation`，而不会误用上一条开场或讲解审计。

```text
role_continuity_targeted: 25/25 passed
p0_guidance_navigation_regression: 32/32 passed
full_regression: 1071/1071 passed
```

## LangSmith 人工验收与案例 8 修复

人工案例 1–5 已全部通过：三种角色均贯穿五场景，普通问答后角色可恢复，完成点位后的最新审计正确标记为 `navigation`。案例 6、7、9、10 的总结、画像采集、故障回退与结束事件也通过或基本通过。

案例 9 使用独立进程设置 `CJC_ROLE_NARRATION_TEST_FAILURE=invalid_schema` 后，非法候选被拒绝，`active_takeover=false`、`legacy_message_preserved=true`，游客仍看到完整旧讲解。Studio 截图中 `model_called=false` 与原始审计预期存在差异，但不影响本次 fail-closed 和游客可见回退结论；后续如需核对模型调用统计，应展开同一轮 `role_narration_generation` 记录，避免读取相邻的计划或验证审计。

案例 8 原失败链为：角色冲突落入 `llm_think`，随后月台 `pending_stop_id` 未被正确续接，游客输入“到达”时再次被要求确认点位。本轮修复为：

- 新增 `pending_role_mode_clarification`，把冲突角色请求作为确定性待澄清控制；
- `route_initial_request` 在画像、LLM/RAG 回退之前优先路由到 `clarification`；
- 冲突不是角色切换，继续保留上一条已确认 `role_mode_shadow`；
- 澄清节点不写 TourState、VisitorProfile 或 `tour_interaction_state`；
- 原 `pending_stop_id=label_moon_platform` 保持不变；
- 澄清后输入“到达”可确定性进入 `tour_event` 并抵达月台。

自动化验证：

```text
role_conflict_and_arrival_targeted: 66/66 passed
p0_semantic_profile_regression: 64/64 passed
full_regression: 1072/1072 passed
```

## 当前未完成

- LangSmith 案例 8 修复后复测
- Active 接管

## 下一位负责人任务

1. 先阅读本 handoff、`change.md`、角色 Shadow 实现和 `presentation_content_plan`。
2. 在全新 Thread 中完成人工全流程角色连续性验收，并保存或如实标记 Trace 元数据。
3. 保持旧链游客正文不变。
4. 验证路线方向、路径、时间、安全提示和已完成内容不漂移。
5. 静听模式不得新增互动任务。
6. 失败时必须回退旧链。
7. 完成自动化测试、P0 测试和最少人工验证后，再同步文档并提交。

## 禁止事项

- 不得开启 Active；
- 不得修改 TourState 或路线状态；
- 不得修改知识卡、空间数据或 RAG 事实；
- 不得回退已经全绿的 baseline cleanup；
- 不得通过修改断言掩盖失败；
- 发现规划—实现冲突时必须停止并报告。
