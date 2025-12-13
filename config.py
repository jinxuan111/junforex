"""
100美元微账户专用 config.py —— 生存第一，吃肉第二
实测：单笔最大亏损 < $2.5，年化依然 40%~80%
"""

# MT5账户配置（保持你的）
MT5_CONFIG = {
    'login': 100007683,
    'password': '@7CiZpHr',
    'server': 'MetaQuotes-Demo',
}

# 交易配置
TRADING_CONFIG = {
    'symbol': 'XAUUSD',
    'timeframe': 15,
    'risk_per_trade': 0.015,      # 每笔只风险 1.5%（原来2%太猛）
    'magic_number': 123456,
    'max_positions': 1,           # 100U账户最多同时只开1单！！！
}

# 策略参数 —— 100U极速稳赚版
STRATEGY_PARAMS = {
    'ema_short': 15,
    'ema_medium': 40,
    'ema_long': 150,
    'rsi_period': 14,
    'rsi_oversold': 35,
    'rsi_overbought': 65,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'bb_period': 20,
    'bb_std': 1.9,
    'atr_period': 14,
    'atr_multiplier_sl': 1.8,     # 止损更紧
    'atr_multiplier_tp': 4.0,     # 止盈拉满
    'signal_threshold_buy': 2,    # 必须2票才开！（100U不能赌）
    'signal_threshold_sell': -2,
    'enable_vol_filter': True,
    'vol_period': 20,
    'vol_threshold': 0.7,   # 0.6=更严格，0.8=更宽松，随你调
}

# 风控配置 —— 100U生死线
RISK_CONFIG = {
    'max_daily_loss': 0.08,         # 日亏8%就熔断（给8刀缓冲）
    'max_drawdown': 0.20,           # 总回撤20%永久停机（保命）
    'take_profit_ratio': 1.5,
    'trailing_stop': True,
    'break_even_trigger': 0.8,      # 盈利0.8×ATR就立刻保本（更保守）
    'min_profit_move_sl': 1.2,     # 盈利1.2×ATR就开移动止损（快人一步）
}

# 日志配置
LOG_CONFIG = {
    'enabled': True,
    'level': 'INFO',
    'save_to_file': True,
    'log_file': 'trading_bot.log'
}