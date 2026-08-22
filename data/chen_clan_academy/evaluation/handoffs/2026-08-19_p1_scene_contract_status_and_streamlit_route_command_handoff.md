# 2026-08-19 P1 场景合约阶段状态与 Streamlit 路线创建指令交接

## 1. 目的与当前结论

本交接记录承接 `2026-08-18_p1_p2_scene_contract_and_bounded_rewrite_handoff.md`。

P1 的代码级场景隔离、公开输出标注、定向/全量自动回归，以及 Streamlit 连续多节点人工验收均已完成并通过；P2（受边界的事实重组）尚未开始。

后续不得以 P1 名义扩大 LLM 对事实、安全结论或状态机的权限。

## 2. 本轮已完成内容

### 2.1 场景合约与公开消息

- 新增 `public_scene_contract.py`：登记 `arrival_confirmation`、`route_opening`、`stop_guidance`、`navigation`、`tour_qa`、`safety_refusal`、`tour_closing` 七种 P1 场景，声明输入、必需/禁止语义、角色/LLM 权限、校验器和回退名。
- 新增到达确认的确定性渲染：`你已到达{display_name}，现在开始本点讲解。`。
- 修复公开消息白名单遗漏：`arrival_confirmation`、`navigation`、`safety_refusal` 不再被 `_public_turn_from_result` 静默过滤。
- 普通问答保持 `tour_qa`；摄影安全拒绝、澄清及限制响应均标为 `safety_refusal`。

### 2.2 场景隔离

- 到达确认不再复用节点正文的 `point_narration_components['opening']`。
- 路线开场改为专用 `RouteOpeningBrief` / `render_route_opening`，只表达整体、路线主题、游览方式与第一站衔接，不再从节点正文借用 opening/closing。
- 节点正文保留兼容入口，但通过 `stop_guidance_compatibility_components()` 读取，生产渲染路径不再裸取 `opening[0]`。
- 正常 `tour_qa` 已绕过角色候选生成/验证/提交链，直接发布已通过事实与公开边界的答案，随后仅进入只读审计路径。

### 2.3 导航与安全拒绝校验

- `validate_navigation()` 仅接受由已核定空间图生成的完整导航文本；不允许混入节点故事或通用导游开场。
- `validate_safety_refusal()` 仅接受前置安全判定已经给出的确定性安全回复；不重新分类安全，也不进行角色改写、检索或重写。
- `tour_event_node` 在 `next_stop_ready` 时发布完整确定性导航（下一站、路径、预计步行、现场提示），并记录校验结果。
- `tour_qa_node` 对安全模式记录专用校验结果，普通问答仍不角色化。

### 2.4 测试与验证

- 新增/更新：`test_public_scene_contract.py`、`test_chat_public_turn.py`、`test_agent_tour_state.py`、`test_agent_tour_qa.py`、`test_tour_opening_program.py`、`test_e5_narration_style_integration.py`。
- 场景与安全定向回归：`Ran 98 tests ... OK`。
- 最终全量自动回归（禁用可选 LangSmith 上报、离线模式）：`Ran 1298 tests in 144.173s`，结果 `OK`。
- 已使用新的 Streamlit 会话完成连续多节点人工验收并通过：创建路线、到达首站、到达确认、路线开场、节点正文、完成本点和下一站导航均符合场景隔离与状态推进要求。

## 3. 已知缺口与未完成事项

### 3.1 P1 人工验收状态

Streamlit 连续多节点人工验收已完成并通过。已确认首站到达时先出现单句到达确认，再进入路线开场和节点正文；完成节点后得到独立的下一站导航，未观察到跨场景 opening、节点故事或状态推进串接。

### 3.2 儿童友好路线开场尚未体现风格

`RouteOpeningBrief` 已携带 `style_id`，但 `tour_opening_program.py::render_route_opening()` 当前只使用 `first_stop_display_name`，输出仍是固定中性模板。截图中的儿童友好开场因此看起来像中性开场。

这不是允许把节点正文的儿童 opening 重新拼到路线开场；正确修复是在 `route_opening` 合约内增加受约束的儿童友好语气模板，只改变称呼、句长与节奏，不改变整体介绍、路线事实、第一站名称或顺序。节点正文仍是儿童讲解风格的主要承载场景。

### 3.3 新增修改目标：修复 Streamlit 路线创建用指令无法识别

需要修复 Streamlit 中“用一句自然语言创建路线”的指令未被识别或未被正确转换为建路线请求的问题。该目标只涉及 UI 输入到现有受控路线创建入口的适配，不能绕过以下约束：

- 继续使用既有的 `route_initial_request`、资料收集和 `direct_route` 受控流程；
- 缺少语言、模式、时间、兴趣或风格时，进入既有的资料收集/澄清流程，不猜测或写入部分路线状态；
- 不把自然语言指令直接当作已核验的路线计划，不绕过时间解析、风格冲突校验、状态机或路线审计；
- 保持 Streamlit 表单“生成我的路线”与聊天输入两条入口的路线结果等价；
- 增加 UI/服务适配测试：典型完整指令、缺字段指令、冲突风格指令、英文/中文分钟表达、已有路线时的新路线请求。

建议先定位 `demo/streamlit_app.py` 的聊天提交与表单提交分别如何构造 `chat_public_turn` / 路线请求；复用已有完整资料输入格式，而不是新建第二套规划器。

## 4. 关键文件

- `agent_graph.py`
- `public_scene_contract.py`
- `tour_opening_program.py`
- `narration_rendering.py`
- `demo/streamlit_app.py`（下一目标的主要入口）
- `tour_navigation.py`
- `photo_spot_runtime.py`
- `tour_qa.py`

## 5. 不得回退的边界

- 不得恢复到达、路线开场或导航对节点正文 `opening` 的复用。
- 不得使安全判定落后于点位解析、摄影候选、RAG 或角色生成。
- 不得移除公共输出对内部字段、来源 ID、文件路径、审核状态等的隔离。
- 不得将正常问答重新接回角色候选生成/提交链。
- 未完成 P1 Streamlit 连续人工验收前，不得开始 P2 事实重组。

## 6. 建议执行顺序

1. 修复 Streamlit 自然语言路线创建指令识别，并为双入口等价性补测试；
2. 补齐 `route_opening` 的受约束儿童友好语气模板及测试；
3. P1 已完成并可关闭；在开始 P2 前，仍需确保 Streamlit 自然语言路线创建修复不回退 P1 已验收场景边界。
