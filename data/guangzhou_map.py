"""
广州市地图数据模型
包含简化的广州市中心区域道路网络、节点和充电站信息
"""

import math
import random
import networkx as nx
import numpy as np

# 广州市中心区域边界
GUANGZHOU_BOUNDARY = {
    'north': 23.15,
    'south': 23.05,
    'east': 113.35,
    'west': 113.25
}

# 主要道路节点（简化模型）
# 格式：(节点ID, 纬度, 经度, 节点名称)
MAIN_NODES = [
    # 天河区节点
    (1, 23.135, 113.33, "天河体育中心"),
    (2, 23.13, 113.32, "广州东站"),
    (3, 23.125, 113.34, "珠江新城"),
    (4, 23.14, 113.34, "广州天河CBD"),
    (5, 23.15, 113.32, "白云山南门"),
    
    # 越秀区节点
    (6, 23.12, 113.28, "北京路"),
    (7, 23.11, 113.27, "广州火车站"),
    (8, 23.125, 113.29, "中山纪念堂"),
    (9, 23.115, 113.28, "广州起义纪念馆"),
    
    # 海珠区节点
    (10, 23.08, 113.31, "广州塔"),
    (11, 23.07, 113.32, "琶洲会展中心"),
    (12, 23.09, 113.30, "海珠广场"),
    (13, 23.06, 113.30, "广州大学城"),
    
    # 荔湾区节点
    (14, 23.10, 113.26, "上下九"),
    (15, 23.11, 113.25, "陈家祠"),
    (16, 23.09, 113.25, "沙面"),
    
    # 白云区节点
    (17, 23.16, 113.28, "广州白云国际机场"),
    (18, 23.17, 113.30, "嘉禾望岗"),
    
    # 黄埔区节点
    (19, 23.10, 113.45, "黄埔港"),
    (20, 23.12, 113.40, "科学城"),
    
    # 番禺区节点
    (21, 22.94, 113.38, "番禺广场"),
    (22, 22.90, 113.33, "广州南站"),
    
    # 花都区节点
    (23, 23.40, 113.22, "花都广场"),
    
    # 仓库节点
    (100, 23.15, 113.35, "中央仓库")
]

# 主要道路连接（简化模型）
# 格式：(起点节点ID, 终点节点ID, 道路名称, 距离(米), 道路类型)
MAIN_ROADS = [
    # 广州大道（南北主干道）
    (1, 3, "广州大道中", 2000, "主干道"),
    (3, 10, "广州大道南", 3000, "主干道"),
    (1, 2, "广州大道北", 1500, "主干道"),
    
    # 黄埔大道（东西主干道）
    (1, 4, "黄埔大道西", 1000, "主干道"),
    (4, 20, "黄埔大道东", 8000, "主干道"),
    
    # 天河路
    (1, 6, "天河路", 5000, "主干道"),
    
    # 中山路
    (6, 8, "中山路", 2000, "主干道"),
    (8, 14, "中山路", 3000, "主干道"),
    
    # 环市路
    (2, 8, "环市东路", 4000, "主干道"),
    (8, 15, "环市西路", 3000, "主干道"),
    
    # 东风路
    (4, 9, "东风东路", 4000, "主干道"),
    (9, 15, "东风西路", 3000, "主干道"),
    
    # 华南快速干线
    (1, 21, "华南快速干线", 15000, "快速路"),
    (21, 22, "华南快速干线", 5000, "快速路"),
    
    # 广园快速路
    (2, 19, "广园快速路", 15000, "快速路"),
    
    # 机场高速
    (17, 18, "机场高速", 10000, "高速路"),
    (18, 2, "机场高速", 15000, "高速路"),
    
    # 环城高速
    (19, 21, "广州环城高速", 20000, "高速路"),
    (21, 13, "广州环城高速", 10000, "高速路"),
    (13, 10, "广州环城高速", 8000, "高速路"),
    (10, 12, "广州环城高速", 5000, "高速路"),
    (12, 16, "广州环城高速", 3000, "高速路"),
    (16, 14, "广州环城高速", 2000, "高速路"),
    (14, 18, "广州环城高速", 15000, "高速路"),
    
    # 其他主要道路
    (10, 11, "阅江路", 5000, "主干道"),
    (12, 16, "沿江西路", 2000, "主干道"),
    (15, 16, "黄沙大道", 2000, "主干道"),
    (11, 13, "科韵路", 6000, "主干道"),
    (20, 19, "开创大道", 5000, "主干道"),
    (17, 23, "大广高速", 20000, "高速路"),
    
    # 仓库连接
    (100, 4, "仓库连接线", 2000, "主干道"),
    (100, 20, "仓库连接线", 5000, "主干道")
]

# 充电站数据（基于真实数据简化）
# 格式：(充电站ID, 节点ID, 充电桩数量, 充电速率(km电量/分钟))
CHARGING_STATIONS = [
    (1, 1, 10, 2.0),    # 天河体育中心充电站
    (2, 3, 8, 2.0),     # 珠江新城充电站
    (3, 6, 6, 1.5),     # 北京路充电站
    (4, 10, 12, 2.5),   # 广州塔充电站
    (5, 14, 6, 1.5),    # 上下九充电站
    (6, 17, 20, 3.0),   # 白云机场充电站
    (7, 19, 8, 2.0),    # 黄埔港充电站
    (8, 21, 10, 2.0),   # 番禺广场充电站
    (9, 22, 15, 2.5),   # 广州南站充电站
    (10, 23, 8, 1.5),   # 花都广场充电站
    (11, 100, 5, 2.0),  # 仓库充电站
    (12, 4, 8, 2.0),    # 天河CBD充电站
    (13, 11, 10, 2.0),  # 琶洲充电站
    (14, 20, 6, 1.5),   # 科学城充电站
    (15, 18, 8, 2.0)    # 嘉禾望岗充电站
]

def create_guangzhou_graph():
    """
    创建广州市道路网络图
    返回：NetworkX图对象
    """
    G = nx.DiGraph()
    
    # 添加节点
    for node_id, lat, lon, name in MAIN_NODES:
        G.add_node(node_id, lat=lat, lon=lon, name=name)
    
    # 添加边
    for u, v, road_name, distance, road_type in MAIN_ROADS:
        # 双向道路
        G.add_edge(u, v, weight=distance, road_name=road_name, road_type=road_type)
        G.add_edge(v, u, weight=distance, road_name=road_name, road_type=road_type)
    
    return G

def get_node_coordinates(node_id):
    """
    获取节点的经纬度坐标
    """
    for nid, lat, lon, name in MAIN_NODES:
        if nid == node_id:
            return (lat, lon)
    return None

def get_node_name(node_id):
    """
    获取节点的名称
    """
    for nid, lat, lon, name in MAIN_NODES:
        if nid == node_id:
            return name
    return f"节点{node_id}"

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    使用Haversine公式计算两个经纬度坐标之间的距离
    返回：距离（米）
    """
    # 地球半径（米）
    R = 6371000
    
    # 将经纬度转换为弧度
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # 计算差值
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Haversine公式
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance

def find_nearest_node(lat, lon):
    """
    找到离给定经纬度最近的节点
    """
    min_distance = float('inf')
    nearest_node = None
    
    for node_id, node_lat, node_lon, name in MAIN_NODES:
        distance = calculate_haversine_distance(lat, lon, node_lat, node_lon)
        if distance < min_distance:
            min_distance = distance
            nearest_node = node_id
    
    return nearest_node, min_distance

def generate_random_location(boundary=None):
    """
    在指定边界内生成随机位置
    """
    if boundary is None:
        boundary = GUANGZHOU_BOUNDARY
    
    lat = random.uniform(boundary['south'], boundary['north'])
    lon = random.uniform(boundary['west'], boundary['east'])
    
    return lat, lon

def get_charging_station_info(station_id):
    """
    获取充电站信息
    """
    for sid, node_id, capacity, charging_rate in CHARGING_STATIONS:
        if sid == station_id:
            node_lat, node_lon = get_node_coordinates(node_id)
            node_name = get_node_name(node_id)
            return {
                'id': sid,
                'node_id': node_id,
                'location': (node_lat, node_lon),
                'name': f"{node_name}充电站",
                'capacity': capacity,
                'charging_rate': charging_rate
            }
    return None

def get_all_charging_stations():
    """
    获取所有充电站信息
    """
    stations = []
    for sid, node_id, capacity, charging_rate in CHARGING_STATIONS:
        node_lat, node_lon = get_node_coordinates(node_id)
        node_name = get_node_name(node_id)
        stations.append({
            'id': sid,
            'node_id': node_id,
            'location': (node_lat, node_lon),
            'name': f"{node_name}充电站",
            'capacity': capacity,
            'charging_rate': charging_rate
        })
    return stations

def get_depot_location():
    """
    获取仓库位置
    """
    for node_id, lat, lon, name in MAIN_NODES:
        if node_id == 100:  # 仓库节点ID
            return node_id, lat, lon, name
    return None

if __name__ == "__main__":
    # 创建地图
    G = create_guangzhou_graph()
    
    # 打印地图信息
    print(f"广州市地图模型包含 {G.number_of_nodes()} 个节点和 {G.number_of_edges()} 条边")
    
    # 打印充电站信息
    print(f"\n共有 {len(CHARGING_STATIONS)} 个充电站：")
    for station in get_all_charging_stations():
        print(f"- {station['name']} (节点{station['node_id']}): {station['capacity']}个充电桩")
    
    # 打印仓库信息
    depot_id, depot_lat, depot_lon, depot_name = get_depot_location()
    print(f"\n仓库位置：{depot_name} (节点{depot_id})，坐标：({depot_lat}, {depot_lon})")