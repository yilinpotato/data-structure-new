import argparse
import json
import os
import random

import numpy as np
import torch

from ev_env import EVDispatchEnv
from gurobi_optimizer import solve_static_oracle
from ppo_agent import PPO_MODEL_PATH, build_policy_observation
from rl_agent import ExpertSelector, TOP_K
from simulator import Simulator
from train_rl import generate_static_tasks, run_fast_simulation, summarize


EXPERT_PATH = os.path.join("models", "gurobi_expert_trajectories.jsonl")


def collect_gurobi_expert_samples(config, episodes, time_limit, task_limit, accept_gap, seed, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    rows = []
    with open(output_path, "w", encoding="utf-8") as file:
        for episode in range(episodes):
            random.seed(seed + episode)
            sim = Simulator(
                fleet_size=config["fleet_size"],
                simulation_time=config["simulation_time"],
                task_rate=config["task_rate"],
                strategy_name="balanced",
                node_count=config["node_count"],
                seed=seed + episode,
            )
            tasks = generate_static_tasks(sim)
            result = solve_static_oracle(
                sim.map,
                sim.fleet,
                tasks,
                config["simulation_time"],
                time_limit=time_limit,
                task_limit=None if task_limit == 0 else task_limit,
                mip_gap=accept_gap,
            )
            learned = 0
            tasks_by_id = {task.id: task for task in tasks}
            served = set()
            for vehicle_plan in result.get("plan", []):
                vehicle = next((v for v in sim.fleet if v.id == vehicle_plan["vehicle_id"]), None)
                if vehicle is None:
                    continue
                dispatch_time = 0
                for stop in vehicle_plan["route"]:
                    target = tasks_by_id.get(stop["task_id"])
                    if target is None:
                        continue
                    sim.map.current_time = dispatch_time
                    available = [
                        task for task in tasks
                        if task.id not in served and task.start_time <= max(dispatch_time, target.start_time)
                    ]
                    if target not in available:
                        available.append(target)
                    action_name = ExpertSelector.action_for_task(vehicle, available, sim.map, target)
                    if action_name is None:
                        continue
                    action = int(action_name.split("_", 1)[1])
                    mask = [False] * TOP_K
                    candidates = ExpertSelector.rank_candidates(vehicle, available, sim.map)
                    for index in range(len(candidates)):
                        mask[index] = True
                    obs = build_policy_observation(vehicle, available, sim.map).tolist()
                    file.write(json.dumps({"obs": obs, "action": action, "mask": mask}, ensure_ascii=False) + "\n")
                    learned += 1

                    vehicle.current_location = target.location
                    dispatch_time = stop["arrival_time"]
                    served.add(target.id)

            rows.append({
                "status": result.get("status"),
                "tasks": len(tasks),
                "completed": result.get("completed_tasks", 0),
                "score": result.get("total_score", 0) or 0,
                "learned": learned,
                "mip_gap": result.get("mip_gap"),
            })
            print(
                f"expert {episode + 1:>3}/{episodes} | status={result.get('status')} | "
                f"tasks={len(tasks)} | learned={learned} | score={(result.get('total_score', 0) or 0):.1f}"
            )
    return rows


def load_expert_samples(path):
    if not os.path.exists(path):
        return []
    samples = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def behavior_clone(model, samples, epochs=8, batch_size=128, learning_rate=1e-4):
    if not samples:
        return
    optimizer = torch.optim.Adam(model.policy.parameters(), lr=learning_rate)
    obs = torch.tensor(np.array([sample["obs"] for sample in samples]), dtype=torch.float32, device=model.device)
    actions = torch.tensor([sample["action"] for sample in samples], dtype=torch.long, device=model.device)
    masks = torch.tensor(np.array([sample["mask"] for sample in samples]), dtype=torch.bool, device=model.device)
    count = len(samples)
    for epoch in range(epochs):
        permutation = torch.randperm(count, device=model.device)
        losses = []
        for start in range(0, count, batch_size):
            index = permutation[start:start + batch_size]
            dist = model.policy.get_distribution(obs[index], action_masks=masks[index])
            log_prob = dist.log_prob(actions[index])
            loss = -log_prob.mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        print(f"bc epoch {epoch + 1}/{epochs} | loss={np.mean(losses):.4f}")


def evaluate_strategy(strategy_name, config, seeds):
    rows = []
    for seed in seeds:
        random.seed(seed)
        sim = Simulator(
            fleet_size=config["fleet_size"],
            simulation_time=config["simulation_time"],
            task_rate=config["task_rate"],
            strategy_name=strategy_name,
            node_count=config["node_count"],
            seed=seed,
        )
        run_fast_simulation(sim)
        rows.append({
            "score": sim.total_score,
            "completed": sim.completed_task_count,
            "failed": sim.failed_task_count,
            "tasks": sim.total_tasks,
        })
    return summarize(rows)


def main():
    parser = argparse.ArgumentParser(description="Train Maskable PPO with optional Gurobi behavior cloning.")
    parser.add_argument("--timesteps", type=int, default=100000)
    parser.add_argument("--bc-epochs", type=int, default=8)
    parser.add_argument("--expert-path", default=EXPERT_PATH)
    parser.add_argument("--model-path", default=PPO_MODEL_PATH)
    parser.add_argument("--refresh-expert", action="store_true")
    parser.add_argument("--gurobi-episodes", type=int, default=8)
    parser.add_argument("--gurobi-time-limit", type=int, default=20)
    parser.add_argument("--gurobi-task-limit", type=int, default=24)
    parser.add_argument("--gurobi-accept-gap", type=float, default=0.05)
    parser.add_argument("--fleet-size", type=int, default=8)
    parser.add_argument("--simulation-time", type=int, default=1800)
    parser.add_argument("--task-rate", type=float, default=0.12)
    parser.add_argument("--node-count", type=int, default=16)
    parser.add_argument("--eval-runs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from sb3_contrib import MaskablePPO

    config = {
        "fleet_size": args.fleet_size,
        "simulation_time": args.simulation_time,
        "task_rate": args.task_rate,
        "node_count": args.node_count,
    }

    if args.refresh_expert or not os.path.exists(args.expert_path):
        expert_rows = collect_gurobi_expert_samples(
            config,
            args.gurobi_episodes,
            args.gurobi_time_limit,
            args.gurobi_task_limit,
            args.gurobi_accept_gap,
            args.seed + 70000,
            args.expert_path,
        )
    else:
        expert_rows = []
        print(f"using existing expert file: {args.expert_path}")

    samples = load_expert_samples(args.expert_path)
    print(f"expert samples: {len(samples)}")

    env = EVDispatchEnv(config=config, seed_base=args.seed)
    model = MaskablePPO(
        "MlpPolicy",
        env,
        seed=args.seed,
        verbose=1,
        n_steps=512,
        batch_size=128,
        gamma=0.96,
        learning_rate=3e-4,
        ent_coef=0.01,
    )
    behavior_clone(model, samples, epochs=args.bc_epochs)
    model.learn(total_timesteps=args.timesteps)
    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    model.save(args.model_path)

    eval_seeds = [args.seed + 10000 + index for index in range(args.eval_runs)]
    report = {
        "ppo": evaluate_strategy("ppo", config, eval_seeds),
        "q_learning": evaluate_strategy("rl", config, eval_seeds),
        "nearest": evaluate_strategy("nearest", config, eval_seeds),
        "max_weight": evaluate_strategy("max_weight", config, eval_seeds),
        "balanced": evaluate_strategy("balanced", config, eval_seeds),
        "urgency": evaluate_strategy("urgency", config, eval_seeds),
        "expert_rows": expert_rows,
        "expert_path": args.expert_path,
        "model_path": args.model_path,
    }
    report_path = os.path.join("models", "ppo_training_report.json")
    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
