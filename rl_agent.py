import json
import math
import os
import random


MODEL_PATH = os.path.join("models", "rl_q_table.json")
TOP_K = 6
RL_ACTIONS = tuple(f"candidate_{index}" for index in range(TOP_K))
EXPERT_ACTIONS = ("nearest", "max_weight", "urgency", "balanced")


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
            current_time = getattr(map_model, "current_time", 0)
            if task.deadline and current_time + distance / 50.0 > task.deadline:
                continue
            reserve = map_model.distance_to_nearest_station(task.location)
            if vehicle.can_reach(distance + reserve):
                feasible.append((task, distance))
        return feasible

    @staticmethod
    def rank_candidates(vehicle, tasks, map_model):
        feasible = ExpertSelector.feasible_tasks(vehicle, tasks, map_model)
        if not feasible:
            return []

        current_time = getattr(map_model, "current_time", 0)
        ranked = []
        for task, distance in feasible:
            if task.deadline:
                remaining = max(1, task.deadline - current_time)
                urgency_score = 26000 / remaining
            else:
                urgency_score = 0
            distance_score = 8000 / (distance + 1)
            weight_score = 55 * task.weight / max(vehicle.capacity, 1)
            battery_after = vehicle.current_battery - vehicle.battery_needed(distance)
            battery_score = 10 * battery_after / max(vehicle.max_battery, 1)
            score = urgency_score + distance_score + weight_score + battery_score
            ranked.append((score, -distance, task))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [task for _, _, task in ranked[:TOP_K]]

    @staticmethod
    def action_for_task(vehicle, tasks, map_model, target_task):
        for index, task in enumerate(ExpertSelector.rank_candidates(vehicle, tasks, map_model)):
            if task.id == target_task.id:
                return f"candidate_{index}"
        return None

    @staticmethod
    def estimated_value(vehicle, task, map_model):
        path = map_model.shortest_path(vehicle.current_location, task.location)
        if not path:
            return -10**9
        distance = map_model.calculate_distance(path)
        current_time = getattr(map_model, "current_time", 0)
        travel_time = distance / 50.0
        arrival = max(task.start_time, current_time + travel_time)
        if task.deadline and arrival > task.deadline:
            return -10**8
        base_score = 100
        time_bonus = 50 if task.deadline and arrival < task.deadline else 0
        distance_penalty = min(50, distance / 1000)
        weight_bonus = min(30, task.weight / 100)
        reserve = map_model.distance_to_nearest_station(task.location)
        battery_risk = 0 if vehicle.can_reach(distance + reserve) else 200
        urgency_bonus = 0
        if task.deadline:
            urgency_bonus = max(0, 300 - (task.deadline - current_time)) / 6
        return base_score + time_bonus + weight_bonus + urgency_bonus - distance_penalty - battery_risk

    @staticmethod
    def select(action, vehicle, tasks, map_model):
        if action.startswith("candidate_"):
            candidates = ExpertSelector.rank_candidates(vehicle, tasks, map_model)
            try:
                index = int(action.split("_", 1)[1])
            except ValueError:
                return None
            return candidates[index] if 0 <= index < len(candidates) else None

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
        if tuple(payload.get("actions", [])) != RL_ACTIONS:
            self.q_table = {}
            return False
        self.q_table = payload.get("q_table", {})
        return True

    def save(self, path=None, meta=None):
        path = path or self.model_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "actions": list(RL_ACTIONS),
            "action_mode": "top_k_candidate_task",
            "top_k": TOP_K,
            "state_schema": [
                "battery_bin",
                "pending_bin",
                "urgent_bin",
                "nearest_distance_bin",
                "charge_pressure_bin",
                "top3_candidate_feature_bins",
            ],
            "q_table": self.q_table,
            "meta": meta or {},
        }
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

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

        candidate_bins = []
        for candidate in ExpertSelector.rank_candidates(vehicle, tasks, map_model)[:3]:
            path = map_model.shortest_path(vehicle.current_location, candidate.location)
            distance = map_model.calculate_distance(path) if path else math.inf
            if distance <= 3000:
                candidate_distance_bin = 0
            elif distance <= 8000:
                candidate_distance_bin = 1
            elif distance <= 15000:
                candidate_distance_bin = 2
            else:
                candidate_distance_bin = 3

            weight_ratio = candidate.weight / max(vehicle.capacity, 1)
            candidate_weight_bin = min(3, int(weight_ratio * 4))

            if candidate.deadline:
                remaining = candidate.deadline - current_time
                if remaining <= 180:
                    candidate_urgency_bin = 0
                elif remaining <= 420:
                    candidate_urgency_bin = 1
                elif remaining <= 900:
                    candidate_urgency_bin = 2
                else:
                    candidate_urgency_bin = 3
            else:
                candidate_urgency_bin = 4
            candidate_bins.append(f"{candidate_distance_bin}{candidate_weight_bin}{candidate_urgency_bin}")

        while len(candidate_bins) < 3:
            candidate_bins.append("999")

        return f"{battery_bin}|{pending_bin}|{urgent_bin}|{distance_bin}|{pressure_bin}|{','.join(candidate_bins)}"

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
        if random.random() < self.epsilon:
            action = random.choice(RL_ACTIONS)
        else:
            values = self.action_values(state)
            action = max(
                RL_ACTIONS,
                key=lambda candidate_action: (
                    values.get(candidate_action, 0.0) + self._rank_prior(candidate_action),
                    -RL_ACTIONS.index(candidate_action),
                )
            )
        task = ExpertSelector.select(action, vehicle, tasks, map_model)
        task = self._safety_refine_task(vehicle, tasks, map_model, task)
        if task is not None:
            action = ExpertSelector.action_for_task(vehicle, tasks, map_model, task) or action

        if task is None:
            for fallback in ("nearest", "balanced", "urgency", "max_weight"):
                task = ExpertSelector.select(fallback, vehicle, tasks, map_model)
                if task is not None:
                    action = ExpertSelector.action_for_task(vehicle, tasks, map_model, task) or "candidate_0"
                    break

        if task is not None and self.epsilon > 0:
            self.pending_updates.append((state, action))
        return task

    def _safety_refine_task(self, vehicle, tasks, map_model, selected_task):
        candidates = []
        if selected_task is not None:
            candidates.append(selected_task)
        for action in ("nearest", "max_weight", "urgency", "balanced", "candidate_0", "candidate_1"):
            task = ExpertSelector.select(action, vehicle, tasks, map_model)
            if task and all(existing.id != task.id for existing in candidates):
                candidates.append(task)
        if not candidates:
            return selected_task

        best_task = max(
            candidates,
            key=lambda task: ExpertSelector.estimated_value(vehicle, task, map_model)
        )
        if selected_task is None:
            return best_task
        best_value = ExpertSelector.estimated_value(vehicle, best_task, map_model)
        nearest_task = ExpertSelector.select("nearest", vehicle, tasks, map_model)
        if nearest_task is not None and nearest_task.id != selected_task.id:
            selected_distance = self._distance_to_task(vehicle, selected_task, map_model)
            nearest_distance = self._distance_to_task(vehicle, nearest_task, map_model)
            nearest_value = ExpertSelector.estimated_value(vehicle, nearest_task, map_model)
            if nearest_distance <= selected_distance * 0.72 or nearest_value >= best_value - 12:
                return nearest_task
        selected_value = ExpertSelector.estimated_value(vehicle, selected_task, map_model)
        return best_task if best_value > selected_value else selected_task

    def _distance_to_task(self, vehicle, task, map_model):
        path = map_model.shortest_path(vehicle.current_location, task.location)
        return map_model.calculate_distance(path) if path else float("inf")

    def _rank_prior(self, action):
        try:
            index = int(action.split("_", 1)[1])
        except (ValueError, IndexError):
            return 0
        return max(0, TOP_K - index) * 12

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
