# 2026-08-15 产品开发交接

## 1. 今日结论

今天完成了产品路线阶段 0、阶段 1、阶段 2，并完成阶段 3“角色化问答 Active”的代码实现和离线测试。阶段 3 尚未完成人工 LangSmith 验收：现场 Trace 显示 Streamlit 进程没有启用 `role_qa` rollout，因此 QA 候选没有调用模型，安全回退到了确定性答案。

当前分支：

```text
experiment/agent-orchestration-v2
```

当前最新提交：

```text
8643603 feat: add controlled QA role activation
```

提交后工作区干净。当前提交尚未推送远端。

## 2. 今日完成事项

### 2.1 冻结比赛资料并转入完整产品开发

- 比赛资料已经冻结，不再继续制作比赛 Demo。
- 比赛历史基线标签已经建立并推送：`competition-baseline-2026-08-15`，指向 `5ffa38a`。
- 完整产品路线图已写入 `end.md`。
- 产品功能状态矩阵已写入 `product_feature_status.md`。
- 比赛资料与产品新增功能已经分开管理。

### 2.2 阶段 1：产品级能力策略与场景校验

提交：

```text
f914498 feat: add product capability rollout policy
```

实现内容：

- 新增 `ProductCapabilityPolicy`、`ProductScenePolicy`、`ProductStylePolicy`。
- 支持按能力、场景、风格控制 Active。
- 支持 0～100% Thread 稳定灰度。
- 支持 kill switch。
- 支持严格校验等级和旧链 fallback。
- 新产品配置不完整时失败关闭，不回退到旧变量扩大权限。
- 保留比赛时期 `ROLE_ACTIVE_*` 环境变量兼容层。
- 拆分五类校验入口：
  - 点位讲解；
  - QA；
  - 导航；
  - 结束语；
  - 重规划说明。
- QA 不再受到点位 space/craft/ornament 组件校验误伤。

测试证据：

```text
定向测试：77/77 OK
完整回归：1180/1180 OK
```

### 2.3 阶段 2：长讲解预算与分轮输出

提交：

```text
297fff7 feat: add adaptive multi-turn narration
```

实现内容：

- 新增生成前 `NarrationBudgetDecision`。
- 支持四级预算策略：
  - `full`；
  - `compact`；
  - `split`；
  - `fallback`。
- 按 `fact_unit` 拆分，保持审核事实原文和顺序。
- 新增 `NarrationContinuation`，保存待讲事实原文、已发布事实和 freshness。
- 支持：
  - 继续；
  - 下一部分；
  - 接着讲；
  - 先讲工艺；
  - 跳过剩余内容。
- “继续前往下一站”不会被误识别为继续讲解。
- 路线、点位或角色变化后 continuation 失效。
- 使用两阶段提交：生成阶段只产生 pending，校验并发布成功后才推进 continuation。
- Coverage 只提交本轮实际发布的对象。
- fallback 不消费 continuation，不提前提交 Coverage。
- 同时兼容 `craft:灰塑` 和 `craft:灰塑:000` 两种事实 ID。

测试证据：

```text
预算合同：10/10 OK
分轮路由与提交定向测试：67/67 OK
完整回归：1210/1210 OK
```

### 2.4 阶段 3：角色化问答 Active

提交：

```text
8643603 feat: add controlled QA role activation
```

已实现：

- `tour_qa` 与 `qa_follow_up_detail` 使用独立产品场景。
- `ROLE_QA` 使用独立 rollout capability。
- QA 校验通过后进入唯一 commit 节点。
- commit 保留原消息 ID 和 QA 元数据。
- QA 表达层不修改 TourState、QAContext、Evidence、Coverage 或路线。
- 校验失败、kill switch 或提交时配置变化时保留确定性 QA 答案。
- Shadow 行为保持兼容。
- 新增 QA 专用组件：
  - opening；
  - direct answer；
  - follow-up；
  - uncertainty；
  - closing。
- 普通问答与追问使用不同表达合同。
- `listen_only` 不提问、不布置任务、不邀请回答。
- 可选语义模型故障不再阻断确定性角色切换。
-游览开始前也可以确定性切换角色，不再掉入通用 `llm_think`。

测试证据：

```text
QA Active/Shadow/策略：21/21 OK
QA 组件与生成：47/47 OK
完整离线回归：1220/1220 OK
语义模型降级定向测试：40/40 OK
```

注意：`1220/1220` 后又增加了语义故障降级修复；该修复通过了 40 项定向测试，但提交前没有再次运行完整回归。明天首先需要补跑完整回归。

## 3. 今日解决的问题

### 3.1 README 的 Streamlit 启动入口过时

错误命令：

```powershell
python -m streamlit run webapp.py
```

`webapp.py` 实际是 LangGraph Agent Server 的 Starlette lifespan 应用，根路径返回 Uvicorn `404 Not Found` 属于正常行为。

正确前端：

```powershell
python -m streamlit run demo/streamlit_app.py
```

README 尚未修正，列入待办。

### 3.2 Hugging Face 启动联网超时

本地已经缓存：

```text
BAAI/bge-small-zh-v1.5
BAAI/bge-reranker-base
```

解决配置：

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_DISABLE_TELEMETRY = "1"
```

配置后 RAG 预热约 3.29 秒，不再访问 Hugging Face。

### 3.3 独立角色切换显示“服务暂时繁忙”

原因：角色切换已被确定性识别，但后续可选语义模型或通用路由故障会中断整轮请求；此外，游览开始前的独立角色切换没有进入确定性确认节点。

解决：

- 可选语义模型故障降级为空候选；
- 只记录脱敏异常类别；
-游览开始前角色切换也进入 `role_mode_confirmation`；
-不修改路线和进度。

现场复测结果：

```text
已确认使用“儿童友好”讲解角色。后续讲解将使用这一角色，当前路线和进度保持不变。
```

该问题已解决。

## 4. 当前待解决问题

### 4.1 QA Active 在 Streamlit 中仍处于 Shadow

LangSmith 现场 Trace：

```text
style_id: child
scene_kind: tour_qa
generation_status: rejected
reason_code: role_qa_rollout_off
model_called: false
mode: shadow
validation_status: rejected
active_takeover: false
legacy_message_preserved: true
```

结论：不是模型质量或校验失败，角色 QA 模型根本没有被调用。Streamlit 进程没有读到 `role_qa` rollout 配置。

确定性 QA 答案仍正常显示，安全 fallback 有效。

### 4.2 Phase 3 尚未完成 LangSmith 人工验收

未完成项目：

- 儿童 QA Active；
- 专业角色追问连续性；
- 古风角色事实边界；
- listen-only 无互动；
-未知现场人员的 uncertainty；
- kill switch；
-模型失败 fallback。

### 4.3 README 尚未跟进今天的实际启动方式

需要把 `webapp.py` 改为 `demo/streamlit_app.py`，并补充：

- Hugging Face 离线模式；
-产品级 `PRODUCT_ROLE_*` 配置；
- `role_qa` 能力；
-当前回归基线。

### 4.4 产品状态矩阵尚未登记 Phase 3 最新状态

阶段 2 已登记完成。阶段 3 应在 LangSmith 人工验收通过后更新为 verified；在此之前只能记录为 implemented/active pending manual verification。

## 5. 明日建议解决方案与执行顺序

### 第一步：补跑提交后的完整回归

```powershell
$env:LANGCHAIN_TRACING_V2 = "false"
$env:LANGSMITH_TRACING = "false"
$env:CJC_READ_ONLY_ROLLOUT_MODE = "off"

python -m unittest discover -v
```

目标：不少于 `1220` 项且全部 `OK`。

### 第二步：显式配置 QA Active

在启动 Streamlit 的同一个 PowerShell 中执行：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_qa"

$env:PRODUCT_ROLE_ACTIVE_ENABLED = "true"
$env:PRODUCT_ROLE_ACTIVE_STYLES = "child,professional,ancient_scholar,listen_only"
$env:PRODUCT_ROLE_ACTIVE_SCENES = "tour_qa,qa_follow_up_detail"
$env:PRODUCT_ROLE_ROLLOUT_PERCENTAGE = "100"
$env:PRODUCT_ROLE_KILL_SWITCH = "false"
$env:PRODUCT_ROLE_VALIDATION_LEVEL = "strict"
$env:PRODUCT_ROLE_FALLBACK_POLICY = "legacy"
```

启动前检查：

```powershell
Get-Item `
  Env:CJC_READ_ONLY_ROLLOUT_MODE,`
  Env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES,`
  Env:PRODUCT_ROLE_ACTIVE_ENABLED,`
  Env:PRODUCT_ROLE_ACTIVE_STYLES,`
  Env:PRODUCT_ROLE_ACTIVE_SCENES,`
  Env:PRODUCT_ROLE_ROLLOUT_PERCENTAGE,`
  Env:PRODUCT_ROLE_KILL_SWITCH
```

必须确认：

```text
CJC_READ_ONLY_ROLLOUT_MODE          read_only_active
CJC_READ_ONLY_ROLLOUT_CAPABILITIES  role_qa
PRODUCT_ROLE_ACTIVE_ENABLED         true
PRODUCT_ROLE_ROLLOUT_PERCENTAGE     100
PRODUCT_ROLE_KILL_SWITCH            false
```

### 第三步：启动正确前端与 LangSmith

不要把任何 API Key 写进文档或提交。

```powershell
$env:LANGCHAIN_TRACING_V2 = "true"
$env:LANGSMITH_TRACING = "true"
$env:LANGSMITH_PROJECT = "cjctourist-phase3-qa-active"

$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_DISABLE_TELEMETRY = "1"

python -m streamlit run demo/streamlit_app.py `
  --server.address 127.0.0.1 `
  --server.port 8502
```

### 第四步：最小 QA Active 复测

新会话第一轮：

```text
请切换为适合小朋友的讲解方式
```

预期：

```text
已确认使用“儿童友好”讲解角色。
```

第二轮：

```text
灰塑是什么？
```

LangSmith 通过标准：

```text
capability: role_qa
style_id: child
scene_kind: tour_qa
mode: active
generation_status: generated
model_called: true
validation_status: accepted
active_takeover: true
fallback_used: false
commit_decision: qa_role_candidate_published
state_writes: []
```

如果仍然是 `role_qa_rollout_off`：

1. 检查启动窗口的 `Get-Item Env:*` 输出；
2. 检查 Streamlit 是否由同一个窗口启动；
3. 检查全局或项目 `.streamlit/secrets.toml` 是否覆盖旧配置；
4. 修改 `demo/streamlit_app.py::_configure_environment`，使本地显式环境变量优先，或补齐所有 `PRODUCT_ROLE_*` secrets 键；
5. 为 `_configure_environment` 增加不含密钥的启动审计测试。

### 第五步：完成 QA LangSmith 案例矩阵

依次验证：

1. child 普通 QA；
2. professional 普通 QA + “详细讲讲”；
3. ancient_scholar 事实保持；
4. listen_only 无问号、任务和邀请；
5. 木雕主题追问不漂移；
6.未知现场修复人员不得编造；
7. kill switch 保留原答案；
8.模型故障保留原答案。

### 第六步：文档与阶段收尾

- 修正 README 的前端启动命令；
-更新 `product_feature_status.md`；
-运行 `git diff --check`；
-再次完整回归；
-提交 Phase 3 验收文档；
-推送 `297fff7`、`8643603` 及后续文档提交；
-进入阶段 4：导航、结束语和重规划说明 Active。

## 6. 关键提交索引

```text
8643603 feat: add controlled QA role activation
297fff7 feat: add adaptive multi-turn narration
f914498 feat: add product capability rollout policy
806d5cb docs: add full product development roadmap
92cb458 冻结比赛基线，转为完整产品版本开发
5ffa38a 代码测试修复5/1170
```

## 7. 安全与注意事项

- 不提交 DeepSeek 或 LangSmith API Key。
- LangSmith Trace 不应包含密钥、原始 chunk、文件路径或内部状态。
- Phase 3 人工验收未通过前，不得把 QA Active 标记为 verified。
- 任何 QA 角色失败必须保留确定性答案。
- QA 表达层不得修改 TourState、路线、QAContext、Evidence 或 Coverage。
-比赛资料保持冻结，后续开发只更新产品文档。
