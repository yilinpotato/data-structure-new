"""
新能源物流车队协同调度系统主程序
"""

import os
import time
import json
import argparse
import webbrowser
from datetime import datetime

from models.simulator import Simulator
from visualization.map_visualizer import MapVisualizer

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='新能源物流车队协同调度系统')
    
    # 模拟参数
    parser.add_argument('--fleet-size', type=int, default=10,
                      help='车队规模')
    parser.add_argument('--simulation-time', type=int, default=3600*8,
                      help='模拟时间(秒)')
    parser.add_argument('--task-rate', type=float, default=0.01,
                      help='每秒生成任务的概率')
    parser.add_argument('--time-step', type=int, default=10,
                      help='时间步长(秒)')
    
    # 策略参数
    parser.add_argument('--strategy', type=str, default='balanced',
                      choices=['nearest', 'max_weight', 'urgency', 'balanced'],
                      help='调度策略')
    parser.add_argument('--enable-cooperation', action='store_true',
                      help='启用多车协同')
    parser.add_argument('--enable-charging', action='store_true',
                      help='启用充电管理')
    
    # 可视化参数
    parser.add_argument('--visualize', action='store_true',
                      help='生成可视化结果')
    parser.add_argument('--show-map', action='store_true',
                      help='显示地图')
    parser.add_argument('--create-animation', action='store_true',
                      help='创建动画')
    
    # 比较参数
    parser.add_argument('--compare-strategies', action='store_true',
                      help='比较不同策略')
    parser.add_argument('--runs-per-strategy', type=int, default=3,
                      help='每个策略运行的次数')
    
    # 输出参数
    parser.add_argument('--output-dir', type=str, default='output',
                      help='输出目录')
    parser.add_argument('--save-results', action='store_true',
                      help='保存结果')
    
    return parser.parse_args()

def create_output_directory(args):
    """创建输出目录"""
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    
    # 创建时间戳子目录
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = os.path.join(args.output_dir, timestamp)
    os.makedirs(output_dir)
    
    return output_dir

def run_simulation(args, output_dir):
    """运行模拟"""
    print("=" * 60)
    print("新能源物流车队协同调度系统")
    print("=" * 60)
    
    # 初始化模拟器
    simulator = Simulator(
        fleet_size=args.fleet_size,
        simulation_time=args.simulation_time,
        task_rate=args.task_rate,
        strategy_name=args.strategy,
        enable_cooperation=args.enable_cooperation,
        enable_charging=args.enable_charging
    )
    
    # 运行模拟
    start_time = time.time()
    results = simulator.run(verbose=True)
    elapsed_time = time.time() - start_time
    
    print(f"\n模拟耗时: {elapsed_time:.2f}秒")
    
    # 保存结果
    if args.save_results:
        results_file = os.path.join(output_dir, 'simulation_results.json')
        simulator.save_results(results_file)
    
    # 可视化
    if args.visualize:
        # 创建地图可视化
        visualizer = MapVisualizer(simulator.graph)
        
        # 添加道路网络
        visualizer.add_road_network(show_labels=True)
        
        # 添加充电站
        visualizer.add_charging_stations()
        
        # 更新车辆和任务
        visualizer.update_vehicles(simulator.fleet)
        visualizer.update_tasks(simulator.tasks + simulator.completed_tasks)
        
        # 保存地图
        map_file = os.path.join(output_dir, 'simulation_map.html')
        visualizer.save_map(map_file)
        print(f"地图已保存到 {map_file}")
        
        # 显示地图
        if args.show_map:
            webbrowser.open(map_file)
        
        # 创建动画
        if args.create_animation:
            animation_file = os.path.join(output_dir, 'simulation_animation.html')
            visualizer.create_animated_simulation(simulator, animation_file)
            print(f"动画已保存到 {animation_file}")
            
            if args.show_map:
                webbrowser.open(animation_file)
    
    return simulator, results

def compare_strategies(args, output_dir):
    """比较不同策略"""
    print("=" * 60)
    print("策略比较")
    print("=" * 60)
    
    # 初始化模拟器
    simulator = Simulator(
        fleet_size=args.fleet_size,
        simulation_time=args.simulation_time,
        task_rate=args.task_rate,
        strategy_name=args.strategy,
        enable_cooperation=args.enable_cooperation,
        enable_charging=args.enable_charging
    )
    
    # 比较策略
    strategies = ['nearest', 'max_weight', 'urgency', 'balanced']
    df, summary = simulator.compare_strategies(
        strategies=strategies,
        runs_per_strategy=args.runs_per_strategy
    )
    
    # 保存比较结果
    comparison_file = os.path.join(output_dir, 'strategy_comparison.csv')
    df.to_csv(comparison_file, index=False)
    
    summary_file = os.path.join(output_dir, 'strategy_summary.csv')
    summary.to_csv(summary_file)
    
    print(f"\n比较结果已保存到 {comparison_file} 和 {summary_file}")
    
    # 创建比较可视化
    if args.visualize:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # 设置图形风格
        sns.set(style="whitegrid")
        
        # 创建图形
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # 完成率
        sns.barplot(x='strategy', y='completion_rate', data=df, ax=axes[0, 0])
        axes[0, 0].set_title('任务完成率')
        axes[0, 0].set_ylabel('完成率 (%)')
        
        # 总评分
        sns.barplot(x='strategy', y='total_score', data=df, ax=axes[0, 1])
        axes[0, 1].set_title('总评分')
        axes[0, 1].set_ylabel('评分')
        
        # 平均任务时间
        sns.barplot(x='strategy', y='average_task_time', data=df, ax=axes[1, 0])
        axes[1, 0].set_title('平均任务时间')
        axes[1, 0].set_ylabel('时间 (分钟)')
        
        # 车辆利用率
        sns.barplot(x='strategy', y='vehicle_utilization', data=df, ax=axes[1, 1])
        axes[1, 1].set_title('车辆利用率')
        axes[1, 1].set_ylabel('利用率 (%)')
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图形
        comparison_plot_file = os.path.join(output_dir, 'strategy_comparison.png')
        plt.savefig(comparison_plot_file, dpi=300)
        print(f"比较图已保存到 {comparison_plot_file}")
        
        if args.show_map:
            webbrowser.open(comparison_plot_file)
    
    return df, summary

def main():
    """主函数"""
    # 解析参数
    args = parse_arguments()
    
    # 创建输出目录
    output_dir = create_output_directory(args)
    
    # 保存参数
    params_file = os.path.join(output_dir, 'parameters.json')
    with open(params_file, 'w', encoding='utf-8') as f:
        json.dump(vars(args), f, ensure_ascii=False, indent=2)
    
    print(f"输出目录: {output_dir}")
    
    # 运行模拟或比较策略
    if args.compare_strategies:
        compare_strategies(args, output_dir)
    else:
        simulator, results = run_simulation(args, output_dir)
    
    print("\n任务完成!")

if __name__ == "__main__":
    main()