import os

import numpy as np

from rl_agent import ExpertSelector, TOP_K


PPO_MODEL_PATH = os.path.join("models", "ppo_dispatch_model.zip")


class PPODispatchStrategy:
    def __init__(self, model_path=PPO_MODEL_PATH):
        self.name = "PPO强化学习策略"
        self.model_path = model_path
        self.model = None
        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            return
        try:
            from sb3_contrib import MaskablePPO
            self.model = MaskablePPO.load(self.model_path)
        except Exception:
            self.model = None

    def select_task(self, vehicle, tasks, map_model):
        candidates = ExpertSelector.rank_candidates(vehicle, tasks, map_model)
        if not candidates:
            return None
        if self.model is None:
            return candidates[0]

        obs = build_policy_observation(vehicle, tasks, map_model)
        mask = np.zeros(TOP_K, dtype=bool)
        mask[:len(candidates)] = True
        try:
            action, _ = self.model.predict(obs, deterministic=True, action_masks=mask)
            action = int(action)
        except Exception:
            action = 0
        if 0 <= action < len(candidates):
            return candidates[action]
        return candidates[0]


def build_policy_observation(vehicle, tasks, map_model):
    current_time = getattr(map_model, "current_time", 0)
    simulation_time = max(getattr(map_model, "simulation_time", 3000), 1)
    fleet_size = max(getattr(map_model, "fleet_size", 1), 1)
    pressure_values = [
        (len(station.occupied) + len(station.queue)) / max(station.capacity, 1)
        for station in map_model.charging_stations
    ]
    queue_pressure = float(np.mean(pressure_values)) if pressure_values else 0.0
    obs = [
        current_time / simulation_time,
        vehicle.current_battery / max(vehicle.max_battery, 1),
        vehicle.capacity / 1500,
        len(tasks) / 50,
        queue_pressure,
        getattr(map_model, "completed_task_count", 0) / 100,
        getattr(map_model, "failed_task_count", 0) / 50,
        getattr(map_model, "total_score", 0) / 10000,
        getattr(map_model, "idle_vehicle_count", 0) / fleet_size,
        getattr(map_model, "charging_vehicle_count", 0) / fleet_size,
        getattr(map_model, "moving_vehicle_count", 0) / fleet_size,
    ]
    candidates = ExpertSelector.rank_candidates(vehicle, tasks, map_model)
    for index in range(TOP_K):
        if index >= len(candidates):
            obs.extend([0, 0, 0, 0, 0, 0, 0])
            continue
        task = candidates[index]
        path = map_model.shortest_path(vehicle.current_location, task.location)
        distance = map_model.calculate_distance(path) if path else 10**7
        reserve = map_model.distance_to_nearest_station(task.location)
        remaining = (task.deadline - current_time) if task.deadline else simulation_time
        est = ExpertSelector.estimated_value(vehicle, task, map_model)
        obs.extend([
            min(distance / 20000, 1.5),
            min(task.weight / max(vehicle.capacity, 1), 1.5),
            min(remaining / simulation_time, 1.5),
            1.0 if task.deadline else 0.0,
            min(reserve / 20000, 1.5),
            1.0 if vehicle.can_reach(distance + reserve) else 0.0,
            est / 200,
        ])
    return np.array(obs, dtype=np.float32)
