import random
import math
from collections import deque

class VehicleStatus:
    IDLE = "idle"
    MOVING = "moving"
    CHARGING = "charging"
    WAITING = "waiting"
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

BATTERY_PER_KM = 1.5
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
        self.target_station = None
        
        self.charging_station = None
        self.charge_start_time = None
        self.charge_start_battery = None
        self.target_charge_ratio = 0.95
        
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
        self.started_charge_sessions = 0
        self.start_battery_total = 0
        self.queue_sample_count = 0
        self.queue_total = 0
        self.occupied_total = 0
        self.peak_queue = 0
        self.peak_load = 0

    def _start_charging(self, vehicle):
        self.occupied.append(vehicle)
        vehicle.status = VehicleStatus.CHARGING
        vehicle.charging_station = self
        vehicle.charge_start_battery = vehicle.get_remaining_battery()
        vehicle.target_charge_ratio = random.uniform(0.88, 1.0)
        self.started_charge_sessions += 1
        self.start_battery_total += vehicle.charge_start_battery
    
    def add_vehicle(self, vehicle):
        if len(self.occupied) < self.capacity:
            self._start_charging(vehicle)
            return True
        
        self.queue.append(vehicle)
        vehicle.status = VehicleStatus.WAITING
        vehicle.charging_station = self
        return False
    
    def remove_vehicle(self, vehicle):
        if vehicle in self.occupied:
            self.occupied.remove(vehicle)
            vehicle.status = VehicleStatus.IDLE
            vehicle.charging_station = None
            self.total_vehicles += 1
            
            if self.queue:
                next_vehicle = self.queue.popleft()
                self._start_charging(next_vehicle)
            return True
        return False

    def get_effective_charging_rate(self):
        load = (len(self.occupied) + len(self.queue)) / max(self.capacity, 1)
        load_factor = max(0.55, 1 - load * 0.18)
        fluctuation = random.uniform(0.85, 1.12)
        return self.charging_rate * load_factor * fluctuation

    def record_load(self):
        queue_len = len(self.queue)
        occupied_len = len(self.occupied)
        self.queue_sample_count += 1
        self.queue_total += queue_len
        self.occupied_total += occupied_len
        self.peak_queue = max(self.peak_queue, queue_len)
        self.peak_load = max(self.peak_load, (queue_len + occupied_len) / max(self.capacity, 1))

    def average_queue(self):
        if self.queue_sample_count == 0:
            return 0
        return self.queue_total / self.queue_sample_count

    def average_load(self):
        if self.queue_sample_count == 0:
            return 0
        return self.occupied_total / (self.queue_sample_count * max(self.capacity, 1))

class GuangzhouMap:
    def __init__(self, node_count=24):
        all_nodes = {
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
            17: {"name": "白云机场", "location": (23.3924, 113.2988), "pos": (300, -120)},
            18: {"name": "嘉禾望岗", "location": (23.2372, 113.2890), "pos": (300, 10)},
            19: {"name": "黄埔港", "location": (23.0850, 113.4820), "pos": (650, 360)},
            20: {"name": "科学城", "location": (23.1719, 113.4441), "pos": (620, 120)},
            21: {"name": "番禺广场", "location": (22.9386, 113.3833), "pos": (500, 620)},
            22: {"name": "广州南站", "location": (22.9909, 113.2690), "pos": (260, 560)},
            23: {"name": "花都广场", "location": (23.4040, 113.2200), "pos": (180, -130)},
            24: {"name": "猎德", "location": (23.1192, 113.3336), "pos": (430, 230)},
            25: {"name": "客村", "location": (23.0967, 113.3200), "pos": (380, 330)},
            26: {"name": "海珠湿地", "location": (23.0667, 113.3676), "pos": (480, 450)},
            27: {"name": "五山", "location": (23.1528, 113.3517), "pos": (470, 80)},
            28: {"name": "岗顶", "location": (23.1340, 113.3460), "pos": (470, 160)},
            29: {"name": "金融城", "location": (23.1188, 113.3722), "pos": (520, 230)},
            30: {"name": "员村", "location": (23.1161, 113.3636), "pos": (500, 250)},
            31: {"name": "东山口", "location": (23.1233, 113.2950), "pos": (320, 240)},
            32: {"name": "越秀公园", "location": (23.1380, 113.2670), "pos": (250, 220)},
            33: {"name": "芳村", "location": (23.0870, 113.2350), "pos": (170, 410)},
            34: {"name": "大学城北", "location": (23.0587, 113.3853), "pos": (500, 500)},
            35: {"name": "琶洲西区", "location": (23.0988, 113.3556), "pos": (460, 360)},
            100: {"name": "中央仓库", "location": (23.1550, 113.3500), "pos": (500, 100)}
        }

        node_count = max(8, min(int(node_count), len(all_nodes) - 1))
        enabled_ids = sorted([n for n in all_nodes if n != 100])[:node_count]
        enabled_ids.append(100)
        self.nodes = {node_id: all_nodes[node_id] for node_id in enabled_ids}

        all_edges = {
            1: [(2, 1500), (3, 2000), (4, 1000), (6, 5000)],
            2: [(1, 1500), (8, 4000), (5, 3000)],
            3: [(1, 2000), (10, 3000), (4, 1500)],
            4: [(1, 1000), (3, 1500), (27, 2000), (28, 1800), (100, 2000), (20, 8000)],
            5: [(2, 3000)],
            6: [(1, 5000), (8, 2000), (12, 3000)],
            7: [(8, 2000), (14, 3000)],
            8: [(2, 4000), (6, 2000), (7, 2000), (15, 3000), (31, 2500), (32, 1800)],
            9: [(8, 2000), (15, 3000), (31, 1800)],
            10: [(3, 3000), (11, 5000), (12, 5000), (24, 1800), (25, 2200), (35, 2500)],
            11: [(10, 5000), (13, 6000), (35, 2000), (26, 3500)],
            12: [(6, 3000), (10, 5000), (16, 2000)],
            13: [(11, 6000), (34, 4500)],
            14: [(7, 3000), (15, 2000), (16, 2000), (33, 3000), (18, 15000)],
            15: [(8, 3000), (14, 2000)],
            16: [(12, 2000), (14, 2000), (33, 2500)],
            17: [(18, 10000), (23, 20000)],
            18: [(17, 10000), (2, 15000), (14, 15000), (23, 16000)],
            19: [(20, 5000), (21, 20000), (2, 15000)],
            20: [(4, 8000), (19, 5000), (100, 5000), (29, 7000)],
            21: [(1, 15000), (19, 20000), (22, 5000), (13, 10000)],
            22: [(21, 5000)],
            23: [(17, 20000), (18, 16000)],
            24: [(3, 1200), (10, 1800), (30, 1600)],
            25: [(10, 2200), (35, 2000), (26, 3500)],
            26: [(11, 3500), (25, 3500), (34, 4500)],
            27: [(4, 2000), (28, 1800), (100, 2500)],
            28: [(1, 1200), (4, 1800), (29, 3500)],
            29: [(28, 3500), (30, 1800), (20, 7000)],
            30: [(24, 1600), (29, 1800), (35, 3500)],
            31: [(8, 2500), (9, 1800), (6, 2200), (32, 2600)],
            32: [(8, 1800), (31, 2600), (7, 1800)],
            33: [(16, 2500), (14, 3000), (22, 12000)],
            34: [(13, 4500), (26, 4500), (21, 9000)],
            35: [(10, 2500), (11, 2000), (25, 2000), (30, 3500)],
            100: [(4, 2000), (20, 5000), (27, 2500)]
        }
        self.adjacency_list = {
            node_id: [(neighbor, distance) for neighbor, distance in edges if neighbor in self.nodes]
            for node_id, edges in all_edges.items()
            if node_id in self.nodes
        }
        
        self.charging_stations = [
            ChargingStation(1, 1, 3, 20.0),
            ChargingStation(2, 3, 2, 20.0),
            ChargingStation(3, 6, 2, 15.0),
            ChargingStation(4, 10, 3, 25.0),
            ChargingStation(5, 14, 2, 15.0),
            ChargingStation(6, 100, 2, 20.0),
            ChargingStation(7, 20, 2, 15.0),
            ChargingStation(8, 21, 3, 20.0),
            ChargingStation(9, 29, 2, 18.0),
            ChargingStation(10, 35, 2, 18.0)
        ]
        self.charging_stations = [s for s in self.charging_stations if s.node_id in self.nodes]
    
    def get_node_name(self, node_id):
        return self.nodes.get(node_id, {}).get("name", f"节点{node_id}")
    
    def get_node_location(self, node_id):
        return self.nodes.get(node_id, {}).get("location", (0, 0))
    
    def get_node_pos(self, node_id):
        return self.nodes.get(node_id, {}).get("pos", (0, 0))
    
    def shortest_path(self, start_node, goal_node):
        if start_node == goal_node:
            return [start_node]
        
        import heapq
        queue = [(0, start_node, [start_node])]
        best_distances = {start_node: 0}

        while queue:
            distance_so_far, current, path = heapq.heappop(queue)
            if current == goal_node:
                return path

            for neighbor, edge_distance in self.adjacency_list.get(current, []):
                next_distance = distance_so_far + edge_distance
                if next_distance < best_distances.get(neighbor, float('inf')):
                    best_distances[neighbor] = next_distance
                    heapq.heappush(queue, (next_distance, neighbor, path + [neighbor]))
        
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

    def distance_to_nearest_station(self, node_id):
        distances = []
        for station in self.charging_stations:
            path = self.shortest_path(node_id, station.node_id)
            if path:
                distances.append(self.calculate_distance(path))
        return min(distances) if distances else 0

    def find_best_charging_station(self, vehicle):
        station_scores = []
        for station in self.charging_stations:
            path = self.shortest_path(vehicle.current_location, station.node_id)
            if not path:
                continue

            distance = self.calculate_distance(path)
            if not vehicle.can_reach(distance):
                continue

            queue_pressure = (len(station.occupied) + len(station.queue)) / max(station.capacity, 1)
            depot_penalty = 6000 if station.node_id == 100 and vehicle.current_location != 100 else 0
            score = distance + depot_penalty + queue_pressure * 5000 - station.charging_rate * 80
            station_scores.append((score, station, distance))

        if not station_scores:
            return None, float('inf')

        station_scores.sort(key=lambda item: item[0])
        return station_scores[0][1], station_scores[0][2]

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
                reserve = map_model.distance_to_nearest_station(task.location)
                if vehicle.can_reach(distance + reserve):
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
                reserve = map_model.distance_to_nearest_station(task.location)
                if vehicle.can_reach(distance + reserve):
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
                reserve = map_model.distance_to_nearest_station(task.location)
                if vehicle.can_reach(distance + reserve):
                    if task.deadline:
                        urgency = task.deadline - getattr(map_model, 'current_time', 0)
                    else:
                        urgency = float('inf')
                    urgent_tasks.append((urgency, distance, task))
        
        if not urgent_tasks:
            return None
        
        urgent_tasks.sort(key=lambda x: (x[0], x[1]))
        return urgent_tasks[0][2]

class BalancedStrategy:
    def __init__(self):
        self.name = "平衡策略"

    def select_task(self, vehicle, tasks, map_model):
        if not tasks or not vehicle.current_location:
            return None

        scored_tasks = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue

            path = map_model.shortest_path(vehicle.current_location, task.location)
            if not path:
                continue

            distance = map_model.calculate_distance(path)
            reserve = map_model.distance_to_nearest_station(task.location)
            if not vehicle.can_reach(distance + reserve):
                continue

            distance_score = 1 / (distance + 1)
            weight_score = task.weight / vehicle.capacity
            if task.deadline:
                remaining = max(1, task.deadline - map_model.current_time)
                urgency_score = 1 / remaining
            else:
                urgency_score = 0

            score = distance_score * 5000 + weight_score * 40 + urgency_score * 20000
            scored_tasks.append((score, distance, task))

        if not scored_tasks:
            return None

        scored_tasks.sort(key=lambda x: (-x[0], x[1]))
        return scored_tasks[0][2]

class Simulator:
    def __init__(self, fleet_size=10, simulation_time=3600*8, task_rate=0.01, strategy_name="nearest", node_count=24, seed=None):
        self.map = GuangzhouMap(node_count=node_count)
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
        self.task_rng = random.Random(seed) if seed is not None else random
        
        self.strategy = self._create_strategy(strategy_name)
        self.map.current_time = self.current_time
        
        self.total_score = 0
        self.total_tasks = 0
        self.completed_task_count = 0
        self.failed_task_count = 0
        self.coordinated_dispatch_count = 0
        self.total_task_score = 0
        self.total_task_time = 0
    
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
            "urgency": UrgencyStrategy,
            "balanced": BalancedStrategy
        }

        if strategy_name.lower() in ("rl", "reinforcement"):
            from rl_agent import RLDispatchStrategy
            return RLDispatchStrategy()
        if strategy_name.lower() in ("ppo", "maskable_ppo"):
            from ppo_agent import PPODispatchStrategy
            return PPODispatchStrategy()
        
        if strategy_name.lower() in strategies:
            return strategies[strategy_name.lower()]()
        else:
            return BalancedStrategy()
    
    def _generate_task(self):
        rng = self.task_rng
        if rng.random() > self.task_rate:
            return None
        
        locations = list(self.map.nodes.keys())
        locations.remove(self.depot_id)
        location = rng.choice(locations)
        
        weight = rng.uniform(10, 800)
        weight = round(weight, 2)
        
        deadline = None
        if rng.random() < 0.8:
            min_delta = max(120, int(self.simulation_time * 0.08))
            max_delta = max(min_delta + self.time_step, int(self.simulation_time * 0.35))
            deadline_delta = rng.randint(min_delta, max_delta)
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
                        if task.status == TaskStatus.COMPLETED:
                            vehicle.current_task = None
                            vehicle.status = VehicleStatus.IDLE
                            vehicle.current_path = []
                            vehicle.path_progress = 0
                            vehicle.distance_remaining = 0
                            continue

                        if task.deadline and self.current_time > task.deadline:
                            self._fail_task(task)
                        else:
                            task.complete(self.current_time)
                            self.completed_tasks.append(task)
                            if task in self.tasks:
                                self.tasks.remove(task)
                            self.completed_task_count += 1
                            self.total_score += task.score
                            self.total_task_score += task.score
                            self.total_task_time += task.completion_time - task.start_time
                        
                        vehicle.current_task = None
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
                        vehicle.path_progress = 0
                        vehicle.distance_remaining = 0
                        vehicle.total_tasks += 1
                    elif vehicle.target_station:
                        station = vehicle.target_station
                        vehicle.target_station = None
                        vehicle.current_path = []
                        vehicle.path_progress = 0
                        vehicle.distance_remaining = 0
                        vehicle.total_path_distance = 0
                        station.add_vehicle(vehicle)
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
                charge_amount = vehicle.charging_station.get_effective_charging_rate()
                vehicle.charge_battery(charge_amount)
                vehicle.total_charge_time += self.time_step
                vehicle.charging_station.total_charge_time += self.time_step
                vehicle.charging_station.total_charge_amount += charge_amount
                
                if vehicle.current_battery >= vehicle.max_battery * vehicle.target_charge_ratio:
                    if vehicle.charging_station:
                        vehicle.charging_station.remove_vehicle(vehicle)
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.charge_start_battery = None
    
    def _check_task_deadlines(self):
        for task in self.tasks[:]:
            if task.deadline and self.current_time > task.deadline:
                self._fail_task(task)

    def _fail_task(self, task):
        if task.status == TaskStatus.FAILED:
            return

        task.status = TaskStatus.FAILED
        if task not in self.failed_tasks:
            self.failed_tasks.append(task)
            self.failed_task_count += 1
            self.total_score -= 100
        if task in self.tasks:
            self.tasks.remove(task)

        for vehicle in self.fleet:
            if vehicle.current_task == task:
                vehicle.current_task = None
                vehicle.status = VehicleStatus.IDLE
                vehicle.current_path = []
                vehicle.path_progress = 0
                vehicle.distance_remaining = 0
                vehicle.total_path_distance = 0
    
    def _allocate_tasks(self):
        self.map.current_time = self.current_time
        self.map.simulation_time = self.simulation_time
        self.map.completed_task_count = self.completed_task_count
        self.map.failed_task_count = self.failed_task_count
        self.map.total_score = self.total_score
        self.map.idle_vehicle_count = sum(1 for v in self.fleet if v.status == VehicleStatus.IDLE)
        self.map.charging_vehicle_count = sum(1 for v in self.fleet if v.status == VehicleStatus.CHARGING)
        self.map.moving_vehicle_count = sum(1 for v in self.fleet if v.status == VehicleStatus.MOVING)
        self.map.fleet_size = len(self.fleet)
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
                    self.coordinated_dispatch_count += 1

    def _manage_charging(self):
        for vehicle in self.fleet:
            if vehicle.status == VehicleStatus.IDLE and vehicle.is_battery_low(0.35):
                nearest_station, _ = self.map.find_best_charging_station(vehicle)

                if nearest_station and nearest_station.node_id != vehicle.current_location:
                    path = self.map.shortest_path(vehicle.current_location, nearest_station.node_id)
                    if path:
                        vehicle.current_path = path
                        vehicle.status = VehicleStatus.MOVING
                        vehicle.path_progress = 0
                        vehicle.target_station = nearest_station
                        
                        distance = self.map.calculate_distance(path)
                        vehicle.total_path_distance = distance
                        vehicle.distance_remaining = distance
                elif nearest_station:
                    nearest_station.add_vehicle(vehicle)

    def _record_station_loads(self):
        for station in self.map.charging_stations:
            station.record_load()

    def get_detail_statistics(self):
        total_charge_sessions = sum(s.started_charge_sessions for s in self.map.charging_stations)
        total_start_battery = sum(s.start_battery_total for s in self.map.charging_stations)
        avg_charge_start_battery = (
            total_start_battery / total_charge_sessions if total_charge_sessions else 0
        )
        station_rows = [
            {
                "id": s.id,
                "node_id": s.node_id,
                "name": self.map.get_node_name(s.node_id),
                "capacity": s.capacity,
                "charging_sessions": s.started_charge_sessions,
                "current_occupied": len(s.occupied),
                "current_queue": len(s.queue),
                "average_queue": s.average_queue(),
                "average_load": s.average_load(),
                "peak_queue": s.peak_queue,
                "peak_load": s.peak_load,
            }
            for s in self.map.charging_stations
        ]
        return {
            "charging_count": total_charge_sessions,
            "coordinated_dispatch_count": self.coordinated_dispatch_count,
            "average_task_score": self.total_task_score / self.completed_task_count if self.completed_task_count else 0,
            "average_task_time": self.total_task_time / self.completed_task_count if self.completed_task_count else 0,
            "average_charge_start_battery": avg_charge_start_battery,
            "station_queue_stats": station_rows,
        }
    
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
            self._record_station_loads()
            self.map.current_time = self.current_time
            
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
