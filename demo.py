"""
新能源物流车队协同调度系统演示版
简化版本，不依赖外部库，用于演示系统核心功能
"""

import os
import sys
import time
import random
import math
import json
from datetime import datetime
from collections import deque

class VehicleStatus:
    """车辆状态枚举"""
    IDLE = "idle"              # 空闲
    MOVING = "moving"          # 移动中
    CHARGING = "charging"      # 充电中
    DELIVERING = "delivering"  # 配送中
    COOPERATIVE = "cooperative" # 协同配送中
    RETURNING = "returning"    # 返回仓库中

class TaskStatus:
    """任务状态枚举"""
    PENDING = "pending"      # 待分配
    ASSIGNED = "assigned"    # 已分配
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    COOPERATIVE = "cooperative"  # 协同配送中

class Vehicle:
    """新能源物流车辆类"""
    def __init__(self, vehicle_id, capacity, max_battery, current_location=None):
        self.id = vehicle_id
        self.capacity = capacity
        self.max_battery = max_battery
        self.current_battery = max_battery
        self.current_location = current_location
        self.status = VehicleStatus.IDLE
        
        # 任务相关属性
        self.current_task = None
        self.schedule = []
        self.current_path = []
        self.path_progress = 0
        
        # 充电相关属性
        self.charging_station = None
        self.charge_start_time = None
        
        # 统计信息
        self.total_distance = 0
        self.total_tasks = 0
        self.total_charge_time = 0
        self.utilization_rate = 0
    
    def get_remaining_capacity(self):
        """获取剩余载重能力"""
        if self.current_task:
            return self.capacity - self.current_task.weight
        return self.capacity
    
    def get_remaining_battery(self):
        """获取剩余电量百分比"""
        return (self.current_battery / self.max_battery) * 100
    
    def is_battery_low(self, threshold=0.2):
        """检查电量是否低"""
        return self.get_remaining_battery() < threshold * 100
    
    def can_reach(self, distance):
        """检查是否有足够电量到达指定距离"""
        return self.current_battery >= distance
    
    def consume_battery(self, distance):
        """消耗电量"""
        self.current_battery = max(0, self.current_battery - distance)
        self.total_distance += distance
    
    def charge_battery(self, amount):
        """充电"""
        self.current_battery = min(self.max_battery, self.current_battery + amount)

class Task:
    """配送任务类"""
    def __init__(self, task_id, location, weight, start_time, deadline=None):
        self.id = task_id
        self.location = location
        self.weight = weight
        self.start_time = start_time
        self.deadline = deadline
        
        # 状态相关属性
        self.status = TaskStatus.PENDING
        self.assigned_vehicles = []
        
        # 完成相关属性
        self.completion_time = None
        self.total_distance = 0
        self.waiting_time = 0
        
        # 评分相关属性
        self.score = 0
        self.score_details = {}
    
    def assign_to_vehicle(self, vehicle):
        """将任务分配给车辆"""
        if vehicle not in self.assigned_vehicles:
            self.assigned_vehicles.append(vehicle)
        
        if len(self.assigned_vehicles) == 1:
            self.status = TaskStatus.ASSIGNED
        else:
            self.status = TaskStatus.COOPERATIVE
    
    def complete(self, completion_time):
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.completion_time = completion_time
        
        # 计算任务评分
        base_score = 100
        time_bonus = 50 if self.deadline and completion_time < self.deadline else 0
        distance_penalty = min(50, self.total_distance / 1000)
        weight_bonus = min(30, self.weight / 100)
        
        self.score = base_score + time_bonus - distance_penalty + weight_bonus
        return self.score

class ChargingStation:
    """充电站类"""
    def __init__(self, station_id, node_id, capacity, charging_rate):
        self.id = station_id
        self.node_id = node_id
        self.capacity = capacity
        self.charging_rate = charging_rate
        
        # 充电队列和占用状态
        self.queue = deque()
        self.occupied = []
        
        # 统计信息
        self.total_vehicles = 0
        self.total_charge_time = 0
        self.total_charge_amount = 0
    
    def add_vehicle(self, vehicle):
        """添加车辆到充电站"""
        if len(self.occupied) < self.capacity:
            self.occupied.append(vehicle)
            vehicle.status = VehicleStatus.CHARGING
            vehicle.charging_station = self
            return True
        
        self.queue.append(vehicle)
        return False
    
    def remove_vehicle(self, vehicle):
        """从充电站移除车辆"""
        if vehicle in self.occupied:
            self.occupied.remove(vehicle)
            vehicle.status = VehicleStatus.IDLE
            vehicle.charging_station = None
            self.total_vehicles += 1
            
            # 处理队列
            if self.queue:
                next_vehicle = self.queue.popleft()
                self.occupied.append(next_vehicle)
                next_vehicle.status = VehicleStatus.CHARGING
                next_vehicle.charging_station = self
            return True
        return False

class GuangzhouMap:
    """广州市地图模型"""
    def __init__(self):
        # 简化的广州地图节点（主要地点）
        self.nodes = {
            1: {"name": "天河体育中心", "location": (23.135, 113.33)},
            2: {"name": "广州东站", "location": (23.13, 113.32)},
            3: {"name": "珠江新城", "location": (23.125, 113.34)},
            4: {"name": "广州天河CBD", "location": (23.14, 113.34)},
            5: {"name": "白云山南门", "location": (23.15, 113.32)},
            6: {"name": "北京路", "location": (23.12, 113.28)},
            7: {"name": "广州火车站", "location": (23.11, 113.27)},
            8: {"name": "中山纪念堂", "location": (23.125, 113.29)},
            9: {"name": "广州起义纪念馆", "location": (23.115, 113.28)},
            10: {"name": "广州塔", "location": (23.08, 113.31)},
            11: {"name": "琶洲会展中心", "location": (23.07, 113.32)},
            12: {"name": "海珠广场", "location": (23.09, 113.30)},
            13: {"name": "广州大学城", "location": (23.06, 113.30)},
            14: {"name": "上下九", "location": (23.10, 113.26)},
            15: {"name": "陈家祠", "location": (23.11, 113.25)},
            16: {"name": "沙面", "location": (23.09, 113.25)},
            100: {"name": "中央仓库", "location": (23.15, 113.35)}
        }
        
        # 简化的道路连接（邻接表）
        self.adjacency_list = {
            1: [(2, 1500), (3, 2000), (4, 1000), (6, 5000)],
            2: [(1, 1500), (8, 4000), (5, 3000)],
            3: [(1, 2000), (10, 3000), (4, 1500)],
            4: [(1, 1000), (3, 1500), (9, 4000),  (100, 2000)],
            5: [(2, 3000), (18, 10000)],
            6: [(1, 5000), (8, 2000), (12, 3000)],
            7: [(8, 2000), (14, 3000)],
            8: [(2, 4000), (6, 2000), (7, 2000), (15, 3000)],
            9: [(4, 4000), (15, 3000)],
            10: [(3, 3000), (11, 5000), (12, 5000)],
            11: [(10, 5000), (13, 6000)],
            12: [(6, 3000), (10, 5000), (16, 2000)],
            13: [(11, 6000), (21, 10000)],
            14: [(7, 3000), (15, 2000), (16, 2000)],
            15: [(8, 3000), (9, 3000), (14, 2000)],
            16: [(12, 2000), (14, 2000)],
            100: [(4, 2000), (20, 5000)]
        }
        
        # 充电站
        self.charging_stations = [
            ChargingStation(1, 1, 10, 2.0),    # 天河体育中心充电站
            ChargingStation(2, 3, 8, 2.0),     # 珠江新城充电站
            ChargingStation(3, 6, 6, 1.5),     # 北京路充电站
            ChargingStation(4, 10, 12, 2.5),   # 广州塔充电站
            ChargingStation(5, 14, 6, 1.5),    # 上下九充电站
            ChargingStation(6, 100, 5, 2.0)    # 仓库充电站
        ]
    
    def get_node_name(self, node_id):
        """获取节点名称"""
        return self.nodes.get(node_id, {}).get("name", f"节点{node_id}")
    
    def get_node_location(self, node_id):
        """获取节点位置"""
        return self.nodes.get(node_id, {}).get("location", (0, 0))
    
    def shortest_path(self, start_node, goal_node):
        """简化的最短路径算法（BFS）"""
        if start_node == goal_node:
            return [start_node]
        
        visited = {}
        queue = deque([start_node])
        visited[start_node] = None
        
        while queue:
            current = queue.popleft()
            
            for neighbor, _ in self.adjacency_list.get(current, []):
                if neighbor not in visited:
                    visited[neighbor] = current
                    queue.append(neighbor)
                    
                    if neighbor == goal_node:
                        # 重建路径
                        path = []
                        node = goal_node
                        while node:
                            path.append(node)
                            node = visited[node]
                        return path[::-1]
        
        return None
    
    def calculate_distance(self, path):
        """计算路径距离"""
        if not path or len(path) < 2:
            return 0
        
        total_distance = 0
        for i in range(len(path) - 1):
            for neighbor, distance in self.adjacency_list.get(path[i], []):
                if neighbor == path[i + 1]:
                    total_distance += distance
                    break
        
        return total_distance

class SchedulingStrategy:
    """调度策略基类"""
    def __init__(self, name):
        self.name = name
    
    def select_task(self, vehicle, tasks, map_model):
        """为车辆选择任务"""
        raise NotImplementedError

class NearestTaskStrategy(SchedulingStrategy):
    """最近任务优先策略"""
    def __init__(self):
        super().__init__("最近任务优先")
    
    def select_task(self, vehicle, tasks, map_model):
        if not tasks or not vehicle.current_location:
            return None
        
        task_distances = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue
            
            path = map_model.shortest_path(vehicle.current_location, task.location)
            if path:
                distance = map_model.calculate_distance(path)
                if vehicle.can_reach(distance):
                    task_distances.append((distance, task))
        
        if not task_distances:
            return None
        
        task_distances.sort(key=lambda x: x[0])
        return task_distances[0][1]

class MaxWeightTaskStrategy(SchedulingStrategy):
    """最大任务优先策略"""
    def __init__(self):
        super().__init__("最大任务优先")
    
    def select_task(self, vehicle, tasks, map_model):
        if not tasks or not vehicle.current_location:
            return None
        
        feasible_tasks = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue
            
            path = map_model.shortest_path(vehicle.current_location, task.location)
            if path:
                distance = map_model.calculate_distance(path)
                if vehicle.can_reach(distance):
                    feasible_tasks.append((task.weight, task))
        
        if not feasible_tasks:
            return None
        
        feasible_tasks.sort(key=lambda x: x[0], reverse=True)
        return feasible_tasks[0][1]

class Simulator:
    """新能源物流车队调度模拟器"""
    def __init__(self, fleet_size=10, simulation_time=3600*8, task_rate=0.01, strategy_name="balanced"):
        # 初始化地图
        self.map = GuangzhouMap()
        
        # 仓库位置
        self.depot_id = 100
        
        # 初始化车队
        self.fleet = self._create_fleet(fleet_size)
        
        # 初始化任务列表
        self.tasks = []
        self.completed_tasks = []
        self.failed_tasks = []
        
        # 模拟参数
        self.simulation_time = simulation_time
        self.current_time = 0
        self.time_step = 10
        self.task_rate = task_rate
        self.task_id_counter = 0
        
        # 调度策略
        self.strategy = self._create_strategy(strategy_name)
        
        # 统计信息
        self.total_score = 0
        self.total_tasks = 0
        self.completed_task_count = 0
        self.failed_task_count = 0
    
    def _create_fleet(self, fleet_size):
        """创建车队"""
        fleet = []
        
        for i in range(fleet_size):
            if i < 3:  # 3辆大型车
                vehicle = Vehicle(
                    vehicle_id=i+1,
                    capacity=1500,
                    max_battery=200,
                    current_location=self.depot_id
                )
            elif i < 7:  # 4辆中型车
                vehicle = Vehicle(
                    vehicle_id=i+1,
                    capacity=800,
                    max_battery=150,
                    current_location=self.depot_id
                )
            else:  # 小型车
                vehicle = Vehicle(
                    vehicle_id=i+1,
                    capacity=500,
                    max_battery=100,
                    current_location=self.depot_id
                )
            fleet.append(vehicle)
        
        return fleet
    
    def _create_strategy(self, strategy_name):
        """创建调度策略"""
        strategies = {
            "nearest": NearestTaskStrategy,
            "max_weight": MaxWeightTaskStrategy
        }
        
        if strategy_name.lower() in strategies:
            return strategies[strategy_name.lower()]()
        else:
            return NearestTaskStrategy()  # 默认使用最近任务优先
    
    def _generate_task(self):
        """生成新任务"""
        if random.random() > self.task_rate:
            return None
        
        # 随机选择任务地点（排除仓库）
        locations = list(self.map.nodes.keys())
        locations.remove(self.depot_id)
        location = random.choice(locations)
        
        # 随机生成货物重量
        weight = random.uniform(10, 1000)
        weight = round(weight, 2)
        
        # 生成截止时间
        deadline = None
        if random.random() < 0.7:
            deadline_delta = random.randint(3600, 21600)
            deadline = self.current_time + deadline_delta
        
        # 创建任务
        task = Task(
            task_id=self.task_id_counter,
            location=location,
            weight=weight,
            start_time=self.current_time,
            deadline=deadline
        )
        
        self.task_id_counter += 1
        return task
    
    def _update_vehicle_states(self):
        """更新车辆状态"""
        for vehicle in self.fleet:
            if vehicle.status == VehicleStatus.MOVING and vehicle.current_path:
                # 模拟车辆移动
                vehicle.path_progress += 1
                
                if vehicle.path_progress >= len(vehicle.current_path) - 1:
                    # 到达目的地
                    if vehicle.current_task:
                        # 完成任务
                        task = vehicle.current_task
                        task.complete(self.current_time)
                        self.completed_tasks.append(task)
                        self.tasks.remove(task)
                        self.completed_task_count += 1
                        
                        # 更新统计
                        self.total_score += task.score
                        
                        # 重置车辆状态
                        vehicle.current_task = None
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
                        vehicle.path_progress = 0
                        vehicle.total_tasks += 1
                    else:
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
                        vehicle.path_progress = 0
            
            elif vehicle.status == VehicleStatus.CHARGING:
                # 模拟充电
                charge_amount = (vehicle.charging_station.charging_rate * self.time_step) / 60
                vehicle.charge_battery(charge_amount)
                
                # 检查是否充满
                if vehicle.current_battery >= vehicle.max_battery * 0.95:
                    if vehicle.charging_station:
                        vehicle.charging_station.remove_vehicle(vehicle)
                        vehicle.status = VehicleStatus.IDLE
    
    def _check_task_deadlines(self):
        """检查任务截止时间"""
        for task in self.tasks[:]:
            if task.deadline and self.current_time > task.deadline:
                task.status = TaskStatus.FAILED
                self.failed_tasks.append(task)
                self.tasks.remove(task)
                self.failed_task_count += 1
                
                # 失败扣分
                self.total_score -= 100
    
    def _allocate_tasks(self):
        """分配任务"""
        pending_tasks = [t for t in self.tasks if t.status == TaskStatus.PENDING]
        idle_vehicles = [v for v in self.fleet if v.status == VehicleStatus.IDLE]
        
        for vehicle in idle_vehicles:
            task = self.strategy.select_task(vehicle, pending_tasks, self.map)
            if task:
                # 分配任务
                task.assign_to_vehicle(vehicle)
                vehicle.current_task = task
                vehicle.status = VehicleStatus.ASSIGNED
                
                # 规划路径
                path = self.map.shortest_path(vehicle.current_location, task.location)
                if path:
                    vehicle.current_path = path
                    vehicle.status = VehicleStatus.MOVING
                    vehicle.path_progress = 0
                    
                    # 计算距离并消耗电量
                    distance = self.map.calculate_distance(path)
                    task.total_distance = distance
                    vehicle.consume_battery(distance)
                    
                    # 更新车辆位置
                    vehicle.current_location = path[0]
                    
                    # 从待分配列表移除
                    pending_tasks.remove(task)
    
    def _manage_charging(self):
        """管理充电"""
        for vehicle in self.fleet:
            if vehicle.status == VehicleStatus.IDLE and vehicle.is_battery_low():
                # 找到最近的充电站
                nearest_station = None
                min_distance = float('inf')
                
                for station in self.map.charging_stations:
                    path = self.map.shortest_path(vehicle.current_location, station.node_id)
                    if path:
                        distance = self.map.calculate_distance(path)
                        if distance < min_distance and vehicle.can_reach(distance):
                            min_distance = distance
                            nearest_station = station
                
                if nearest_station:
                    # 前往充电站
                    path = self.map.shortest_path(vehicle.current_location, nearest_station.node_id)
                    if path:
                        vehicle.current_path = path
                        vehicle.status = VehicleStatus.MOVING
                        vehicle.path_progress = 0
                        
                        # 消耗电量
                        distance = self.map.calculate_distance(path)
                        vehicle.consume_battery(distance)
                        
                        # 更新位置
                        vehicle.current_location = path[0]
                        
                        # 添加到充电站
                        nearest_station.add_vehicle(vehicle)
    
    def run(self, verbose=True):
        """运行模拟"""
        print(f"开始模拟...")
        print(f"模拟时间: {self.simulation_time/3600:.1f}小时")
        print(f"车队规模: {len(self.fleet)}辆")
        print(f"调度策略: {self.strategy.name}")
        print("-" * 50)
        
        start_time = time.time()
        
        # 模拟主循环
        while self.current_time < self.simulation_time:
            # 生成新任务
            new_task = self._generate_task()
            if new_task:
                self.tasks.append(new_task)
                self.total_tasks += 1
            
            # 更新车辆状态
            self._update_vehicle_states()
            
            # 检查任务截止时间
            self._check_task_deadlines()
            
            # 分配任务
            self._allocate_tasks()
            
            # 管理充电
            self._manage_charging()
            
            # 打印进度
            if verbose and self.current_time % 3600 == 0:
                hours = self.current_time // 3600
                print(f"时间: {hours}小时 | "
                      f"待处理: {len(self.tasks)} | "
                      f"已完成: {len(self.completed_tasks)} | "
                      f"失败: {len(self.failed_tasks)} | "
                      f"总分: {self.total_score}")
            
            # 推进时间
            self.current_time += self.time_step
        
        elapsed_time = time.time() - start_time
        
        # 打印总结
        print("-" * 50)
        print("模拟完成!")
        print(f"总耗时: {elapsed_time:.2f}秒")
        print(f"总任务数: {self.total_tasks}")
        print(f"完成任务: {self.completed_task_count} ({self.completed_task_count/self.total_tasks*100:.1f}%)")
        print(f"失败任务: {self.failed_task_count} ({self.failed_task_count/self.total_tasks*100:.1f}%)")
        print(f"总评分: {self.total_score}")
        
        # 打印车辆统计
        print("\n车辆统计:")
        total_distance = sum(v.total_distance for v in self.fleet)
        avg_distance = total_distance / len(self.fleet)
        print(f"平均行驶距离: {avg_distance/1000:.1f}公里")
        
        # 打印充电站统计
        print("\n充电站统计:")
        total_charged = sum(s.total_vehicles for s in self.map.charging_stations)
        print(f"总充电车辆数: {total_charged}")
        
        return {
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_task_count,
            "failed_tasks": self.failed_task_count,
            "total_score": self.total_score,
            "average_distance": avg_distance,
            "total_charged_vehicles": total_charged
        }

def main():
    """主函数"""
    print("=" * 60)
    print("新能源物流车队协同调度系统 - 演示版")
    print("=" * 60)
    
    # 创建模拟器
    simulator = Simulator(
        fleet_size=10,
        simulation_time=3600*2,  # 2小时
        task_rate=0.02,
        strategy_name="nearest"
    )
    
    # 运行模拟
    results = simulator.run()
    
    print("\n模拟结果:")
    print(f"总任务数: {results['total_tasks']}")
    print(f"完成率: {results['completed_tasks']/results['total_tasks']*100:.1f}%")
    print(f"总评分: {results['total_score']}")
    print(f"平均行驶距离: {results['average_distance']/1000:.1f}公里")
    
    # 保存结果
    output_dir = "demo_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = os.path.join(output_dir, f'results_{timestamp}.json')
    
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存到: {results_file}")
    
    print("\n系统功能说明:")
    print("1. 车队管理: 模拟10辆不同类型的新能源车辆")
    print("2. 任务生成: 动态生成配送任务，包含位置、重量和截止时间")
    print("3. 路径规划: 基于简化的广州市地图进行最短路径规划")
    print("4. 充电管理: 车辆电量低时自动前往充电站充电")
    print("5. 调度策略: 实现了'最近任务优先'和'最大任务优先'两种策略")
    print("6. 评分系统: 根据任务完成时间、距离等计算收益/扣分")
    
    print("\n要运行完整版本，请安装所需依赖:")
    print("pip install -r requirements.txt")
    print("然后运行: python main.py --visualize --show-map")

if __name__ == "__main__":
    main()