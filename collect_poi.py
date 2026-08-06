import requests
import pandas as pd

# ========== 配置区，修改这里 ==========
AMAP_KEY = "b2b169dd3a7f24219f9b683288f1c2f6"
# 陈家祠正门 GCJ02坐标
# 错误旧坐标（北偏1km，彩虹桥）
# center_lnglat = "113.243722,23.137221"
# 正确高德GCJ02陈家祠景区坐标（中山七路正门）
CENTER_LNG_LAT = "113.245158,23.126692"
SEARCH_RADIUS = 1000
# 筛选品类：美食|风景名胜|公园广场|购物|餐饮甜品
SEARCH_TYPES = "010100|020000|030200|050000|140000"
OUTPUT_CSV = "chenjiaci_poi_full_auto.csv"
# ======================================

def get_poi_detail(poi_id, key):
    """调用POI详情接口，extensions=all获取扩展信息"""
    url = "https://restapi.amap.com/v3/place/detail"
    params = {
        "key": key,
        "id": poi_id,
        "extensions": "all",
        "output": "json"
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if data.get("status") != "1":
        return {}
    return data["pois"][0]

def calc_walk_info(origin, dest_lnglat, key):
    """步行规划，返回真实道路距离、分钟数"""
    url = "https://restapi.amap.com/v3/direction/walking"
    params = {
        "key": key,
        "origin": origin,
        "destination": dest_lnglat,
        "output": "json"
    }
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()
    if data["status"] == "1" and data["route"]["paths"]:
        path = data["route"]["paths"][0]
        road_m = int(path["distance"])
        walk_min = round(int(path["duration"]) / 60)
        return road_m, walk_min
    return None, "unknown"

if __name__ == "__main__":
    # 1. 周边搜索获取POI列表
    around_url = "https://restapi.amap.com/v3/place/around"
    around_params = {
        "key": AMAP_KEY,
        "location": CENTER_LNG_LAT,
        "radius": SEARCH_RADIUS,
        "types": SEARCH_TYPES,
        "output": "json",
        "page": 1,
        "offset": 50
    }
    res_around = requests.get(around_url, around_params, timeout=10)
    json_around = res_around.json()

    if json_around.get("status") != "1":
        print("周边搜索接口失败：", json_around.get("info"))
        exit()

    poi_list_raw = json_around["pois"]
    export_rows = []

    for item in poi_list_raw:
        poi_name = item.get("name", "")
        poi_addr = item.get("address", "")
        lnglat = item.get("location", "")
        line_dist_m = int(item.get("distance", 0))
        poi_id = item.get("id", "")
        typecode = item.get("typecode", "")

        # 2. 调用详情接口拿扩展信息
        detail = get_poi_detail(poi_id, AMAP_KEY)
        # 营业时间
        opentime = detail.get("opentime", "unknown")
        # 人均消费
        cost = detail.get("cost", "unknown")
        # 标签数组转字符串
        tag_arr = detail.get("tag", "").split("|") if detail.get("tag") else []
        tag_str = str(tag_arr)
        # 高德POI网页链接
        amap_url = f"https://amap.com/poi/{poi_id}" if poi_id else ""
        # 联系电话
        tel = detail.get("tel", "")

        # 3. 计算步行真实距离、步行分钟
        real_walk_m, walk_min = calc_walk_info(CENTER_LNG_LAT, lnglat, AMAP_KEY)

        row = {
            # 基础定位字段（原有）
            "poi_name": poi_name,
            "address": poi_addr,
            "lnglat": lnglat,
            "line_distance_m": line_dist_m,
            "real_walk_m": real_walk_m,
            "walk_minutes": walk_min,

            # 新增自动化扩展字段（可预填充人工补充表）
            "amap_poi_id": poi_id,
            "typecode": typecode,
            "business_hour_api": opentime,
            "avg_cost_api": cost,
            "tag_list_api": tag_str,
            "poi_tel": tel,
            "amap_detail_url": amap_url
        }
        export_rows.append(row)

    # 导出CSV，中文不乱码
    df = pd.DataFrame(export_rows)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"完整数据导出完成：{OUTPUT_CSV}")
    print("新增自动获取字段：高德唯一ID、业态编码、营业时间、人均、标签、高德详情链接、联系电话")