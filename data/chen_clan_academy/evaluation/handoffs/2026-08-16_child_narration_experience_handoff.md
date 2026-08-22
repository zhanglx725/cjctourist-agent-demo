# 儿童友好点位讲解体验优化交接

## 1. 交接范围

本轮处理 LangSmith Studio 中儿童点位讲解的以下问题：

- Active 正文仍像成人资料卡，只增加少量儿童连接词；
- 游客正文暴露“存在审核关联”“可结合现场标识”等后台措辞；
- 对象详情强制输出整段传说，正文过长；
- 角色校验失败后回退到带 `【工艺背景】`、`【观察对象】` 的资料卡；
- 到站时自动拼接完整拍照建议；
- 原儿童组件机械、缺少温柔陪伴和趣味感。

本轮不修改路线、TourState、Coverage、审核来源或对象注册表。

## 2. 复现方式

在 LangGraph Studio 的新 Thread 中依次输入：

```text
中文，定制模式，30分钟，喜欢灰塑和木雕，标准讲解，选择儿童友好风格
我到了
```

验收 Active 正文时使用：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration"
$env:PRODUCT_ROLE_ACTIVE_ENABLED = "true"
$env:PRODUCT_ROLE_ACTIVE_STYLES = "child"
$env:PRODUCT_ROLE_ACTIVE_SCENES = "stop_guidance"
$env:PRODUCT_ROLE_ROLLOUT_PERCENTAGE = "100"
$env:PRODUCT_ROLE_KILL_SWITCH = "false"
$env:PRODUCT_ROLE_VALIDATION_LEVEL = "strict"
$env:PRODUCT_ROLE_FALLBACK_POLICY = "legacy"
$env:PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED = "true"
```

注意：`run_langgraph_studio.cmd` 当前默认强制 Shadow。Shadow 只审计角色候选，`visitor_localization` 仍发布确定性正文。

## 3. 根因

### 3.1 角色层无法删除已经进入计划的事实

`narration_rendering.py` 原先把对象详情的全部段落写入 `fact_units`，随后 `narration_content_plan.py` 将其变成不可编辑事实。为了通过 `approved_statement_not_preserved` 校验，角色层只能原样插入事实。因此审核提示和长故事进入计划后，角色层无法安全删除。

### 3.2 回退正文没有角色体验保证

此前的自然话语优化只影响角色候选。模型不可用、JSON 无效、预算超限或风格校验失败时，`deterministic_narration_fallback` 会重新发布完整 E5 资料卡，造成体验断层。

### 3.3 主动拍照卡与儿童首轮讲解竞争

`maybe_trigger_photo_guidance` 会在审核拍照点首次到达时自动追加卡片，没有控制儿童首轮的信息密度。

## 4. 已实施修改

### 4.1 儿童事实单元选择

文件：`narration_rendering.py`

新增 `_child_role_fact_statements`：

- 过滤“审核关联”“可结合现场标识”“构件位置辨认”“未核验”；
- 工艺最多保留两条审核事实；
- 每件装饰保留对象身份和一条简短事实；
- 优先选择造型、颜色、构图、姿态等现场可观察事实；
- 没有视觉句时选择最短审核详情，避免强制输出长篇传说。

模型仍不能自由补写事实。进入角色层的文字来自审核渲染结果，事实 ID 和原文保持校验继续生效。

### 4.2 儿童确定性回退同步游客化

文件：`narration_rendering.py`

儿童模式的确定性正文现在：

- 不显示三个资料卡标题；
- 不发布审核关联句和冗长灾害故事；
- 使用与角色稿一致的精简事实边界；
- 使用温柔开场、工艺引入、对象“新朋友”和儿童收束。

因此角色失败回退后也不会重新变成内部说明书。其他角色仍使用原有确定性渲染。

### 4.3 温柔寻宝式表达组件

文件：`data/chen_clan_academy/narration_styles/point_narration_components_v1.yaml`

儿童 full/compact 组件改为“小线索、建筑寻宝图、装饰新朋友、新发现、我们慢慢来”等表达。组件避免连续提问、考试口吻和强迫互动，继续遵守 `optional_observation` 合同。

### 4.4 儿童首轮不主动追加拍照卡

文件：`proactive_photo_guidance.py`

当 `visitor_profile.explanation_style == "child"` 时，不在到站讲解里自动触发拍照建议。游客显式询问拍照时，仍由现有拍照问答链处理。

## 5. 测试变更

`test_e5_narration_rendering.py` 新增断言：

- 每件装饰最多两条角色事实；
- 角色事实和回退正文均不含审核措辞；
- 不输出资料卡标题和长灾害故事；
- 保留对象身份与视觉事实；
- 包含“像找宝藏一样”“小线索”“新朋友”“我们慢慢来”。

`test_proactive_photo_guidance.py` 新增儿童模式不自动触发拍照卡的断言。

## 6. 当前验证状态

已完成：

```text
Python 语法编译：通过
git diff --check：通过（仅有仓库既有 YAML 行尾提示）
```

尚未完成：

```text
定向 unittest
完整回归
LangSmith 新 Thread 真实模型验收
```

阻塞原因：`.venv` 的启动器仍指向已删除的解释器：

```text
C:\Users\muziw\AppData\Local\Programs\Python\Python312\python.exe
```

同机 MySQL Workbench Python 只能完成 `py_compile`，缺少完整 `unittest` 标准库。

## 7. 接手后的必做步骤

安装 Python 3.11/3.12，重建或修复虚拟环境，然后运行：

```powershell
.\.venv\Scripts\python.exe -m unittest `
  test_e5_narration_rendering.py `
  test_narration_content_plan.py `
  test_role_narration_generation.py `
  test_role_discourse.py `
  test_role_narration_graph.py `
  test_proactive_photo_guidance.py
```

再运行完整回归：

```powershell
$env:LANGCHAIN_TRACING_V2 = "false"
$env:LANGSMITH_TRACING = "false"
.\.venv\Scripts\python.exe -m unittest discover
```

LangSmith 验收要求：

1. 使用 Active 环境变量重启 `langgraph dev --port 2037`；
2. 打开 `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2037`；
3. 必须新建 Thread，旧 Thread 已保存旧 `fact_units`；
4. 查看最终 `visitor_localization`，不要把 `stop_guidance` 中间节点当最终正文；
5. 分别验收 `narration_commit` 与 `deterministic_narration_fallback`。

## 8. 人工验收标准

- 开场温柔、有陪伴感，不命令儿童；
- 至少有一处自然的探索或寻宝表达；
- 对象名称、工艺名称和选中的审核事实准确；
- 不出现“审核、证据、关联、节点、构件位置辨认”等后台话语；
- 不把长篇故事一次倾倒给儿童；
- 不连续提问，不使用“考考你”“必须回答”；
- 不诱导触摸、攀爬、摆拍或阻塞通道；
- 没有明确拍照请求时不追加完整拍照卡；
- 角色成功与确定性回退之间没有明显体验断层。

目标语气示例：

```text
现在来到前院中部。别着急，我们一起慢慢看看，像找宝藏一样发现藏在建筑里的小线索。
第一条小线索，是一种叫作“灰塑”的传统工艺……
接着和独角狮这位新朋友打个招呼……
这一站的小秘密先看到这里。您想再仔细看看，或者准备好后完成本点都可以。
```

## 9. 风险与边界

1. 当前采用“审核事实子集 + 原文保持”，尚未实现任意事实的模型自由儿童化改写；部分工艺事实仍可能偏成人化。
2. 若未来允许意译，必须增加逐事实语义一致性、数字与专名锁定、否定关系检查和故障回退，不能直接放松事实保存校验。
3. 儿童事实子集使用确定性启发式选择视觉短句，新知识格式接入时需扩充样本矩阵。
4. 工作区同时包含阶段 3C 自然话语等既有未提交修改，提交前必须拆分 diff。

## 10. 涉及文件

本轮直接修改：

```text
narration_rendering.py
proactive_photo_guidance.py
data/chen_clan_academy/narration_styles/point_narration_components_v1.yaml
test_e5_narration_rendering.py
test_proactive_photo_guidance.py
```

相关既有未提交开发：

```text
role_discourse.py
role_narration_generation.py
narration_validation.py
agent_graph.py
narration_budget.py
narration_style_policy.py
```

不要假定 `git status` 中所有修改都属于本轮儿童体验修复。
