陈家祠打卡点卡库
本目录的卡片用于在游客到达相应 node_id 时，按同行人群与打卡意图提供可选的拍摄主题。它不等于实时客流、网络热度或现场通行许可。

本次整理(2026-08-06,Pass 1+2+3)

Pass 1 — 给 12 张打卡点卡、8 个姿势模板、5 条平台观察加新字段(4 维 verification / mounting / node_status / 装饰拆解 / dependency_blockers / linked_observation_disposition)
Pass 2 — 新字段名 editorial_recommended_status / content_review_status 与旧字段名 popularity_status / review_status / trend_status 并存(用户 override:保留旧字段,向后兼容)
Pass 3 — 未拆 pose_templates_v0.yaml(用户 override:不拆),改用注释 SECTION A/B 分段区分 editorial / ornament;platform_observations_v0.yaml 按原计划也未拆
修了原 photo_craft_ornament_route 的重复 platform_observation_ids key(原 YAML 解析错误)
详见 TEAMMATE_HANDOFF.md 中"队友需要做的事"清单
使用规则
1.
editorial_recommended 仅表示项目人工策划的推荐，不得表述为"网红""最火"或实时热门。
2.
只有 review_status: approved 的卡才可主动推荐；draft_manual_review 仅供编辑审核，不进入游客端输出。
3.
所有卡必须有已审核的 node_id 和可追溯的装饰/点位来源；人物站位、最佳光线、画面角度须经现场复核后才可填写为确定建议。
4.
不得建议触摸文物、攀爬、跨越围栏、占用通道、使用闪光灯/补光设备或影响他人参观。现场告示和工作人员要求优先。
5.
family_blessing 只说明纹样的传统寓意，不承诺实际结果；craft_detail 建议拍摄时须遵守展厅及文保拍摄规定。
6.
姿势建议分为 editorial_pose_template（项目策划的通用、安全姿势）与 ornament_pose_reference（模仿具体装饰人物）。后者必须有现场照片、明确人物身份和动作说明后才能启用；不得由 Agent 根据题材名称臆造姿势。
热度字段
editorial_recommended：项目策划推荐，当前第一批卡均使用此值。该值仅表示"项目编辑选了这张卡"，不表示"游客在用""网络上最热"。
visitor_observed：由人工观察记录的稳定游客偏好，需有记录日期与采样说明。
real_time_verified：由已接入的实时平台/现场数据验证，必须带核验时间；当前不使用。
第一批为"家庭祝福、建筑辨识、工艺细节、故事任务"四类候选(此表述已并入 themes 字段,README 不再单独罗列)，待现场审核后再关联至 node_guide_cards_v1.json 的 photo_spot_card_ids。

字段参考表(Pass 1+2 新增)
全部新增字段与资格清单 card_runtime_eligibility_experience_v1.yaml 对齐。本节只列新增/重命名字段,旧字段见原文。

打卡点卡(photo_spot_cards_v0.yaml)
字段	类型	枚举值	说明
editorial_recommended_status	enum	editorial_recommended	新字段名(原 popularity_status),项目编辑推荐
content_review_status	enum	draft_manual_review / approved / rejected	新字段名(原 review_status)
content_verification_status	enum	pending / partial / verified / rejected	文字内容是否准确
source_verification_status	enum	同上	RAG 引用、装饰出处是否可靠
location_verification_status	enum	同上	现场站位/装饰位置是否核
safety_verification_status	enum	同上	客流/许可/儿童安全是否核
mounting_status	enum	not_yet_mounted / mounted / disabled	是否已挂到 node_guide(12 张卡当前全是 not_yet_mounted)
node_status	enum	in_node_guide_v1 / not_in_node_guide_v1 / node_id_will_change	stop_juxian_hall 和 label_rear_garden 当前为 not_in_node_guide_v1
verified_ornament_ids	list[str]	orn_xxx	target_ornaments 中有审核对象 ID 的部分
ornament_categories	list[str]	工艺类别(灰塑/木雕/石雕/陶塑)	工艺类别拆解(原 target_ornaments 含类名时填此)
pending_ornament_review	list[str]	自由文本	待审核或同名歧义(瓜瓞绵绵/木雕屏门 等)
disambiguated_ornament_ids	list[str]	orn_xxx	全部候选 ID(含同名多个,目前只有屏门用了)
dependency_blockers	list[obj]	见 §状态机	卡无法输出的依赖项
linked_observation_disposition	list[obj]	见下	平台观察的镜像(卡视角)
dependency_blockers 单条结构:

yaml


- blocker_id: <string>            # blocker 唯一标识

  blocker_type: <string>          # pose_disabled | node_missing | evidence_pending

  blocked_target: <string>        # 被卡的姿势/节点/装饰 ID

  reason: <string>                # 卡的原因

  must_resolve_before_output: <bool>
linked_observation_disposition 单条结构:

yaml


- observation_id: <string>          # 平台观察 ID

  disposition: <enum>                # visual_inspiration_only | rejected | pending_evidence

  notes: <string>                    # 引用此观察时的备注
姿势模板(pose_templates_v0.yaml)
字段	类型	枚举值	说明
editorial_recommended_status	enum	editorial_recommended / editorial_recommended_from_visual_reference / disabled_until_visual_review	新字段名(原 trend_status)
content_verification_status	enum	pending/partial/verified/rejected	文字内容是否准确
source_verification_status	enum	同上	RAG 引用、装饰出处
location_verification_status	enum	同上	现场站位/装饰位置
safety_verification_status	enum	同上	客流/许可/儿童安全
dependency_blockers	list[obj]	同上结构	模板的依赖项
平台观察(platform_observations_v0.yaml)
字段	类型	枚举值	说明
observation_kind	enum	rejected / visual_inspiration / pending_evidence	5 条观察当前全部 rejected(按资格清单)
content_verification_status	enum	pending/partial/verified/rejected	文字内容
source_verification_status	enum	同上	来源
location_verification_status	enum	同上	位置
safety_verification_status	enum	同上	客流/许可
visual_inspiration_available	bool	true/false	是否可作视觉参考(只有 morning_photo_time 和 roof_ridge_crafts=true)
状态机说明
4 维 verification 含义
维度	含义	资格清单对应字段
content_verification_status	文字内容是否准确	资格清单
source_verification_status	RAG 引用、装饰出处是否可靠	资格清单
location_verification_status	现场站位/装饰位置是否核	资格清单
safety_verification_status	客流/许可/儿童安全是否核	资格清单
4 个维度独立评估,组合决定卡/模板/观察是否可输出。

mounting_status × dependency_blockers 矩阵
mounting	dep_blockers 为空	dep_blockers 非空
not_yet_mounted	桌面草稿,不可输出	桌面草稿,不可输出(等 blocker 解)
mounted	可输出	不可输出(等 blocker 解)
disabled	永久禁挂	永久禁挂
dependency_blockers 与 gate 读取
重要:dependency_blockers 字段当前没有被 experience_card_runtime_gate.py 读取。gate 仍只读资格清单的 enabled/disabled。队友清单里要请工具团队决定是否要把本字段纳入 gating。

editorial_recommended_status 状态机
text


editorial_recommended ─(现场审核通过 + mounted)─→ 仍 editorial_recommended

                 └─(来源是平台视觉参考)─→ editorial_recommended_from_visual_reference

ornament_pose_reference 视觉审核未通过 → disabled_until_visual_review

rejected → 永不进入游客回答(仅平台观察)
跟资格清单的对应关系
本目录新字段	资格清单对应字段	同步要求
content_verification_status	资格清单 4 维 verification	资格清单是 source of truth,卡上是镜像;两边修改需同步
source_verification_status	同上	同上
location_verification_status	同上	同上
safety_verification_status	同上	同上
mounting_status	资格清单 mounting 字段(若存在)	当前 12 张卡全部 not_yet_mounted
dependency_blockers	无对应字段(本目录新增)	队友清单请工具团队决定是否纳入 gating
linked_observation_disposition	无对应字段(本目录新增)	卡内镜像平台观察,资格清单不放
verified_ornament_ids	装饰位置索引	由路线团队维护
pending_ornament_review	资格清单 limitations	待现场复核
disambiguated_ornament_ids	装饰位置索引	路线团队消歧后才正式启用
红线:资格清单不动本目录的任何字段;本目录是 source of truth 给资格清单镜像。

拆文件说明(Pass 3 用户 override)
本节为本次 override 的特别说明。原计划 §1.3 打算拆 pose_templates_v0.yaml 成 2 文件;但用户要求 Pass 3 不拆。

决定与原因
文件	原计划	实际做法	原因
pose_templates_v0.yaml	拆为 editorial_pose_templates_v0.yaml(7) + ornament_pose_references_v0.yaml(1)	不拆,改用注释 SECTION A/B 分段	用户 override:避免外部代码按文件名引用时断裂
platform_observations_v0.yaml	不拆(原计划)	不拆	5 条观察全是 rejected,无 visual_inspiration_only 状态可拆
photo_spot_cards_v0.yaml	不拆	不拆	12 张同构,无拆分必要
pose_templates_v0.yaml 当前内部结构
SECTION A — editorial_pose_template 共 7 条,默认 editorial_recommended,4 维 verification = partial/pending/pending/partial
SECTION B — ornament_pose_reference 共 1 条(pose_ornament_reference_pending),disabled_until_visual_review,4 维 verification 全 pending,带 2 个 dependency_blockers(自身被锁 + 仍需已启用打卡卡)
后续可拆时机
如果未来满足以下任一条件,可考虑真拆:

工具团队 experience_card_runtime_gate.py 决定按文件类型分流读 editorial/ornament
ornament_pose_reference 数量增加到 5 条以上,管理成本明显
团队人手足够并行维护两文件
D0-E 运行资格审计(关闭门控)
../card_runtime_eligibility_experience_v1.yaml 是本模块唯一的运行资格清单。它覆盖 12 张打卡点卡、8 个姿势模板和 5 条平台观察记录；资格记录缺失时默认 disabled。

12 张打卡点卡的运行资格由 card_runtime_eligibility_experience_v1.yaml 决定；D5-A 之后的默认启用覆盖见本文末尾。
当前 5 条平台观察均为 disabled；平台文字、截图、热度、票价、光线和机位都不能直接进入游客回答。
8 个姿势模板的运行资格由 card_runtime_eligibility_experience_v1.yaml 决定；即使启用，也应优先作为打卡卡的附属建议使用。
pose_ornament_reference_pending 的原始 trend_status=disabled_until_visual_review 仍保留；运行资格如有覆盖，以资格清单为准。
editorial_recommended 仅表示项目编辑推荐，不能表述为"热门""网红"或实时平台热度。
关闭门控的纯数据读取模块为仓库根目录 experience_card_runtime_gate.py，不接入 Agent。它在没有 enabled 资格记录时返回"暂无审核通过内容"，不回退使用草稿。验证见 test_experience_card_runtime_eligibility.py。

本审计不创建 raw_location、ornament_id 或新节点：瓜瓞绵绵、工艺类别"灰塑/木雕/石雕/陶塑"、以及"木雕屏门"尚不能精确匹配到审核对象；同名装饰（如"福""踏雪寻梅""太平有象"）也不自动消歧。所有这类问题均在资格清单的 limitations 中保留，待现场复核。

D5-A 逐项审核结果(2026-07-27,Pass 1 增补)
本轮完成对 12 张打卡点卡和 8 个姿势模板的桌面审核，审核结论仍只保存在 ../card_runtime_eligibility_experience_v1.yaml。初始桌面审核没有具名人工现场审核人或审核日期；后续按用户指令施加默认启用覆盖：打卡点卡 12/12 启用、姿势模板 8/8 启用；5 条平台观察继续全部 disabled。

12 张打卡卡均已复查现有 node_id、姿势/平台引用和 evidence_refs。但所有卡仍缺少现场对位置、客流、光线、开放状态、拍摄许可及实际站位的核验；平台观察仅是线索，不能作为事实或解锁依据。
photo_architecture_corridor_perspective、photo_solo_corridor_frame、photo_rear_garden_foliage_frame 被确认是空间构图主题，不是遗漏装饰对象；但各自的具体构图位置仍未现场确认。
瓜瓞绵绵、工艺类别"灰塑/木雕/石雕/陶塑"与"木雕屏门"仍无精确审核对象映射；不创建新对象 ID，也不自动消歧同名装饰。
8 个姿势模板已按默认启用覆盖开放；仍建议只作为打卡卡的附属建议使用。pose_ornament_reference_pending 保留原始 disabled_until_visual_review 标记，使用方需优先读取资格清单和现场管理要求。
现场复核优先项：月台/门厅/廊道/后花园的可停留区域与拍摄许可，室内屏门和展陈拍摄规则，儿童与通道安全，闪光灯/设备规则，以及需要动作呼应的装饰人物身份与视觉风险。
Pass 1 增补(2026-08-06)
修了 photo_craft_ornament_route 重复 platform_observation_ids key(YAML 解析错误),合并为 1 个含 3 个 ID 的合集
12 张卡的 4 维 verification 默认全 partial,只有 card 9(safety)、card 11(content+safety)、card 12(content) 是个别 pending
3 张卡有 dependency_blockers:card 9 → pose_ornament_reference_pending_disabled;card 11 → node_missing_stop_juxian_hall;card 12 → node_missing_label_rear_garden
2 张卡 node_status: not_in_node_guide_v1:photo_juxian_hall_screen_door(缺 stop_juxian_hall)、photo_rear_garden_foliage_frame(缺 label_rear_garden)
7 张卡有 linked_observation_disposition 镜像平台观察(只有 2 条观察可作 visual_inspiration)
待办清单
详细清单见 TEAMMATE_HANDOFF.md,本节只列大纲。

A. 路线/装饰团队
node_guide_cards_v1.json 缺 2 个 node(stop_juxian_hall / label_rear_garden)
ornament_spatial_mapping_v1.csv 4 条 craft 字段名拼接错误(orn_081/054/083/093)
拼写不一致:瓜瓞绵绵 (README/卡) vs 瓜瓞连绵 (orn_085 实际值)
B. 现场审核团队
12 个 node 的 photo_spot_card_ids: [] 现场审核后填
C. 知识/运行资格团队
card_runtime_eligibility_experience_v1.yaml 字段重命名是否同步
experience_card_runtime_gate.py 是否读新字段(尤其 dependency_blockers)
test_experience_card_runtime_eligibility.py 加新字段测试
D. 工具/平台观察团队
grep platform_observations_v0 字符串引用,确认拆/不拆文件的影响
grep popularity_status / trend_status 字符串引用(本目录已与新字段并存,外部仍用旧字段即可)