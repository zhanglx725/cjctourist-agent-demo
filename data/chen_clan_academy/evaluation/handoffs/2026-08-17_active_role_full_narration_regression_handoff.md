# 2026-08-17 Active 角色全文讲解：回归通过后的交接

## 当前结论

本轮受控自然全文讲解、详情状态隔离、Active Coverage 统计与测试环境兼容已完成统一自动化回归：

```text
Ran 120 tests in 30.986s
OK
```

这只表示下列自动化契约通过；不表示 18 种风格或 60 分钟全程体验已经人工验收。

## 已完成的修改

1. **受控自然全文角色讲解**
   - 18 种角色均可使用 `role_discourse` 生成开场、承接、观察与收束；审核事实仍由服务端事实块约束。
   - 允许自然短段落，不再因为正常换行直接判失败。
   - 新旧模型候选协议兼容：开启 `PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED=true` 时，旧 token 候选仍按严格旧协议校验；新版自然叙事使用独立 schema。错误输出仍 fail-closed。

2. **路线场景自然表达基础**
   - 在 Active 且两个自然叙事开关均开启时，路线规划、开场、引路、结束可由模型围绕不可改写的路线句单元组织表达。
   - 路线、时间、方向和站点信息仍是锁定单元，模型不能新增或重排。

3. **详情与状态完整性**
   - `request_stop_detail` 改用 E5 审核证据路径，且作为只读重讲：不写 Coverage、不创建待续讲、不附加完成/下一站服务尾、不触发主动拍照。
   - 详情可进入 Active 角色生成；失败时只回退当前点安全正文，不改变 TourState。
   - 详情后的 `active_stop_program.node_id` 必须等于 `tour_state.current_stop_id`。

4. **Coverage 与总结口径**
   - 结束总结现在识别 `narration_commit` 与 `deterministic_narration_fallback` 的首讲 Coverage，避免 Active 成功发布却被总结误报为“无可确认覆盖”。
   - 主动拍照仍允许在已审核、路线计划且适宜的到站位置出现，但必须独立成服务段、无内部术语；详情不触发。

5. **风格选择入口**
   - 自定义画像正在询问讲解风格时，中文显示名会作为当前字段答案处理，不再先走独立角色切换导致重复询问。

## 本地启动配置

在同一个 PowerShell 窗口设置。新开终端需要重新设置：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration,role_qa"
$env:PRODUCT_ROLE_ACTIVE_ENABLED = "true"
$env:PRODUCT_ROLE_ACTIVE_STYLES = "neutral,child,family,student_research,professional,listen_only,mixed_group,dominant_ceo,cute_junior,ancient_scholar,warm_sister,bestie_chat,buddy_guide,exploration_game,photo_guide,hostel_scholar,xiguan_young_master,cantonese_storyteller"
$env:PRODUCT_ROLE_ACTIVE_SCENES = "route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail,navigation,tour_closing,replan_presentation"
$env:PRODUCT_ROLE_ROLLOUT_PERCENTAGE = "100"
$env:PRODUCT_ROLE_KILL_SWITCH = "false"
$env:PRODUCT_ROLE_VALIDATION_LEVEL = "strict"
$env:PRODUCT_ROLE_FALLBACK_POLICY = "legacy"
$env:PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED = "true"
$env:PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED = "true"
.\.venv\Scripts\python.exe -m streamlit run demo\streamlit_app.py --server.address 127.0.0.1 --server.port 8502
```

## 队友下一步：只做一条 60 分钟主线复测

不要继续逐个风格重复人工展开节点。请选一个辨识度强的风格（优先 `bestie_chat`、`buddy_guide`、`exploration_game` 或 `ancient_scholar`），完成以下固定路径：

1. 中文 / 定制模式 / 60 分钟 / 兴趣选择“灰塑”或“工艺、故事” / 深度讲解；
2. 在风格选择问题出现时，直接输入中文显示名，不使用“跳过”；
3. 生成路线后，到第一站并完成本点；
4. 到第二、第三个正式讲解点；如路线经过月台，必须在月台观察一次；
5. 在一个当前点输入“再讲详细一点”，随后“完成本点”，再到下一站；
6. 结束导览。

## 仅记录这些结果

### 游客端

- 路线规划、开场、首站、第二/第三站、月台、详情、引路、结束是否持续带有同一角色的关系感和叙事节奏；
- 后续站是否回落为通用资料卡/成人术语长段；
- 月台是否讲到该站承诺的栏杆、望柱、通花装饰或对应工艺，而不是错换到木雕等其他点位；
- “详情→完成→下一站”和“直接完成→下一站”是否出现不同的下一站内容、Coverage 或信息密度；
- 主动拍照是否仅在合适点位以独立、自然、无内部术语的短段出现；
- 文本是否有自然短段，不再全部挤成一个大段或产生异常缩进。

### LangSmith（仅在游客端失败时展开）

对**首个失去风格的后续点位**按顺序展开：

```text
visitor_localization
  → performance_metrics
    → stop_guidance
    → role_narration_generation
    → narration_validation
    → narration_commit 或 deterministic_narration_fallback
```

记录字段：

```text
stop_guidance.status
role_narration_generation.status / model_called / role_mode_style_id
narration_validation.validation_status / reason_codes
narration_commit.active_takeover / commit_decision
deterministic_narration_fallback.fallback_used / reason_codes
active_stop_program.node_id（如可见）
```

## 未完成、待根据这次 60 分钟结果处理的重点

目前仍有一条人工现象待确认：**60 分钟模式可能只有首站保留角色风格，后续点位回落为通用输出。**

代码上，后续点位只有在 `stop_guidance.status == guided_e5` 时才会进入点位角色 Active 链。若复测出现回落，请先用上述字段确认是：

1. 后续站未取得 `guided_e5`；
2. ContentPlan / 预算拒绝；
3. 角色候选验证拒绝；
4. 提交阶段回退；
5. 点位程序与当前 `stop_id` 不一致。

不要仅通过在 YAML 增加口头禅，或放松事实/安全校验来处理；应修复实际截断节点，并保持“LLM 在受控知识内完整成文”的架构目标。
