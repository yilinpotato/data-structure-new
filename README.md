# 新能源物流车队协同调度实验报告

## 1. 实验题目

新能源物流车队协同调度：假设中央仓库配置一支数量有限的新能源物流车队，城市中会在模拟时间内动态出现配送任务。系统需要基于道路图结构规划车辆路径，在车辆电量、载重、任务截止时间和充电站排队压力等约束下，比较不同调度策略的总收益。

本项目使用 Python 实现后端模拟器和算法模块，使用 Flask 与高德地图前端实现图形化展示；同时实现启发式策略、Q-learning 策略、Maskable PPO 强化学习策略，以及 Gurobi 静态上帝视角求解器。

## 2. 实验目标与完成情况

| 题目要求 | 本项目实现 |
|---|---|
| 使用图结构实现道路和寻路 | `GuangzhouMap` 使用节点表、邻接表和最短路搜索表示道路网络 |
| 车队数量有限，车辆有电量和载重上限 | `Vehicle` 中维护 `capacity`、`max_battery`、`current_battery`、状态和路径 |
| 动态生成任务 | `Simulator._generate_task()` 按任务生成率随机生成任务 |
| 任务包含时间、地点、货物重量 | `Task` 保存 `start_time`、`location`、`weight`、`deadline` |
| 完成越早、路径越短收益越高，超时扣分 | `Task.complete()` 和失败任务统计共同计算收益 |
| 电量不足时寻找充电站 | `Simulator._manage_charging()` 与 `GuangzhouMap.find_best_charging_station()` 实现补能 |
| 考虑充电站排队和负荷 | `ChargingStation` 使用队列、占用列表和负荷统计 |
| 至少两种调度策略 | 已实现最近、最大重量、紧急、平衡、Q-learning、PPO |
| 至少三种规模实验 | Web 预设小/中/大规模，也支持自定义节点数、任务率和车队数 |
| 可选强化学习 | 实现 Q-learning 与 Maskable PPO |
| 可选精确求解器 | 实现 Gurobi 静态上帝视角 MILP 求解 |
| 图形界面展示 | Flask + 高德地图前端展示车辆、任务、充电站和策略对比 |

## 3. 系统总体架构

系统由四层组成：

1. 数据结构层：道路图、车辆、任务、充电站。
2. 模拟执行层：任务生成、车辆移动、电量消耗、充电排队、任务完成和超时判定。
3. 策略算法层：启发式策略、Q-learning、Maskable PPO、Gurobi 静态求解。
4. 可视化交互层：Flask API 与高德地图网页。

主要文件：

```text
data structure/
├── app.py                         # Flask API 与一键策略对比
├── simulator.py                   # 核心数据结构、模拟器和启发式策略
├── gurobi_optimizer.py            # Gurobi 静态上帝视角求解器
├── rl_agent.py                    # Q-learning Top-K 候选任务策略
├── ev_env.py                      # Maskable PPO 的 Gymnasium 环境
├── ppo_agent.py                   # PPO 模型加载与在线调度策略
├── train_rl.py                    # Q-learning 训练流程
├── train_ppo.py                   # PPO + Gurobi 专家轨迹训练流程
├── templates/index.html           # 图形界面
└── models/                        # 训练模型、专家轨迹和训练报告
```

## 4. 核心数据结构设计

### 4.1 道路图结构

道路网络由 `GuangzhouMap` 表示，核心结构为：

```python
self.nodes = {
    node_id: {
        "name": 地点名称,
        "location": (纬度, 经度),
        "pos": 前端显示坐标
    }
}

self.adjacency_list = {
    node_id: [(neighbor_id, distance_m), ...]
}
```

其中：

- 节点代表中央仓库、任务点、充电站所在位置。
- 边代表可通行道路。
- 边权为两节点间距离，作为路径成本。
- 中央仓库节点固定为 `100`。
- `node_count` 可控制启用的城市节点数量，用于构造小、中、大不同规模问题。

寻路方法为 `GuangzhouMap.shortest_path(start_node, goal_node)`。实现上使用优先队列思想维护当前已知最短距离，返回从起点到终点的节点路径。路径距离由 `calculate_distance(path)` 对路径边权求和得到。

该设计满足题目中“使用图结构实现道路和寻路”的要求，并且所有调度策略、车辆移动、电量估计和 Gurobi 距离矩阵都复用同一张道路图，保证评价口径一致。

### 4.2 车辆结构

车辆由 `Vehicle` 类表示，关键字段包括：

| 字段 | 含义 |
|---|---|
| `id` | 车辆编号 |
| `capacity` | 载重上限 |
| `max_battery` | 电量上限 |
| `current_battery` | 当前电量 |
| `current_location` | 当前所在节点 |
| `status` | 当前状态 |
| `current_task` | 当前服务任务 |
| `current_path` | 当前行驶路径 |
| `distance_remaining` | 当前路径剩余距离 |
| `target_station` | 当前目标充电站 |

车辆状态由 `VehicleStatus` 枚举管理：

```text
IDLE, MOVING, CHARGING, WAITING, DELIVERING, COOPERATIVE, RETURNING
```

电量相关方法：

- `battery_needed(distance_m)`：根据距离计算电量消耗。
- `can_reach(distance_m)`：判断当前电量是否足够到达目标。
- `consume_battery(distance_m)`：车辆移动时扣除电量。
- `charge_battery(amount)`：充电时增加电量。

当前电耗参数为：

```python
BATTERY_PER_KM = 1.5
SPEED_KM_PER_STEP = 0.5
```

也就是说，车辆每行驶 1 km 消耗 1.5 单位电量，每个模拟步最多移动 0.5 km。车辆位置通过路径进度连续推进，不允许任务完成后直接跳回仓库。

### 4.3 任务结构

任务由 `Task` 类表示，关键字段包括：

| 字段 | 含义 |
|---|---|
| `id` | 任务编号 |
| `location` | 任务节点 |
| `weight` | 货物重量 |
| `start_time` | 任务生成时间 |
| `deadline` | 截止时间，可为空 |
| `status` | 任务状态 |
| `assigned_vehicles` | 分配车辆列表 |
| `completion_time` | 完成时间 |
| `total_distance` | 完成任务路径距离 |
| `score` | 任务得分 |

任务状态由 `TaskStatus` 管理：

```text
PENDING, ASSIGNED, IN_PROGRESS, COMPLETED, FAILED, COOPERATIVE
```

任务生成方法为 `Simulator._generate_task()`：

- 使用独立的 `task_rng` 随机数生成器。
- 任务位置从非仓库节点中随机选取。
- 货物重量随机生成。
- 部分任务带截止时间。
- 同一随机种子下，各策略面对同一批任务，保证公平比较。

### 4.4 充电站结构

充电站由 `ChargingStation` 表示，核心数据结构为：

```python
self.queue = deque()
self.occupied = []
```

其中：

- `occupied` 保存正在充电的车辆。
- `queue` 保存等待充电的车辆，使用双端队列 `deque` 实现先进先出排队。
- `capacity` 表示可同时充电车辆数。
- `charging_rate` 表示基础充电速度。

负荷统计字段：

| 字段 | 含义 |
|---|---|
| `started_charge_sessions` | 充电开始次数 |
| `start_battery_total` | 开始充电时电量累计 |
| `queue_total` | 队列长度累计 |
| `occupied_total` | 占用数累计 |
| `peak_queue` | 峰值队列长度 |
| `peak_load` | 峰值负荷 |

充电速度并非固定值，而由 `get_effective_charging_rate()` 根据负荷压力和随机波动计算：

```text
有效充电速度 = 基础充电速度 × 负荷因子 × 随机波动
```

因此，当某充电站排队车辆较多时，车辆补能速度会受到负荷压力影响。

## 5. 模拟流程设计

核心模拟器为 `Simulator`。每个模拟步执行以下过程：

1. 动态生成新任务。
2. 更新车辆移动、到达、任务完成和电量消耗。
3. 检查任务是否超时。
4. 为低电量空闲车辆安排充电。
5. 为可用车辆分配任务。
6. 记录充电站负荷。
7. 时间推进一个 `time_step`。

主要方法：

| 方法 | 功能 |
|---|---|
| `_generate_task()` | 按任务率生成动态任务 |
| `_update_vehicle_states()` | 推进车辆沿路径移动，处理到达和完成 |
| `_check_task_deadlines()` | 检查超时任务并扣分 |
| `_allocate_tasks()` | 调用当前策略为车辆选择任务 |
| `_manage_charging()` | 低电量车辆选择充电站并排队 |
| `_record_station_loads()` | 统计充电站队列与负荷 |
| `get_detail_statistics()` | 汇总详细实验指标 |

该流程保证车辆调度是动态的：策略只能看到当前已经产生且仍待处理的任务，而不能提前知道未来任务。

## 6. 评分函数

任务完成时由 `Task.complete(completion_time)` 计算得分：

```text
score = base_score
      + time_bonus
      - distance_penalty
      + weight_bonus
```

当前实现：

```python
base_score = 100
time_bonus = 50 if deadline exists and completion_time < deadline else 0
distance_penalty = min(50, total_distance / 1000)
weight_bonus = min(30, weight / 100)
```

含义：

- 完成任务获得基础分。
- 有截止时间且按时完成获得额外奖励。
- 路径越长，距离惩罚越大。
- 货物越重，收益略高。
- 超时未完成任务会进入失败统计并扣分。

因此，策略需要在“抢近任务”“抢高重量任务”“避免超时”“避免低电量风险”之间权衡。

## 7. 启发式调度策略

### 7.1 最近任务优先

`NearestTaskStrategy` 对所有待处理任务计算车辆当前位置到任务节点的最短路距离，选择距离最短且车辆电量可达的任务。

优点：路径短、响应快。  
缺点：可能忽略任务重量和截止时间。

### 7.2 最大任务优先

`MaxWeightTaskStrategy` 优先选择重量最大的可行任务。

优点：倾向获得更高重量奖励。  
缺点：可能产生较长路径或错过紧急任务。

### 7.3 紧急任务优先

`UrgencyStrategy` 对带截止时间的任务计算剩余时间，优先选择更紧急且可达的任务。

优点：减少超时失败。  
缺点：可能在距离较远时增加路径成本。

### 7.4 平衡策略

`BalancedStrategy` 结合距离、重量、截止时间和电量安全性进行评分。

设计目的：作为比单一规则更稳定的启发式基线，也作为强化学习候选排序的参考思想。

## 8. 充电调度方法

当车辆空闲且电量低于阈值时，`Simulator._manage_charging()` 调用 `GuangzhouMap.find_best_charging_station(vehicle)` 搜索充电站。

充电站选择不是只看距离，而是综合：

- 当前车辆到充电站的最短路距离。
- 车辆当前电量是否可达。
- 充电站当前占用数。
- 充电站排队长度。
- 充电站容量。

到达充电站后：

- 若 `occupied < capacity`，车辆直接进入充电。
- 否则加入 `queue` 等待。
- 前车充电完成后，从队列头取出下一辆车开始充电。

该设计对应题目中“当电量不足时寻找充电站补能”和“考虑充电站排队与负荷压力”的要求。

## 9. Q-learning 强化学习策略

Q-learning 是保留的轻量强化学习策略，模型文件为：

```text
models/rl_q_table.json
```

### 9.1 动作空间

动作不是固定专家策略，而是 Top-K 候选任务：

```text
candidate_0, candidate_1, candidate_2, candidate_3, candidate_4, candidate_5
```

候选任务由 `ExpertSelector.rank_candidates()` 生成，最多 6 个。候选任务必须满足：

- 不超载。
- 路径存在。
- 电量可达并预留到充电站的安全余量。
- 不会预计超时。

### 9.2 状态离散化

Q 表状态由若干离散特征组成：

- 电量档位。
- 待处理任务数量档位。
- 紧急任务数量。
- 最近候选任务距离档位。
- 充电站压力档位。
- Top-K 候选任务特征。

Q-learning 的优点是可解释、训练快；缺点是状态离散较粗，泛化能力不如神经网络策略。

## 10. Maskable PPO 强化学习策略

Maskable PPO 是当前主要强化学习方案，模型文件为：

```text
models/ppo_dispatch_model.zip
```

专家轨迹文件为：

```text
models/gurobi_expert_trajectories.jsonl
```

### 10.1 为什么使用 Maskable PPO

普通 PPO 在固定动作空间中采样动作，但调度场景的合法动作数量不断变化。例如某一时刻只有 2 个任务可服务，则 `candidate_2` 到 `candidate_5` 都是非法动作。Maskable PPO 通过动作掩码屏蔽非法动作，只在合法候选任务中采样和更新策略，减少无效探索。

### 10.2 环境封装

`ev_env.py` 中的 `EVDispatchEnv` 将模拟器封装为 Gymnasium 环境：

| 方法/属性 | 作用 |
|---|---|
| `reset()` | 创建新模拟场景 |
| `step(action)` | 执行动作并推进到下一个决策点 |
| `action_masks()` | 返回当前合法动作掩码 |
| `observation_space` | PPO 状态空间 |
| `action_space` | PPO 动作空间 |

当前：

```text
TOP_K = 6
action_space = Discrete(6)
observation_space = 11 + TOP_K × 7 = 53 维
```

### 10.3 状态空间

状态分为全局状态和候选任务状态。

全局 11 维：

| 特征 | 含义 |
|---|---|
| `time_ratio` | 当前时间 / 总模拟时间 |
| `battery` | 当前车辆电量比例 |
| `capacity` | 当前车辆载重归一化 |
| `pending_count` | 待处理任务数 |
| `queue_pressure` | 充电站平均负荷压力 |
| `completed_count` | 已完成任务数 |
| `failed_count` | 失败任务数 |
| `total_score` | 当前总分 |
| `idle_ratio` | 空闲车辆比例 |
| `charging_ratio` | 充电车辆比例 |
| `moving_ratio` | 移动车辆比例 |

每个候选任务 7 维：

| 特征 | 含义 |
|---|---|
| `distance` | 当前车辆到任务点距离 |
| `weight_ratio` | 任务重量 / 车辆载重 |
| `remaining_time` | 距截止时间剩余比例 |
| `has_deadline` | 是否有截止时间 |
| `reserve_distance` | 任务点到最近充电站距离 |
| `battery_reachable` | 电量是否安全可达 |
| `estimated_value` | 启发式估计收益 |

这种状态设计让 PPO 同时观察局部任务质量和全局车队压力。

### 10.4 动作空间与动作掩码

PPO 输出 0 到 5 的整数：

```text
0 -> 当前第 0 个候选任务
1 -> 当前第 1 个候选任务
...
5 -> 当前第 5 个候选任务
```

若当前只有 3 个合法任务，则动作掩码为：

```text
[true, true, true, false, false, false]
```

策略不会选择被掩码屏蔽的动作。

### 10.5 奖励函数

PPO 奖励由即时估值奖励和总分变化奖励组成：

```text
reward = estimated_value / 25 + score_delta / 20
```

其中：

- `estimated_value` 鼓励模型选择短距离、高收益、低风险任务。
- `score_delta` 让模型最终仍以总分提升为目标。
- 非法动作会得到负奖励，但正常情况下会被动作掩码过滤。

### 10.6 Gurobi 专家初始化

Gurobi 不再直接把结果灌入 Q 表，而是作为 PPO 的专家教师。

训练流程：

1. 在给定 seed 下生成静态任务集合。
2. Gurobi 上帝视角求解车辆访问任务的高质量路线。
3. 将路线转换为专家轨迹样本：

```json
{"obs": [...], "action": 2, "mask": [true, true, true, false, false, false]}
```

4. 保存到 `models/gurobi_expert_trajectories.jsonl`。
5. PPO 先通过行为克隆学习专家动作。
6. 再在动态模拟环境中用 PPO 继续强化学习。

这种方法比“直接提高某个 Q 值”更细致，因为它学习的是 Gurobi 在具体状态下的候选任务选择规律。

### 10.7 PPO 训练命令

首次生成专家轨迹并训练：

```bash
python train_ppo.py --refresh-expert --gurobi-episodes 8 --gurobi-time-limit 20 --gurobi-task-limit 24 --gurobi-accept-gap 0.05 --timesteps 50000 --bc-epochs 8 --eval-runs 8 --fleet-size 8 --simulation-time 1800 --task-rate 0.12 --node-count 16 --seed 42
```

复用已有专家轨迹继续训练：

```bash
python train_ppo.py --gurobi-episodes 8 --gurobi-time-limit 20 --gurobi-task-limit 24 --gurobi-accept-gap 0.05 --timesteps 50000 --bc-epochs 8 --eval-runs 8 --fleet-size 8 --simulation-time 1800 --task-rate 0.12 --node-count 16 --seed 42
```

主要参数：

| 参数 | 说明 |
|---|---|
| `--refresh-expert` | 重新调用 Gurobi 生成专家轨迹 |
| `--gurobi-episodes` | 生成专家样本的场景数量 |
| `--gurobi-time-limit` | 单次 Gurobi 求解时间 |
| `--gurobi-task-limit` | 单次 Gurobi 参与精确优化的任务数上限 |
| `--gurobi-accept-gap` | 接受的 MIP gap |
| `--timesteps` | PPO 强化学习步数 |
| `--bc-epochs` | 行为克隆轮数 |
| `--seed` | 随机种子 |

当前 PPO 超参数：

| 参数 | 当前值 |
|---|---:|
| policy | `MlpPolicy` |
| n_steps | 512 |
| batch_size | 128 |
| gamma | 0.96 |
| learning_rate | 3e-4 |
| ent_coef | 0.01 |

## 11. Gurobi 静态上帝视角模型

Gurobi 模型位于 `gurobi_optimizer.py`。它假设某段模拟时间内全部任务已知，求解静态车辆路线规划问题。

### 11.1 决策变量

| 变量 | 含义 |
|---|---|
| `served[t]` | 任务 t 是否被完成 |
| `visit[v,t]` | 车辆 v 是否访问任务 t |
| `x[v,i,j]` | 车辆 v 是否从节点 i 行驶到任务 j |
| `arrival[v,t]` | 车辆 v 到达任务 t 的时间 |
| `order[v,t]` | MTZ 顺序变量，用于消除子回路 |

### 11.2 约束

模型约束包括：

- 每个任务最多由一辆车服务。
- 超载任务不能分配给对应车辆。
- 每辆车从中央仓库出发。
- 车辆路线连续，不能出现断裂路径。
- 到达时间必须晚于任务生成时间。
- 有截止时间的任务必须按时到达。
- 单车总行驶时间不能超过模拟时间。
- 使用 MTZ 顺序约束避免子回路。

### 11.3 目标函数

目标是最大化静态总收益：

```text
maximize 完成任务收益 + 时间奖励 + 重量奖励 - 距离成本 - 失败惩罚
```

Gurobi 还使用贪心静态方案作为 warm start，以便在有限时间内更快找到高质量可行解。

### 11.4 与动态策略的差异

Gurobi 是“上帝视角”，提前知道全部任务；动态策略只能看到当前已经出现的任务。因此 Gurobi 更像性能上界或教师样本，而不是与动态策略完全同条件竞争。

## 12. 实验规模设计

系统支持三类默认规模，也支持自定义：

| 规模 | 车队规模 | 模拟时间 | 任务率 | 节点数 | 适用目的 |
|---|---:|---:|---:|---:|---|
| 小规模 | 6 | 1800 | 0.12 | 16 | 快速展示与小样本验证 |
| 中规模 | 10 | 3600 | 0.15 | 24 | 常规策略对比 |
| 大规模 | 18 | 7200 | 0.28 | 35 | 高负荷、充电压力和算法稳定性测试 |

网页左侧可以设置随机种子。固定同一 seed 时，所有策略面对同一任务流；更换 seed 可生成不同实验样本。正式报告建议每个规模使用多个 seed，取平均总分、完成率和失败率。

## 13. 实验指标

主要评价指标：

| 指标 | 含义 |
|---|---|
| 总任务数 | 模拟时间内生成的任务数量 |
| 完成任务数 | 成功完成的任务 |
| 失败任务数 | 超时或未完成任务 |
| 完成率 | 完成任务数 / 总任务数 |
| 总分 | 策略总体收益 |
| 单任务平均得分 | 完成任务的平均收益 |
| 单任务平均用时 | 任务从生成到完成的平均时间 |
| 充电次数 | 车辆进入充电流程次数 |
| 平均充电起始电量 | 车辆开始充电时的平均电量 |
| 充电站平均队列 | 充电站排队压力 |
| 充电站峰值负荷 | 高峰时充电站压力 |

这些指标由 `Simulator.get_detail_statistics()` 汇总，并在网页详细数据表和一键策略对比表中展示。

## 14. 运行方式

### 14.1 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：

```text
Flask
networkx
torch
gymnasium
stable-baselines3
sb3-contrib
gurobipy
```

`gurobipy` 需要本机已安装 Gurobi 并配置 license；如果不可用，动态策略仍可运行。

### 14.2 启动图形界面

```bash
python app.py
```

访问：

```text
http://127.0.0.1:5000
```

### 14.3 一键策略对比

网页会调用 `/run_all_strategies`，依次运行：

```text
nearest, max_weight, urgency, balanced, rl, ppo, gurobi_oracle
```

请求参数示例：

```json
{
  "fleet_size": 8,
  "simulation_time": 1800,
  "task_rate": 0.12,
  "node_count": 16,
  "seed": 42,
  "gurobi_time_limit": 180
}
```

## 15. 结果分析思路

报告中可按以下角度分析：

1. 最近任务优先通常路径短，但可能忽略高价值任务和紧急任务。
2. 最大任务优先可能提升重量收益，但在高密度场景中容易增加路程。
3. 紧急任务优先有助于减少超时，但可能牺牲距离成本。
4. 平衡策略在多数场景中更稳定。
5. Q-learning 能学习候选任务序号偏好，但离散状态限制了泛化。
6. Maskable PPO 通过连续状态特征和动作掩码减少无效决策，并可从 Gurobi 专家轨迹中学习更接近全局优化的局部选择。
7. Gurobi 静态上帝视角通常代表更高质量方案，但由于提前知道未来任务，不能直接等同于在线动态调度策略。
8. 大规模场景中，Gurobi 求解时间和 gap 会明显影响静态最优结果质量。

## 16. 项目特点与难度

本项目的难点主要体现在：

- 使用邻接表道路图和最短路算法统一支持调度、移动、电量和 Gurobi 距离计算。
- 同时模拟车辆载重、电量、充电排队、任务截止时间和动态任务流。
- 实现多策略统一接口，便于在同一随机种子下公平比较。
- 使用 Gurobi 建立静态 MILP 模型，作为上帝视角性能参考。
- 使用 Maskable PPO 处理动态变化的合法动作集合。
- 将 Gurobi 路线转化为专家轨迹，完成行为克隆初始化与强化学习结合。
- 提供可视化界面展示车辆、任务、充电站和策略对比结果。

## 17. 可扩展方向

后续可以继续扩展：

- 多车协同拆分同一超大任务，目前代码结构中 `assigned_vehicles` 和 `COOPERATIVE` 状态已预留基础。
- 引入实时交通拥堵，使边权随时间变化。
- 将 PPO 动作从“选择任务”扩展为“选择任务或充电站”。
- 使用多智能体强化学习，让每辆车拥有独立策略。
- 将 Gurobi 静态模型进一步加入充电约束和充电站容量约束。

## 18. 结论

本项目围绕新能源物流车队调度问题，完成了从图结构建模、动态任务模拟、车辆电量与载重约束、充电站排队，到多策略调度、Gurobi 静态优化和 Maskable PPO 强化学习的完整实现。系统既满足基础模拟合理性，也包含精确求解器和强化学习等难度加分内容，并通过网页界面提供了直观展示和实验对比能力。

## 许可证

MIT License
