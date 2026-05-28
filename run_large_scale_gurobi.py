"""
大规模Gurobi优化脚本
专门用于计算大规模问题的高质量解，时间限制3000秒
"""
import random
import json
import time
from simulator import Simulator
from gurobi_optimizer import solve_static_oracle

def generate_static_tasks(sim):
    """生成静态任务集合"""
    tasks = []
    while sim.current_time < sim.simulation_time:
        for _ in range(3):
            new_task = sim._generate_task()
            if new_task:
                tasks.append(new_task)
        sim.current_time += sim.time_step
    sim.current_time = 0
    return tasks

def run_large_scale_optimization(
    fleet_size=18,
    simulation_time=7200,
    task_rate=0.28,
    node_count=35,
    seed=42,
    gurobi_time_limit=9000,
    mip_gap=0.2
):
    """
    运行大规模Gurobi优化

    参数:
    - fleet_size: 车队规模
    - simulation_time: 模拟时间（秒）
    - task_rate: 任务生成率
    - node_count: 节点数量
    - seed: 随机种子
    - gurobi_time_limit: Gurobi时间限制（秒）
    - mip_gap: 允许的MIP gap（0.01 = 1%）
    """
    print("=" * 60)
    print("大规模Gurobi优化")
    print("=" * 60)
    print(f"车队规模: {fleet_size}")
    print(f"模拟时间: {simulation_time}秒 ({simulation_time/3600:.1f}小时)")
    print(f"任务生成率: {task_rate}")
    print(f"节点数量: {node_count}")
    print(f"随机种子: {seed}")
    print(f"Gurobi时间限制: {gurobi_time_limit}秒 ({gurobi_time_limit/60:.1f}分钟)")
    print(f"允许MIP gap: {mip_gap*100:.1f}%")
    print("=" * 60)

    # 设置随机种子
    random.seed(seed)

    # 创建模拟器
    print("\n[1/3] 创建模拟器并生成任务...")
    sim = Simulator(
        fleet_size=fleet_size,
        simulation_time=simulation_time,
        task_rate=task_rate,
        strategy_name="balanced",
        node_count=node_count,
        seed=seed
    )

    # 生成静态任务
    tasks = generate_static_tasks(sim)
    print(f"✓ 生成了 {len(tasks)} 个任务")

    # 运行Gurobi优化
    print(f"\n[2/3] 运行Gurobi优化（最多{gurobi_time_limit}秒）...")
    print("提示: 这可能需要较长时间，请耐心等待...")

    start_time = time.time()
    result = solve_static_oracle(
        sim.map,
        sim.fleet,
        tasks,
        simulation_time,
        time_limit=gurobi_time_limit,
        task_limit=None,  # 不限制任务数，优化所有任务
        mip_gap=mip_gap
    )
    elapsed_time = time.time() - start_time

    print(f"✓ Gurobi求解完成，耗时: {elapsed_time:.1f}秒 ({elapsed_time/60:.1f}分钟)")

    # 输出结果
    print("\n[3/3] 优化结果:")
    print("=" * 60)
    print(f"状态: {result['status']}")
    print(f"消息: {result['message']}")
    print(f"生成任务数: {result.get('generated_tasks', 0)}")
    print(f"优化任务数: {result.get('optimized_tasks', 0)}")
    print(f"未优化任务数: {result.get('unoptimized_tasks', 0)}")
    print(f"完成任务数: {result['completed_tasks']}")
    print(f"失败任务数: {result.get('failed_tasks', 0)}")
    print(f"完成率: {result['completed_tasks']/max(result.get('optimized_tasks', 1), 1)*100:.1f}%")
    print(f"总分: {result['total_score']}")

    if result.get('mip_gap') is not None:
        print(f"最终MIP gap: {result['mip_gap']*100:.2f}%")
    if result.get('model_bound') is not None:
        print(f"模型上界: {result['model_bound']:.1f}")

    print("=" * 60)

    # 保存结果
    output_file = f"large_scale_gurobi_result_seed{seed}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "parameters": {
                "fleet_size": fleet_size,
                "simulation_time": simulation_time,
                "task_rate": task_rate,
                "node_count": node_count,
                "seed": seed,
                "gurobi_time_limit": gurobi_time_limit,
                "mip_gap": mip_gap
            },
            "result": result,
            "elapsed_time": elapsed_time
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_file}")

    return result

if __name__ == "__main__":
    # 大规模配置
    result = run_large_scale_optimization(
        fleet_size=18,
        simulation_time=7200,
        task_rate=0.28,
        node_count=35,
        seed=42,
        gurobi_time_limit=9000,  # 9000秒 = 150分钟
        mip_gap=0.25  # 允许2% gap
    )
