# Role Narration LengthFinishReasonError 修复交接

## 问题基线

```text
branch: experiment/agent-orchestration-v2
reported_commit: 8d334ba
mode: shadow
active_takeover: disabled
reason_code: model_unavailable:LengthFinishReasonError
```

真实 `stop_guidance` 的 `narration_content_plan` 已为 `ready`，但角色模型在
完整候选 JSON 返回前达到 1800 token 上限。原调用绑定了
`response_format={"type":"json_object"}`，使当前 LangChain/OpenAI SDK 走
`chat.completions.parse()`。当 `finish_reason=length` 时，SDK 会在项目自己的
严格 JSON 解析器看到原始响应前抛出 `LengthFinishReasonError`。

## 修复

- 角色模型改用普通 Chat Completions 文本返回，不再调用 SDK structured-output
  parse；项目原有的精确字段 Schema 解析继续作为唯一候选入口；
- DeepSeek V4 显式设置 `thinking.type=disabled`，避免默认思考内容耗尽最终
  JSON 的输出预算；JSON Output 通过 `extra_body` 下发，不触发 SDK parse；
- `ROLE_NARRATION_MAX_TOKENS` 默认值由 1800 调整为 4096；
- token 配置限制在 512–8192，非法配置失败关闭；
- 即使普通响应返回 `finish_reason=length`，也明确拒绝部分 JSON，不尝试接受；
- 提示仍携带全部审核事实、`must_include`、`must_not_claim`、预算和互动边界；
- 模型在 `public_text` 中排列不可变的 `[[FACT_000]]` 占位符，生成模块在验证前
  确定性替换为审核 statement；模型不再负责逐字重打事实；
- 缺少、重复或未知事实占位符以 `invalid_fact_placeholders` 失败关闭；
- 仅移除模型不需要的 `stop_id`、`already_covered` 等非表达字段；
- Schema 修复请求中截取的错误输出由 2000 字符缩减为 500 字符，避免第二次
  请求无意义膨胀；
- 候选 Schema、事实逐字保留、事实 ID、安全输出、静听、预算和状态写入校验
  均未放宽；
- rollout 仍为 Shadow，`active_takeover=false`，旧游客正文仍为权威输出。

## 自动化验证

新增或更新测试覆盖：

- 模型调用不再绑定 `response_format`；
- 默认角色输出预算为 4096；
- `finish_reason=length` 明确失败关闭；
- 越界 token 配置被拒绝；
- 紧凑提示仍保留全部事实及 `must_include`；
- 不可变事实占位符可恢复为逐字审核原文，缺失与未知占位符均拒绝；
- 严格候选 Schema 和原有安全校验保持不变。

## 修复后单点位冒烟

使用全新 Thread 和最新 Graph：

```text
中文，定制模式，60分钟，我喜欢灰塑和木雕，选择中性清晰风格
我到前院中部了
```

通过标准：

```text
generation_status = generated
public_text 非空
validation_status = accepted
active_takeover = false
legacy_message_preserved = true
same_public_message = true
same_fact_boundary = true
public_message_safe = true
state_writes = []
内部字段泄漏 = 0
```

仅当该冒烟测试稳定通过后，恢复 18 种风格批量验收。

## 第二轮质量门修复

首次 Studio 复测确认长度截断已解除，但暴露出三个后续阻断：

```text
role_mode_status = not_requested
same_fact_boundary = false
role_consistent = false
within_budget = false
```

根因与修复：

1. `role_mode_shadow` 仍停留在早期三角色范围。现已统一使用审核风格目录与
   `profile_dialogue` 的18种受控别名，`neutral` 及其余审核风格均可产生
   `selected` 审计；未知风格继续澄清。
2. 原 JSON 示例只使用第一条 fact，并把剩余 facts 标为 omitted，与 required
   契约冲突。示例现使用所有 required fact IDs 和所有 required tokens，仅允许
   optional facts 进入 omitted。
3. 提示新增确定性 `max_public_text_characters` 和
   `max_role_connector_characters`。连接语预算取事实恢复后的剩余字符与既有连接
   上限的较小值；若 required facts 本身已超过内容预算，则在调用模型前以
   `fact_budget_infeasible` 失败关闭，不生成注定超预算的候选。

真实 DeepSeek 两事实调用验证结果：

```text
finish_reason = stop
reasoning_length = 0
exact_schema = true
style_id = neutral
FACT_000 count = 1
FACT_001 count = 1
unknown token count = 0
used_fact_ids = fact:a,fact:b
omitted_count = 0
```

批量测试仍保持暂停，必须先在全新 Studio Thread 中重跑同一中性清晰单点，
并确认 `validation_status=accepted` 后才能恢复。
