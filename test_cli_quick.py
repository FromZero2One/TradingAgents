#!/usr/bin/env python3
"""
快速测试 CLI 分析流程
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import sys

# 配置
config = DEFAULT_CONFIG.copy()
config['data_vendors'] = {
    'core_stock_apis': 'mysql',
    'technical_indicators': 'mysql',
    'fundamental_data': 'mysql',
    'news_data': 'mysql',
}
config['selected_analysts'] = ['market_analyst']
config['output_language'] = 'Chinese'
config['llm_provider'] = 'deepseek'
config['deep_think_llm'] = 'deepseek-chat'
config['quick_think_llm'] = 'deepseek-chat'

print("=" * 80)
print("🧪 测试完整分析流程")
print("=" * 80)
print()
print(f"股票代码: 600519.SS")
print(f"分析日期: 2025-10-22")
print(f"输出语言: Chinese")
print(f"分析师: Market Analyst")
print(f"数据源: MySQL")
print()

try:
    print("⏳ 正在初始化交易图...")
    graph = TradingAgentsGraph(
        selected_analysts=['market'],  # 第一个参数是分析师列表
        config=config  # 第二个参数是配置字典
    )
    print("✅ 交易图初始化成功")
    print()
    
    print("⏳ 开始分析贵州茅台...")
    print("-" * 80)
    
    # 执行分析（使用 propagate 方法）
    final_state, signal = graph.propagate("600519.SS", trade_date="2025-10-22")
    
    print("-" * 80)
    print("✅ 分析完成!")
    print()
    print("📊 最终交易决策:")
    print(final_state.get('final_trade_decision', 'N/A'))
    print()
    print("📈 信号处理结果:")
    print(signal)
    
except Exception as e:
    print()
    print("=" * 80)
    print("❌ 分析失败!")
    print("=" * 80)
    print()
    print(f"错误类型: {type(e).__name__}")
    print(f"错误消息: {e}")
    print()
    print("详细堆栈跟踪:")
    print("-" * 80)
    import traceback
    traceback.print_exc()
    print()
    sys.exit(1)
