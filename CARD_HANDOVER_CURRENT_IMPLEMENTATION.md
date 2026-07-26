# 现有知识卡标准与成果交接说明（当前真实实现）

> 盘点日期：2026-07-26。本文只描述仓库现状；不因交接要求批量改名、补字段或重排既有卡片。

## 一、成果基本信息

```text
负责人：muziw（按当前仓库拥有者推定；建议团队交接时确认）
卡片模块名称：陈家祠术语卡、学术研究摘要卡、比较卡、打卡点卡及其辅助记录
卡片主要类型：YAML 术语/比较/打卡卡；JSON 论文摘要卡；YAML 姿势模板与平台观察记录
卡片所在目录：data/chen_clan_academy/{glossary,research_cards,comparisons,photo_spots}/
主要文件格式：YAML、JSON、Markdown
当前 Git 分支：main
最近提交：2d519ca feat: enrich photo spot references
最后更新时间：2026-07-26
```

```text
data/chen_clan_academy/
  glossary/
    glossary_zh_en_v0.yaml
    glossary_retrieval_rules_v0.yaml
    research_references.md
    README.md
  research_cards/
    research_001_*.json ... research_020_*.json
    research_sources_v1.json
    research_card_review_index_v1.json
    README.md
  comparisons/
    comparison_cards_v0.yaml
    comparison_card_catalog_v0.yaml
    comparison_dimensions_v0.yaml
    comparison_evidence_notes_v0.md
    README.md
  photo_spots/
    photo_spot_cards_v0.yaml
    pose_templates_v0.yaml
    platform_observations_v0.yaml
    README.md
  routes/
    term_stop_associations_v1.json
  sources/
    source_registry.md
```

## 二、卡片类型体系

| 类型 | 用途 | 数量 | 当前完成度 | 人工审核现状 |
|---|---|---:|---|---|
| 双语术语卡 | 统一术语、领域、中文/拼音/英文表达 | 82 | 首批完成 | 来源日期已填写；英文 `reviewed` 48、`draft` 34 |
| 学术研究摘要卡 | 保留论文问题、作者观点、方法、限制与安全讲解提要 | 20 | 首批完成 | 专题通过 12；背景参考 8 |
| 比较卡 | 让 Agent 有范围和证据边界地回答“与谁不同” | 8 | 首批完成 | 均为 `approved_research_only`，不面向普通游客直接输出 |
| 打卡点卡 | 到达点位后按人群/主题提供可选拍摄思路 | 12 | 草稿完成 | 全部 `draft_manual_review`，不可主动推荐 |
| 姿势模板 | 复用安全、非接触式姿势建议 | 8 | 草稿完成 | 无独立人工审核状态；其中 1 条明确禁用待视觉审核 |
| 平台观察记录 | 保存用户提供的小红书线索、截图观察与未证实项 | 5 | 持续整理 | 不是事实卡；全部须按各自 `verification_status` 限制使用 |
| 术语—点位关联 | 将术语作为当前点位检索提示 | 181 条 / 12 节点 | 已生成 | `derived_from_approved_ornament_mapping`，仍需现场可见性复核 |

术语卡用于“这是什么/英文怎么说/属于什么工艺领域”；不适合独自回答某件构件在现场的精确位置或完整历史。研究摘要卡用于论文、研学和深度问题；不等同馆方事实库。比较卡与研究卡均可能回答工艺/建筑差异，前者直接给出成型的比较结构，后者保留单篇研究论证。打卡卡、姿势模板和平台观察彼此配合，但只有打卡卡是未来游客端候选；其余两类是内部材料。

目前计划：术语检索、术语—点位关联和比较检索已存在 Python 调用模块；研究摘要卡、打卡点卡、姿势模板、平台观察尚未接入 `agent_graph.py`。

## 三、当前字段标准

以下为文件中实际出现的字段；“必填”指当前所有该类记录均有，而不是未来的理想 schema。

### 3.1 双语术语卡 `terms[]`

| 字段 | 含义 / 类型 | 当前必填 | Agent 需要 |
|---|---|---|---|
| `term_id` | 稳定 ID，string | 是 | 是 |
| `domain` | 受控领域，string | 是 | 是 |
| `zh` / `pinyin` / `en` | 中文、拼音、英文，string | 是 | 是 |
| `short_definition_zh` | 简短中文定义，string | 是 | 是 |
| `translation_status` | `reviewed` 或 `draft`，string | 是 | 是 |
| `source_ids` | 来源登记编号，list[string] | 是 | 是 |
| `verified_at` | 核验日期，YAML date | 是 | 是 |
| `aliases_en` | 英文别名，list[string] | 否（5 条） | 可选 |
| `discouraged_translations` | 不建议单独使用的译法，list[string] | 否（1 条） | 可选 |
| `research_reference_ids` | `research_references.md` 内待核验参考编号，list[string] | 否（10 条） | 否，供人工 |

`source_ids` 是陈家祠资料的事实来源；`research_reference_ids` 只登记学术定义/译法线索，不能替代前者。代码尝试读取 `aliases_zh`，但现有 YAML 没有该字段，故当前是允许但未实际使用的兼容字段。无空字符串约定；可选字段直接缺失。`translation_status=draft` 不应自动面向游客输出英文。

### 3.2 学术研究摘要卡（一文件一张 JSON）

实际字段：`card_id`、`title_zh`、`status`、`verified_at`、`source`、`research_question`、`author_position`、`method_and_evidence`、`guide_safe_takeaway`、`supported_questions`、`applicable_node_ids`、`applicable_scope`、`topic_tags`、`agreement_and_limits`、`integration_rule`。

`source` 是对象，实际含 `citation`、`local_file`、`page_locator`、`access_scope`；`agreement_and_limits` 含 `agreement` 与 `limits`。20 条均具备上述字段。`status` 实际值为 `reviewed`（12）或 `background`（8），并由 `research_card_review_index_v1.json` 再分层；这里的 `reviewed` 不保证书目信息和每个构件定名已经馆方复核，必须同时读取 `integration_rule` 与 `agreement_and_limits.limits`。

### 3.3 比较卡 `cards[]`

实际字段：`comparison_id`、`theme_zh`、`comparison_level`、`comparison_objects`、`dimensions`、`scope_zh`、`similarities_zh`、`differences_zh`、`on_site_observation_prompt`、`visitor_conclusion_zh`、`source_refs`、`status`、`claim_strength`、`limitations_zh`。全部 8 条都有这些字段。

当前 `status=approved_research_only`、`claim_strength=research_only` 均为全量现状；没有 `node_id`。`visitor_conclusion_zh` 是面向游客的概括，但并非可无条件输出：检索器只在研究型比较问题中返回，并要求保留“研究认为”等归因边界。

### 3.4 打卡点卡 `cards[]`

实际字段：`photo_spot_id`、`title_zh`、`node_id`、`target_ornaments`、`target_groups`、`themes`、`pose_template_ids`、`cultural_prompt_zh`、`recommended_capture_zh`、`popularity_status`、`review_status`、`evidence_refs`、`boundaries_zh`；`platform_observation_ids` 为可选字段（6/12 条）。

全部 12 条目前 `review_status=draft_manual_review`、`popularity_status=editorial_recommended`。后者是项目编辑推荐，绝不是实时热度。`target_ornaments` 可以为空（3 条）。`recommended_capture_zh` 同时容纳构图建议和待现场确认条件，属混合编辑字段；不能将其当作已核验现场事实。

### 3.5 姿势模板与平台观察（辅助记录）

姿势模板字段：`pose_template_id`、`title_zh`、`pose_kind`、`suitable_groups`、`instruction_zh`、`trend_status`、`safety_boundary_zh`，其中 `source_observation_ids` 为可选。`pose_kind` 分为 `editorial_pose_template` 与 `ornament_pose_reference`；后者目前有 1 条 `disabled_until_visual_review`。

平台观察字段并不统一：固定核心为 `observation_id`、`platform`、`observation_type`、`verification_status`、`possible_subjects`、`linked_photo_spot_ids`；根据收到的文字/截图选择性记录 `short_link`、`supplied_title_zh`、`user_supplied_caption_fragment_zh`、`user_supplied_shot_list_zh`、`verified_facts_zh`、`visual_observations_from_user_images_zh`、`unverified_items_zh`、`user_supplied_claims_needing_evidence_zh`、`adoption_rule_zh`。允许额外字段；这是内部溯源笔记，不是稳定 schema。

人工填写/人工整理的是现有全部卡片文本、来源标记、状态和关联；模型可参与初稿归纳，但仓库没有字段标记“由模型生成”。`verified_at`、`review_status`、`status`、`claim_strength` 由人工设置。缺少逐字段编辑人、审核人或变更日志。

## 四、完整样例

以下保留真实字段；第二个研究样例说明“文件状态与可用性并非同义”。

### 可正式作为检索提示使用：术语卡

```yaml
term_id: term_balustrade
domain: architectural_components
zh: 栏杆
pinyin: Lan Gan
en: balustrade
short_definition_zh: 台阶、月台等边缘用于围护和装饰的构件。
translation_status: reviewed
source_ids: [S10]
verified_at: 2026-07-23
```

`term_id` 用于引用；`domain` 用于过滤；三种语言和定义供导游组织；`translation_status` 决定英文能否默认输出；`source_ids` 与日期是可追溯性边界。

### 尚不可作为普通游客事实直接输出：研究摘要卡

```json
{
  "card_id": "research_019_stone_platform_and_railings",
  "title_zh": "石雕细读：聚贤堂月台栏板的狮子、果实与通透构图",
  "status": "reviewed",
  "verified_at": "2026-07-26",
  "source": {
    "citation": "戴瑶, 李景明. (2017). 广州陈家祠的建筑装饰艺术. 江西建材, No.219(18), 31-32.",
    "local_file": "data/chen_clan_academy/raw/research_papers/陈家祠文献/广州陈家祠的建筑装饰艺术.pdf",
    "page_locator": "石雕段（PDF p. 2）；书目信息待人工复核。",
    "access_scope": "本地研究资料；卡片仅保存概括与引文定位，不复制论文全文。"
  },
  "research_question": "聚贤堂月台的石雕栏板、望柱与果实、狮子题材，如何同时承担边界、礼仪强调与岭南地域意象的作用？",
  "author_position": "作者将聚贤堂前月台栏板视为陈家祠石雕工艺的重点部位……",
  "method_and_evidence": ["以聚贤堂月台栏板、望柱头和台阶周边石构件为主要观察对象；", "辨析狮子、菠萝、杨桃、佛手等题材与石雕部位之间的关系；", "把石雕的镂通效果、石材质感与月台的仪式性空间结合讨论。"],
  "guide_safe_takeaway": "读月台石雕可从“框架—通花—柱头”三层入手……",
  "supported_questions": ["聚贤堂月台栏杆为什么既厚重又通透？", "石狮与岭南果实为什么会一起出现在望柱头？", "怎样在不触碰文物的前提下细读石雕栏板？"],
  "applicable_node_ids": [],
  "applicable_scope": "whole_site",
  "topic_tags": ["石雕", "聚贤堂", "月台", "栏板", "望柱"],
  "agreement_and_limits": {"agreement": "在既有石雕故事卡之外，补足可现场观察的石雕构件、空间位置和构图逻辑。", "limits": "本地文献的刊名、年份和页码尚未可靠提取；果实和瑞兽的具体名称、数量与寓意均须与馆方图录或现场标识复核后，才能作为事实性回答。"},
  "integration_rule": "书目信息、题材定名与点位复核完成前，仅限研究草稿；审核后用于深度讲解，不得用于触摸、攀爬或聚集停留的现场引导。"
}
```

此卡的 `status=reviewed` 表示其进入“专题通过”层，而 `page_locator` 与 `integration_rule` 仍明确书目信息、题材与点位未完成事实核验。因此它是高质量研究整理样例，也是“不能直接下放”的问题样例。

完整比较卡、打卡卡、姿势模板和平台观察分别见原文件：`comparisons/comparison_cards_v0.yaml`、`photo_spots/photo_spot_cards_v0.yaml`、`photo_spots/pose_templates_v0.yaml`、`photo_spots/platform_observations_v0.yaml`。它们的字段已在第三节完整列出；不在本文复制以免产生第二份可漂移副本。

## 五、ID 与命名规则

```text
术语 ID：term_<英文概念>，如 term_balustrade
研究卡 ID：research_<三位序号>_<英文主题>
比较卡 ID：cmp_<英文主题>
打卡卡 ID：photo_<英文主题>
姿势 ID：pose_<英文主题>
平台观察 ID：xhs_<日期>_<英文主题>
```

当前每个本类文件内 ID 唯一；跨类型前缀不同，未发现重号。研究卡文件名以 `card_id` 为主体；其他卡收纳在集合文件，文件名不等于单卡 ID。标题不要求唯一。中文名称保存在 `zh`、`title_zh`、`theme_zh` 等字段；术语英文别名仅有 `aliases_en`，没有通用中文别名字段。关联以各类 ID 列表引用（如 `pose_template_ids`、`platform_observation_ids`、`source_refs`）。未维护跨所有卡片的总 ID 注册表；未发现“ID 已变但引用未同步”的自动检查结果，但尚无全仓库引用扫描测试。

## 六、审核状态与完成标准

| 状态/标记 | 使用位置 | 含义与最终用户可见性 |
|---|---|---|
| `translation_status=reviewed` | 48 术语 | 可作默认英文表达；人工设置 |
| `translation_status=draft` | 34 术语 | 仅人工审阅，不应自动英文输出 |
| `status=reviewed` | 12 研究卡 | 研究专题通过，仍须按限制和归因使用 |
| `status=background` | 8 研究卡 | 只作背景/比较线索，不单独支撑现场事实 |
| `approved_research_only` / `research_only` | 8 比较卡 | 研究型提问可用，普通比较问答不返回 |
| `draft_manual_review` | 12 打卡卡 | 编辑草稿，不可向游客主动推荐 |
| `disabled_until_visual_review` | 1 姿势模板 | 不可使用 |

没有记录“谁可设置”或审核人字段；按现状均需项目人工维护者设置。内容实质修改后，应重新核对来源、点位与相应状态，但系统尚未强制执行。

```text
主卡总数（术语+研究+比较+打卡）：122
研究专题通过：12；研究背景：8
术语英文已审核：48；术语英文草稿：34
比较卡研究专用：8
打卡卡草稿：12；打卡卡已批准：0
存在来源/事实边界问题：至少 8 背景研究卡，且研究卡中仍有待核验书目信息或点位
存在字段规范问题：平台观察记录 5 条（非固定 schema）
暂不可游客端主动使用：12 打卡卡、1 禁用姿势模板、8 比较卡（普通模式）
```

## 七、来源与证据标准

- 稳定事实来源用 `Sxx` 等编号，登记在 `data/chen_clan_academy/sources/source_registry.md`；术语卡用 `source_ids`。
- 比较卡用 `CMPREF_*`，证据摘记在 `comparison_evidence_notes_v0.md`，单卡可有 1–6 个 `source_refs`。
- 研究卡采用每卡 `source`，另有 `research_sources_v1.json` 和 `research_card_review_index_v1.json`；页码/段落放在 `page_locator`。
- 平台观察不进入上述稳定来源注册表；短链、用户转录文字和截图观察只保存为线索，须标注未证实项和采用规则。

直接事实应来自来源登记或馆方/政府资料；`author_position` 是论文作者观点；`guide_safe_takeaway`、`visitor_conclusion_zh`、`cultural_prompt_zh` 是团队归纳/面向导游改写；平台图文、民间寓意和文学描写均不得自动转成事实。研究卡保留页定位但通常不保留长原文摘录，避免版权复制；可存在二手书目信息或“待人工复核”页码。来源可靠性已按卡类做人工筛选，但无统一的来源评级字段。

## 八、空间节点与对象关联标准

- `node_id` 使用 `data/chen_clan_academy/spatial/marker_inventory_v0.csv` 和路线路径中的既有节点，如 `label_moon_platform`、`stop_juxian_hall`、`label_rear_garden`。
- 术语—点位关联由 `build_term_stop_associations.py` 根据已审核装饰—点位映射生成到 `routes/term_stop_associations_v1.json`；181 条关联覆盖 12 节点，状态统一为 `derived_from_approved_ornament_mapping`。
- 打卡卡必须有一个现有 `node_id`；可列 `target_ornaments`（名称而非 `ornament_id`）。3 张卡没有具体装饰对象，表示空间/构图主题。
- 研究卡用 `applicable_node_ids`（10/20 有值）和 `applicable_scope`；其余用 `whole_site` 或空数组，不能据此假定具体位置。
- 比较卡没有空间字段，且 README 明确不得改变路线、边或文物—点位关联。

原始对象位置使用 `raw_location` 时，应来自 `raw/chenjiaci_ornaments_source.json` 或 `knowledge/09_ornament_locations.md` 的资料原文；经人工映射后进入 `spatial/ornament_spatial_mapping_v1.csv`。当前打卡卡不保存 `raw_location` 或 `ornament_id`，对象同名/别名冲突尚未机器校验。茶艺室、中西展厅、展柜、室内桌椅等小红书机位尚未映射，已留在平台观察中。

## 九、内容组织与写作标准

- 术语定义是一两句的通俗解释，保留中文、拼音与英文；无 Markdown 正文。
- 研究卡以“问题—作者观点—方法/证据—安全讲解提要—限制—接入规则”组织；可含列表，主要供 Agent 内部选择与深度讲解。
- 比较卡将相同点、不同点、范围、现场观察和游客结论分字段；`visitor_conclusion_zh` 可面向游客，但必须受 `claim_strength` 和 `limitations_zh` 限制。
- 打卡卡把文化提示、构图建议和安全边界分字段；没有完整导游词，不承诺光线、客流、开放性或“热门”。

没有统一摘要长度/正文长度标准，也没有明确模型补充字段。事实、观点和建议大体分字段，但研究卡的 `guide_safe_takeaway` 与打卡卡的 `recommended_capture_zh` 都混有事实边界与建议，调用方须同时读取限制字段。

## 十、检索与调用设想

| 用户问题 | 卡片 | 可能命中 | 选择依据 | 需当前点/画像/RAG |
|---|---|---|---|---|
| “通花栏板是什么？英文怎么说？” | 术语卡 | `term_openwork`、`term_balustrade` | 关键词、`domain` | 当前点可排序；必须结合 RAG |
| “我在月台，石雕为什么通透？” | 术语+研究 | 月台关联术语、`research_019...` | `node_id`、研究标签 | 需要当前点；必须结合 RAG |
| “陈家祠的灰塑和鄄城砖塑有什么不同？” | 比较卡 | `cmp_grey_plaster_vs_juancheng_brick_plastic` | 比较提示词和对象标签 | 不需点位；研究模式+来源边界 |
| “带父母孩子到前庭拍什么？” | 打卡卡 | `photo_family_five_blessings` | 当前 `node_id`、家庭画像、主题 | 需点位/画像；仅批准后可用 |
| “我一个人怎样在连廊拍？” | 打卡+姿势 | `photo_solo_corridor_frame`、`pose_walkaway_corridor` | 点位、人群、主题 | 需点位/画像；遵守现场规则 |

术语调用已实现关键词匹配、按当前节点关联和命中优先排序（`glossary_retrieval.py`）；比较卡已实现比较词触发、标签匹配、普通/研究模式门控（`comparison_retrieval.py`）。两者均非向量检索。研究摘要卡、打卡卡尚无检索模块，预计可按 `topic_tags`/问题、`node_id`、`target_groups`、`themes` 过滤后再做语义检索。未命中时应退回基础 RAG 或明确无可用卡；卡片不能单独替代基础 RAG。当前比较卡不能影响路线，打卡卡未来可能受游览状态影响但尚未接入。

## 十一、基础 RAG 更新候选

| 候选稳定内容 | 来源 | 对应卡 | 原因 | 审核 |
|---|---|---|---|---|
| 术语中文定义、拼音、已审核英文 | `Sxx` 来源登记 | 48 个 `translation_status=reviewed` 术语 | 可提升术语识别与双语一致性 | 部分已审核 |
| 月台栏杆/望柱/通花作为观察对象 | 馆方/稳定 RAG 与 `S11` | 月台术语关联、打卡卡 | 属现场基础描述；仍需避免扩展寓意 | 点位映射已审，表述需复核 |
| “1888 年开始筹建” | 既有 `knowledge/02_history_architecture.md` 所述馆方来源 | 非卡片主张 | 已是通用历史事实，优先维护基础 RAG | 已存在 |

研究作者观点、比较结论、英文草稿译法、平台热度/最佳光线/小红书机位、具体展柜和未核验寓意应留在卡片层，不应批量灌入基础 RAG。1893/1894 年建成表述在现有基础知识中已有来源差异，不能以平台文字覆盖。

## 十二、校验与测试情况

```text
已运行命令：
py -3.10 -m unittest -v test_glossary.py test_glossary_retrieval.py test_term_stop_associations.py test_comparison_retrieval.py

结果：19 tests，全部通过（2026-07-26）
```

- `test_glossary.py`：术语 ID 唯一、必备来源/日期、领域检索规则、核心范围等。
- `test_term_stop_associations.py`：关联只使用已知术语和讲解节点，且讲解包有双语术语上下文。
- `test_glossary_retrieval.py`：缺关联文件的安全降级、关键词优先。
- `test_comparison_retrieval.py`：比较意图识别、研究专用卡不泄漏到普通模式、归因边界。
- 本轮额外手工 YAML 解析与引用检查：12 打卡卡、8 姿势模板、5 平台观察；姿势/平台引用均无缺失。

尚未覆盖：研究卡字段完整性、研究卡与来源/节点的一致性、比较卡 YAML schema、打卡卡 `node_id` 有效性、重复/相似卡、平台观察字段约束、跨全仓 ID 和引用、冲突结论、空白正文及照片现场可用性。

## 十三、已知问题与待决策事项

| 问题 | 影响 | 当前处理 | 集成人需决定 |
|---|---|---|---|
| 研究卡 `reviewed` 与 `integration_rule` 的事实可用性不完全一致 | 至少研究卡 019，可能更多 | 保留限制文字，不直接下放 | 是否新增统一 `fact_verification_status` |
| 术语卡无独立 `review_status` | 82 术语 | 用翻译状态和来源日期替代 | 是否区分概念核验与英文核验 |
| 比较卡全是 `research_only` | 8 卡不能服务普通比较问答 | 检索器已拦截 | 是否补充普通游客可用的 `confirmed/cautious` 卡 |
| 打卡卡全是草稿 | 12 卡不可主动使用 | README 门控 | 现场审核由谁、按何标准完成 |
| 平台观察 schema 可变 | 5 条内部记录 | 仅作线索，避免事实化 | 是否单独建观察数据 schema |
| 打卡卡只存装饰名称，不存 `ornament_id/raw_location` | 名称歧义、难追溯 | 依赖 `node_id` 和 `S11` | 是否加对象 ID 映射层 |
| 无总 ID 注册表及跨卡引用测试 | 后续改名风险 | 当前靠手工/YAML 校验 | 是否加 schema/注册表/CI |
| 若干来源页码/书目信息待复核 | 研究深度问答风险 | 在 `limits`/`page_locator` 标注 | 是否补充原始 PDF 核验 |

建议当前保留所有现有 ID 和文件格式；先通过转换/适配器统一调用，再经三方确认后批量调整 schema。

## 十四、可修改范围与兼容要求

1. 可新增可选字段（如审核人、最后编辑时间、对象 ID），但需同步写入读取器或适配器。
2. `term_id` 已被 `term_stop_associations_v1.json`、`node_guide_cards_v1.json`、`glossary_retrieval.py` 使用；应视为冻结。
3. `comparison_id` 已被 `comparison_retrieval.py` 使用；应视为冻结。
4. 打卡/姿势/平台 ID 已互相引用；改名须全量迁移引用。
5. 研究卡文件名、`card_id`、研究来源索引和审核索引应一起维护。
6. 字段重命名不应直接进行；优先用转换器兼容旧字段。
7. 必须保留：来源编号、限制/边界字段、审核/翻译状态、现有节点 ID、平台观察中的未证实项。
8. 术语和比较检索代码已依赖当前文件路径与关键字段；其他成员可能依赖这些结构，修改前需协调。

## 十五、最终交接文件清单

- [x] 卡片原始文件：四个卡片目录中的 YAML/JSON
- [x] 当前标准：本文件及各目录 README
- [x] 完整目录结构：第一节
- [x] 每类字段与真实样例：第三、四节及原始文件
- [x] 卡片数量与状态统计：第二、六节
- [x] 来源登记：`sources/source_registry.md`、研究/比较来源文件
- [x] 节点与对象关联：`spatial/*`、`routes/term_stop_associations_v1.json`
- [x] 校验脚本和结果：第十二节
- [x] RAG 更新候选：第十一节
- [x] 已知问题清单：第十三节
- [x] Git 分支和提交信息：第一节

后续建议严格按既定流程：先对比体系、标记映射和冲突、三方确认统一标准；之后再修改卡片，并最后接入 Agent。
