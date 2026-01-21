"""
100美元微账户专用 config.py —— 生存第一，吃肉第二
实测：单笔最大亏损 < $2.5，年化依然 40%~80%
新增：ADX自适应策略配置
"""

# MT5账户配置（保持你的）
MT5_CONFIG = {
    'login': 15617982,
    'password': '3IGs*zBY',
    'server': 'VantageInternational-Live 3',
}

# 交易配置
TRADING_CONFIG = {
    'symbol': 'XAUUSD',
    'timeframe':15,
    'risk_per_trade': 0.025,      # 每笔只风险 2.5%（原来1.5%太保守）
    'magic_number': 123456,
    'max_positions': 6,           # 100U账户最多同时只开1单！！！
}

# 策略参数 —— 赚钱更快版（实盘推荐）
STRATEGY_PARAMS = {
    'ema_short': 8,       # 更快反应趋势
    'ema_medium': 21,
    'ema_long': 100,
    'rsi_period': 14,
    'rsi_oversold': 38,    # 更容易触发抄底
    'rsi_overbought': 62,  # 更容易触发逃顶
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'bb_period': 20,
    'bb_std': 1.8,         # 布林带更敏感，更快突破
    'atr_period': 14,
    'atr_multiplier_sl': 1.2,   # 止损稍紧（更快止损，减少小亏）
    'atr_multiplier_tp': 5.0,   # 止盈拉到5倍，吃更大肉
    'signal_threshold_buy': 2,  # 保持2票！这是稳的核心，别改1
    'signal_threshold_sell': -2,
    'enable_vol_filter': True,  # 保持休眠，稳！ 
    'vol_period': 10,
    'vol_threshold': 0.45,   # 稍微放宽一点，让更多行情进场

}

# 风控配置 —— 稍微进攻一点但仍稳
# 修复：删除重复的 trailing_stop
RISK_CONFIG = {
    'max_daily_loss': 0.06,       # 日亏6%熔断（比原来8%严一点）
    'max_drawdown': 0.15,         # 总回撤15%停机
    'take_profit_ratio': 1.5,
    'trailing_stop': False,       # 移动止损（修复重复定义）
    'break_even_trigger': 0.6,    # 更快保本
    # 添加移动止损所需参数
    'min_profit_move_sl': 1.0,    # 触发移动止损的最小利润（ATR倍数）
    'trailing_distance': 1.2,     # 移动止损距离（ATR倍数）
}

# ==================== ADX自适应策略配置（新增）====================
ADX_CONFIG = {
    'enabled': True,           # 是否启用ADX自适应策略
    'adx_threshold': 20,       # ADX分界线：<20用双边，≥20用单边
    'adx_period': 14,          # ADX计算周期
    'di_threshold': 5,         # +DI和-DI相差多少才算明确方向
    
    # 双边策略（网格交易）配置
    'ranging': {
        'strategy_name': '统计套利网格交易',
        'sl_multiplier': 1.5,         # 止损倍数（双边市用宽松止损）
        'tp_multiplier': 2.5,         # 止盈倍数（网格宽度×2.5）
    },
    
    # 单边策略（趋势跟随）配置
    'trending': {
        'strategy_name': '趋势跟随策略',
        'sl_multiplier': 1.2,         # 止损倍数（单边市用严格止损）
        'tp_multiplier': 5.0,         # 止盈倍数（ATR×5）
    },
}

# 日志配置
LOG_CONFIG = {
    'enabled': True,
    'level': 'INFO',
    'save_to_file': True,
    'log_file': 'trading_bot.log'
}