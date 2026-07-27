# D阶段后人工验证与优化统一标准

## 1. 目的

本标准用于统一两位内容负责人对Agent进行人工验证、问题记录和优化建议提交。

当前阶段先发现问题、复现问题和提出方案，不立即多人修改公共代码。

统一流程：

```text
冻结测试基线
→ 按相同标准人工测试
→ 分别提交问题
→ 集成负责人去重归类
→ 确认优先级
→ 分批修改
→ 定向测试
→ 完整回归
→ LangSmith复验
```

---

## 2. 文件命名

每位负责人分别建立：

```text
data/chen_clan_academy/evaluation/manual_reviews/
  d_stage_review_<reviewer>_v1.yaml
```

例如：

```text
d_stage_review_muziw_v1.yaml
d_stage_review_xiaolin_v1.yaml
```

相关截图、LangSmith记录和输出证据放在：

```text
data/chen_clan_academy/evaluation/manual_reviews/evidence/<reviewer>/
```

命名：

```text
<finding_id>_trace.png
<finding_id>_response.txt
<finding_id>_state.json
```

不要使用：

```text
最新版
最终版
修改版
新问题
问题汇总2
```

公共去重问题池由集成负责人维护：

```text
data/chen_clan_academy/evaluation/d_stage_optimization_backlog_v1.yaml
```

两位测试负责人不能同时修改公共问题池。

---

## 3. 测试基线

每次人工测试必须记录：

```text
tested_commit
tested_branch
test_date
python_version
test_environment
reviewer
```

同一轮比较必须基于相同Git提交。

拉取到新提交后，不能把旧结果直接当作新版本结果；需要重新复现并更新记录。

---

## 4. 每条问题的统一结构

```yaml
findings:
  - finding_id: rvw_muziw_001
    reviewer: muziw
    tested_commit: ""
    test_date: "2026-07-27"

    module: tour_qa
    issue_type: routing
    severity: P1
    reproducibility: always

    preconditions:
      thread_id: test_thread_001
      current_node_id: stop_front_courtyard_center
      active_route: true
      visitor_profile:
        audience_mode: family
        knowledge_level: general
        explanation_style: standard

    conversation:
      - role: user
        content: "我到前院中部了"
      - role: user
        content: "这里怎么拍？"

    expected:
      route: photo_guidance
      state_change: none
      card_type: photo_spot_card
      behavior: "优先推荐当前节点候选，并给出现场条件提示。"

    actual:
      route: ""
      response_summary: ""
      state_change: ""
      selected_card_ids: []
      source_ids: []

    problem_description: ""
    evidence_refs: []

    suspected_layer: routing
    proposed_solution: ""
    acceptance_test: ""

    status: new
```

如果没有观察到问题，也可以记录为通过案例，但应设置：

```yaml
status: passed
```

---

## 5. 受控分类

### `module`

只允许使用：

```text
route_planning
tour_event
stop_guidance
tour_qa
glossary
research_cards
comparison_cards
photo_spots
visitor_profile
guidance_policy
rag
memory
fallback
presentation
```

### `issue_type`

```text
state_error
routing
factual_error
source_error
card_selection
spatial_mapping
profile_mismatch
content_quality
language_style
safety_boundary
fallback_error
thread_isolation
performance
interface
documentation
```

### `suspected_layer`

```text
data
base_rag
card_content
card_eligibility
spatial_mapping
intent_routing
tour_state
visitor_profile
guidance_policy
stop_program
response_rendering
memory
test
documentation
unknown
```

如果不能确定原因，使用 `unknown`，不要猜测代码模块。

### `reproducibility`

```text
always
frequent
occasional
once
not_reproduced
```

---

## 6. 问题优先级

### P0：立即停止合并

包括：

- 错误修改TourState。
- 到达、完成、跳过语义错误。
- 不同线程状态串线。
- 输出危险现场建议。
- 编造严重历史事实或来源。
- 未审核内部资料直接泄漏。
- 数据损坏导致系统整体不可用。

### P1：下一批必须修复

包括：

- 意图路由错误。
- 关键功能无法使用。
- 错误选择卡片。
- 研究观点被说成事实。
- 草稿英文泄漏。
- 当前点位严重错配。
- 拍照建议自动改变路线。
- 无法安全回退。

### P2：质量优化

包括：

- 回答过长、重复或结构不清。
- 个性化效果不明显。
- 讲解重点与兴趣不匹配。
- 回答没有充分利用合格卡片。
- 位置提示不够自然。
- 来源展示不够清晰。
- 内容对儿童、家庭或专业游客适配不足。

### P3：体验改进

包括：

- 语言风格润色。
- 按钮文案。
- 排版、符号和提示语。
- 表达节奏。
- 非关键性能问题。
- 演示美观性。

排序原则：

```text
P0安全与状态
> P1事实、来源与路由
> P2内容与个性化
> P3风格与界面
```

不能因为某项优化更容易完成就跳过高优先级问题。

---

## 7. 统一评分

每个测试回答按以下维度评分：

```text
0 = 不合格
1 = 部分合格
2 = 合格
```

评分维度：

| 维度 | 重点 |
|---|---|
| `routing_score` | 是否进入正确节点 |
| `state_score` | 是否只发生允许的状态变化 |
| `factual_score` | 事实是否正确、有边界 |
| `source_score` | 来源是否可追溯 |
| `card_score` | 卡片类型和卡片选择是否正确 |
| `spatial_score` | 当前点、对象和位置是否匹配 |
| `profile_score` | 是否正确使用游客画像 |
| `clarity_score` | 是否自然、简洁、可理解 |
| `safety_score` | 是否包含必要安全与现场提示 |

任何以下情况出现时，整体不能判定合格：

- `state_score=0`
- `factual_score=0`
- `safety_score=0`
- 输出未审核内部资料

---

## 8. 必测功能

两位负责人都必须测试相同的基础场景。

### 路线与状态

- 规划30分钟路线。
- 到达第一站。
- 讲解结束。
- 确认完成。
- 下一站。
- 跳过。
- 修改时间。
- 结束路线。

### 站点讲解

- 到达后生成讲解。
- 再讲详细一点。
- 不同兴趣的讲解重点。
- general与professional表达差异。
- listen_only不布置互动任务。

### 游览问答

- “这里有什么？”
- “这里的灰塑有什么特点？”
- “这个对象在哪里？”
- 问答后继续当前讲解。

### 术语卡

- 中文定义。
- 拼音。
- 已审核英文。
- 草稿英文阻止。

### 研究卡

- 明确学术问题。
- 研究方法。
- 研究限制。
- 普通问题不自动注入论文。

### 比较卡

- 普通比较。
- 学术比较。
- 比较对象不明确。
- 比较后路线状态不变。

### 打卡推荐

- 全馆推荐。
- 当前点“这里怎么拍”。
- 家庭合影。
- 个人拍摄。
- 无候选回退。
- 禁用姿势和平台观察隔离。

### 连续对话

至少完成一次：

```text
规划路线
→ 到达
→ 讲解
→ 术语追问
→ 研究追问
→ 比较追问
→ 拍照建议
→ 结束讲解
→ 确认完成
```

---

## 9. 内容审核标准

发现内容问题时，必须区分：

```text
基础事实错误
论文观点问题
比较范围问题
术语翻译问题
空间映射问题
编辑推荐问题
语言表达问题
```

不得用语言润色掩盖事实或来源错误。

新增事实必须给出：

- 来源编号。
- 来源位置。
- 适用范围。
- 是否人工审核。
- 应进入基础RAG还是知识卡。

判断原则：

- 通用、稳定事实 → 基础RAG更新候选。
- 论文观点 → 研究卡。
- 成型比较框架 → 比较卡。
- 术语定义和翻译 → 术语卡。
- 拍照、姿势和观察建议 → 打卡卡。
- 仅作线索的信息 → 内部观察记录。

---

## 10. 优化方案要求

每个建议必须说明：

```text
修改什么
为什么修改
属于数据还是代码
影响哪些功能
是否改变冻结契约
需要新增哪些测试
如何判断修改成功
```

不接受以下模糊建议：

```text
让回答更智能
优化提示词
提高准确率
增强个性化
改得更自然
```

应改写为可验收方案，例如：

```text
在当前点位问答中，将审核对象限制为node_guide_cards中的对象；
新增测试，确保前院中部不会返回未关联对象。
```

---

## 11. 文件所有权

测试负责人可以修改：

- 自己的人工测试记录。
- 自己负责的卡片和来源。
- 自己模块的测试数据。
- 自己模块的README。

未经确认不能修改：

- `agent_graph.py`
- TourState
- `tour_interaction.py`
- VisitorProfile
- GuidancePolicy
- StopProgram
- 公共卡片注册表
- 公共问题池
- 公共进度与协作文档

发现公共代码问题时，只提交问题和方案，由集成负责人统一修改。

---

## 12. 优化批次

### 第一批：正确性

处理：

- P0、P1
- 状态
- 路由
- 事实
- 来源
- 安全
- 线程隔离

### 第二批：数据与关联

处理：

- 空间映射
- 卡片ID
- 对象关联
- 来源补充
- 术语翻译
- 打卡候选

### 第三批：内容与个性化

处理：

- VisitorProfile适配
- 讲解重点
- 内容深度
- 儿童、家庭、研学和专业表达
- 故事、比较和观察任务

### 第四批：体验与产品化

处理：

- 语言风格
- 按钮与展示协议
- 性能
- UI
- 演示流程

每批完成后必须完整回归，不能累计到最后一次性测试。

---

## 13. 冲突报告

如果优化建议需要改变冻结契约，先报告：

```text
## 发现优化建议—冻结契约冲突

问题ID：
现有契约：
实际问题：
影响模块：
最小修改方案：
推荐方案：
需要新增的回归测试：
```

不得自行创建第二套状态、路由或事实来源绕过冲突。

---

## 14. 提交流程

每位负责人完成一轮后提交：

```text
个人审核YAML
证据文件
新增验收案例
数据修正候选
RAG更新候选
建议优化方案
```

集成负责人执行：

```text
汇总
→ 去重
→ 复现
→ 确认优先级
→ 分配负责人
→ 分批实现
→ 回归
```

问题只有满足以下条件才能关闭：

- 原问题能够稳定复现。
- 修复后定向测试通过。
- 新增回归测试。
- 完整测试通过。
- 人工复验通过。
- 没有破坏其他阶段功能。