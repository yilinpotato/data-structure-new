import math
import random

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from rl_agent import ExpertSelector, TOP_K
from simulator import Simulator, TaskStatus, VehicleStatus


class EVDispatchEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, config=None, seed_base=42):
        super().__init__()
        self.config = config or {}
        self.seed_base = seed_base
        self.episode_index = 0
        self.sim = None
        self.current_vehicle = None
        self.pending_tasks = []
        self.last_score = 0

        self.action_space = spaces.Discrete(TOP_K)
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(11 + TOP_K * 7,),
            dtype=np.float32,
        )

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is None:
            seed = self.seed_base + self.episode_index
        self.episode_index += 1
        random.seed(seed)
        self.sim = Simulator(
            fleet_size=self.config.get("fleet_size", 8),
            simulation_time=self.config.get("simulation_time", 1800),
            task_rate=self.config.get("task_rate", 0.12),
            strategy_name="balanced",
            node_count=self.config.get("node_count", 16),
            seed=seed,
        )
        self.current_vehicle = None
        self.pending_tasks = []
        self.last_score = 0
        self._advance_until_decision()
        return self._get_obs(), {}

    def step(self, action):
        terminated = self.sim.current_time >= self.sim.simulation_time
        if terminated:
            return self._get_obs(), 0.0, True, False, {}

        before_score = self.sim.total_score
        immediate_reward = 0.0
        candidates = self._candidates()
        if self.current_vehicle is not None and 0 <= action < len(candidates):
            task = candidates[action]
            immediate_reward = self._assign_task(self.current_vehicle, task) / 25.0
        else:
            immediate_reward = -8.0

        self._advance_until_decision()
        score_delta = self.sim.total_score - before_score
        reward = immediate_reward + score_delta / 20.0
        terminated = self.sim.current_time >= self.sim.simulation_time
        info = {
            "score": self.sim.total_score,
            "completed": self.sim.completed_task_count,
            "failed": self.sim.failed_task_count,
        }
        return self._get_obs(), reward, terminated, False, info

    def action_masks(self):
        mask = np.zeros(TOP_K, dtype=bool)
        for index, _ in enumerate(self._candidates()):
            mask[index] = True
        if not mask.any():
            mask[0] = True
        return mask

    def _advance_until_decision(self):
        while self.sim.current_time < self.sim.simulation_time:
            self.pending_tasks = [task for task in self.sim.tasks if task.status == TaskStatus.PENDING]
            idle = [vehicle for vehicle in self.sim.fleet if vehicle.status == VehicleStatus.IDLE]
            for vehicle in idle:
                if ExpertSelector.rank_candidates(vehicle, self.pending_tasks, self.sim.map):
                    self.current_vehicle = vehicle
                    return

            for _ in range(3):
                new_task = self.sim._generate_task()
                if new_task:
                    self.sim.tasks.append(new_task)
                    self.sim.total_tasks += 1
            self.sim._update_vehicle_states()
            self.sim._check_task_deadlines()
            self.sim._manage_charging()
            self.sim._record_station_loads()
            self.sim.map.current_time = self.sim.current_time
            self.sim.current_time += self.sim.time_step

        self.current_vehicle = None
        self.pending_tasks = []

    def _assign_task(self, vehicle, task):
        task.assign_to_vehicle(vehicle)
        vehicle.current_task = task
        vehicle.status = VehicleStatus.MOVING
        path = self.sim.map.shortest_path(vehicle.current_location, task.location)
        if not path:
            return -20.0
        distance = self.sim.map.calculate_distance(path)
        vehicle.current_path = path
        vehicle.path_progress = 0
        vehicle.total_path_distance = distance
        vehicle.distance_remaining = distance
        task.total_distance = distance
        self.sim.coordinated_dispatch_count += 1
        return ExpertSelector.estimated_value(vehicle, task, self.sim.map)

    def _candidates(self):
        if self.current_vehicle is None:
            return []
        self.pending_tasks = [task for task in self.sim.tasks if task.status == TaskStatus.PENDING]
        return ExpertSelector.rank_candidates(self.current_vehicle, self.pending_tasks, self.sim.map)

    def _get_obs(self):
        obs = []
        sim = self.sim
        vehicle = self.current_vehicle
        if sim is None or vehicle is None:
            return np.zeros(self.observation_space.shape, dtype=np.float32)

        time_ratio = sim.current_time / max(sim.simulation_time, 1)
        battery = vehicle.current_battery / max(vehicle.max_battery, 1)
        capacity = vehicle.capacity / 1500
        pending_count = len([task for task in sim.tasks if task.status == TaskStatus.PENDING]) / 50
        queue_pressure = np.mean([
            (len(station.occupied) + len(station.queue)) / max(station.capacity, 1)
            for station in sim.map.charging_stations
        ]) if sim.map.charging_stations else 0
        obs.extend([
            time_ratio,
            battery,
            capacity,
            pending_count,
            queue_pressure,
            sim.completed_task_count / 100,
            sim.failed_task_count / 50,
            sim.total_score / 10000,
            len([v for v in sim.fleet if v.status == VehicleStatus.IDLE]) / max(len(sim.fleet), 1),
            len([v for v in sim.fleet if v.status == VehicleStatus.CHARGING]) / max(len(sim.fleet), 1),
            len([v for v in sim.fleet if v.status == VehicleStatus.MOVING]) / max(len(sim.fleet), 1),
        ])

        current_time = sim.current_time
        candidates = self._candidates()
        for index in range(TOP_K):
            if index >= len(candidates):
                obs.extend([0, 0, 0, 0, 0, 0, 0])
                continue
            task = candidates[index]
            path = sim.map.shortest_path(vehicle.current_location, task.location)
            distance = sim.map.calculate_distance(path) if path else 10**7
            reserve = sim.map.distance_to_nearest_station(task.location)
            remaining = (task.deadline - current_time) if task.deadline else sim.simulation_time
            est = ExpertSelector.estimated_value(vehicle, task, sim.map)
            obs.extend([
                min(distance / 20000, 1.5),
                min(task.weight / max(vehicle.capacity, 1), 1.5),
                min(remaining / max(sim.simulation_time, 1), 1.5),
                1.0 if task.deadline else 0.0,
                min(reserve / 20000, 1.5),
                1.0 if vehicle.can_reach(distance + reserve) else 0.0,
                est / 200,
            ])
        return np.array(obs, dtype=np.float32)
