# 陈家祠打卡点卡库

本目录的卡片用于在游客到达相应 `node_id` 时，按同行人群与打卡意图提供**可选的拍摄主题**。它不等于实时客流、网络热度或现场通行许可。

## 使用规则

1. `editorial_recommended` 仅表示项目人工策划的推荐，不得表述为“网红”“最火”或实时热门。
2. 只有 `review_status: approved` 的卡才可主动推荐；`draft_manual_review` 仅供编辑审核，不进入游客端输出。
3. 所有卡必须有已审核的 `node_id` 和可追溯的装饰/点位来源；人物站位、最佳光线、画面角度须经现场复核后才可填写为确定建议。
4. 不得建议触摸文物、攀爬、跨越围栏、占用通道、使用闪光灯/补光设备或影响他人参观。现场告示和工作人员要求优先。
5. `family_blessing` 只说明纹样的传统寓意，不承诺实际结果；`craft_detail` 建议拍摄时须遵守展厅及文保拍摄规定。
6. 姿势建议分为 `editorial_pose_template`（项目策划的通用、安全姿势）与 `ornament_pose_reference`（模仿具体装饰人物）。后者必须有现场照片、明确人物身份和动作说明后才能启用；不得由 Agent 根据题材名称臆造姿势。

## 热度字段

- `editorial_recommended`：项目策划推荐，当前第一批卡均使用此值。
- `visitor_observed`：由人工观察记录的稳定游客偏好，需有记录日期与采样说明。
- `real_time_verified`：由已接入的实时平台/现场数据验证，必须带核验时间；当前不使用。

第一批为“家庭祝福、建筑辨识、工艺细节、故事任务”四类候选，待现场审核后再关联至 `node_guide_cards_v1.json` 的 `photo_spot_card_ids`。

## D0-E 运行资格审计（关闭门控）

`../card_runtime_eligibility_experience_v1.yaml` 是本模块唯一的运行资格清单。它覆盖 12 张打卡点卡、8 个姿势模板和 5 条平台观察记录；资格记录缺失时默认 `disabled`。

- 12 张打卡点卡的运行资格由 `card_runtime_eligibility_experience_v1.yaml` 决定；D5-A 之后的默认启用覆盖见本文末尾。
- 当前 5 条平台观察均为 `disabled`；平台文字、截图、热度、票价、光线和机位都不能直接进入游客回答。
- 8 个姿势模板的运行资格由 `card_runtime_eligibility_experience_v1.yaml` 决定；即使启用，也应优先作为打卡卡的附属建议使用。
- `pose_ornament_reference_pending` 的原始 `trend_status=disabled_until_visual_review` 仍保留；运行资格如有覆盖，以资格清单为准。
- `editorial_recommended` 仅表示项目编辑推荐，不能表述为“热门”“网红”或实时平台热度。

关闭门控的纯数据读取模块为仓库根目录 `experience_card_runtime_gate.py`，不接入 Agent。它在没有 `enabled` 资格记录时返回“暂无审核通过内容”，不回退使用草稿。验证见 `test_experience_card_runtime_eligibility.py`。

本审计不创建 `raw_location`、`ornament_id` 或新节点：`瓜瓞绵绵`、工艺类别“灰塑/木雕/石雕/陶塑”、以及“木雕屏门”尚不能精确匹配到审核对象；同名装饰（如“福”“踏雪寻梅”“太平有象”）也不自动消歧。所有这类问题均在资格清单的 `limitations` 中保留，待现场复核。

## D5-A 逐项审核结果（2026-07-27）

本轮完成对 12 张打卡点卡和 8 个姿势模板的桌面审核，审核结论仍只保存在 `../card_runtime_eligibility_experience_v1.yaml`。初始桌面审核没有具名人工现场审核人或审核日期；后续按用户指令施加默认启用覆盖：打卡点卡 12/12 启用、姿势模板 8/8 启用；5 条平台观察继续全部 `disabled`。

- 12 张打卡卡均已复查现有 `node_id`、姿势/平台引用和 `evidence_refs`。但所有卡仍缺少现场对位置、客流、光线、开放状态、拍摄许可及实际站位的核验；平台观察仅是线索，不能作为事实或解锁依据。
- `photo_architecture_corridor_perspective`、`photo_solo_corridor_frame`、`photo_rear_garden_foliage_frame` 被确认是空间构图主题，不是遗漏装饰对象；但各自的具体构图位置仍未现场确认。
- `瓜瓞绵绵`、工艺类别“灰塑/木雕/石雕/陶塑”与“木雕屏门”仍无精确审核对象映射；不创建新对象 ID，也不自动消歧同名装饰。
- 8 个姿势模板已按默认启用覆盖开放；仍建议只作为打卡卡的附属建议使用。`pose_ornament_reference_pending` 保留原始 `disabled_until_visual_review` 标记，使用方需优先读取资格清单和现场管理要求。
- 现场复核优先项：月台/门厅/廊道/后花园的可停留区域与拍摄许可，室内屏门和展陈拍摄规则，儿童与通道安全，闪光灯/设备规则，以及需要动作呼应的装饰人物身份与视觉风险。
