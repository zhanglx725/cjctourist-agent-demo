# 陈家祠空间网络 v0：人工审核说明

本目录保存导游路线规划所需的**人工核验空间数据**。它不是 GPS 导航数据，也不应让模型依据图片自行猜测通行关系。

## 第一步：地图审核员的工作

1. 将底图另存为 `assets/maps/chenjiaci_plan_v0.png`；若不能确认公开使用授权，不要提交图片，只在 `map_manifest_v0.json` 填写本地保存位置和来源。
2. 在 `map_manifest_v0.json` 填写图片来源、版本、审核人和方位。当前图面推定为上北下南、左西右东，必须人工确认后再改为 `verified`。
3. 在 `marker_inventory_v0.csv` 维护正式空间节点。蓝色标记使用 `map_feature=blue_marker`，图中文字使用 `map_feature=text_label`。
4. 蓝点和图中文字都不一定都是讲解点。请区分 `entrance`、`guide_stop`、`junction`、`hall`、`wing`、`study`、`courtyard`、`platform`、`gate`、`service` 和 `unknown`。
5. 只有确认实际可通行的连廊、门洞、台阶和院落后，才创建路线边；官网路线顺序可以作为初始证据，但仍需现场复核。

## 坐标记录方法

坐标采用图片像素：左上角为 `(0, 0)`，向右为 `x` 增大，向下为 `y` 增大。可使用 QGIS、任意图片标注工具，或先只填写候选名称和审核状态；坐标可在第二轮补录。

## 审核状态

- `needs_review`：尚未核验，不能作为正式路线依据。
- `confirmed_from_map`：能从可靠底图确认，仍建议现场核验。
- `verified_on_site`：已现场或由馆方权威平面图确认。
- `rejected`：不是可用点位，或原先判断错误。

## 本轮完成条件

- 已确认地图来源和可否在仓库中保存；
- 已确认东、西、南、北以及前院/后花园方向；
- 红点和所有蓝点均有唯一 `marker_id`；
- 每个标记均有候选名称、类型和审核状态；
- 不确定项保留 `needs_review`，不强行命名。

## 首次连边测试：如何标注

在 `edges_v0.csv` 中，一行代表一条**已知或待核验的可行移动关系**，不是把地图上所有相邻建筑都连起来。

```text
from_node_id        起点节点 ID
to_node_id          终点节点 ID
direction           `both`、`forward_only` 或 `unknown`
walk_seconds        步行秒数；必须搭配 `time_basis`，不能将估算值写成实测值
time_basis          `measured_on_site`、`estimated_from_map_and_official_route` 或 `unknown`
accessibility       `accessible`、`stairs`、`unknown`
status              `verified_on_site`、`provisional_from_map` 或 `provisional_from_official_route`
source              图、官网路线或现场核验记录
```

当前 v0 已录入官网路线骨架及少量人工审核的相邻关系。路线规划可使用其中的估算时间做初步测试：

```text
大门外 → 前院中部 → 首进正厅 → 月台 → 中进聚贤堂
```

其中“首进正厅 → 月台 → 中进聚贤堂”来自馆方公开的一小时路线顺序；这可证明参观顺序，但不等于已验证每一段的精确步行线路、单双向通行或无障碍条件。当前 `estimated_from_map_and_official_route` 仅服务原型的路线时长预算；到现场后应将每条边的 `walk_seconds` 改为实测值，并把 `time_basis` 更新为 `measured_on_site`。
