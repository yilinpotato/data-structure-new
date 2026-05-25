"""
路径规划算法模块
"""

import heapq
import math
import networkx as nx
from data.guangzhou_map import get_node_coordinates, calculate_haversine_distance

def a_star_search(graph, start_node, goal_node, weight='weight'):
    """
    A*搜索算法实现最短路径查找
    
    参数:
    - graph: NetworkX图对象
    - start_node: 起始节点ID
    - goal_node: 目标节点ID
    - weight: 边权重属性名
    
    返回:
    - list: 最短路径节点ID列表，None表示无路径
    """
    if start_node not in graph.nodes or goal_node not in graph.nodes:
        return None
    
    # 如果起点和终点相同，直接返回
    if start_node == goal_node:
        return [start_node]
    
    # 初始化开放列表和关闭列表
    open_list = [(0, start_node)]  # (f_score, node)
    closed_set = set()
    
    # 记录到达每个节点的最小代价
    g_score = {node: float('inf') for node in graph.nodes}
    g_score[start_node] = 0
    
    # 记录到达每个节点的前一个节点
    came_from = {}
    
    # 获取节点坐标用于计算启发函数
    start_coords = get_node_coordinates(start_node)
    goal_coords = get_node_coordinates(goal_node)
    
    while open_list:
        # 获取f_score最小的节点
        _, current = heapq.heappop(open_list)
        
        if current == goal_node:
            # 重建路径
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start_node)
            return path[::-1]  # 反转路径
        
        closed_set.add(current)
        
        # 遍历当前节点的所有邻居
        for neighbor in graph.neighbors(current):
            if neighbor in closed_set:
                continue
            
            # 获取边权重（距离）
            if graph.has_edge(current, neighbor):
                edge_weight = graph[current][neighbor].get(weight, 1)
            else:
                continue
            
            # 计算从起点经过当前节点到邻居的代价
            tentative_g = g_score[current] + edge_weight
            
            if tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                
                # 计算启发函数值（使用Haversine距离）
                neighbor_coords = get_node_coordinates(neighbor)
                h_score = calculate_haversine_distance(
                    neighbor_coords[0], neighbor_coords[1],
                    goal_coords[0], goal_coords[1]
                )
                
                f_score = tentative_g + h_score
                
                # 如果邻居不在开放列表中，添加它
                if not any(neighbor == node for _, node in open_list):
                    heapq.heappush(open_list, (f_score, neighbor))
    
    return None  # 没有找到路径

def shortest_path(graph, start_node, goal_node, weight='weight'):
    """
    计算最短路径
    
    参数:
    - graph: NetworkX图对象
    - start_node: 起始节点ID
    - goal_node: 目标节点ID
    - weight: 边权重属性名
    
    返回:
    - list: 最短路径节点ID列表
    """
    try:
        # 首先尝试使用A*算法
        path = a_star_search(graph, start_node, goal_node, weight)
        
        # 如果A*失败，使用NetworkX内置的Dijkstra算法
        if path is None:
            path = nx.shortest_path(graph, source=start_node, target=goal_node, weight=weight)
        
        return path
    except nx.NetworkXNoPath:
        return None
    except Exception:
        return None

def shortest_path_length(graph, start_node, goal_node, weight='weight'):
    """
    计算最短路径长度
    
    参数:
    - graph: NetworkX图对象
    - start_node: 起始节点ID
    - goal_node: 目标节点ID
    - weight: 边权重属性名
    
    返回:
    - float: 最短路径长度，None表示无路径
    """
    try:
        return nx.shortest_path_length(graph, source=start_node, target=goal_node, weight=weight)
    except nx.NetworkXNoPath:
        return None
    except Exception:
        return None

def calculate_path_distance(graph, path, weight='weight'):
    """
    计算路径总距离
    
    参数:
    - graph: NetworkX图对象
    - path: 路径节点ID列表
    - weight: 边权重属性名
    
    返回:
    - float: 路径总距离
    """
    if not path or len(path) < 2:
        return 0
    
    total_distance = 0
    for i in range(len(path) - 1):
        if graph.has_edge(path[i], path[i+1]):
            edge_weight = graph[path[i]][path[i+1]].get(weight, 1)
            total_distance += edge_weight
    
    return total_distance

def find_nearest_node(graph, lat, lon):
    """
    找到离给定经纬度最近的节点
    
    参数:
    - graph: NetworkX图对象
    - lat: 纬度
    - lon: 经度
    
    返回:
    - tuple: (最近节点ID, 距离)
    """
    min_distance = float('inf')
    nearest_node = None
    
    for node in graph.nodes:
        node_lat, node_lon = get_node_coordinates(node)
        if node_lat is None or node_lon is None:
            continue
            
        distance = calculate_haversine_distance(lat, lon, node_lat, node_lon)
        if distance < min_distance:
            min_distance = distance
            nearest_node = node
    
    return nearest_node, min_distance

def find_nearest_charging_station(vehicle, graph, charging_stations):
    """
    找到离车辆最近的充电站
    
    参数:
    - vehicle: 车辆对象
    - graph: NetworkX图对象
    - charging_stations: 充电站列表
    
    返回:
    - tuple: (最近充电站对象, 距离)
    """
    if not vehicle.current_location or not charging_stations:
        return None, float('inf')
    
    min_distance = float('inf')
    nearest_station = None
    
    for station in charging_stations:
        # 计算车辆到充电站的距离
        distance = shortest_path_length(graph, vehicle.current_location, station.node_id)
        
        if distance is not None and distance < min_distance:
            # 检查车辆是否有足够电量到达充电站
            if vehicle.can_reach(distance):
                min_distance = distance
                nearest_station = station
    
    return nearest_station, min_distance

def has_enough_battery(vehicle, distance_to_destination, destination_node, graph, charging_stations):
    """
    检查车辆是否有足够电量到达目的地，考虑是否需要充电
    
    参数:
    - vehicle: 车辆对象
    - distance_to_destination: 到目的地的距离
    - destination_node: 目的地节点ID
    - graph: NetworkX图对象
    - charging_stations: 充电站列表
    
    返回:
    - bool: 是否有足够电量
    - ChargingStation: 需要充电的充电站，None表示不需要充电
    """
    # 如果直接有足够电量到达目的地，返回True
    if vehicle.can_reach(distance_to_destination):
        return True, None
    
    # 查找途中最近的充电站
    nearest_station, distance_to_station = find_nearest_charging_station(vehicle, graph, charging_stations)
    
    if not nearest_station:
        return False, None
    
    # 计算从充电站到目的地的距离
    distance_from_station_to_destination = shortest_path_length(graph, nearest_station.node_id, destination_node)
    
    if distance_from_station_to_destination is None:
        return False, None
    
    # 检查是否有足够电量到达充电站
    if vehicle.can_reach(distance_to_station):
        return True, nearest_station
    
    return False, None

def find_optimal_charging_station(vehicle, graph, charging_stations, destination_node=None):
    """
    找到最优充电站，考虑距离、排队情况和充电速率
    
    参数:
    - vehicle: 车辆对象
    - graph: NetworkX图对象
    - charging_stations: 充电站列表
    - destination_node: 目的地节点ID（可选）
    
    返回:
    - tuple: (最优充电站对象, 到充电站的距离)
    """
    if not vehicle.current_location or not charging_stations:
        return None, float('inf')
    
    station_scores = []
    
    for station in charging_stations:
        # 计算到充电站的距离
        distance_to_station = shortest_path_length(graph, vehicle.current_location, station.node_id)
        
        if distance_to_station is None or not vehicle.can_reach(distance_to_station):
            continue
        
        # 计算充电站评分
        # 1. 距离因子（距离越近分数越高）
        distance_factor = 1000 / (distance_to_station + 100)  # 避免除以0
        
        # 2. 排队因子（排队车辆越少分数越高）
        queue_factor = max(0, 1 - (station.get_queue_length() / 10))  # 最多10辆车排队
        
        # 3. 充电速率因子（充电越快分数越高）
        rate_factor = station.charging_rate / 3.0  # 假设最高充电速率为3.0km/分钟
        
        # 4. 可用充电桩因子（越多越好）
        availability_factor = station.get_available_spots() / station.capacity
        
        # 5. 如果有目的地，考虑从充电站到目的地的距离
        destination_factor = 1.0
        if destination_node:
            distance_from_station = shortest_path_length(graph, station.node_id, destination_node)
            if distance_from_station:
                destination_factor = 1000 / (distance_from_station + 100)
        
        # 综合评分
        score = (distance_factor * 0.3 + 
                 queue_factor * 0.2 + 
                 rate_factor * 0.2 + 
                 availability_factor * 0.1 + 
                 destination_factor * 0.2)
        
        station_scores.append((score, station, distance_to_station))
    
    if not station_scores:
        return None, float('inf')
    
    # 选择评分最高的充电站
    station_scores.sort(key=lambda x: x[0], reverse=True)
    return station_scores[0][1], station_scores[0][2]

if __name__ == "__main__":
    # 测试路径规划算法
    from data.guangzhou_map import create_guangzhou_graph
    
    # 创建地图
    G = create_guangzhou_graph()
    
    # 测试A*算法
    start_node = 1  # 天河体育中心
    goal_node = 10  # 广州塔
    
    print(f"测试从节点{start_node}到节点{goal_node}的最短路径:")
    
    # 使用A*算法
    path = a_star_search(G, start_node, goal_node)
    if path:
        print(f"A*算法找到路径: {path}")
        print(f"路径长度: {calculate_path_distance(G, path)} 米")
    else:
        print("A*算法未找到路径")
    
    # 使用NetworkX内置算法
    try:
        nx_path = nx.shortest_path(G, source=start_node, target=goal_node, weight='weight')
        print(f"NetworkX最短路径: {nx_path}")
        print(f"路径长度: {nx.shortest_path_length(G, source=start_node, target=goal_node, weight='weight')} 米")
    except nx.NetworkXNoPath:
        print("NetworkX未找到路径")
    
    # 测试充电站查找
    from models.vehicle import Vehicle
    from models.charging_station import create_charging_stations_from_data
    
    # 创建测试车辆
    vehicle = Vehicle(
        vehicle_id=1,
        capacity=1000,
        max_battery=200,
        current_battery=50,  # 低电量
        current_location=1
    )
    
    # 创建充电站
    stations = create_charging_stations_from_data()
    
    # 查找最近充电站
    nearest_station, distance = find_nearest_charging_station(vehicle, G, stations)
    if nearest_station:
        print(f"\n离车辆最近的充电站: ID={nearest_station.id}, 距离={distance:.1f}米")
    
    # 查找最优充电站
    optimal_station, distance = find_optimal_charging_station(vehicle, G, stations, goal_node)
    if optimal_station:
        print(f"最优充电站: ID={optimal_station.id}, 距离={distance:.1f}米")
        print(f"排队车辆: {optimal_station.get_queue_length()}, 可用充电桩: {optimal_station.get_available_spots()}")