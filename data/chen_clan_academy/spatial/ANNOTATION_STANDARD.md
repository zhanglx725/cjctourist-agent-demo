# 装饰位置与既有地图点位人工核验标准 v0

适用文件：`ornament_spatial_candidates_v0.csv`。

## 核验目标

对每一件装饰，判断官网记录的摆放位置是否能对应到**已经建立的地图节点**。只有确认可对应时，才填写 `final_node_id`；不能对应时，不要为了凑路线而猜测。

`marker_inventory_v0.csv` 是本阶段的**最终可选点位清单**：

- 只能从它的 `node_id` 中选择并填写 `final_node_id`；
- 用同一行的 `name` 和地图坐标 `x`、`y` 判断该节点是否是正确空间；
- 找不到对应节点时，选择 `add_node` 或 `skip`，不能自造 ID。

## 判断证据的优先顺序

1. 馆方官网 720 导览地图及其图中文字、热点位置；
2. 馆方官网的装饰图文页或展厅/导览说明；
3. `knowledge/09_ornament_locations.md` 的 `raw_location`（官网整理快照）；
4. `marker_inventory_v0.csv` 中已经建好的节点；
5. `candidate_node_id`、`candidate_node_name`（程序建议，只能辅助，不能代替官网核验）。

当官网图与文字位置冲突，先不关联，备注写“官网资料待核”；现场或馆方最新说明优先。

## 团队只填写三列

| 人工填写列 | 填写规则 |
| --- | --- |
| `reviewer_decision` | 只能填 `accept`、`change`、`add_node`、`skip`。 |
| `final_node_id` | 必须从 `marker_inventory_v0.csv` 的 `node_id` 复制；仅 `accept`、`change` 时填写。 |
| `review_notes` | 写“官网证据 + 判断理由”，例如“720 图中月台热点，官网文字为月台正面”。 |

## 决定选项

| 值 | 何时使用 | `final_node_id` |
| --- | --- | --- |
| `accept` | 官网核验后确认程序候选点就是正确的既有地图点 | 复制 `candidate_node_id` |
| `change` | 官网核验后确认应对应另一个既有地图点 | 填 `marker_inventory_v0.csv` 中正确的 `node_id` |
| `add_node` | 官网能定位，但 `marker_inventory_v0.csv` 没有该节点，如“庆基廊门” | 留空；备注写“新增节点：名称、官网依据” |
| `skip` | 位置过泛、官网无法定位，或暂不作为路线讲解点 | 留空；写明原因 |

## 操作顺序

1. 在候选表看 `raw_location`，了解官网记录的原始位置。
2. 打开官网 720 导览地图和相关官网图文，核对该位置实际位于哪个建筑/廊门/院落。
3. 打开 `spatial/marker_inventory_v0.csv`，在 `name` 列找该空间；以该行的 `node_id` 作为唯一可填写 ID，并结合 `x`、`y` 回看地图位置。
4. 再看候选表的 `candidate_node_id`、`candidate_node_name`：一致则 `accept`，不一致但已有正确节点则 `change`。
5. 没有既有节点则 `add_node` 或 `skip`，不填写 `final_node_id`。

## 最小范例

```text
raw_location: 月台正面
官网核验: 720 图与馆方装饰说明均指向月台
marker_inventory_v0.csv: name=月台, node_id=label_moon_platform
reviewer_decision: accept
final_node_id: label_moon_platform
review_notes: 官网720图月台位置；官网文字“月台正面”
```

不要修改 `ornament_id`、`raw_heading`、`raw_location`、`detail_lookup_key`、`candidate_*` 与 `match_*` 列。这些是来源信息和可重复生成的程序候选。
