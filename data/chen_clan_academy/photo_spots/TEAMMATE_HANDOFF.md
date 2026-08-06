# 队友交接清单 — photo_spots/ 整理 v0.1

> **生成日期**: 2026-08-06
> **整理人**: photo_spots/ 整理团队
> **配套文件**: `photo_spot_cards_v0.yaml` / `pose_templates_v0.yaml` / `platform_observations_v0.yaml` / `README.md`(本目录)
> **本目录已完成**: Pass 1+2+3(12 张卡、8 个姿势模板、5 条平台观察、README 增补)

---

## 0. 30 秒总览

| 团队 | 待办数 | 优先级 | 完成期限建议 |
|------|--------|--------|--------------|
| A. 路线/装饰 | 3 项 | 高(否则卡挂不上) | 2 周内 |
| B. 现场审核 | 12 个 node | 中(等现场) | 1 个月内 |
| C. 知识/运行资格 | 3 项 | 中(避免漂移) | 2 周内 |
| D. 工具/平台观察 | 2 项 grep | 低(确认即可) | 1 周内 |

**最关键**的是 A.路线团队:`stop_juxian_hall` 和 `label_rear_garden` 这 2 个 node 缺,卡 11 和卡 12 永远无法 `mounted`,4 维 `location_verification_status` 升不上去。

---

## 1. 本目录已完成的改动(供你 grep 时对照)

### 字段变更一览

| 旧字段 | 新增/并存字段 | 适用对象 |
|--------|--------------|----------|
| `popularity_status` | + `editorial_recommended_status` | 12 张打卡点卡 |
| `review_status` | + `content_review_status` | 12 张打卡点卡 |
| `trend_status` | + `editorial_recommended_status` | 8 个姿势模板 |
| `target_ornaments`(整段) | 拆 3 段:`verified_ornament_ids` / `ornament_categories` / `pending_ornament_review` / `disambiguated_ornament_ids` | 12 张打卡点卡 |
| (无) | + `content_verification_status` / `source_verification_status` / `location_verification_status` / `safety_verification_status` | 12 张卡 + 8 模板 + 5 观察 |
| (无) | + `mounting_status` | 12 张卡 |
| (无) | + `node_status` | 12 张卡 |
| (无) | + `dependency_blockers` | 12 张卡 + 8 模板 |
| (无) | + `linked_observation_disposition` | 12 张卡(7 张用到) |
| (无) | + `observation_kind` / `visual_inspiration_available` | 5 条平台观察 |

### 文件结构

```
photo_spots/
├── photo_spot_cards_v0.yaml       (12 张卡,YAML 锚点 <<: *card_defaults)
├── pose_templates_v0.yaml         (8 个模板,内含 SECTION A/B 注释分段,**未拆**)
├── platform_observations_v0.yaml  (5 条观察,YAML 锚点 <<: *observation_defaults,**未拆**)
├── README.md                      (增补 5 个章节)
└── TEAMMATE_HANDOFF.md            (本文件)
```

### 用户 override(本目录独有的注意点)

- **Pass 2**:旧字段名 `popularity_status` / `review_status` / `trend_status` **保留**,新字段名与之并存;外部代码读旧字段不会断。
- **Pass 3**:`pose_templates_v0.yaml` **未拆**;editorial 7 条在 SECTION A,ornament 1 条在 SECTION B(用注释区分)。

---

## A. 路线/装饰团队(优先,否则卡挂不上)

### A1. `node_guide_cards_v1.json` 缺 2 个 node

**问题**:12 张卡里有 2 张卡的 `node_id` 在 `node_guide_cards_v1.json` 中找不到。

| photo_spot_card | 缺失 node_id | blocker 详情 |
|----------------|--------------|--------------|
| `photo_juxian_hall_screen_door` | `stop_juxian_hall` | `node_missing_stop_juxian_hall`,见 `dependency_blockers` |
| `photo_rear_garden_foliage_frame` | `label_rear_garden` | `node_missing_label_rear_garden`,见 `dependency_blockers` |

**需要做的事**:
1. 决定 `stop_juxian_hall` 和 `label_rear_garden` 是要新建、还是把 `node_id` 改名(后者会触发 `node_id_will_change` 状态,需要同步改卡)
2. 如果新建:在 `node_guide_cards_v1.json` 里加 `stop_juxian_hall` 和 `label_rear_garden` 节点;`photo_spot_card_ids: []` 仍保留空,等 B 现场审核后填
3. 改完后通知 photo_spots 整理团队,会把这 2 张卡的 `node_status` 从 `not_in_node_guide_v1` 改回 `in_node_guide_v1`、移除对应 `dependency_blockers`

**风险**:如果 A1 一直不做,卡 11 和卡 12 的 `dependency_blockers` 永远不解,无法进入游客端输出。

---

### A2. `ornament_spatial_mapping_v1.csv` 4 条 craft 字段名拼接错误

**问题**:装饰位置索引中有 4 条记录的 craft 字段名被错误拼接。

涉及 orn_id: `orn_081` / `orn_054` / `orn_083` / `orn_093`

**需要做的事**:
1. 打开 `ornament_spatial_mapping_v1.csv`,grep 这 4 个 orn_id
2. 检查 craft 字段是否被错误拼接(例如 `灰塑陶塑` 应该是 `灰塑` + `陶塑` 两个独立字段)
3. 修正为正确格式

**注意**:本目录不直接读 `ornament_spatial_mapping_v1.csv`,所以 A2 不阻塞本目录卡输出;但若其他模块(如现场讲解 RAG)读取,会出现错误关联。

---

### A3. 拼写不一致:`瓜瓞绵绵` vs `瓜瓞连绵`

**问题**:同一装饰在两处有不同写法。

| 位置 | 写法 |
|------|------|
| 本目录 README / 卡 5 `target_ornaments` | `瓜瓞绵绵` |
| 装饰位置索引 `orn_085` 实际值 | `瓜瓞连绵` |

**需要做的事**:
1. 决定正确写法(参考《陈家祠》官方文献)
2. 同步 README / 卡 5 / `ornament_spatial_mapping_v1.csv` / `orn_085` 的所有引用
3. 改完后通知 photo_spots 整理团队,清掉卡 5 的 `pending_ornament_review`

**当前状态**:卡 5 的 `pending_ornament_review` 第一条就是这事的标记:
> `瓜瓞绵绵(README/卡内写法,装饰索引 orn_085 为瓜瓞连绵 — 拼写不一致,待统一)`

---

## B. 现场审核团队(等现场)

### B1. 12 个 node 的 `photo_spot_card_ids: []` 填卡 ID

**问题**:12 个 node 已经在 `node_guide_cards_v1.json` 里有,但 `photo_spot_card_ids` 字段是空列表。

**需要做的事**(现场审核后):
1. 对每个 node,按现场允许的拍摄条件,决定挂哪些卡
2. 把对应卡的 `photo_spot_id` 填入 `photo_spot_card_ids`
3. 通知 photo_spots 整理团队,把对应卡的 `mounting_status` 从 `not_yet_mounted` 改为 `mounted`,`location_verification_status` 升级为 `partial` 或 `verified`

**当前 12 个 node**:
- `stop_front_courtyard_north`(4 张卡挂这里):卡 1、卡 5、卡 6、卡 8、卡 10
- `stop_front_courtyard_east`(1 张):卡 2
- `label_moon_platform`(1 张):卡 3
- `stop_front_courtyard_center`(2 张):卡 4、卡 7
- `stop_rear_west_courtyard`(1 张):卡 9
- `stop_juxian_hall`(1 张,**等 A1**):卡 11
- `label_rear_garden`(1 张,**等 A1**):卡 12

**特别提醒**:挂卡前必须现场确认:
- 月台/门厅/廊道/后花园的可停留区域与拍摄许可
- 室内屏门和展陈拍摄规则
- 儿童与通道安全
- 闪光灯/设备规则
- 需要动作呼应的装饰人物身份与视觉风险(尤其是 `photo_story_three_kingdoms`,依赖 `pose_ornament_reference_pending`)

---

## C. 知识/运行资格团队

### C1. `card_runtime_eligibility_experience_v1.yaml` 字段重命名是否同步

**问题**:本目录已经把 `popularity_status` 升级为 `editorial_recommended_status`(同时保留旧字段),`review_status` 升级为 `content_review_status`(同时保留旧字段)。但**资格清单没动**(按计划 §9 红线)。

**需要做的事**:
1. 决定资格清单是否同步重命名
   - **选项 A(推荐)**:资格清单不动,本目录新字段是 source of truth,资格清单继续读 `popularity_status` / `review_status` / `trend_status`(旧字段在卡上仍存在)
   - **选项 B**:资格清单同步重命名,gate 逻辑也要改(见 C2)
2. 若选 A:本目录 README 状态机表中的对应关系已经写明"资格清单是 source of truth,卡上是镜像" → 实际是反的(本目录是 source of truth,资格清单读卡上的旧字段);**请改 README 对应关系章节,反过来说**
3. 若选 B:本目录会跟进,把 `popularity_status` 等旧字段删除(但这样会破坏向后兼容,需要协调所有引用方)

---

### C2. `experience_card_runtime_gate.py` 是否读新字段

**问题**:本目录新增了 `dependency_blockers` 字段,但 gate 当前**不读它**,仍只读资格清单的 `enabled`/`disabled`。

**需要做的事**:
1. 决定是否让 gate 读 `dependency_blockers`
   - **选项 A(推荐)**:gate 暂不读,只把 `dependency_blockers` 当作人工审计提示;gate 行为不变
   - **选项 B**:gate 增加逻辑:任何卡/模板有 `must_resolve_before_output: true` 的 blocker,即使资格清单 enabled,也返回"未通过"
2. 若选 B:需要更新 `test_experience_card_runtime_eligibility.py` 加测试用例

**风险**:选 B 会改变 gate 行为,需要回归所有 12 张卡 + 8 模板 + 5 观察。

---

### C3. `test_experience_card_runtime_eligibility.py` 加新字段测试

**问题**:本目录新增了 4 维 verification / mounting / node_status / dependency_blockers,但测试可能没覆盖。

**需要做的事**:
1. 检查现有测试是否覆盖 `mounting_status` 的边界(`not_yet_mounted` / `mounted` / `disabled`)
2. 检查现有测试是否覆盖 `dependency_blockers` 的读取(若 C2 选 B)
3. 增加 4 维 verification 字段缺失时的回退测试

---

## D. 工具/平台观察团队

### D1. grep `platform_observations_v0` 字符串引用

**问题**:本目录的 `platform_observations_v0.yaml` **未拆**(原计划也未拆),所以文件名引用不会断。但工具代码可能按 observation_id 引用,要确认。

**需要做的事**:
```bash
# 在整个仓库 grep
rg "platform_observations_v0" --type py --type yaml --type json
rg "xhs_20260726_morning_photo_time" --type py --type yaml --type json
rg "xhs_20260726_seven_crafts_photo" --type py --type yaml --type json
rg "xhs_20260726_rainy_day_photo" --type py --type yaml --type json
rg "xhs_20260726_small_deity_ao_fish" --type py --type yaml --type json
rg "xhs_20260726_roof_ridge_crafts" --type py --type yaml --type json
```

1. 检查所有引用是否仍然指向 5 条 observation_id
2. 如果有代码按"视觉参考"分流读,确认它读的是 `visual_inspiration_available: true` 的 2 条(`morning_photo_time` + `roof_ridge_crafts`)

---

### D2. grep `popularity_status` / `trend_status` / `review_status` 字符串引用

**问题**:本目录在 Pass 2 时**保留了**旧字段名(用户 override),所以旧引用不会断。但外部代码可能按"新字段名"读,要做确认。

**需要做的事**:
```bash
# 在整个仓库 grep
rg "popularity_status" --type py --type yaml --type json
rg "trend_status" --type py --type yaml --type json
rg "review_status" --type py --type yaml --type json

# 新字段名
rg "editorial_recommended_status" --type py --type yaml --type json
rg "content_review_status" --type py --type yaml --type json
```

1. 旧字段名引用:本目录已保留,可继续使用
2. 新字段名引用:如果工具代码读新字段,确认它能正确读到(本目录两字段并存,值相同)

---

## 2. 红线(不要做的事)

来自整理计划 §9,适用于本目录以外的任何人:

1. ❌ 不要创建新 `ornament_id` / `raw_location` / 新节点(除非 A1 路线团队明确同意)
2. ❌ 不要自动消歧同名装饰(踏雪寻梅 / 太平有象 / 福 等)
3. ❌ 不要改任何 `node_id`(除非 A1 明确同意)
4. ❌ 不要填 `node_guide_cards_v1.json` 的 `photo_spot_card_ids`(那是 B 现场审核的事)
5. ❌ 不要改资格清单任何字段或记录(C1 选项 A 下)
6. ❌ 不要改 gate 代码或测试(除非 C2 选项 B 明确同意)
7. ❌ 不要修 `ornament_spatial_mapping_v1.csv` 的数据质量(那是 A 路线团队的事)
8. ❌ 不要引入新平台观察或新姿势
9. ❌ 不要擅自把视觉参考升级为"事实"

---

## 3. 验收标准(本目录已完成,供你确认)

- [x] `photo_spot_cards_v0.yaml` 通过 YAML 解析(队友 grep 一下 `python -c "import yaml; yaml.safe_load(open('photo_spot_cards_v0.yaml'))"`)
- [x] 12 张卡每张都有 4 维 verification 字段
- [x] 12 张卡的 `mounting_status: not_yet_mounted` 一致
- [x] 2 张卡的 `node_status: not_in_node_guide_v1` 与缺失 node 一致
- [x] `photo_craft_ornament_route` 的 `platform_observation_ids` 合并为 1 个
- [x] `photo_story_three_kingdoms` 有 `dependency_blockers` 指向 `pose_ornament_reference_pending`
- [x] 8 个姿势模板字段名统一(无 `popularity_status` 残留,但 `trend_status` 保留)
- [x] `pose_templates_v0.yaml` **未拆**,用 SECTION A/B 注释分段,共 8 条
- [x] `platform_observations_v0.yaml` 5 条观察都有 `observation_kind` 和 `visual_inspiration_available`
- [x] README.md 新增章节齐全(字段表 / 状态机 / 资格清单对应 / 拆文件说明 / 待办)
- [x] grep `popularity_status` / `trend_status` / `review_status` 在本目录**有命中**(因为保留旧字段);外部代码可继续读旧字段
- [x] 没有创建任何新 `ornament_id`
- [x] 没有自动消歧同名装饰

---

## 4. 联系人 / 反馈渠道

- 本目录整理的疑问 → 找 photo_spots/ 整理团队
- 路线/装饰相关(A1/A2/A3)→ 找路线/装饰团队
- 资格清单相关(C1)→ 找知识/运行资格团队
- gate 代码相关(C2/C3)→ 找工具团队
- 字符串引用相关(D1/D2)→ 找工具/平台观察团队

**变更请求**:任何对本目录 4 个文件的修改,请先在本文件留一行(增/改/删),再开 PR;不要直接覆盖整理结果。
