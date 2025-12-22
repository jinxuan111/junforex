"""
交易策略模块 - 顶级量化升级版
开单更快 + 吃肉更多 + 假期保护本金
"""

class TradingStrategies:
    """交易策略集合"""
    
    @staticmethod
    def trend_following_strategy(df, params):
        """策略1: 趋势跟踪 - 更快反应（EMA10/30/100）"""
        latest = df.iloc[-1]
        
        if (latest['EMA_10'] > latest['EMA_30'] > latest['EMA_100'] and
            latest['RSI'] < params['rsi_overbought'] and 
            latest['MACD_hist'] > 0):
            return 1
        elif (latest['EMA_10'] < latest['EMA_30'] < latest['EMA_100'] and
              latest['RSI'] > params['rsi_oversold'] and 
              latest['MACD_hist'] < 0):
            return -1
        return 0
    
    @staticmethod
    def mean_reversion_strategy(df, params):
        """策略2: 均值回归 - 更敏感（bb_position 0.3/0.7）"""
        latest = df.iloc[-1]
        bb_position = (latest['close'] - latest['BB_lower']) / (latest['BB_upper'] - latest['BB_lower'])
        
        if latest['RSI'] < params['rsi_oversold'] and bb_position < 0.3:
            return 1
        elif latest['RSI'] > params['rsi_overbought'] and bb_position > 0.7:
            return -1
        return 0
    
    @staticmethod
    def breakout_strategy(df, params):
        """策略3: 突破策略 - 更容易触发（ATR > 平均0.8倍）"""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        atr_mean = df['ATR'].iloc[-20:].mean()
        
        if (latest['close'] > latest['BB_upper'] and 
            prev['close'] <= prev['BB_upper'] and
            latest['ATR'] > atr_mean * 0.8):  # 放宽到0.8倍
            return 1
        elif (latest['close'] < latest['BB_lower'] and 
              prev['close'] >= prev['BB_lower'] and
              latest['ATR'] > atr_mean * 0.8):
            return -1
        return 0
    
    @staticmethod
    def momentum_strategy(df, params):
        """策略4: 动量策略 - 加RSI过滤，更准"""
        latest = df.iloc[-1]
        
        if (latest['MOM'] > 0 and 
            latest['STOCH_K'] > latest['STOCH_D'] and 
            latest['STOCH_K'] < 80 and
            latest['RSI'] > 50):  # 加RSI确认多头
            return 1
        elif (latest['MOM'] < 0 and 
              latest['STOCH_K'] < latest['STOCH_D'] and 
              latest['STOCH_K'] > 20 and
              latest['RSI'] < 50):
            return -1
        return 0
    
    @staticmethod
    def generate_combined_signal(df, params):
        """
        终极综合信号生成器（已加入震荡市自动休眠）
        """
        latest = df.iloc[-1]

        # ==================== 震荡市自动休眠神器 ====================
        if params.get('enable_vol_filter', False):
            vol_period = params.get('vol_period', 20)
            vol_threshold = params.get('vol_threshold', 0.6)
            
            atr_history = df['ATR'].rolling(window=vol_period).mean()
            atr_avg = atr_history.iloc[-2] if len(atr_history) > 1 else latest['ATR']
            
            if latest['ATR'] < atr_avg * vol_threshold:
                strategy_names = ['趋势跟踪', '均值回归', '突破', '动量']
                signal_details = {name: '休眠(低波动)' for name in strategy_names}
                return 0, signal_details
        # ==========================================================

        # 四大策略正常投票
        signals = [
            TradingStrategies.trend_following_strategy(df, params),
            TradingStrategies.mean_reversion_strategy(df, params),
            TradingStrategies.breakout_strategy(df, params),
            TradingStrategies.momentum_strategy(df, params)
        ]
        
        total_signal = sum(signals)
        
        strategy_names = ['趋势跟踪', '均值回归', '突破', '动量']
        signal_details = {
            name: '买入' if sig == 1 else '卖出' if sig == -1 else '中性'
            for name, sig in zip(strategy_names, signals)
        }
        
        if total_signal >= params['signal_threshold_buy']:
            return 1, signal_details
        elif total_signal <= params['signal_threshold_sell']:
            return -1, signal_details
        else:
            return 0, signal_details