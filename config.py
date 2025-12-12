"""
交易系统配置文件
集中管理所有参数
"""

# MT5账户配置
MT5_CONFIG = {
    'login': 5043557497,
    'password': 'Jinxu11@',
    'server': 'MetaQuotes-Demo',
}

# 交易配置
TRADING_CONFIG = {
    'symbol': 'XAUUSD',           # 交易品种(黄金)
    'timeframe': 15,              # 时间周期(15分钟)
    'risk_per_trade': 0.02,       # 每笔风险2%
    'magic_number': 123456,       # 魔术数字
    'max_positions': 3,           # 最大持仓数
}

# 策略参数
STRATEGY_PARAMS = {
    # 趋势指标
    'ema_short': 20,
    'ema_medium': 50,
    'ema_long': 200,
    
    # RSI参数
    'rsi_period': 14,
    'rsi_oversold': 30,
    'rsi_overbought': 70,
    
    # MACD参数
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    
    # 布林带参数
    'bb_period': 20,
    'bb_std': 2,
    
    # ATR参数
    'atr_period': 14,
    'atr_multiplier_sl': 2,    # 止损距离(ATR倍数)
    'atr_multiplier_tp': 3,    # 止盈距离(ATR倍数)
    
    # 信号阈值
    'signal_threshold_buy': 2,   # 买入需要至少2个策略同意
    'signal_threshold_sell': -2, # 卖出需要至少2个策略同意
}

# 风险管理配置
RISK_CONFIG = {
    'max_daily_loss': 0.05,       # 最大日亏损5%
    'max_drawdown': 0.15,         # 最大回撤15%
    'take_profit_ratio': 1.5,     # 盈亏比1:1.5
    'trailing_stop': True,        # 启用移动止损
    'break_even_trigger': 1.0,    # 盈利1倍ATR时移至盈亏平衡
    'min_profit_move_sl': 1.5,    # 移动止损的最小盈利(ATR倍数)
}

# 日志配置
LOG_CONFIG = {
    'enabled': True,
    'level': 'INFO',              # DEBUG, INFO, WARNING, ERROR
    'save_to_file': True,
    'log_file': 'trading_bot.log'
}