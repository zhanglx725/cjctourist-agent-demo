import csv
from datetime import datetime, timedelta

# ===================== 配置常量（按需修改） =====================
INPUT_CSV = "chenjiaci_poi_full.csv"
OUTPUT_YAML = "data\\chen_clan_academy\\evaluation\\manual_reviews\\p4_04_nearby_poi_card_authoring_template_v1.yaml"
# 高德来源固定ID
MAP_SRC_ID = "SRC_MAP_001"
# 基础固定参数
CITY = "广州市"
DISTRICT = "荔湾区"
EXIT_NAME = "陈家祠正门"
SUIT_TIME = '["after_visit"]'
# 今日日期用于核验时效
today = datetime.now().strftime("%Y-%m-%d")
valid_until = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
# 基础yaml头部固定模板
yaml_header = """# P4-04 馆外附近推荐卡 自动生成文件
# 自动来源：高德API采集CSV，仅填充客观定位/分类/步行数据，文案与事实需人工补全
schema_version: nearby_poi_card_authoring_v1
catalog_version: "0.1.0-draft"
venue_id: chen_clan_academy
locale_default: zh-CN
catalog_policy:
  recommendation_count:
    min: 2
    max: 3
  require_category_diversity: true
  runtime_approved_only: true
  isolate_from_indoor_tour_state: true
  allowed_categories:
    - food
    - cafe_or_rest
    - heritage_site
    - museum_or_gallery
    - park_or_public_space
    - shopping_or_craft
    - transport_service
    - visitor_service
  budget_bands:
    - free
    - low
    - medium
    - high
    - unknown
  source_priority:
    - poi_official
    - government_or_public_institution
    - official_map_listing
    - reviewed_editorial
  volatile_information_types:
    - opening_hours
    - admission_or_price
    - temporary_closure
    - queue_or_crowding
    - walking_time
    - public_transport_time
    - availability
  required_public_uncertainty_zh: 营业、价格、排队和交通信息可能变化，出发前请以商家、场馆或地图的最新信息为准。
cards:
"""

# ===================== 单行POI YAML生成函数 =====================
def build_single_card(row, idx):
    # 读取CSV字段
    poi_name = row["poi_name"]
    address = row["address"]
    lnglat = row["lnglat"]
    line_dist = row["line_distance_m"]
    walk_min = row["walk_minutes"]
    main_cat = row["main_category"]
    sub_cat = row["secondary_categories"]

    # 拆分经纬度
    lng, lat = lnglat.split(",") if lnglat else ("null", "null")
    lng = lng.strip()
    lat = lat.strip()

    # 处理步行时间文案
    if walk_min.isdigit():
        walk_text = f"步行约{walk_min}分钟"
        walk_status = "verified"
    else:
        walk_text = "unknown"
        walk_status = "unverified"

    # 唯一poi_id 简易生成：拼音+序号，人工可后续修改
    simple_id = f"poi_auto_{idx:03d}"

    # YAML卡片模板，{{xxx}}为占位符，人工补填
    card_tpl = f"""  - poi_id: {simple_id}
    names:
      zh-CN: {poi_name}
      en: ""
      ko: ""
    category: {main_cat}
    secondary_categories: {sub_cat}
    editorial:
      one_line_summary_zh: "【人工补】客观描述门店特色，禁止使用最佳/必去"
      why_nearby_zh: "【人工补】说明参观陈家祠后顺路游览逻辑"
      cultural_context_zh: ""
      recommendation_tags:
        - 【人工补】兴趣标签
      suitable_time_windows: {SUIT_TIME}
      estimated_visit_minutes:
        min: 30
        max: 60
      budget_band: unknown
      suitable_for: []
      unsuitable_or_caution_for: []
    location:
      address_zh: {address}
      district: {DISTRICT}
      city: {CITY}
      latitude: {lat if lat != "" else "null"}
      longitude: {lng if lng != "" else "null"}
      nearest_chen_clan_academy_exit: unknown
      meeting_or_entrance_note_zh: ""
      map_query_text: "{poi_name}{address}"
    stable_facts:
      - claim_id: fill_poi_identity_claim
        claim_kind: identity_or_category
        public_text_zh: "【人工补】场所基础身份描述"
        source_ids:
          - {MAP_SRC_ID}
        verified_at: "{today}"
        review_status: draft
      - claim_id: fill_poi_feature_claim
        claim_kind: reviewed_feature
        public_text_zh: "【人工补】核验后的核心特色"
        source_ids:
          - {MAP_SRC_ID}
        verified_at: "{today}"
        review_status: draft
    volatile_facts:
      opening_hours:
        value_zh: unknown
        status: unverified
        source_ids: []
        verified_at: ""
        valid_until: ""
        official_check_url: ""
      admission_or_price:
        value_zh: unknown
        currency: CNY
        status: unverified
        source_ids: []
        verified_at: ""
        valid_until: ""
        official_check_url: ""
      temporary_closure:
        value_zh: unknown
        status: unverified
        source_ids: []
        verified_at: ""
        valid_until: ""
        official_check_url: ""
      queue_or_crowding:
        value_zh: unknown
        status: unverified
        source_ids: []
        verified_at: ""
        valid_until: ""
        official_check_url: ""
      walking_time:
        origin_zh: {EXIT_NAME}
        destination_zh: {poi_name}入口
        value_zh: {walk_text}
        status: {walk_status}
        source_ids:
          - {MAP_SRC_ID}
        verified_at: "{today}"
        valid_until: "{valid_until}"
        official_check_url: "【人工补】高德POI详情网页链接"
      public_transport_time:
        origin_zh: {EXIT_NAME}
        destination_zh: {poi_name}入口
        value_zh: unknown
        status: unverified
        source_ids: []
        verified_at: ""
        valid_until: ""
        official_check_url: ""
    visitor_constraints:
      accessibility:
        status: unknown
        public_note_zh: 暂无已核验无障碍信息，请出发前向场所确认。
        source_ids: []
        verified_at: ""
      dietary_or_allergen:
        status: not_applicable_or_unknown
        public_note_zh: ""
        source_ids: []
        verified_at: ""
      child_or_family:
        status: unknown
        public_note_zh: ""
        source_ids: []
        verified_at: ""
      weather_exposure:
        status: unknown
        public_note_zh: ""
      reservation:
        status: unknown
        public_note_zh: ""
        source_ids: []
        verified_at: ""
    recommendation_boundaries:
      do_not_recommend_when: []
      required_disclosures:
        - volatile_information_may_change
      prohibited_claims:
        - best_or_top_ranking_without_evidence
        - guaranteed_open
        - guaranteed_price
        - guaranteed_no_queue
        - inferred_spending_capacity
      fallback_action_zh: 易变信息无法核实时，请游客查看该 POI 官方页面或地图实时信息。
    sources:
      - source_id: {MAP_SRC_ID}
        title: 高德地图-{poi_name}官方收录页
        publisher: 高德地图
        source_type: official_map_listing
        url: "【人工补】高德POI网页链接"
        published_at: ""
        accessed_at: "{today}T10:00:00+08:00"
        supports_claim_ids:
          - fill_poi_identity_claim
          - fill_poi_feature_claim
        archive_or_snapshot: ""
        notes: 基础地址、坐标、步行时长来源于高德Web服务API
    review:
      content_review_status: draft
      cultural_review_status: pending
      safety_review_status: pending
      location_review_status: pending
      volatile_data_review_status: pending
      reviewed_by: []
      reviewed_at: ""
      next_review_due: ""
      rejection_or_revision_notes: []
    enabled: false
"""
    return card_tpl

# ===================== 主执行入口 =====================
if __name__ == "__main__":
    all_cards = []
    # 读取csv
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for index, row in enumerate(reader, start=1):
            card_yaml = build_single_card(row, index)
            all_cards.append(card_yaml)
    # 写入yaml文件
    full_output = yaml_header + "\n".join(all_cards)
    with open(OUTPUT_YAML, "w", encoding="utf-8") as f:
        f.write(full_output)
    print(f"转换完成！输出文件：{OUTPUT_YAML}")
    print("提示：文件内所有【人工补】占位内容需要内容团队逐条完善，完善后修改review状态与enabled:true")