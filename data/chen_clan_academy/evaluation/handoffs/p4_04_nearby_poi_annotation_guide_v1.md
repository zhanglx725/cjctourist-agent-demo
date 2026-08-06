# P4-04 周边 POI 人工标注需求（精简版）

## 1. 标注目标

从 `chenjiaci_poi_full_auto.csv` 中筛出少量真实、稳定、适合在陈家祠游览结束后推荐的馆外 POI。首期追求可信和类型多样，不追求把爬取结果全部上线。

人工标注不是补全百科资料，也不负责估算游客应该停留多久。人工只回答三个问题：

1. 这个 POI 是否适合进入推荐池？
2. 它是什么，为什么适合在陈家祠之后推荐？
3. 推荐时需要提醒游客什么？

## 2. 自动导入字段

以下字段由 CSV 转换程序写入，人工只检查明显错误：

| 字段 | 说明 |
|---|---|
| `source_row_id` | CSV 行号或原始平台稳定 ID |
| `poi_id` | 系统生成的稳定 ID |
| `name_zh` | POI 中文名称 |
| `original_category` | 爬取平台原始分类 |
| `address_zh` | 原始地址 |
| `latitude` / `longitude` | 坐标；没有则留空 |
| `map_url` | 地图详情链接；没有则留空 |
| `source_url` | 原始数据页面 |

自动字段缺失不等于必须填 `unknown`。缺失但不影响判断时可以留空；名称或地点无法确认时标记 `needs_review` 或 `reject`。

## 3. 人工必填字段

### decision

- `approve`：适合推荐，身份和地点能够核实。
- `needs_review`：可能适合，但存在重名、地址、分类、来源或真实性问题。
- `reject`：不适合进入推荐池。

### category

只能选择一个主类别：`food`、`cafe_or_rest`、`heritage_site`、`museum_or_gallery`、`park_or_public_space`、`shopping_or_craft`、`hotel_or_accommodation_area`、`transport_or_visitor_service`。

### one_line_summary_zh

20–60个汉字，说明 POI 类型和一项稳定特色，只写来源能够支持的内容。

合格：

> 一处以岭南传统建筑和地方历史展示为主要看点的文化场所。

不合格：

> 广州最好玩、最出片、绝对不能错过的宝藏景点。

### why_recommend_zh

20–80个汉字，说明它与陈家祠参观后的衔接价值。可以写主题延伸、休息、餐饮、购物或交通衔接，但不能编造精确耗时。

合格：

> 适合在看完岭南建筑装饰后继续了解广州旧城文化，也可作为下一段步行游览的方向。

### tags

选择1–4个模板中的受控标签。不要自由制造近义标签。例如已有 `photography`，不要再写“拍照”“出片”“摄影打卡”。

### evidence_url

至少提供一个直接来源，优先使用 POI 官方网站、政府或公共机构页面、官方地图详情页、可靠机构介绍页。不得填写搜索结果页、模型回答或无法打开的聚合转载页。

## 4. 可选字段

以下内容只有在确实有用且能够核实时才填写；否则从卡片中删除，不写 `unknown`：

- `location_hint_zh`：稳定的相对方位描述；
- `arrival_note_zh`：入口、换乘或到达提醒；
- `caution_zh`：真实必要的边界提醒；
- 营业时间、价格、预约和无障碍信息。

只要填写任一动态信息，就必须同时填写 `checked_at` 和 `official_url`。动态信息过期后可以不展示，不影响基础 POI 卡继续存在。

## 5. 首期明确删除的人工字段

- 建议最短停留时间、最长停留时间；
- 人工估算步行时间或公交时间；
- 排队和拥挤程度；
- 临时关闭预测；
- 预算高低分档；
- 对儿童、家庭、饮食和天气的全量适配判断；
- 多语言名称和未经审核的机器翻译；
- 为每句话手工编写 `claim_id`、`source_id` 和来源映射；
- 对所有缺失信息批量填写 `unknown`。

距离和交通耗时如后续确有需要，应由地图服务在请求时动态计算，不能让标注人员主观估算。

## 6. reject 标准

满足任一情况时标记 `reject`：

- 已关闭、搬迁、重复或无法确认真实存在；
- 名称与坐标明显不对应；
- 与陈家祠周边推荐没有合理关系；
- 只有广告软文或内容农场来源；
- 涉及违法、危险、成人服务或明显不适合普通游客的内容；
- 推荐理由只能依赖实时折扣、排名、评分或未经证实的网红宣传。

## 7. needs_review 标准

以下情况不要猜测，标记 `needs_review`：

- 同名 POI 无法判断具体分店；
- 地址、坐标和名称存在冲突；
- 分类模糊，无法确定是餐厅、商店还是景点；
- 特色可能真实，但现有页面不能直接支持；
- POI 看起来已更名或近期搬迁；
- 唯一来源已过期或无法访问。

## 8. 质量抽检

- 首批前20条建议全检，后续每批抽检不少于20%；
- 名称、地址和坐标必须指向同一 POI；
- `approve` 卡必须有至少一个有效直接来源；
- 文案不得出现“最好、第一、必去、保证营业、绝对不排队”等表达；
- 同一推荐池至少覆盖三种主类别，避免全部是餐饮或全部是景点。

## 9. 完整示例

```yaml
- source_row_id: csv_000123
  poi_id: poi_example_heritage_001
  name_zh: 示例文化场所
  original_category: 景点
  address_zh: 广州市荔湾区示例路1号
  latitude: 23.000000
  longitude: 113.000000
  map_url: https://example.invalid/map-entry
  source_url: https://example.invalid/source-entry

  decision: approve
  category: heritage_site
  one_line_summary_zh: 一处以地方建筑与历史文化展示为主要内容的文化场所。
  why_recommend_zh: 适合在陈家祠游览后继续了解广州旧城及岭南建筑文化。
  tags: [architecture, history]
  evidence_url: https://example.invalid/direct-authoritative-source
  location_hint_zh: 位于陈家祠馆外周边区域，具体路线请以地图实时导航为准。

  review:
    status: approved
    reviewed_by: reviewer_name
    reviewed_at: "YYYY-MM-DD"
    notes: ""
  enabled: true
```

以上名称、地址和链接只用于展示填写方式，不能作为真实 POI 上线。

## 10. 交付标准

首批建议交付15–30张 `approve` 卡，并覆盖至少三种类别。其余爬取记录可以保留为 `reject` 或 `needs_review`，不需要为了提高通过数量补写无法验证的信息。

只有同时满足以下条件的卡片才能进入运行时推荐池：

```text
decision = approve
review.status = approved
enabled = true
evidence_url 可访问并直接支持核心描述
```
