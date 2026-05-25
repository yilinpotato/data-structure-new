import json
import math
import os
import random


MODEL_PATH = os.path.join("models", "rl_q_table.json")
RL_ACTIONS = ("nearest", "max_weight", "urgency", "balanced")


class ExpertSelector:
    @staticmethod
    def feasible_tasks(vehicle, tasks, map_model):
        feasible = []
        for task in tasks:
            if task.weight > vehicle.capacity:
                continue
            path = map_model.shortest_path(vehicle.current_location, task.location)
            if not path:
                continue
            distance = map_model.calculate_distance(path)
            reserve = map_model.distance_to_nearest_station(task.location)
            if vehicle.can_reach(distance + reserve):
                feasible.append((task, distance))
        return feasible

    @staticmethod
    def select(action, vehicle, tasks, map_model):
        feasible = ExpertSelector.feasible_tasks(vehicle, tasks, map_model)
        if not feasible:
            return None

        current_time = getattr(map_model, "current_time", 0)
        if action == "nearest":
            return min(feasible, key=lambda item: item[1])[0]

        if action == "max_weight":
            return max(feasible, key=lambda item: (item[0].weight, -item[1]))[0]

        if action == "urgency":
            return min(
                feasible,
                key=lambda item: (
                    item[0].deadline - current_time if item[0].deadline else math.inf,
                    item[1],
                ),
            )[0]

        scored = []
        for task, distance in feasible:
            distance_score = 5000 / (distance + 1)
            weight_score = 40 * task.weight / max(vehicle.capacity, 1)
            if task.deadline:
                remaining = max(1, task.deadline - current_time)
                urgency_score = 20000 / remaining
            else:
                urgency_score = 0
            battery_after = vehicle.current_battery - vehicle.battery_needed(distance)
            battery_score = 8 * battery_after / max(vehicle.max_battery, 1)
            scored.append((distance_score + weight_score + urgency_score + battery_score, -distance, task))
        return max(scored, key=lambda item: (item[0], item[1]))[2]


class RLDispatchStrategy:
    def __init__(self, model_path=MODEL_PATH, epsilon=0.0, learning_rate=0.15, discount=0.88):
        self.name = "强化学习策略"
        self.model_path = model_path
        self.epsilon = epsilon
        self.learning_rate = learning_rate
        self.discount = discount
        self.q_table = {}
        self.pending_updates = []
        self.load(model_path)

    def load(self, path=None):
        path = path or self.model_path
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        self.q_table = payload.get("q_table", {})
        return True

    def save(self, path=None, meta=None):
        path = path or self.model_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "actions": list(RL_ACTIONS),
            "state_schema": [
                "battery_bin",
                "pending_bin",
                "urgent_bin",
                "nearest_distance_bin",
                "charge_pressure_bin",
            ],
            "q_table": self.q_table,
            "meta": meta or {},
        }
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def encode_state(self, vehicle, tasks, map_model):
        battery_ratio = vehicle.current_battery / max(vehicle.max_battery, 1)
        battery_bin = min(4, int(battery_ratio * 5))

        pending_count = len(tasks)
        if pending_count <= 2:
            pending_bin = 0
        elif pending_count <= 6:
            pending_bin = 1
        elif pending_count <= 12:
            pending_bin = 2
        else:
            pending_bin = 3

        current_time = getattr(map_model, "current_time", 0)
        urgent_count = 0
        nearest_distance = math.inf
        for task in tasks:
            if task.deadline and task.deadline - current_time <= 300:
                urgent_count += 1
            path = map_model.shortest_path(vehicle.current_location, task.location)
            if path:
                nearest_distance = min(nearest_distance, map_model.calculate_distance(path))

        urgent_bin = min(3, urgent_count)
        if nearest_distance == math.inf:
            distance_bin = 3
        elif nearest_distance <= 3000:
            distance_bin = 0
        elif nearest_distance <= 8000:
            distance_bin = 1
        elif nearest_distance <= 15000:
            distance_bin = 2
        else:
            distance_bin = 3

        pressure_values = [
            (len(station.occupied) + len(station.queue)) / max(station.capacity, 1)
            for station in map_model.charging_stations
        ]
        charge_pressure = sum(pressure_values) / len(pressure_values) if pressure_values else 0
        pressure_bin = min(3, int(charge_pressure * 2))

        return f"{battery_bin}|{pending_bin}|{urgent_bin}|{distance_bin}|{pressure_bin}"

    def action_values(self, state):
        if state not in self.q_table:
            self.q_table[state] = {action: 0.0 for action in RL_ACTIONS}
        return self.q_table[state]

    def reinforce_action(self, state, action, reward):
        if action not in RL_ACTIONS:
            return
        values = self.action_values(state)
        values[action] = values.get(action, 0.0) + reward

    def choose_action(self, state):
        if random.random() < self.epsilon:
            return random.choice(RL_ACTIONS)
        values = self.action_values(state)
        return max(RL_ACTIONS, key=lambda action: (values.get(action, 0.0), -RL_ACTIONS.index(action)))

    def select_task(self, vehicle, tasks, map_model):
        state = self.encode_state(vehicle, tasks, map_model)
        action = self.choose_action(state)
        task = ExpertSelector.select(action, vehicle, tasks, map_model)

        if task is None:
            for fallback in ("balanced", "urgency", "nearest", "max_weight"):
                task = ExpertSelector.select(fallback, vehicle, tasks, map_model)
                if task is not None:
                    action = fallback
                    break

        if task is not None and self.epsilon > 0:
            self.pending_updates.append((state, action))
        return task

    def learn_from_step(self, reward, next_state):
        if not self.pending_updates:
            return
        next_best = max(self.action_values(next_state).values(), default=0.0)
        for state, action in self.pending_updates:
            values = self.action_values(state)
            old_value = values.get(action, 0.0)
            values[action] = old_value + self.learning_rate * (
                reward + self.discount * next_best - old_value
            )
        self.pending_updates.clear()
