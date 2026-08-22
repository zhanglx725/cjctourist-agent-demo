# 2026-08-18 全风格与全流程批量测试交接

## 本轮基线

- 自动化全量回归已通过：`Ran 1276 tests in 209.837s — OK`。
- Streamlit 入口：`demo\\streamlit_app.py`。
- 当前真实模型批量快照：
  `data/chen_clan_academy/evaluation/snapshots/role_narration_20260818T104609_deepseek-all-styles-v3.json`
  （54 条记录、`active_takeover_count=54`、`fallback_count=0`、
  `model_unavailable_count=0`、`assertion_failure_count=0`）。

## 本次必须验证的产品合同

1. **所有节点到达即讲解。** 到达提示可以存在，但同一轮必须自动给出该节点的完整正文；不得要求用户再点“开始本点讲解”。
2. **正文属于当前节点。** 每站必须覆盖当前节点的审核对象、可见特征、位置/辨认线索，以及可用的工艺或故事；不能只剩工艺定义或一两句概述。
3. **风格只作用于导览正文。** 到达和当前点讲解应符合已选风格；普通知识问答必须直接、中性地回答，不带“眼光看过来”“咱先看”等导览开场与收束。
4. **游客文本零内部术语。** 不得出现“审核关联”“审核位置”“后台”“未核验”“项目编辑整理”等内容，也不得出现 `【工艺背景】`、`【观察对象】` 这类字段筐。
5. **Active 与兼容回退体验一致。** 即使使用自然组件回退，仍要有该风格的审核开场、自然连接和收束，不能变回无风格的原始事实堆叠。

## 先执行的自动化命令（cmd）

```cmd
python -m unittest -v
```

如只复核角色、风格和普通问答边界：

```cmd
python -m unittest -v test_e5_narration_style_integration.py test_qa_role_components.py test_qa_role_shadow.py test_qa_role_active.py test_role_discourse.py test_role_narration_generation.py test_role_narration_style_matrix.py
```

如需重新比较真实 DeepSeek 结果，当前 cmd 窗口先设置：

```cmd
set ROLE_NARRATION_PROVIDER=deepseek
set ROLE_NARRATION_MODEL=deepseek-v4-flash
python tools\capture_role_narration_snapshots.py --styles neutral child family student_research professional listen_only mixed_group dominant_ceo cute_junior ancient_scholar warm_sister bestie_chat buddy_guide exploration_game photo_guide hostel_scholar xiguan_young_master cantonese_storyteller --provider-label deepseek-all-styles-YYYYMMDD
```

快照验收：`model_unavailable_count=0`、`assertion_failure_count=0`、`fallback_count=0`；允许局部 `natural_component_fallback_count`，但必须检查最终文本仍有正确风格。

## Streamlit 启动与准备

```cmd
streamlit run demo\streamlit_app.py
```

- 打开 `http://localhost:8501`。
- 每一个风格组均使用**重置会话后的新会话**；旧聊天记录不会随代码改动重新生成。
- 固定首轮配置：60 分钟、标准节奏、兴趣选“灰塑、故事”。再为少量代表风格补测 30 分钟和深度节奏。

## 18 种风格批量手测清单

| 组别 | 风格 ID | 页面名称/重点观察 |
|---|---|---|
| 基线 | `neutral` | 中性清晰、无角色腔。 |
| 受众 | `child` | 儿童友好、短句、可理解，不幼稚堆叠。 |
| 受众 | `family` | 适合同行家庭，照顾共同观察。 |
| 受众 | `student_research` | 研究线索清楚，但不变成生硬报告。 |
| 受众 | `professional` | 专业准确、术语克制、结构明确。 |
| 受众 | `listen_only` | 无强制互动或提问。 |
| 受众 | `mixed_group` | 兼顾不同人群，措辞包容。 |
| 角色 | `dominant_ceo` | 果断、有取舍，不能冒犯。 |
| 角色 | `cute_junior` | 轻快亲切，不能幼态化或撒娇过度。 |
| 角色 | `ancient_scholar` | 文雅但可听懂，开场应有“诸位且看”一类标记。 |
| 角色 | `warm_sister` | 温和自然、有陪伴感。 |
| 角色 | `bestie_chat` | 朋友聊天感，不能沦为口头禅。 |
| 重点 | `buddy_guide` | 先看实物→造型/位置→工艺或故事；哥们聊天式短句，不出现课本定义腔。 |
| 重点 | `exploration_game` | 有探索引导，但不把导览变成任务指令。 |
| 重点 | `photo_guide` | 观察/拍摄提示单列服务区，不干扰讲解。 |
| 角色 | `hostel_scholar` | 有书生气但不空泛；兼容路径仍应有“行至此处”类开场。 |
| 地域 | `xiguan_young_master` | 西关年轻少爷口吻；开场可检验“得闲”类标记。 |
| 地域 | `cantonese_storyteller` | 粤味讲古节奏；不用生硬方言堆砌。 |

## 每个风格的标准流程

1. 重置会话，选择该风格、60 分钟、标准节奏、灰塑+故事，生成路线。
2. 首节点：输入“我到了”。确认到达消息之后**立即**出现完整“当前点讲解”。
3. 阅读正文：确认首个对象不是被工艺背景挤掉；对象名称、位置、特征与故事/知识均围绕当前站。
4. 输入“完成本点”，在下一节点输入“我到了”；至少连续完成 **3 个节点**。每次都必须到达即讲解，且正文切换到新节点。
5. 在第二或第三节点输入“再讲详细一点”；确认详情只扩写当前节点，不污染下一站的首讲。
6. 输入一次普通问题，例如“陈家祠几点关门”；确认回答直接给出开放信息，不含已选导游人设的开场、观察指令或收束。
7. 对 `buddy_guide`、`hostel_scholar`、`ancient_scholar`、`xiguan_young_master` 额外截图留证：其风格开场必须出现且全文持续符合人设。

## 人工验收记录模板

每个风格至少记录一行：

| 风格 | 首节点 | 第 2 节点 | 第 3 节点 | 详情扩写 | 普通 QA 中性 | 内部术语/字段筐 | 结果 | 截图/备注 |
|---|---|---|---|---|---|---|---|---|
| `style_id` | 通过/失败 | 通过/失败 | 通过/失败 | 通过/失败 | 通过/失败 | 无/有 | 通过/阻塞 | 文件名或现象 |

遇到失败时必须同时保存：当前风格、`current_stop_id`、用户输入、到达消息、完整“当前点讲解”文本、是否点过“再讲详细一点”、截图。不要只描述“看起来不对”。

## 优先级与处理顺序

1. **P0：到达即讲解、当前节点对象覆盖、普通 QA 去风格化。** 任一项失败即停止风格润色，先修状态/渲染/QA 路由。
2. **P1：18 风格连续三站体验。** 先修完全无风格的兼容回退，再调具体风格表达。
3. **P2：节奏差异。** 在 `buddy_guide`、`student_research`、`professional` 上比较标准与深度、30 与 60 分钟的长度和信息密度。
4. **P3：外部模型比较。** 仅在 DeepSeek 快照稳定后，再单独配置并验证其他 API；不得用模型不可用的快照比较文风。

## 当前已知注意事项

- Windows 当前终端是 **cmd**，环境变量必须用 `set NAME=value`，不能用 PowerShell 的 `$env:NAME = ...`。
- 若快照出现 `model_unavailable_count>0`，先看 `generation_reason_code` 判断模型名、provider 或 API 权限；该快照不能用于文风比较。
- `narration_rendering.py` 已负责将内部位置事实转换为游客语言；不要重新把原始审核字段或 `【】` 标题输出到页面。
- QA 不属于到站导览：角色语气不得写入普通问答。正常 QA 与导览正文必须分别验收。
