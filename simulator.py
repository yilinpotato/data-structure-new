import random
import math
from collections import deque

class VehicleStatus:
    IDLE = "idle"
    MOVING = "moving"
    CHARGING = "charging"
    DELIVERING = "delivering"
    COOPERATIVE = "cooperative"
    RETURNING = "returning"

class TaskStatus:
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    COOPERATIVE = "cooperative"

BATTERY_PER_KM = 0.3
SPEED_KM_PER_STEP = 0.5

class Vehicle:
    def __init__(self, vehicle_id, capacity, max_battery, current_location=None):
        self.id = vehicle_id
        self.capacity = capacity
        self.max_battery = max_battery
        self.current_battery = max_battery
        self.current_location = current_location
        self.status = VehicleStatus.IDLE
        
        self.current_task = None
        self.schedule = []
        self.current_path = []
        self.path_progress = 0
        self.distance_remaining = 0
        self.total_path_distance = 0
        
        self.charging_station = None
        self.charge_start_time = None
        
        self.total_distance = 0
        self.total_tasks = 0
        self.total_charge_time = 0
    
    def get_remaining_capacity(self):
        if self.current_task:
            return self.capacity - self.current_task.weight
        return self.capacity
    
    def get_remaining_battery(self):
        return (self.current_battery / self.max_battery) * 100
    
    def is_battery_low(self, threshold=0.2):
        return self.get_remaining_battery() < threshold * 100
    
    def battery_needed(self, distance_m):
        return (distance_m / 1000.0) * BATTERY_PER_KM
    
    def can_reach(self, distance_m):
        needed = self.battery_needed(distance_m)
        return self.current_battery >= needed
    
    def consume_battery(self, distance_m):
        consumed = self.battery_needed(distance_m)
        self.current_battery = max(0, self.current_battery - consumed)
        self.total_distance += distance_m
    
    def charge_battery(self, amount):
        self.current_battery = min(self.max_battery, self.current_battery + amount)

class Task:
    def __init__(self, task_id, location, weight, start_time, deadline=None):
        self.id = task_id
        self.location = location
        self.weight = weight
        self.start_time = start_time
        self.deadline = deadline
        
        self.status = TaskStatus.PENDING
        self.assigned_vehicles = []
        
        self.completion_time = None
        self.total_distance = 0
        self.waiting_time = 0
        
        self.score = 0
    
    def assign_to_vehicle(self, vehicle):
        if vehicle not in self.assigned_vehicles:
            self.assigned_vehicles.append(vehicle)
        
        if len(self.assigned_vehicles) == 1:
            self.status = TaskStatus.ASSIGNED
        else:
            self.status = TaskStatus.COOPERATIVE
    
    def complete(self, completion_time):
        self.status = TaskStatus.COMPLETED
        self.completion_time = completion_time
        
        base_score = 100
        time_bonus = 50 if self.deadline and completion_time < self.deadline else 0
        distance_penalty = min(50, self.total_distance / 1000)
        weight_bonus = min(30, self.weight / 100)
        
        self.score = base_score + time_bonus - distance_penalty + weight_bonus
        return self.score

class ChargingStation:
    def __init__(self, station_id, node_id, capacity, charging_rate):
        self.id = station_id
        self.node_id = node_id
        self.capacity = capacity
        self.charging_rate = charging_rate
        
        self.queue = deque()
        self.occupied = []
        
        self.total_vehicles = 0
        self.total_charge_time = 0
        self.total_charge_amount = 0
    
    def add_vehicle(self, vehicle):
        if len(self.occupied) < self.capacity:
            self.occupied.append(vehicle)
            vehicle.status = VehicleStatus.CHARGING
            vehicle.charging_station = self
            return True
        
        self.queue.append(vehicle)
        return False
    
    def remove_vehicle(self, vehicle):
        if vehicle in self.occupied:
            self.occupied.remove(vehicle)
            vehicle.status = VehicleStatus.IDLE
            vehicle.charging_station = None
            self.total_vehicles += 1
            
            if self.queue:
                next_vehicle = self.queue.popleft()
                self.occupied.append(next_vehicle)
                next_vehicle.status = VehicleStatus.CHARGING
                next_vehicle.charging_station = self
            return True
        return False

class GuangzhouMap:
    def __init__(self):
        self.nodes = {
            1: {"name": "天河体育中心", "location": (23.1349, 113.3308), "pos": (400, 150)},
            2: {"name": "广州东站", "location": (23.1297, 113.3215), "pos": (380, 180)},
            3: {"name": "珠江新城", "location": (23.1233, 113.3394), "pos": (450, 200)},
            4: {"name": "天河CBD", "location": (23.1405, 113.3366), "pos": (420, 120)},
            5: {"name": "白云山南门", "location": (23.1520, 113.3240), "pos": (360, 80)},
            6: {"name": "北京路", "location": (23.1187, 113.2824), "pos": (280, 250)},
            7: {"name": "广州火车站", "location": (23.1066, 113.2658), "pos": (250, 300)},
            8: {"name": "中山纪念堂", "location": (23.1239, 113.2878), "pos": (320, 270)},
            9: {"name": "广州起义纪念馆", "location": (23.1153, 113.2785), "pos": (270, 280)},
            10: {"name": "广州塔", "location": (23.1060, 113.3245), "pos": (380, 380)},
            11: {"name": "琶洲会展中心", "location": (23.0669, 113.3350), "pos": (420, 420)},
            12: {"name": "海珠广场", "location": (23.0942, 113.2998), "pos": (340, 340)},
            13: {"name": "大学城", "location": (23.0569, 113.3237), "pos": (380, 480)},
            14: {"name": "上下九", "location": (23.1027, 113.2564), "pos": (220, 350)},
            15: {"name": "陈家祠", "location": (23.1120, 113.2518), "pos": (200, 320)},
            16: {"name": "沙面", "location": (23.0924, 113.2527), "pos": (200, 380)},
            100: {"name": "中央仓库", "location": (23.1550, 113.3500), "pos": (500, 100)}
        }
        
        self.adjacency_list = {
            1: [(2, 1500), (3, 2000), (4, 1000), (6, 5000)],
            2: [(1, 1500), (8, 4000), (5, 3000)],
            3: [(1, 2000), (10, 3000), (4, 1500)],
            4: [(1, 1000), (3, 1500), (100, 2000)],
            5: [(2, 3000)],
            6: [(1, 5000), (8, 2000), (12, 3000)],
            7: [(8, 2000), (14, 3000)],
            8: [(2, 4000), (6, 2000), (7, 2000), (15, 3000)],
            9: [(8, 2000), (15, 3000)],
            10: [(3, 3000), (11, 5000), (12, 5000)],
            11: [(10, 5000), (13, 6000)],
            12: [(6, 3000), (10, 5000), (16, 2000)],
            13: [(11, 6000)],
            14: [(7, 3000), (15, 2000), (16, 2000)],
            15: [(8, 3000), (14, 2000)],
            16: [(12, 2000), (14, 2000)],
            100: [(4, 2000)]
        }
        
        self.charging_stations = [
            ChargingStation(1, 1, 10, 20.0),
            ChargingStation(2, 3, 8, 20.0),
            ChargingStation(3, 6, 6, 15.0),
            ChargingStation(4, 10, 12, 25.0),
            ChargingStation(5, 14, 6, 15.0),
            ChargingStation(6, 100, 5, 20.0)
        ]
    
    def get_node_name(self, node_id):
        return self.nodes.get(node_id, {}).get("name", f"节点{node_id}")
    
    def get_node_location(self, node_id):
        return self.nodes.get(node_id, {}).get("location", (0, 0))
    
    def get_node_pos(self, node_id):
        return self.nodes.get(node_id, {}).get("pos", (0, 0))
    
    def shortest_path(self, start_node, goal_node):
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
                        path = []
                        node = goal_node
                        while node:
                            path.append(node)
                            node = visited[node]
                        return path[::-1]
        
        return None
    
    def calculate_distance(self, path):
        if not path or len(path) < 2:
            return 0
        
        total_distance = 0
        for i in range(len(path) - 1):
            for neighbor, distance in self.adjacency_list.get(path[i], []):
                if neighbor == path[i + 1]:
                    total_distance += distance
                    break
        
        return total_distance
    
    def get_edge_distance(self, from_node, to_node):
        for neighbor, distance in self.adjacency_list.get(from_node, []):
            if neighbor == to_node:
                return distance
        return 2000

class NearestTaskStrategy:
    def __init__(self):
        self.name = "最近任务优先"
    
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

class MaxWeightTaskStrategy:
    def __init__(self):
        self.name = "最大任务优先"
    
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

class UrgencyStrategy:
    def __init__(self):
        self.name = "紧急任务优先"
    
    def select_task(self, vehicle, tasks, map_model):
        if not tasks or not vehicle.current_location:
            return None
        
        urgent_tasks = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue
            
            path = map_model.shortest_path(vehicle.current_location, task.location)
            if path:
                distance = map_model.calculate_distance(path)
                if vehicle.can_reach(distance):
                    if task.deadline:
                        urgency = task.deadline - self.current_time if hasattr(self, 'current_time') else task.deadline
                    else:
                        urgency = float('inf')
                    urgent_tasks.append((urgency, distance, task))
        
        if not urgent_tasks:
            return None
        
        urgent_tasks.sort(key=lambda x: (x[0], x[1]))
        return urgent_tasks[0][2]

class Simulator:
    def __init__(self, fleet_size=10, simulation_time=3600*8, task_rate=0.01, strategy_name="nearest"):
        self.map = GuangzhouMap()
        self.depot_id = 100
        self.fleet = self._create_fleet(fleet_size)
        self.tasks = []
        self.completed_tasks = []
        self.failed_tasks = []
        
        self.simulation_time = simulation_time
        self.current_time = 0
        self.time_step = 10
        self.task_rate = task_rate
        self.task_id_counter = 0
        
        self.strategy = self._create_strategy(strategy_name)
        
        self.total_score = 0
        self.total_tasks = 0
        self.completed_task_count = 0
        self.failed_task_count = 0
    
    def _create_fleet(self, fleet_size):
        fleet = []
        
        for i in range(fleet_size):
            if i < 3:
                vehicle = Vehicle(
                    vehicle_id=i+1,
                    capacity=1500,
                    max_battery=100,
                    current_location=self.depot_id
                )
            elif i < 7:
                vehicle = Vehicle(
                    vehicle_id=i+1,
                    capacity=800,
                    max_battery=80,
                    current_location=self.depot_id
                )
            else:
                vehicle = Vehicle(
                    vehicle_id=i+1,
                    capacity=500,
                    max_battery=60,
                    current_location=self.depot_id
                )
            fleet.append(vehicle)
        
        return fleet
    
    def _create_strategy(self, strategy_name):
        strategies = {
            "nearest": NearestTaskStrategy,
            "max_weight": MaxWeightTaskStrategy,
            "urgency": UrgencyStrategy
        }
        
        if strategy_name.lower() in strategies:
            return strategies[strategy_name.lower()]()
        else:
            return NearestTaskStrategy()
    
    def _generate_task(self):
        if random.random() > self.task_rate:
            return None
        
        locations = list(self.map.nodes.keys())
        locations.remove(self.depot_id)
        location = random.choice(locations)
        
        weight = random.uniform(10, 800)
        weight = round(weight, 2)
        
        deadline = None
        if random.random() < 0.7:
            deadline_delta = random.randint(3600, 10800)
            deadline = self.current_time + deadline_delta
        
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
        for vehicle in self.fleet:
            if vehicle.status == VehicleStatus.MOVING and vehicle.current_path:
                vehicle.distance_remaining -= SPEED_KM_PER_STEP * 1000
                vehicle.consume_battery(SPEED_KM_PER_STEP * 1000)
                
                if vehicle.distance_remaining <= 0:
                    vehicle.current_location = vehicle.current_path[-1]
                    
                    if vehicle.current_task:
                        task = vehicle.current_task
                        task.complete(self.current_time)
                        self.completed_tasks.append(task)
                        if task in self.tasks:
                            self.tasks.remove(task)
                        self.completed_task_count += 1
                        self.total_score += task.score
                        
                        vehicle.current_task = None
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
                        vehicle.path_progress = 0
                        vehicle.distance_remaining = 0
                        vehicle.total_tasks += 1
                    else:
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
                        vehicle.path_progress = 0
                        vehicle.distance_remaining = 0
                else:
                    total_dist = vehicle.total_path_distance
                    if total_dist > 0:
                        traveled = total_dist - vehicle.distance_remaining
                        progress_ratio = traveled / total_dist
                        vehicle.path_progress = int(progress_ratio * (len(vehicle.current_path) - 1))
                        vehicle.path_progress = min(vehicle.path_progress, len(vehicle.current_path) - 2)
                        vehicle.current_location = vehicle.current_path[vehicle.path_progress]
            
            elif vehicle.status == VehicleStatus.CHARGING:
                charge_amount = vehicle.charging_station.charging_rate
                vehicle.charge_battery(charge_amount)
                
                if vehicle.current_battery >= vehicle.max_battery * 0.95:
                    if vehicle.charging_station:
                        vehicle.charging_station.remove_vehicle(vehicle)
                        vehicle.status = VehicleStatus.IDLE
    
    def _check_task_deadlines(self):
        for task in self.tasks[:]:
            if task.deadline and self.current_time > task.deadline:
                task.status = TaskStatus.FAILED
                self.failed_tasks.append(task)
                self.tasks.remove(task)
                self.failed_task_count += 1
                self.total_score -= 100
    
    def _allocate_tasks(self):
        pending_tasks = [t for t in self.tasks if t.status == TaskStatus.PENDING]
        idle_vehicles = [v for v in self.fleet if v.status == VehicleStatus.IDLE]
        
        for vehicle in idle_vehicles:
            if vehicle.is_battery_low():
                continue
            
            task = self.strategy.select_task(vehicle, pending_tasks, self.map)
            if task:
                task.assign_to_vehicle(vehicle)
                vehicle.current_task = task
                vehicle.status = VehicleStatus.MOVING
                
                path = self.map.shortest_path(vehicle.current_location, task.location)
                if path:
                    vehicle.current_path = path
                    vehicle.path_progress = 0
                    
                    distance = self.map.calculate_distance(path)
                    task.total_distance = distance
                    vehicle.total_path_distance = distance
                    vehicle.distance_remaining = distance
                    
                    if task in pending_tasks:
                        pending_tasks.remove(task)
    
    def _manage_charging(self):
        for vehicle in self.fleet:
            if vehicle.status == VehicleStatus.IDLE and vehicle.is_battery_low():
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
                    path = self.map.shortest_path(vehicle.current_location, nearest_station.node_id)
                    if path:
                        vehicle.current_path = path
                        vehicle.status = VehicleStatus.MOVING
                        vehicle.path_progress = 0
                        
                        distance = self.map.calculate_distance(path)
                        vehicle.total_path_distance = distance
                        vehicle.distance_remaining = distance
                        
                        nearest_station.add_vehicle(vehicle)
    
    def run(self, verbose=True):
        if verbose:
            print(f"开始模拟...")
            print(f"模拟时间: {self.simulation_time/3600:.1f}小时")
            print(f"车队规模: {len(self.fleet)}辆")
            print(f"调度策略: {self.strategy.name}")
            print("-" * 50)
        
        while self.current_time < self.simulation_time:
            new_task = self._generate_task()
            if new_task:
                self.tasks.append(new_task)
                self.total_tasks += 1
            
            self._update_vehicle_states()
            self._check_task_deadlines()
            self._allocate_tasks()
            self._manage_charging()
            
            if verbose and self.current_time % 3600 == 0:
                hours = self.current_time // 3600
                print(f"时间: {hours}小时 | "
                      f"待处理: {len(self.tasks)} | "
                      f"已完成: {len(self.completed_tasks)} | "
                      f"失败: {len(self.failed_tasks)} | "
                      f"总分: {self.total_score}")
            
            self.current_time += self.time_step
        
        if verbose:
            print("-" * 50)
            print("模拟完成!")
            print(f"总任务数: {self.total_tasks}")
            print(f"完成任务: {self.completed_task_count} ({self.completed_task_count/self.total_tasks*100:.1f}%)")
            print(f"失败任务: {self.failed_task_count} ({self.failed_task_count/self.total_tasks*100:.1f}%)")
            print(f"总评分: {self.total_score}")
        
        return {
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_task_count,
            "failed_tasks": self.failed_task_count,
            "total_score": self.total_score,
            "average_distance": sum(v.total_distance for v in self.fleet) / len(self.fleet),
            "total_charged_vehicles": sum(s.total_vehicles for s in self.map.charging_stations)
        }
