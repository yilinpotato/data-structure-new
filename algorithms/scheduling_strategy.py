"""
调度策略模块
实现多种任务分配策略
"""

import math
import random
import heapq
from algorithms.path_planning import (
    shortest_path, shortest_path_length, calculate_path_distance,
    has_enough_battery, find_optimal_charging_station
)
from models.task import TaskStatus
from models.vehicle import VehicleStatus

class SchedulingStrategy:
    """调度策略基类"""
    
    def __init__(self, name):
        self.name = name
    
    def select_task(self, vehicle, tasks, graph, charging_stations):
        """
        为车辆选择任务
        
        参数:
        - vehicle: 车辆对象
        - tasks: 任务列表
        - graph: 道路网络图
        - charging_stations: 充电站列表
        
        返回:
        - Task: 选中的任务，None表示没有合适的任务
        """
        raise NotImplementedError
    
    def allocate_tasks(self, vehicles, tasks, graph, charging_stations):
        """
        分配任务给车队
        
        参数:
        - vehicles: 车辆列表
        - tasks: 任务列表
        - graph: 道路网络图
        - charging_stations: 充电站列表
        
        返回:
        - dict: 任务分配结果 {vehicle: task}
        """
        allocation = {}
        
        # 获取空闲车辆
        idle_vehicles = [v for v in vehicles if v.status == VehicleStatus.IDLE]
        
        # 过滤待分配任务
        pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]
        
        # 为每辆车分配任务
        for vehicle in idle_vehicles:
            task = self.select_task(vehicle, pending_tasks, graph, charging_stations)
            if task:
                allocation[vehicle] = task
                pending_tasks.remove(task)
        
        return allocation

class NearestTaskStrategy(SchedulingStrategy):
    """最近任务优先策略"""
    
    def __init__(self):
        super().__init__("最近任务优先")
    
    def select_task(self, vehicle, tasks, graph, charging_stations):
        if not tasks or not vehicle.current_location:
            return None
        
        # 计算车辆到每个任务地点的距离
        task_distances = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue  # 超过载重限制
            
            # 计算距离
            distance = shortest_path_length(graph, vehicle.current_location, task.location)
            if distance is None:
                continue
            
            # 检查电量是否足够
            enough_battery, _ = has_enough_battery(
                vehicle, distance, task.location, graph, charging_stations
            )
            
            if enough_battery:
                task_distances.append((distance, task))
        
        if not task_distances:
            return None
        
        # 选择最近的任务
        task_distances.sort(key=lambda x: x[0])
        return task_distances[0][1]

class MaxWeightTaskStrategy(SchedulingStrategy):
    """最大任务优先策略"""
    
    def __init__(self):
        super().__init__("最大任务优先")
    
    def select_task(self, vehicle, tasks, graph, charging_stations):
        if not tasks or not vehicle.current_location:
            return None
        
        # 筛选车辆能够执行的任务
        feasible_tasks = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue  # 超过载重限制
            
            # 计算距离
            distance = shortest_path_length(graph, vehicle.current_location, task.location)
            if distance is None:
                continue
            
            # 检查电量是否足够
            enough_battery, _ = has_enough_battery(
                vehicle, distance, task.location, graph, charging_stations
            )
            
            if enough_battery:
                feasible_tasks.append((task.weight, task))
        
        if not feasible_tasks:
            return None
        
        # 选择重量最大的任务
        feasible_tasks.sort(key=lambda x: x[0], reverse=True)
        return feasible_tasks[0][1]

class UrgencyTaskStrategy(SchedulingStrategy):
    """紧急任务优先策略"""
    
    def __init__(self):
        super().__init__("紧急任务优先")
    
    def select_task(self, vehicle, tasks, graph, charging_stations):
        if not tasks or not vehicle.current_location:
            return None
        
        # 计算每个任务的紧急度
        current_time = 0  # 应该从模拟器获取
        urgent_tasks = []
        
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue  # 超过载重限制
            
            # 计算距离
            distance = shortest_path_length(graph, vehicle.current_location, task.location)
            if distance is None:
                continue
            
            # 检查电量是否足够
            enough_battery, _ = has_enough_battery(
                vehicle, distance, task.location, graph, charging_stations
            )
            
            if not enough_battery:
                continue
            
            # 计算紧急度分数
            urgency_score = 0
            
            if task.deadline:
                # 剩余时间越少，紧急度越高
                remaining_time = task.deadline - current_time
                if remaining_time > 0:
                    urgency_score = 10000 / remaining_time  # 剩余时间的倒数
                else:
                    urgency_score = 1000  # 已超时，非常紧急
            else:
                # 没有截止时间的任务，给予基础分数
                urgency_score = 10
            
            # 考虑距离因素（距离越近，紧急度相对提高）
            urgency_score = urgency_score * (1000 / (distance + 100))
            
            urgent_tasks.append((-urgency_score, task))  # 负号用于最小堆排序
        
        if not urgent_tasks:
            return None
        
        # 使用最小堆选择紧急度最高的任务
        heapq.heapify(urgent_tasks)
        return heapq.heappop(urgent_tasks)[1]

class BalancedStrategy(SchedulingStrategy):
    """平衡策略：综合考虑距离、重量和紧急度"""
    
    def __init__(self):
        super().__init__("平衡策略")
    
    def select_task(self, vehicle, tasks, graph, charging_stations):
        if not tasks or not vehicle.current_location:
            return None
        
        # 计算每个任务的综合评分
        current_time = 0  # 应该从模拟器获取
        task_scores = []
        
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue  # 超过载重限制
            
            # 计算距离
            distance = shortest_path_length(graph, vehicle.current_location, task.location)
            if distance is None:
                continue
            
            # 检查电量是否足够
            enough_battery, _ = has_enough_battery(
                vehicle, distance, task.location, graph, charging_stations
            )
            
            if not enough_battery:
                continue
            
            # 1. 距离分数（距离越近分数越高）
            distance_score = 1000 / (distance + 100)
            
            # 2. 重量分数（重量越大分数越高）
            weight_score = min(100, task.weight / 10)
            
            # 3. 紧急度分数
            urgency_score = 0
            if task.deadline:
                remaining_time = task.deadline - current_time
                if remaining_time > 0:
                    urgency_score = 5000 / remaining_time
                else:
                    urgency_score = 500
            
            # 综合评分（加权平均）
            total_score = (distance_score * 0.3 + 
                          weight_score * 0.3 + 
                          urgency_score * 0.4)
            
            task_scores.append((-total_score, task))  # 负号用于最小堆排序
        
        if not task_scores:
            return None
        
        # 使用最小堆选择评分最高的任务
        heapq.heapify(task_scores)
        return heapq.heappop(task_scores)[1]

def cooperative_task_allocation(vehicles, tasks, graph, charging_stations):
    """
    多车辆协同任务分配
    
    参数:
    - vehicles: 车辆列表
    - tasks: 任务列表
    - graph: 道路网络图
    - charging_stations: 充电站列表
    
    返回:
    - dict: 协同任务分配结果 {task: [vehicles]}
    """
    cooperation_allocations = {}
    
    # 筛选需要多车协同的大任务
    large_tasks = [task for task in tasks if 
                  task.status == TaskStatus.PENDING and 
                  task.weight > max(v.capacity for v in vehicles)]
    
    # 获取空闲车辆
    idle_vehicles = [v for v in vehicles if v.status == VehicleStatus.IDLE]
    
    for task in large_tasks:
        # 计算需要的车辆数量
        max_capacity = max(v.capacity for v in vehicles)
        required_vehicles = math.ceil(task.weight / max_capacity)
        
        if len(idle_vehicles) >= required_vehicles:
            # 计算每辆车到任务地点的距离
            vehicle_distances = []
            for vehicle in idle_vehicles:
                distance = shortest_path_length(graph, vehicle.current_location, task.location)
                if distance is not None:
                    # 检查电量是否足够
                    enough_battery, _ = has_enough_battery(
                        vehicle, distance, task.location, graph, charging_stations
                    )
                    
                    if enough_battery:
                        vehicle_distances.append((distance, vehicle))
            
            # 选择最近的几辆车
            if len(vehicle_distances) >= required_vehicles:
                vehicle_distances.sort(key=lambda x: x[0])
                selected_vehicles = [v for _, v in vehicle_distances[:required_vehicles]]
                
                # 分配任务
                cooperation_allocations[task] = selected_vehicles
                
                # 更新任务和车辆状态
                task.status = TaskStatus.COOPERATIVE
                for vehicle in selected_vehicles:
                    vehicle.status = VehicleStatus.COOPERATIVE
                    vehicle.current_task = task
                    idle_vehicles.remove(vehicle)
    
    return cooperation_allocations

def charging_strategy(vehicles, charging_stations, graph, current_time):
    """
    充电策略：决定哪些车辆需要充电以及选择哪个充电站
    
    参数:
    - vehicles: 车辆列表
    - charging_stations: 充电站列表
    - graph: 道路网络图
    - current_time: 当前时间
    
    返回:
    - dict: 充电分配结果 {vehicle: station}
    """
    charging_allocations = {}
    
    # 检查每辆车的电量
    for vehicle in vehicles:
        # 只有空闲或正在移动的车辆需要考虑充电
        if vehicle.status not in [VehicleStatus.IDLE, VehicleStatus.MOVING]:
            continue
        
        # 如果电量低于20%，需要充电
        if vehicle.is_battery_low(threshold=0.2):
            # 找到最优充电站
            station, distance = find_optimal_charging_station(vehicle, graph, charging_stations)
            
            if station:
                charging_allocations[vehicle] = station
    
    return charging_allocations

def create_strategy(strategy_name):
    """
    创建调度策略实例
    
    参数:
    - strategy_name: 策略名称
    
    返回:
    - SchedulingStrategy: 调度策略实例
    """
    strategies = {
        "nearest": NearestTaskStrategy,
        "max_weight": MaxWeightTaskStrategy,
        "urgency": UrgencyTaskStrategy,
        "balanced": BalancedStrategy
    }
    
    if strategy_name.lower() in strategies:
        return strategies[strategy_name.lower()]()
    else:
        # 默认使用平衡策略
        print(f"未知策略: {strategy_name}，使用默认平衡策略")
        return BalancedStrategy()

if __name__ == "__main__":
    # 测试调度策略
    from data.guangzhou_map import create_guangzhou_graph, get_depot_location
    from models.vehicle import Vehicle, VehicleStatus, create_default_fleet
    from models.task import Task, TaskStatus
    from models.charging_station import create_charging_stations_from_data
    
    # 创建地图
    G = create_guangzhou_graph()
    
    # 获取仓库位置
    depot_id, _, _, _ = get_depot_location()
    
    # 创建车队
    fleet = create_default_fleet(depot_id, fleet_size=5)
    
    # 创建充电站
    stations = create_charging_stations_from_data()
    
    # 创建测试任务
    tasks = [
        Task(task_id=1, location=1, weight=500, start_time=0, deadline=3600),  # 天河体育中心
        Task(task_id=2, location=3, weight=800, start_time=0, deadline=7200),  # 珠江新城
        Task(task_id=3, location=10, weight=1200, start_time=0, deadline=5400), # 广州塔
        Task(task_id=4, location=6, weight=300, start_time=0, deadline=10800), # 北京路
        Task(task_id=5, location=20, weight=2000, start_time=0, deadline=9000)  # 科学城（大型任务）
    ]
    
    # 测试不同策略
    strategies = [
        NearestTaskStrategy(),
        MaxWeightTaskStrategy(),
        UrgencyTaskStrategy(),
        BalancedStrategy()
    ]
    
    print("测试不同调度策略:")
    print("-" * 50)
    
    for strategy in strategies:
        print(f"\n{strategy.name}:")
        
        # 复制车辆和任务以避免相互影响
        test_vehicles = [v.copy() for v in fleet]
        test_tasks = [t.copy() for t in tasks]
        
        # 分配任务
        allocation = strategy.allocate_tasks(test_vehicles, test_tasks, G, stations)
        
        # 打印分配结果
        for vehicle, task in allocation.items():
            distance = shortest_path_length(G, vehicle.current_location, task.location)
            print(f"  车辆{vehicle.id} -> 任务{task.id} (位置:节点{task.location}, 重量:{task.weight}kg, 距离:{distance}m)")
    
    # 测试协同任务分配
    print("\n测试协同任务分配:")
    print("-" * 50)
    
    # 重置车辆和任务
    test_vehicles = [v.copy() for v in fleet]
    test_tasks = [t.copy() for t in tasks]
    
    # 只保留大型任务
    large_task = next(t for t in test_tasks if t.id == 5)
    test_tasks = [large_task]
    
    # 分配协同任务
    cooperation = cooperative_task_allocation(test_vehicles, test_tasks, G, stations)
    
    for task, vehicles in cooperation.items():
        print(f"  任务{task.id} (重量:{task.weight}kg) 需要 {len(vehicles)} 辆车协同完成:")
        for vehicle in vehicles:
            distance = shortest_path_length(G, vehicle.current_location, task.location)
            print(f"    - 车辆{vehicle.id} (载重:{vehicle.capacity}kg, 距离:{distance}m)")
    
    # 测试充电策略
    print("\n测试充电策略:")
    print("-" * 50)
    
    # 设置一辆车电量低
    test_vehicles[0].current_battery = 30  # 30km，低于20%阈值
    
    # 充电分配
    charging = charging_strategy(test_vehicles, stations, G, 0)
    
    for vehicle, station in charging.items():
        distance = shortest_path_length(G, vehicle.current_location, station.node_id)
        print(f"  车辆{vehicle.id} (电量:{vehicle.current_battery}/{vehicle.max_battery}km) "
              f"-> 充电站{station.id} (节点{station.node_id}, 距离:{distance}m)")