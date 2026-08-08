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

- 角色定向测试：22/22 passed
- P0 安全/游客输出：18/18 passed
- 完整回归：1053/1058；仅保留既有 5 项失败
- 既有 5 个基线问题：保持原状态，未混入本阶段。
- Trace 元数据：metadata_unavailable（本阶段尚未保存人工 Trace 元数据）。

## 当前未完成

- navigation 角色化正文 Shadow
- tour_closing 角色化正文 Shadow
- 全流程角色连续性验证
- Active 接管

## 下一位负责人任务

1. 先阅读本 handoff、`change.md`、角色 Shadow 实现和 `presentation_content_plan`。
2. 实现 navigation 与 tour_closing 的角色化正文 Shadow。
3. 保持旧链游客正文不变。
4. 验证路线方向、路径、时间、安全提示和已完成内容不漂移。
5. 静听模式不得新增互动任务。
6. 失败时必须回退旧链。
7. 完成自动化测试、P0 测试和最少人工验证后，再同步文档并提交。

## 禁止事项

- 不得开启 Active；
- 不得修改 TourState 或路线状态；
- 不得修改知识卡、空间数据或 RAG 事实；
- 不得修复之前 5 个基线问题；
- 不得通过修改断言掩盖失败；
- 发现规划—实现冲突时必须停止并报告。
